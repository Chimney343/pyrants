"""Deterministic corpus for the F-013 Part B projection differential tests.

Random playouts do not place spies (0 spy states in 344 sampled states — see
``docs/validation/f013-part-b-fix-plan.md`` § 1.2 / § 4.3), so a corpus whose
composition is trusted must be built deliberately, from three sources:

1. **Random playouts** across ``PLAYOUT_SEEDS`` (breadth, cheap; 2 players);
2. **Scenario files** under ``data/scenarios/`` that carry at least one spy on
   the board (the ``--require-spy-on-board`` generator output that already
   exists in the tree) plus a plain-state control set;
3. **Directed playouts** that prefer board-mutating move types when legal.

The corpus is exposed as a *lazy generator* of live states
(``iter_corpus_states``) so a test never holds hundreds of C arenas at once.
Each yielded item is a ``CorpusState`` with a ``state_id``, a live adapter, the
state's player ids, and board-occupancy metadata (spies / full troop-slot
lists) computed from the general-purpose ``view.build_c_board_view`` — never
from the fast path under test.

Iteration is fully deterministic: playouts replay from a fixed seed line, and
scenario selection scans ``data/scenarios`` in sorted path order. ``phase 0``
of the fix plan freezes ``private_view_json`` for every yielded
``(state, player)`` pair into ``docs/validation/baseline/f013b_view_vectors.jsonl``;
the tests then rebuild the same states and compare live output to the frozen
vectors (G1).
"""

from __future__ import annotations

import glob
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from engine_c.bindings.c_adapter import CEngineAdapter
from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_board_view

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data"
_SCENARIO_DIRS = (
    _DATA_DIR / "scenarios" / "batch_card_generation",
    _DATA_DIR / "scenarios" / "random_card_generation",
)

# Chance-action ids (must be < shuffle_seed_count, i.e. < 1000) for the
# playout and directed sources; each also seeds its own numpy RNG stream.
PLAYOUT_SEEDS = [11, 37, 99, 137, 271, 333, 555, 707, 888, 42, 21, 43, 65, 777]
PLAYOUT_DEPTH_START = 6
PLAYOUT_DEPTH_STEP = 6
PLAYOUT_DEPTH_MAX = 60

# A scenario "has a spy" iff any node's spies array is non-empty.
SCENARIO_SPY_LIMIT = 130
SCENARIO_PLAIN_LIMIT = 90

_BOARD_MUTATING_MOVE_TYPES = frozenset({"assassinate", "deploy", "return_spy"})

_scan_cache: dict[str, list[str]] = {}


def _load_c_game():
    import pyspiel

    import openspiel_pyrants  # noqa: F401

    return pyspiel.load_game("python_pyrants_c", {"num_players": str(2)})


def _scenario_files(with_spy: bool) -> list[str]:
    """Deterministically selected scenario paths (sorted scan, capped)."""
    key = f"{with_spy}"
    if key not in _scan_cache:
        spy_paths: list[str] = []
        plain_paths: list[str] = []
        for d in _SCENARIO_DIRS:
            for p in sorted(glob.glob(str(d / "*.json"))):
                text = Path(p).read_text(encoding="utf-8")
                try:
                    doc = json.loads(text)
                except Exception:
                    continue
                if not isinstance(doc, dict):
                    continue
                state = doc.get("state")
                if not isinstance(state, dict) or not isinstance(
                    state.get("nodes"), list
                ):
                    continue  # aggregation/notes file, not a deserializable state
                if any(bool(n.get("spies")) for n in state["nodes"]):
                    spy_paths.append(p)
                else:
                    plain_paths.append(p)
        limit = SCENARIO_SPY_LIMIT if with_spy else SCENARIO_PLAIN_LIMIT
        chosen = (spy_paths if with_spy else plain_paths)[:limit]
        # only include scenario files that actually deserialize; discovered lazily
        _scan_cache[key] = chosen
    return _scan_cache[key]


@dataclass
class CorpusState:
    """One live corpus state. Keeps its owner alive; exposes the adapter."""

    state_id: str
    owner: object  # object with ``.adapter`` that keeps engine + C state alive
    player_ids: tuple[str, ...]
    n_spies: int
    n_full_slot_nodes: int
    source: str

    @property
    def adapter(self) -> CEngineAdapter:
        return self.owner.adapter


class _Holder:
    """Keeps a corpus adapter's underlying C resources alive.

    ``adapter`` is the live CEngineAdapter; ``keeper`` is the object that owns
    the C-state lifecycle (a ``PyrantsCState`` or a ``CSession``, transitively
    keeping its engine/arena alive too). A ``PyrantsCState`` that is dropped
    destroys its adapter's C state out from under any holder that pinned only
    the adapter, so the keeper must live exactly as long as the corpus entry.
    """

    __slots__ = ("adapter", "_keeper")

    def __init__(self, adapter: CEngineAdapter, keeper):
        self.adapter = adapter
        self._keeper = keeper


def _board_counts(adapter: CEngineAdapter) -> tuple[int, int]:
    """(total spies on the board, nodes with a fully-occupied troop-slot list)."""
    view = build_c_board_view(adapter)
    n_spies = 0
    n_full = 0
    for n in view.board_nodes:
        n_spies += len(n.spies)
        if n.troop_slots and all(t is not None for t in n.troop_slots):
            n_full += 1
    return n_spies, n_full


def _playout_state(game, seed: int, depth: int, rng_seed: int) -> CorpusState:
    rng = np.random.RandomState(rng_seed)
    state = game.new_initial_state()
    state.apply_action(seed)
    for _ in range(depth):
        if state.is_terminal() or state.current_player() < 0:
            break
        legal = state.legal_actions()
        if not legal:
            break
        state.apply_action(int(rng.choice(legal)))
    adapter = state._adapter
    pids = tuple(game.get_player_ids())
    n_spies, n_full = _board_counts(adapter)
    holder = _Holder(adapter, state)
    return CorpusState(
        state_id=f"playout_s{seed}_d{depth}",
        owner=holder,
        player_ids=pids,
        n_spies=n_spies,
        n_full_slot_nodes=n_full,
        source="playout",
    )


def iter_playout_states():
    game = _load_c_game()
    for seed in PLAYOUT_SEEDS:
        for depth in range(PLAYOUT_DEPTH_START, PLAYOUT_DEPTH_MAX + 1, PLAYOUT_DEPTH_STEP):
            yield _playout_state(game, seed, depth, rng_seed=seed)


def _directed_state(game, seed: int) -> CorpusState:
    """One directed playout preferring board-mutating moves when legal."""
    rng = np.random.RandomState(seed)
    state = game.new_initial_state()
    state.apply_action(seed)
    legal = [int(a) for a in state.legal_actions()]
    if legal:
        state.apply_action(int(rng.choice(legal)))
    for _ in range(40):
        if state.is_terminal() or state.current_player() < 0:
            break
        legal = state.legal_actions()
        if not legal:
            break
        preferred = [
            a for a in legal
            if state.decode_action(int(a)).move_type in _BOARD_MUTATING_MOVE_TYPES
        ]
        pool = preferred or legal
        state.apply_action(int(rng.choice(pool)))
    adapter = state._adapter
    pids = tuple(game.get_player_ids())
    n_spies, n_full = _board_counts(adapter)
    holder = _Holder(adapter, state)
    return CorpusState(
        state_id=f"directed_s{seed}",
        owner=holder,
        player_ids=pids,
        n_spies=n_spies,
        n_full_slot_nodes=n_full,
        source="directed",
    )


def _iter_directed_states():
    game = _load_c_game()
    for seed in [101, 202, 303, 404, 505]:
        yield _directed_state(game, seed)


def _iter_scenario_states():
    engine = CEngine()
    engine.initialize()
    for with_spy in (True, False):
        for path in _scenario_files(with_spy):
            session = CSession.load(path, engine=engine)
            pids = tuple(session.state.player_ids)
            adapter = CEngineAdapter(session.state, engine, pids, 0)
            n_spies, n_full = _board_counts(adapter)
            holder = _Holder(adapter, session)
            source = "scenario_spy" if with_spy else "scenario"
            yield CorpusState(
                state_id=f"{Path(path).parent.name}/{Path(path).stem}",
                owner=holder,
                player_ids=pids,
                n_spies=n_spies,
                n_full_slot_nodes=n_full,
                source=source,
            )


def iter_corpus_states():
    """Yield every corpus state once, in a stable order.

    Yields playout states, then directed states, then spy scenarios, then
    plain scenarios. Each item is a live, owned state; the caller must not
    hold them all simultaneously (each owns a 512 KB C arena).
    """
    yield from iter_playout_states()
    yield from _iter_directed_states()
    yield from _iter_scenario_states()


def corpus_composition(states: list[CorpusState]) -> dict:
    """Summarise a collected corpus for T3's composition guard."""
    return {
        "total": len(states),
        "with_spies": sum(1 for s in states if s.n_spies > 0),
        "full_slot_nodes": sum(1 for s in states if s.n_full_slot_nodes > 0),
        "by_source": {
            src: sum(1 for s in states if s.source == src)
            for src in sorted({s.source for s in states})
        },
        "seeds": len(PLAYOUT_SEEDS),
    }
