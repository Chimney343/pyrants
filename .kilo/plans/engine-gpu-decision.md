# Plan: Can the `engine/` Hot Path Run on GPU?

## Short answer

**No, not as a drop-in.** The engine is a small-pointer-chasing Python
workload built on Pydantic v2 immutable models and hand-rolled
`__deepcopy__` (see `engine/state.py:376-410`, which already shares the
frozen `GameDefinition` tree to avoid ~10 ms of wasted allocation per
`apply`). A GPU would not make a single `apply(state, move)` faster; it
would only pay off if the engine were rewritten to run **N rollouts in
parallel as a batched tensor op** — a multi-month reimplementation, not an
optimization.

## Evidence

- **Workload shape is pointer-chasing, not numeric.**
  `engine/state.py:42-100` defines `DeckDefinition`, `CardAction`,
  `CardOption`, `SequenceExecutionModel` — small named records with
  frozen Pydantic models. The runtime state in `GameState` (line 370+)
  holds `dict[str, NodeState]`, `list[PlayerState]`, `set[str]`, and
  recursive `PendingGenericChoiceState`. There is no natural dense
  tensor. A 2-player Tyrants game has ~12-30 sites, ~40-80 cards in
  decks, and tiny per-node integer counters. Flattening to a tensor
  costs more than the work itself.
- **Hot path is dominated by Python object overhead, not arithmetic.**
  62 `state.model_copy(deep=True)` sites across
  `engine/rules.py`, `engine/generic_runtime/_actions.py`,
  `engine/generic_runtime/_custom_effects.py`, `engine/state.py:473`,
  etc. IS-MCTS measures ~10 ms per state clone
  (`scripts/run_ismcts.py:7-10`). The cost is Pydantic field
  enumeration + recursive `deepcopy`, neither of which benefits from
  GPU SIMD.
- **Engine has no batch dimension today.** One game = one state = one
  Python object. A GPU kernel needs a batch. The only natural batch is
  "many independent games in parallel", and `scripts/run_ismcts.py:27`
  already parallelizes that across CPU processes with
  `ProcessPoolExecutor` (the right tool for CPU-bound CPython work).
- **Stack has no GPU dependencies.** `pyproject.toml` lists
  `pydantic`, `open-spiel`, `structlog`, `tqdm`. `poetry.lock` mentions
  `torch` only in the `full` extras of `open-spiel`, which is a
  transitive optional test-dep, not a runtime dep. NumPy is the only
  numeric lib, and it is not used inside the engine.
- **Engine must stay pure.** `tests/test_engine_purity.py` forbids
  I/O. A JAX/torch port would still satisfy purity, but the cost of
  porting the rules interpreter (`engine/generic_runtime/_actions.py`,
  `_custom_effects.py`, `_resolve.py`) to jax.jit-compatible pure
  functions is enormous: every `if state.pending_ability is None`
  branch, every dict lookup, every `model_copy` would need a tensor
  analogue.

## When GPU *would* make sense (future, if ever)

The AlphaZero / MuZero / Polygames pattern **does** justify a GPU port
for game engines, but the conditions are not met here:

| Condition | This repo |
|---|---|
| Engine reimplemented in a tensor framework from day 1 | ✗ Engine is Python + Pydantic |
| Hundreds of self-play games per training step | ✗ IS-MCTS runs 50-200 sims × 1-2 games for evaluation, not training |
| Neural net evaluator is the dominant cost | ✗ No NN; rollout cost dominates |
| Batched legal-move masking | ✗ Legal moves computed per-state in Python |

If a future RL training loop (e.g. AlphaZero self-play for IS-MCTS)
needs thousands of games per second, the right move is **port
`engine/rules.py::apply` and `engine/rules.py::legal_moves` to JAX
or torch** (drop-in for the deterministic parts, keep Pydantic for
data loading) and run a `vmap`-batched rollouter. This is a
multi-month project, not a profile-and-tune.

## Realistic low-effort wins (in priority order, none GPU)

These are the actual levers; the user's previous "not now" answer
explicitly deferred them, so they stay out of scope for this plan:

1. **Structural sharing for state updates.** Today every `apply` does a
   full `model_copy(deep=True)` even when only one counter changed
   (`engine/rules.py:141,229,393,425,467,488,530,536,571,607,670,693,
   700,707`; `engine/generic_runtime/_actions.py` 16 sites;
   `engine/generic_runtime/_custom_effects.py` 7 sites). A persistent
   data structure (pyrsistent, or hand-rolled dict-of-dicts with
   path-copying) would cut the ~10 ms/clone that dominates IS-MCTS
   wall time.
2. **Faster cloning of the mutable sub-tree.** `engine/state.py:376`
   already shares the frozen definition; the remaining mutable part
   (players, board nodes, pending states) is what costs ~10 ms.
   Targeted work there beats any architecture change.
3. **`asyncio.to_thread` or `ProcessPoolExecutor` for batched
   simulation** in `game_simulation.py` (already used in
   `scripts/run_ismcts.py:27`). This is "GPU-on-CPU" for embarrassingly
   parallel work.
4. **Cython/Numba on inner loops** in `engine/scoring.py:46-90` and
   the `board_index` / `card_index` lookups at `engine/state.py:419,
   425` — but the gains will be small relative to the clone cost.

## Decision

Document the reasoning in `docs/engine/async-decision.md` (the
follow-up doc to be added by the previous "engine async" plan) under
a new section **"Why not GPU?"**, and do not pursue a GPU port.

## Out of scope

- No GPU dependencies added to `pyproject.toml`.
- No JAX / torch / numba / cupy imports anywhere in `engine/`.
- No batched-rollout prototype. The IS-MCTS round-cap plan
  (`.kilo/plans/ismcts-round-cap.md`) already exposes the
  `cProfile` workflow needed to confirm where time actually goes
  before any porting decision is made.
- No structural-sharing or `pyrsistent` work. Deferred per the
  user's earlier "Not now" answer.

## Validation

- `grep -rE "torch|jax|cupy|numba|triton|taichi" engine/` → still
  zero matches.
- New paragraph in `docs/engine/async-decision.md` (when that doc is
  created by the prior plan) explains the GPU decision next to the
  async decision.
- `just test` and `ruff check .` continue to pass.
