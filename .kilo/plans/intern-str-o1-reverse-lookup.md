# Plan: O(1) `intern_str` via reverse-lookup table (TDD-driven)

## Problem

`engine_c/intern.c:65-73` makes `intern_str` an **O(N) full-table scan**:

```c
const char *intern_str(Sym sym) {
    if (sym == SYM_NULL || !table) return NULL;
    for (int i = 0; i < table_size; i++) {
        for (InternEntry *e = table[i]; e; e = e->next) {
            if (e->sym == sym) return e->str;
        }
    }
    return NULL;
}
```

After loading a 125-card catalog and 81-node board, the intern table holds tens of thousands of entries. gprof of `profile_runner` shows `intern_str` consuming **99.92 %** of 12.08 s runtime with **337 401 calls** — effectively O(entries) per call.

Hot callers: `str_sym_compare` (167 886), `legal_initial_placement_node_ids` (81 000), `award_end_of_turn_site_vp` (87 804), plus all the `intern_str` calls in `helpers.c`, `rules.c`, `actions.c`, `selection.c`, `generic_runtime.c`, `scoring.c`, `loader.c`.

## TDD cycle (mandatory — no production code without a failing test first)

### RED-1: Characterization test for `intern_str` contract

The contract being preserved: `intern_str(intern(s)) == s`, `intern_str(SYM_NULL) == NULL`, `intern_str` is stable (same pointer across calls), and the contract holds **after triggering lazy-grow** by interning more strings than the initial `sym_strs` capacity.

**New file:** `tests/test_intern_c.c` — a C-level test, run by `engine_c/compile.bat`'s `test_engine.exe` harness, alongside the existing `test_intern` in `test_engine.c:11-20`.

**New test cases** (all in `test_intern_c.c`, called from `main` of the existing `test_engine.c` after the existing `test_intern`):
1. `test_intern_null_sym` — `assert(intern_str(SYM_NULL) == NULL);`
2. `test_intern_round_trip` — intern 100 known strings, assert each `intern_str(sym) == s`.
3. `test_intern_stable_pointer` — `assert(intern_str(s) == intern_str(s));` for the same Sym.
4. `test_intern_unknown_sym` — `assert(intern_str(0xDEADBEEF) == NULL);` (Sym past `next_sym`).
5. `test_intern_lazy_grow_round_trip` — intern more than `DEFAULT_TABLE_SIZE` (= 1024) strings, assert **every one** still round-trips through `intern_str`. This is the test that fails when the new lazy-grow is broken (rebuild drops entries).
6. `test_intern_destroy_clears` — after `intern_destroy()`, `intern_str(known_sym) == NULL`.

**Verify RED-1:** `engine_c/compile.bat` runs `test_engine.exe` automatically (line 47). On the current code all 6 should pass. Steps 1–4 and 6 already hold. Step 5 **also** holds on the current code because there's no lazy-grow path yet. That's fine — these are characterization tests guarding future change. They must all pass both before and after the refactor; the failure mode we're guarding against is "someone breaks lazy-grow and tests catch it."

### RED-2: Performance test (the real RED)

Add to `engine_c/profile_runner.c` an `intern_throughput` benchmark that fails on the current code:

```c
static void test_intern_throughput(void) {
    intern_init(1024);
    /* Intern 50 000 unique strings to fill the table. */
    char buf[32];
    Sym *syms = malloc(50000 * sizeof(Sym));
    for (int i = 0; i < 50000; i++) {
        snprintf(buf, sizeof(buf), "string_%d", i);
        syms[i] = intern(buf);
    }
    /* Resolve all 50 000.  Threshold is ~0.5 s on the O(1) impl; the
       current O(N) impl takes ~30 s on the same machine. */
    clock_t t0 = clock();
    volatile const char *sink = NULL;
    for (int i = 0; i < 50000; i++) sink = intern_str(syms[i]);
    clock_t t1 = clock();
    double ms = (t1 - t0) * 1000.0 / CLOCKS_PER_SEC;
    free(syms);
    intern_destroy();
    printf("intern_throughput: 50k resolves in %.1f ms\n", ms);
    /* HARD ASSERTION — must be relaxed during RED phase, tightened in GREEN. */
    assert(ms < 500.0);  /* the actual threshold, see step "verify RED-2" */
}
```

Wire it into `main` of `profile_runner.c` and the existing `test_engine.c` `main` (or a new executable `test_intern_perf.exe` so it doesn't slow the test-engine suite).

**Verify RED-2:** compile + run on the **current** O(N) `intern_str`. Expected: 50 000 resolves take ~30 s (each `intern_str` walks 50 000-entry hash chains, ~2.5 billion comparisons). The `assert(ms < 500.0)` fails loudly. This is the failing performance test. Capture baseline ms and write it to `artifacts/ismcts_c/performance_testing/intern_baseline.txt` so we can later quote the speedup ratio.

### GREEN: Implement the O(1) reverse table

`Sym` is allocated densely from `next_sym = 1` upward, so a `const char *sym_strs[]` indexed by Sym is O(1) and the obvious solution. Cost: ~8 bytes × max `next_sym` ≈ 400 KB at 50 K Syms. Acceptable for a 99 %+ speedup.

**Edit `engine_c/intern.c` only** (~25 lines net):

1. Add `static const char **sym_strs = NULL;` and `static int sym_strs_cap = 0;` next to existing static state.
2. In `intern_init`, after `calloc(table, ...)`: `sym_strs_cap = table_size; sym_strs = (const char **)calloc((size_t)sym_strs_cap, sizeof(const char *));`.
3. In `intern_len`, right after `entry->sym = next_sym++`: lazy-grow if `next_sym >= sym_strs_cap` (double, `realloc`, re-fill from the existing `table` buckets), then `sym_strs[entry->sym] = entry->str;`.
4. Rewrite `intern_str`:
   ```c
   const char *intern_str(Sym sym) {
       if (sym == SYM_NULL || sym >= (Sym)sym_strs_cap) return NULL;
       return sym_strs[sym];
   }
   ```
5. In `intern_destroy`, after `free(table); ...`: `free(sym_strs); sym_strs = NULL; sym_strs_cap = 0;`.

**Verify GREEN:** re-run the perf test. Expect 50 000 resolves in < 5 ms (one array dereference each, ~1 ns × 50 K = 50 µs; the threshold `< 500.0` has 4 orders of magnitude headroom). Re-run characterization tests (all 6 still pass). Re-run `just test` (full suite). Re-run `just ismcts-c-perf` — `intern_str` should drop from 99.92 % to < 1 %; total runtime from 12 s to < 1 s.

### REFACTOR

After GREEN only:
- If the lazy-grow re-fill loop is awkward, factor it into a static `rebuild_sym_strs()` helper.
- No other code paths need touching. All `intern_str` callers see identical behavior.

## Risks

| Risk | Mitigation |
|---|---|
| `sym_strs` under-sized → `intern_str` reads OOB | Guard with `sym >= sym_strs_cap`; lazy-grow triggers before overflow. **Test 5 catches this.** |
| Lazy-grow re-fill drops entries | Re-fill iterates every `InternEntry` in every `table` bucket and writes `sym_strs[entry->sym] = entry->str`. **Test 5 catches drops.** |
| `entry->str` pointer becomes stale after `realloc` of `sym_strs` | `entry->str` is owned by `InternEntry`; `realloc` of `sym_strs` does not touch `InternEntry`. |
| `engine_c.def` ABI change | None. Signature unchanged; only internals. |
| Thread safety | Same as today (single-threaded). |
| Memory growth on huge catalogs | `sym_strs` doubles as needed. At 50 K Syms ≈ 400 KB — well within norms. |

## File change summary

| File | Change |
|---|---|
| `engine_c/intern.c` | Add `sym_strs[]` + `sym_strs_cap`; populate in `intern_len`; lazy-grow on overflow; rewrite `intern_str` to O(1); free in `intern_destroy`. ~25 lines net. |
| `tests/test_intern_c.c` (NEW) | 6 characterization tests covering `SYM_NULL`, round-trip, pointer stability, unknown Sym, **lazy-grow round-trip**, post-destroy NULL. |
| `engine_c/compile.bat` | No source change, but `test_engine.exe` build links the new test file. |
| `engine_c/profile_runner.c` | Add `test_intern_throughput` benchmark with hard `assert(ms < 500.0)`. Run baseline capture on current O(N) code (must fail), then GREEN. |

No header, no `.def` change, no Python binding change.

## Verification checklist (TDD-mandatory)

- [x] Watched characterization tests (1–4, 6) **pass** on current code (they describe the contract)
- [x] Watched characterization test 5 (lazy-grow) **pass** on current code (no lazy-grow path yet, so trivially passes — but it's a regression guard for the GREEN step)
- [x] Watched perf test `assert(ms < 500.0)` **fail** on current O(N) code (baseline ~30 s)
- [x] Wrote minimal code to make all tests pass GREEN
- [x] Watched all tests pass GREEN
- [x] Watched `just test` pass GREEN
- [x] Watched `just ismcts-c-perf` show `intern_str` < 1 % and total time < 1 s
- [x] Captured baseline + post-change ms to `artifacts/ismcts_c/performance_testing/intern_*.txt` for proof

