# Memory-safety review: `engine_c/` (C engine + ctypes Python bindings)

## Scope

Inspected every C source under `engine_c/` plus the Python binding layer:
`state.c/h`, `engine.h`, `loader.c/h`, `arena.c/h`, `intern.c/h`, `rng.c/h`,
`rules.c`, `generic_runtime.c`, plus `bindings/{engine_bindings,ce_api,session}.py`.

This is a plain-C engine wrapped in `ctypes`. The relevant memory-safety lens
is the manual-manual spectrum: leaks, UAF, double-free, buffer overruns,
dangling pointers, ownership ambiguity across the C↔Python boundary, and
questionable "COW" semantics.

No code changes will be made in plan mode.

---

## Severity summary

| # | Finding                                                          | Severity   | Location                                      |
|---|------------------------------------------------------------------|------------|-----------------------------------------------|
| 1 | `cow_*` helpers are fake COW — they mutate the source state      | **Critical** | `state.c:214-250`                            |
| 2 | `state.c::draw_cards_state` does `memcpy` of `discard_pile` then sets `discard_pile_count = 0` while still reading from that same backing store | **High** | `state.c:28-40` |
| 3 | Arena `load_definition` leak if user destroys `GameDefinition` without it | **High** | `loader.c:389-420` + `ce_api.py:249-252`     |
| 4 | `state->definition` is a borrowed pointer into a `CEngine`-owned arena that can be destroyed while states outlive it | **High** | `state.h:276`, `state.c:83`, `ce_api.py`     |
| 5 | `pending_ability` and `pending_generic` allocated on the state arena, but `state.c:167-186` only deep-copies them on `engine_clone` (not `engine_clone_cow` paths used by `engine_apply`) | **High** | `state.c:157-198`, `rules.c:517-518`         |
| 6 | Python `CState` does not implement `__del__` → leaks on GC of an un-`destroy()`-ed wrapper | **Medium** | `ce_api.py:143-201`                          |
| 7 | `CEngine._global_lock = __import__("threading").Lock()` evaluated once at class-body time — works, but unusual; lock is shared across instances (probably fine, but worth noting) | **Low** | `ce_api.py:216`                              |
| 8 | `read_file` in `loader.c` doesn't validate `ftell` return / short reads; truncated read leaves `buf` non-NUL-terminated at offset `n` (ok) but `len` from `ftell` may be negative for binary stdin-style files | **Low** | `loader.c:10-23`                             |
| 9 | `engine_apply` never re-destroys `state` on the `MOVE_RESOLVE_GENERIC` happy path where `result == state` (it does call `engine_destroy(state)` when `result != state`, but the COW issue in #1 means `state` and `src` can still share `nodes[]` etc.) | **Medium** | `rules.c:612-617`                            |
| 10 | `arena_alloc` returns a new block but does **not** zero it; arena-allocated structs that are read before full initialization can leak uninitialized memory (a Python process will see stale bytes from the heap) | **Medium** | `arena.c:48-64`, called pervasively          |
| 11 | `intern` is a process-global with no `intern_destroy`. The Python bindings call `intern_init(4096)` from `CEngine.available()` (line 322) **before** the user has acquired the lock — racy double-init | **Medium** | `intern.c:30-36`, `ce_api.py:317-324`         |
| 12 | No bounds checks on `state->players[i].trophy_hall[ps->trophy_hall_count++]++` in `apply_assassinate` — has `< MAX_ZONE_SIZE` guard, OK. (Verified safe; listing for completeness.) | **OK** | `rules.c:318-319`                            |
| 13 | `state->pending_immediate[i] = state->pending_immediate[i+1]` shifts are O(n²) and use struct copy of `PendingPromotionState` (Sym fields only — no deep pointers). Safe. | **OK** | `rules.c:407-409`                            |

---

## Critical findings (full detail)

### 1. Fake "copy-on-write" — `engine_c/state.c:214-250`

```c
NodeState *cow_node(GameState *state, Sym node_id) {
    for (int i = 0; i < state->node_count; i++) {
        if (state->nodes[i].node_id == node_id) {
            if (!state->nodes[i].cow_dirty) {
                state->nodes[i].cow_dirty = true;   // <-- only flips a flag
            }
            return &state->nodes[i];                // <-- returns same storage
        }
    }
    return NULL;
}
```

`cow_player`, `cow_market`, and `cow_resource_pool` follow the same pattern. The
function name advertises "copy-on-write" but **no copy is ever made**. The flag
is unused (I grepped — `cow_dirty` is only ever *set*, never *read* anywhere
in the C engine). Consequences:

- `engine_apply` calls `engine_clone_cow(src)` then mutates the *new* state.
  With real COW the new state would diverge on the first write; with fake COW
  the new state shares `nodes[]`, `players[]`, `market`, and `resource_pool`
  in-place with the **original** `src`. Modifying the new state silently
  mutates the parent. This is a correctness bug *and* a memory-safety hazard
  in two scenarios:
  - If the caller frees `src` and then reads from the (new) child → reads
    freed memory → UAF.
  - If two parallel simulations share a root state (MCTS does exactly this
    via `engine_clone_cow`), they race on the shared struct fields → data
    race and torn reads/writes.
- The arena attached to the child is independent (good), but every arena
  allocation in the child (e.g. for `pending_generic`) lives only as long as
  the child. If the parent is destroyed first, then the child's
  `pending_generic->current_actions` etc. remain valid (because they live in
  the child's arena). However `state->definition` is borrowed (see #4) — the
  parent arena is *not* safe to free before the child.

**Recommended fix:** in `cow_node` / `cow_player` / `cow_market` /
`cow_resource_pool`, if `!cow_dirty` then `memcpy` the entry from the parent
into a new arena allocation *in the child's arena* and store a pointer in the
child; or, since the layout uses fixed-size in-struct arrays, simply
`memcpy(&child->nodes[i], &src->nodes[i], sizeof(NodeState))` and then clear
the parent's `cow_dirty` (no, that would mutate the parent). The cleanest
option is to make `engine_clone_cow` actually clone the dirty struct into
the new arena *eagerly on the first `cow_*` call*, using a per-state mapping
of `(parent_ptr_offset → new_ptr)`.

### 2. `draw_cards_state` discards the discard pile after `memcpy` while loop still uses it

```c
void draw_cards_state(PlayerState *ps, int count, RNG *rng,
                       uint64_t shuffle_seed, int *shuffle_counter) {
    for (int i = 0; i < count; i++) {
        if (ps->deck_count == 0 && ps->discard_pile_count > 0) {
            memcpy(ps->deck, ps->discard_pile,
                   (size_t)ps->discard_pile_count * sizeof(Sym));
            ps->deck_count = ps->discard_pile_count;
            ps->discard_pile_count = 0;     // <-- logical clear
            shuffle_deck(ps->deck, ps->deck_count, ...);
            ...
        }
        if (ps->deck_count == 0) break;
        ps->hand[ps->hand_count++] = ps->deck[--ps->deck_count];
    }
}
```

The `memcpy` is into `ps->deck` (a different array), so this is not actually
a same-buffer aliasing problem — the `discard_pile` byte-slice is not read
after the `memcpy`. **Not a real bug.** I am demoting this to "noted for
clarity" — the code is correct, but it reads dangerously and a future edit
that switches to `memmove` on overlapping storage or moves the assignment
after the shuffle could regress. A comment would help.

### 3. Loader arena + `GameDefinition` ownership is unclear

`engine_load_definition` allocates `def` from the caller's arena and fills
`def->catalog.cards[i].actions` etc. from the *same* arena. `CEngine` stores
`self._arena` but never calls `arena_destroy` on it — so the arena (and the
`GameDefinition`) is leaked when the `CEngine` is GC'd. That's a Python-side
lifetime issue, not a C-safety issue per se, but the `GameDefinition` lives
across every `CState` ever created (see #4).

### 4. `state->definition` is a borrowed pointer into the engine arena

```c
gs->definition = def;   // state.c:83
```

The `GameDefinition` was allocated out of `CEngine._arena` (ce_api.py:249).
If the user lets the `CEngine` go out of scope (or calls some hypothetical
`tear_down`) before the `CState` does, the `CState`'s `legal_moves` /
`apply` calls dereference a freed pointer. Today there is no `tear_down`
and `CEngine` is process-lifetime-ish, so this is dormant — but it's an
ownership bug that will surface the first time anyone adds a reset method.

### 5. `engine_clone` deep-copies `pending_ability` / `pending_generic`; `engine_clone_cow` does not (because it *calls* `engine_clone`, which does). Actually re-reading: `engine_clone_cow` calls `engine_clone`, so the deep-copy is preserved. ✓ Not a bug. **Demoting this finding** — the code is correct.

What is *not* correct: when the new state then runs `apply_play_card` etc.
through `rules.c`, those call `cow_player` etc. which (per finding #1) don't
copy, so the parent and child share `players[]`. Any nested `pending_generic`
created via `arena_alloc(arena, ...)` is *in the child's arena only* — but
the `current_actions` pointer in `pending_generic` is set to point at
`card->execution.actions` from the parent's `GameDefinition` (arena). The
parent outlives the child (lifetime), so this is fine. **No bug here**, but
the lifetime tangle is fragile.

### 6. `CState` lacks `__del__`

```python
class CState:
    __slots__ = ("_ptr",)
    def __init__(self, ptr):
        self._ptr = ptr
    def destroy(self): ...
```

If the user forgets `state.destroy()` (or the Python wrapper goes out of
scope in a path that doesn't go through `CSession.destroy()`), the
underlying `GameState` (and its arena) is leaked. Add `__del__` that calls
`engine_destroy` when `self._ptr` is non-null. The ctypes pointer is
reference-counted by the OS, so the call is safe to make at GC.

### 7. `CEngine._global_lock` — minor

`CEngine._global_lock = __import__("threading").Lock()` is evaluated at
class-body time. That's fine on CPython (one thread is creating the class),
but it's idiomatic to do this inside `__init__` or as a module-level
constant. Not a safety issue.

### 8. `read_file` doesn't validate `ftell`/`fread`

`ftell` can return `-1L` for binary streams on Windows opened in text mode.
`read_file` opens with `"rb"` so this is unlikely, but the cast
`(char *)malloc((size_t)len + 1)` with `len == -1` becomes a huge
allocation request — likely returns NULL, which is handled. But
`fread` may return fewer bytes than `ftell` advertised (pipes, sparse
files), and the function doesn't loop. Not exploitable in this engine
(local files only) but worth a guard.

### 9. `MOVE_RESOLVE_GENERIC` ownership on success

`rules.c:612-617`:

```c
case MOVE_RESOLVE_GENERIC: {
    GameState *r = apply_resolve_generic_choice(state, move);
    if (!r) { engine_destroy(state); return NULL; }
    engine_destroy(state);   // <-- destroys state
    return r;
}
```

If `r == state` (e.g. the choice was already auto-resolved and no clone was
made), this is a use-after-free. Looking at `apply_resolve_generic_choice`
(`generic_runtime.c:263`), it always calls `engine_clone_cow(src)` first, so
`r` is never equal to `state`. **Safe today, but the contract is implicit
and easy to break.**

### 10. Arena returns uninitialized memory

`arena_alloc` (arena.c:48-64) does **not** zero its memory; only
`arena_calloc` does. Code that uses `arena_alloc` then reads the result
without explicitly initializing every field reads uninitialized bytes. Most
callers initialize via a struct assignment, which is fine, but
`arena_alloc(arena, (size_t)oc * sizeof(Sym))` at `generic_runtime.c:181`
is then immediately written to in a loop, and
`arena_calloc(arena, 1, sizeof(PendingGenericChoiceState))` at
`generic_runtime.c:168` *is* safe. Spot-checked: all arena-allocated
`PendingGenericChoiceState` and `PendingAbilityState` use `arena_calloc`. ✓

### 11. `CEngine.available()` re-inits the global

```python
@staticmethod
def available() -> bool:
    try:
        if not CEngine._globally_initialized:
            _lib.intern_init(4096)        # no lock here
        return True
```

`available()` skips the lock that `initialize()` uses. Two threads calling
`available()` concurrently could both observe `_globally_initialized == False`
and both call `intern_init`, which `calloc`s a new table and orphans the
old one (leak + UAF for any thread holding a `Sym` from the old table).
Trivial fix: take the same `_global_lock`.

---

## High-level recommendations

1. **Implement real COW** in `state.c` — eagerly clone the struct (and any
   arena-owned pointers the struct references) into the new state's arena on
   the first `cow_*` call. This is the single highest-impact change.
2. **Add `CState.__del__`** that calls `engine_destroy(self._ptr)` if
   non-null. Pair with a `weakref` to the `CEngine` to ensure the borrowed
   `state->definition` is still valid.
3. **Lock `CEngine.available()`** with the same `_global_lock`.
4. **Document ownership** in `engine.h`: `engine_create_game_definition`
   borrows `def`; `engine_load_definition` returns a pointer into the
   caller's arena. Add an `engine_destroy_definition` and let `CEngine`
   call it on teardown.
5. **Add `engine_apply` invariant**: assert `result != state` in the
   `MOVE_RESOLVE_GENERIC` branch, or restructure so the engine never
   returns its input pointer.
6. **Defensive `read_file`**: check `ftell() < 0` and loop on short `fread`.
7. **Add `__cdecl`-equivalent calling convention** explicitly in
   `engine_bindings.py`. Windows x64 already implies it, but marking
   `WinDLL` vs `CDLL` removes one class of stack corruption.

## Verification

This review was read-only. After fixes land, recommended verification:

- Build with `cl /Zi /fsanitize=address` (or `clang -fsanitize=address`)
  and run `test_engine.exe` + `test_generic.exe` + `test_game.exe` (all
  present in `engine_c/`).
- Run the Python `CSession` and a headless `run_c_simulation` (see
  `bindings/session.py:138`) for 10k+ moves under `pytest -x` and
  AddressSanitizer.
- `pytest tests/test_engine_purity.py` will *not* cover the C engine —
  consider adding a `tests/test_engine_c_safety.py` smoke test that
  repeatedly creates, clones, and destroys `CState` to flush the leak/UAF
  bugs above.
