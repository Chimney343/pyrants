# ADR-0011: One pyspiel-free game handle for every Python caller

- **Status:** Proposed
- **Date:** 2026-11-11
- **Decision owner:** the project owner (design chosen 2026-11-11, with the conditions recorded below)
- **Supersedes:** -
- **Superseded by:** -
- **Related:** ADR-0006 (its pending-storage deferral is retargeted, not closed), F-037, F-038, F-042

## Context

Candidate 8 (handoff "2.2") is one game handle for every Python caller. Two
adapters wrap the same C engine with different failure semantics and no shared
interface, and five other shortcuts have grown around them. Re-verified on
`7359ac2` (2026-11-11), line numbers as of that commit:

| Claim | Verdict | Evidence |
|---|---|---|
| `CSession` returns `None`; `CEngineAdapter` raises | Confirmed | `engine_c/bindings/session.py:128-135` returns `None`; `engine_c/bindings/c_adapter.py:103-120` raises `RuntimeError`. `CEngineAdapter.__deepcopy__` (`c_adapter.py:52-60`) returns **`self`** when the clone fails, so a "copy" aliases the original and a search simulation mutates the root (F-042). |
| Replay is implemented three times | Confirmed | `openspiel_pyrants/state_c.py:127` (`clone_via_replay`); `scripts/_nn_dataset.py:243-350` (its own apply loop, `find_matching_move` at `:333`); `interface/replay_player.py:91-137` (rebuild/seek). |
| The seed mixer is copied | Confirmed | `interface/replay_loader.py:53-59` and `openspiel_pyrants/state_c.py:15-21`; only `tests/test_replay_loader.py:24-28` keeps them equal. |
| The NN pipeline imports the GUI package | Confirmed | `scripts/_nn_dataset.py:20-21` imports `interface.replay_loader` and `interface.replay_player`. |
| Four calls bypass the seam | Confirmed as three calls plus one import | `state_c.py:296` (`engine_clone`), `c_adapter.py:178` (`engine_infostate_hash`), `c_rollout_evaluator.py:30` (`state._adapter`), `_nn_dataset.py:20-21` (the cross-package import). |
| `pending_context.py` reads raw memory | Confirmed, undercounted | `engine_c/bindings/pending_context.py:38-40,79-80`; also `c_adapter.py:110-111,137-144,183`, `engine_c/bindings/view.py:224,236-271` (the promotion head), `scripts/run_ismcts.py:428,567`. Six sites, not one. |
| F-037 drops `setup_data_json` in `_init_attrs` | Confirmed, still latent | `openspiel_pyrants/game_c.py:150-163` omits it where `:135-141` passes it. The only entry is `cls.__new__` without `__init__`; `__deepcopy__` (`:143-148`) calls `__init__`, so no in-repo caller. |
| ADR-0006 deferred moving pending storage | Confirmed | `engine_c/pending.h:12-15`; storage is `GameState.pending_ability` and `.pending_generic` (`engine_c/state.h:363,370`); ADR-0006:64-71. |
| F-038's error is in the failure surface | Confirmed | `ce_api.py:52-67`; `legal_moves`/`display_moves` raise `MoveCapacityError` (`:468`, `:483`). The C rollout clamps instead of raising (handoff "Deferred and open"). |

Two notes the brief got slightly wrong, recorded so nobody re-derives them: the
"four calls" are three calls plus one import, and the raw-memory reads are six
sites. Leverage is larger than the brief implies: `CEngine` is constructed and
initialized at ten production sites — `interface/game_viewer.py:404`,
`interface/replay_player.py:49`, `engine_c/bindings/scenario_search.py:283`,
`session.py:60,196,229`, `game_c.py:135,158`, `scripts/_nn_dataset.py:249`,
`scripts/generate_move_label_templates.py:316` — 15 production modules name one of
the two adapters (`c_adapter.py` and `session.py` define them; the other thirteen
are `state_c.py`, `c_rollout_evaluator.py`, `nn/actions.py`, `view.py`,
`scenario_search.py`, `game_viewer.py`, `replay_player.py`, `_session_protocol.py`,
`_nn_dataset.py`, `run_ismcts.py`, `_state_snapshot.py`, `bench_determinize.py`,
`generate_move_label_templates.py`), and 104 `tests/c_engine` files use them.

## Decision

One concrete handle, a new `handle` module under `engine_c/bindings/`. Of
three sketched interfaces the owner chose **A, one concrete handle**, over **B, a
C-side opaque handle** and **C, a Protocol with two implementations**. The owner's
three conditions on A:

1. **The interface exposes no `CState`, no ctypes struct and no raw pointer**, so
   B can later replace the body without callers moving. B is recorded below as
   the follow-on path.
2. **The `PyrantsCState` chunk must not cost speed**: content-identical on the
   quick check and within noise on games/h in a same-session pair, with no extra
   ctypes crossing on `clone`, `apply` or `legal_moves`. `ce_api.py:82-83`
   records that one extra ctypes round trip per decision measured as a 6 %
   games/h regression when `move_capacity()` was not cached, and the handoff's
   C2 row records a slower version of the counting contract at about 10 %.
3. **F-042 is logged for `c_adapter.__deepcopy__` returning `self`**, and the
   raise-only clone failure fixes it in the `PyrantsCState` chunk.

### The interface

`GameHandle` owns one game: the loaded definition, the current C state, the move
log, the player ids and the shuffle seed. Every value crossing the interface is
a Python value (`str`, `int`, `bool`, `dict`, `list`, `tuple`) or a `Move` value
object; nothing is a ctypes type.

- **Setup.** `GameHandle.new(player_ids, seed, *, definition=None)` and
  `GameHandle.from_files(*, board_path, card_path, setup_path, setup_data_json="")`.
  `setup_data_json` is a first-class argument, which is what fixes F-037 once.
- **Apply.** `apply(move) -> None`, mutating, raising `EngineApplyRejected`.
  `try_apply(move) -> bool` is not offered: one way to do one thing.
- **Clone.** `clone() -> GameHandle` (C `engine_clone`), raising
  `EngineCloneFailed`; never returns `self` (F-042).
- **Determinize.** `determinize(observing_player_id, seed) -> GameHandle`,
  raising `EngineDeterminizeFailed`.
- **Moves.** `legal_moves() -> list[Move]`, `display_moves() ->
  list[tuple[Move, bool]]`; either raises `MoveCapacityError` above the frozen
  capacity. `Move` carries `move_type`, `data` and `to_payload()` as public
  values, so no caller needs `_c_move` or `_move_type`.
- **Decision record.** `decision_record() -> dict | None`, decoding one JSON
  record from C (below).
- **Views.** `player_view(player_id) -> str`, `infostate_key(player_id) ->
  tuple[int, int]`, plus `phase()`, `round_number()`, `current_player_id()`,
  `is_terminal()`, `scores()`, `winner()`, `rollout(seed, max_length)`.
- **Replay.** `GameHandle.from_log(*, player_ids, seed, setup_data_json, log)`
  takes an in-memory log of move payloads and never a path; `advance(n)` and
  `seek(n)` are the cursor that `ReplayPlayer` needs. `load_scenario(path)` /
  `save_scenario(path)` cover the engine's own scenario document
  (`saveload.c`), which is a data format, not a run artifact.
- **Lifetime.** A context manager, so `destroy()` cannot be forgotten and the
  three existing teardown sites (`session.py:137-140`, `c_adapter.py:240-246`,
  `state_c.py:88-101`) collapse into one.

### Failure semantics

One family, one base class, all subclasses of `RuntimeError` so today's `except
RuntimeError` call sites keep working:

- `EngineError(RuntimeError)` — the base, and not for catching.
- `EngineApplyRejected(EngineError)` — `engine_apply` returned NULL.
- `EngineCloneFailed(EngineError)` — `engine_clone` returned NULL (F-042).
- `EngineDeterminizeFailed(EngineError)` — `engine_determinize` returned NULL.
- `MoveCapacityError(EngineError)` — moved here from `ce_api.py:52-67`, not
  duplicated. `tests/c_engine/test_move_capacity_binding.py` keeps importing it
  from the bindings package.

`CSession.submit_move` catches **only** `EngineApplyRejected` and returns
`None`, which is its current contract and the GUI's; a capacity or determinant
failure propagates, so the viewer can no longer hide it.

### The decision record

One JSON record from C, not a scalar-plus-detail pair: every reader (`run_ismcts`
telemetry, `_nn_dataset`, `view.py` label enrichment, crash diagnostics) runs
once per real decision and never per simulation, so a scalar fast path buys
nothing and two shapes would make the module shallower.

- `engine_pending_decision_json(state, buf, cap) -> size_t`, the same size-query
  contract as `engine_player_view_json`: return the bytes needed excluding the
  NUL, and a caller retries with a bigger buffer. Returns 0 for "nothing
  pending".
- It covers **every** `PendingKind` (`engine_c/pending.h:16-23`), not just the
  generic frame: `kind`, `priority`, `count`, a `generic` block with today's ten
  keys, a `promotion` block with the head's `source_card_id`/`required_aspect`/
  `focus_aspect` that `view.py:236-271` reads today, and an `ability` block.
- The Python mapping keeps today's flat dict keys exactly, so
  `read_pending_generic_context` and `..._full` become projections of the JSON.
- A test proves the decision log's `pending_context` line and the NN encoder's
  inputs are byte-identical before and after the change.

### Pending storage stays where it is, and the deferral is retargeted

`pending_ability` and `pending_generic` keep living in `GameState` (verified
`engine_c/state.h:363,370`). With the JSON decision record no Python code reads
pending storage at all, so where it lives no longer touches the handle's
interface; it is a C-internal refactor. It is also about 95 non-comment
reach-ins outside `pending.c` and the tests, 42 of them in
`generic_runtime.c`, which lane D is about to rewrite for `custom_effect`.
ADR-0011 therefore **retargets** ADR-0006's storage deferral: from candidate 8
to a separate engine brief after lane D, when the `custom_effect` split has
removed many of those reach-ins. It is not closed, and ADR-0006's status line is
updated to say so.

### Where the code lives, and the import rules

- The handle is in `engine_c/bindings/`, next to `ce_api` and the adapters it
  replaces. `engine_c.bindings` already imports `game_setup`, so no new
  layering direction is introduced.
- **Replay is split by what the code does.**
  - Into the handle: `engine_seed`, `find_matching_move`, `ReplayDesyncError`,
    replay-from-log, and `ReplayPlayer`'s step/seek cursor. Replay takes an
    in-memory log (seed, setup, move payloads). `state_c.py` uses the same seed
    mixer, so the copy disappears.
  - Into a new neutral package, `run_artifacts/`, named for the format it owns:
    `load_replay`, `discover_replays`, `ReplayBundle`/`ReplayMeta`,
    `is_complete_game`, and the run manifest, per-game summary and decision-log
    parsing. G0's recorder puts the **writer** side there, so the decision log
    and the replay document have one owner.
  - `interface/` keeps only `replay_viewer.py`. The NN stops importing it.
- **Import guards**, added in F1 and extended in F4:
  - no module under `engine_c/bindings/` may import `interface`,
    `openspiel_pyrants`, `pyspiel`, `scripts` or `run_artifacts` (the handle
    knows no filesystem artifact layout);
  - no module under `run_artifacts/` may import `interface`;
  - each rule has a test that fails on a temporary violation. None of them is
    violated today (checked).

### Follow-on path: B, a C-side handle

If the decision record ever needs a C ABI (a native caller, or per-simulation
cost), an `engine_c`-side handle implementation can take over the body behind
the same Python interface: one C struct owning definition, state, log and seed;
one `PendingKind` enum as the failure surface; the record read without a JSON
parse. Because condition 1 keeps ctypes out of the interface, that swap moves no
caller. It would be an engine-lane brief with asan, replay and speed gates.

## Alternatives considered

- **A, one concrete handle (chosen).** Deep: lifetime, move capacity, pending
  decode and failure modes behind about fifteen operations. Highest leverage of
  the three that keeps the work in one package; a change lands in one place.
- **B, a C-side opaque handle.** Deeper and at least as high-leverage, and it
  makes clone/determinize/replay impossible to re-implement in Python. Rejected
  now for cost, not shape: it is engine-lane, so its chunks serialise against
  lane D and lane A on `develop`, every chunk needs asan plus replay
  verification, and the record layout freezes early. Kept as the follow-on.
- **C, a Protocol with two implementations.** Same depth per implementation and
  better DLL-free tests, but worse locality (a contract change touches the
  Protocol and both implementations). By the handoff's own vocabulary it is the
  weak option: `PyrantsCState` and `CSession` already exist as the two
  production adapters, so a test-only `ScriptedHandle` makes the seam fake and
  has to be kept honest by hand.

## Consequences

- **Deletion test.** Deleting the handle puts three replay loops, two failure
  policies, six raw-memory pending readers and ten `CEngine` setup sites back
  where they are today, so the module earns its keep. The two adapters survive
  as thin implementations of their own contracts, which is what they are for.
- **F-042** is logged (OPEN) for `c_adapter.__deepcopy__` returning `self` on a
  clone failure; the `PyrantsCState` chunk fixes it by routing clone through the
  handle's `EngineCloneFailed`.
- **F-037** is fixed in the `PyrantsCState` chunk, the first chunk that edits
  `game_c.py:150-163`.
- **Wire formats are untouched.** Move payloads, the decision log and the NN
  action ids do not change; the decision record is additive to the dict the
  Python mapping already produces, and a byte-identity test pins that.
- **Determinism is untouched.** The handle wraps the same C calls in the same
  order; no RNG is drawn differently, so `just verify-replays` must stay green
  in every chunk.
- **Speed is a gate, not a hope.** The `PyrantsCState` chunk needs a
  content-identical quick check and a same-session pair within noise; the
  evaluator and replay chunks need content-identical quick checks because they
  sit on the clone/determinize/rollout paths.

## Chunk list

Execution order: F1, F6, F2, F3, F5, F4. F6 needs only F1 because the C record
does not touch the adapters. The table lists the chunks by id. Each chunk is one
`[engine-c]`/`[docs]` pair that leaves every gate green.

| Chunk | Work | Gates |
|---|---|---|
| **F1** | New `handle` module under `engine_c/bindings/`: the handle, the `Move` value, the failure family with `MoveCapacityError` rehomed, a context manager, and tests at the interface (setup/apply/clone/determinize/moves/views/seed). The import guard. Nothing delegates to it yet. | Full gates; asan; the new tests; `ruff` clean in the new files. No speed run: no caller moved. |
| **F2** | `PyrantsCState` becomes a delegating adapter: it holds a `GameHandle`, and `_adapter` goes away. `game_c.py` hands the state a handle and passes `setup_data_json` in `_init_attrs` (**F-037**). Clone goes through the handle, so **F-042** is fixed and its test proves a failed clone raises rather than aliasing. | Full gates; asan; **content-identical quick check** (8 games; the decision log and each game's final decks equal, only `replay_context` may differ) **and a same-session pair within noise** (no extra ctypes crossing on clone/apply/legal_moves); verify-replays. |
| **F3** | `CSession` becomes a delegating adapter over `GameHandle`, keeping its public surface (`state`, `move_count`, `legal_moves`, `display_moves`, `submit_move`, `snapshot`, `save`/`load`, `from_files`) and returning `None` **only** for `EngineApplyRejected`. `_session_protocol.SessionLike` and the GUI are unchanged; `submit_move` gains a capacity/determinize failure path the GUI can see. | Full gates; the GUI/`tests/c_engine` suites; content-identical quick check. |
| **F4** | Replay-from-log, `engine_seed`, `find_matching_move` and `ReplayDesyncError` move into the handle; `run_artifacts/` takes the format side (`load_replay`, `discover_replays`, bundles, `is_complete_game`, artifact parsing); `interface/` keeps only `replay_viewer.py`; `_nn_dataset` stops importing `interface`; both import guards extend; the seed-mixer copy in `state_c.py` goes. | Full gates; `tests/test_replay_loader.py` and `tests/test_replay_player.py` (how they reach the code only); content-identical quick check; verify-replays. |
| **F5** | Evaluators and scripts stop touching `state._adapter`: `c_rollout_evaluator.py:30`, `scripts/_replay_payload.py:20-34`, `scripts/run_ismcts.py:428,567,777,781,798,800`, the bench scripts, and the harness copies that production reads. The `_move_type` compatibility shim and the 48 card test files that read it are cleaned up here, through the handle's public `move_type`. | Full gates; **content-identical quick check** (the rollout evaluator is on the hot path); verify-replays; `just ismcts-perf` compared. |
| **F6** | `engine_pending_decision_json` in C, `pending_context.py` reduced to projections of it, `view.py:236-271`'s promotion head read through it, and the byte-identity test for the decision log's `pending_context` line and the NN encoder's inputs. | Full gates; asan; every `tests/c_engine/test_pending_context*.py`; content-identical quick check. |

**Dropped:** former F7 (pending storage). Retargeted per ADR-0006 above.

## Speed

No speed run was made: F0 writes no code. The two constraints the chunks inherit
come from C2, whose record is in `speed-records.md` and in the handoff's C2 row:
one extra ctypes round trip per decision measured as a 6 % games/h regression
(`ce_api.py:82-83`), which is why F2's gate is a same-session pair rather than a
micro-benchmark, and why the handle must not add a crossing to `clone`, `apply`
or `legal_moves`. Each chunk records its own run ids in `speed-records.md`.
