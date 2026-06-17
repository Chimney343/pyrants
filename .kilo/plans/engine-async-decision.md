# Plan: Why asyncio does not belong in `engine/`

## Goal

Produce a written rationale (added to `docs/engine/`) explaining why the `engine/` package
must stay synchronous, and where asynchronous patterns *can* and *cannot* be used in this
repo. No code changes to the engine.

## Why this exists

`engine/` is searched for `async|asyncio|await` and returns 14 matches — all of them
reference a player-input field called `awaiting_option` (see `engine/state.py:346`,
`engine/generic_runtime/_resolve.py` throughout). There is **zero** actual `asyncio`
usage in the engine today, but the name collision makes the topic worth pinning down
explicitly so a future contributor does not "fix" it by introducing coroutines.

## Findings (read-only evidence)

1. **Engine is pure by contract.** `tests/test_engine_purity.py:9` forbids `print`,
   `input`, `open` in `engine/*.py`, and forbids importing `interface.*`. There is
   no I/O boundary in the engine to await.
2. **Engine is CPU-bound.** Hot path is `apply(state, move) -> state'`, which
   chains `model_copy(deep=True)` (62 occurrences across `engine/rules.py`,
   `engine/state.py`, `engine/generic_runtime/*`). IS-MCTS measures ~10 ms per
   state clone (`scripts/run_ismcts.py:7-10`). asyncio yields zero benefit on
   CPU-bound work.
3. **Engine has no event sources.** No sockets, files, timers, queues, or
   subprocesses are reached from `engine/`. The event loop has nothing to schedule.
4. **The `awaiting_option` field is a domain concept, not a coroutine.**
   `engine/state.py:346` declares `awaiting_option: bool = False` on
   `GenericCardRuntimeState`; it is a flag for the *card game* ("the player must
   pick an option"), not Python `await`. Renaming it to `awaiting_player_option`
   would prevent future grep confusion and is the only naming change worth making.
5. **Async at the engine boundary would cascade.** `engine/__init__.py:3` exports
   `apply`, `is_terminal`, `legal_moves`, `winner`. Every consumer
   (`game_session.py`, `game_simulation.py`, `interface/game_viewer.py`,
   `openspiel_pyrants/game.py`, `scripts/run_ismcts.py`) calls these directly.
   Making them `async` would require `asyncio.run` wrappers or full event-loop
   plumbing at ~6 call sites for no throughput gain.
6. **Real parallelism in this repo is `multiprocessing`, not `asyncio`.**
   `scripts/run_ismcts.py:27` already uses `ProcessPoolExecutor` to run independent
   game simulations across cores. That is the right tool for CPU-bound parallelism
   on CPython.

## Plan (documentation only)

### 1. Add `docs/engine/async-decision.md`

Single short file under `docs/engine/` (new directory; the existing
`docs/engine/cards/`, `docs/engine/board-creator/` directories show the layout).
Contents:

- **Decision:** `engine/` stays synchronous. The package's public API
  (`apply`, `is_terminal`, `legal_moves`, `winner`) is sync and must remain so.
- **Rationale:** the three points above (pure, CPU-bound, no event sources),
  plus the cascade cost at 6 call sites.
- **Naming hygiene:** rename `awaiting_option` → `awaiting_player_option` to
  remove the keyword collision that triggered this question. This is a *field
  rename*, not an async change. It propagates to `engine/player_view.py:89,193`
  and `engine/generic_runtime/_resolve.py` (8 references). Pydantic models mean
  this is a refactor, not a runtime break, once the field aliases are updated.
- **Where async *is* appropriate** in this repo, listed for future work:
  - `interface/` — if a web/TUI loop ever needs non-blocking I/O
    (e.g. streaming replays over a socket).
  - `game_setup/scenario_generation/` — concurrent file reads when scenario
    counts grow.
  - `scripts/run_ismcts.py` — could wrap the `ProcessPoolExecutor` in
    `asyncio.to_thread` for progress reporting, but the executor itself is
    the right primitive.
- **Cross-reference:** link to the async-python-patterns skill and to
  `tests/test_engine_purity.py` as the enforced contract.

### 2. Update `AGENTS.md` "Conventions" block

Add one line under the existing `engine/` purity bullet:

> `engine/` is sync. Do not introduce `async def` or `asyncio` in the engine
> package; see `docs/engine/async-decision.md`.

### 3. Test

Add a guard test in `tests/test_engine_purity.py` that fails if any file in
`engine/` contains `async def`, `await `, or `import asyncio` (AST-based, same
style as the existing test). This is a small, mechanical addition (~10 lines)
and locks the decision in.

## Out of scope

- No code changes to `engine/`, `interface/`, or `scripts/`.
- No async/await introduction anywhere.
- No profiling or cloning optimization. The user explicitly chose
  "Document why async is wrong here" + "Not now" for parallelism targets.
- No rename of `awaiting_option` (deferred to a future change once the
  documentation lands and the contract is explicit).

## Validation

- `just test` (pytest) — passes, including the new purity guard.
- `ruff check .` — passes.
- `grep -rE "async def|asyncio" engine/` — still zero matches.
- New doc file is linked from `AGENTS.md`.

## Estimated effort

- 1 new doc file (~60 lines markdown).
- 1 new AST guard test (~10 lines).
- 2-line edit to `AGENTS.md`.
- Total: small, single-session change.
