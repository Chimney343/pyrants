# ADR-0001: Adopt C as the engine source of truth, deprecate the Python `engine/`

- **Status:** Active
- **Date:** 2026-06-25
- **Decision owner:** Chimney343
- **Supersedes:** —
- **Superseded by:** —

## Context

pyrants implements *Tyrants of the Underdraft* as a turn-based board/card-game
engine. The repository contains **two** engine implementations:

1. `engine/` — a pure-Python port (Pydantic-typed state, pure-function
   `apply(state, move) -> state'` transitions, generic card-effect runtime).
2. `engine_c/` — a C11 library (`*.c`/`*.h`, compiled to `engine_c.dll` /
   `libengine.a`) exposing state, rules, moves, phases, scoring, a card-effect
   runtime, player-view projection, save/load, and JSON loading via cJSON. A
   thin Python ctypes/CPython binding layer in `engine_c/bindings/` wraps it.

Both implementations overlap in surface area (state, rules, moves, scoring,
generic runtime), and both are still present in the tree. Before this decision
was recorded, nothing in the codebase formally designated one as authoritative,
which led to:

- Contributors extending `engine/` instead of `engine_c/`.
- Test coverage and churn hotspots accumulating in the legacy Python module
  (Repowise: `engine/rules.py` is the repo's worst-performing file at 1.0/10,
  with 8 commits in 90 days and 29 dependents; `engine/state.py` has 62
  dependents).
- `engine_c/bindings/` carrying critical untested hotspots
  (`engine_bindings.py`, `ce_api.py`, `view.py`) because the test effort was
  split across two engines.

`AGENTS.md` already states the convention informally ("the engine is written
in C and lives in `/engine_c`"); this ADR makes it a recorded architectural
decision rather than an undocumented rule.

## Decision

**`engine_c/` is the engine source of truth.** All engine logic — state,
rules, moves, phases, scoring, the card-effect runtime, player-view
projection, save/load, and JSON loading — lives in C under `engine_c/` and is
the canonical implementation.

**`engine/` is a deprecated legacy Python port.** It must not be extended.
New engine features go in `engine_c/`, never in `engine/`. The legacy module
is retained only for:

- Historical reference and diff archaeology.
- Fallback execution when the C DLL cannot be built (clearly marked as a
  degraded path).
- Explicit, scoped migrations (e.g. porting a Python-only feature into C),
  which are the *only* acceptable reason to touch `engine/` source.

The Python surface that callers depend on is provided by the bindings layer in
`engine_c/bindings/` (`engine_bindings.py`, `ce_api.py`, `session.py`,
`view.py`, `label_enrich.py`), not by `engine/`.

## Consequences

### Positive

- **Single performance path.** The C engine is the hot path for simulation,
  IS-MCTS, and OpenSpiel training loops; keeping one implementation avoids
  divergence between a "fast" and a "correct" engine.
- **Clear ownership for tests.** New engine tests target `engine_c/`
  (C tests in `engine_c/tests/` plus Python-side C-binding tests in
  `tests/test_engine_c.py`). Stops the test effort from being split across
  two engines.
- **Engine purity stays enforceable.** `tests/test_engine_purity.py` already
  forbids I/O and `interface.*` imports in both `engine/` and `engine_c/`;
  this decision keeps that contract intact on the canonical side.
- **Churn consolidation.** Repowise hotspots currently split across
  `engine/rules.py`, `engine/state.py`, `engine/helpers.py` consolidate onto
  the C side, where the bindings layer can be hardened in one place.

### Negative

- **`engine/` carries live health debt.** Until the legacy module is frozen or
  removed, it will keep scoring low (4.33/10 module average) and surfacing as
  untested-hotspot findings. This is accepted debt, not a reason to extend it.
- **C toolchain dependency.** `engine_c.dll` must be built (`just build-c`)
  before any `--engine c` tooling or C-binding tests work. This is already
  documented in `AGENTS.md` and is not new.
- **Binding layer is the new critical surface.** With `engine/` frozen, the
  ctypes/CPython bindings in `engine_c/bindings/` become the load-bearing
  Python interface and need targeted tests (currently gaps in
  `engine_bindings.py`, `ce_api.py`, `view.py`).

### Neutral

- `game_session.py`, `game_simulation.py`, `interface/game_viewer.py`,
  `openspiel_pyrants/game.py`, and `scripts/run_ismcts.py` already call into
  the C-backed bindings by default (`--engine c`); no caller-side migration is
  required.

## Alternatives Considered

1. **Keep both engines as peers.** Rejected: the two implementations have
   already drifted in churn and test coverage, and dual maintenance doubles the
   cost of every rule change. Repowise hotspots confirm the Python side is
   accruing debt, not staying current.
2. **Make Python `engine/` the source of truth, drop C.** Rejected: the C
   engine exists specifically for simulation/RL throughput (IS-MCTS, OpenSpiel
   training loops). Reverting would discard the performance work that
   motivated `engine_c/` and regress `scripts/run_ismcts.py` benchmarks.
3. **Rewrite `engine/` to call `engine_c/` internally (shim).** Rejected for
   now: it would preserve the import surface but add an indirection layer and
   keep the worst-performing files alive. A future ADR may revisit a shim if a
   Python-API compatibility boundary is needed.

## Compliance

- `AGENTS.md` already encodes this convention under "CRITICAL: Engine
  Language" and "Pull Request Guidelines" (engine changes must keep
  `tests/test_engine_purity.py` green; do not extend `engine/` in a PR unless
  scoped). This ADR is the referenced rationale.
- `tests/test_engine_purity.py` enforces engine purity on both sides; no
  additional guard test is required for this decision, but a follow-up could
  add a lint/AST guard failing if `engine/` files are modified outside a
  scoped migration.
- Repowise should treat `engine/` findings as accepted legacy debt rather
  than active maintenance targets.

## References

- `AGENTS.md` — "CRITICAL: Engine Language" and "Project Overview" sections.
- `docs/engine-status.md` — current engine surface and backlog (note: still
  references `engine/` paths; a follow-up should re-point these at
  `engine_c/`).
- `tests/test_engine_purity.py` — enforced purity contract.
- Repowise health dashboard (2026-06-24 index): `engine` module 4.33/10,
  `engine_c` module 6.49/10; critical untested hotspots in both `engine/`
  and `engine_c/bindings/`.
- `.kilo/plans/engine-async-decision.md` — related decision keeping the
  engine (either side) synchronous.
