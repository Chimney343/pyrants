"""Board-view cache tests for F-013.

The F-011 fix routed ``build_c_board_view`` (which calls the monolithic C
``engine_build_view``) into ``private_view_json``'s ``_board_nodes_view``, at
~388 us/call — a 9.66x end-to-end search wall-time regression (see
``docs/validation/findings.md`` F-013 and ``docs/validation/f013-fix-plan.md``).

The fix caches the player-agnostic board projection on ``CEngineAdapter`` and
invalidates it on ``apply()``. These tests follow the house pattern: the
anti-regression controls (T1, T3) and the structural trip-wire (T5) describe
invariants that must hold regardless of whether caching exists, and are written
before the one genuinely red test (T2).

See ``docs/validation/f013-fix-plan.md`` § 4 for the T1–T6 mapping.

F-013 Part B (``docs/validation/f013-part-b-fix-plan.md``) supersedes two of
the assertions below:

- ``test_determinize_and_clone_get_independent_fresh_caches`` (T4) asserted
  ``build_c_board_view`` is called exactly twice after a parent's cache is
  warmed — one fresh projection per child. Part B Phase 4 (L2) propagates the
  parent's projection to ``determinize()``/``deepcopy()`` children, making zero
  fresh projections correct. The test is superseded by
  ``test_board_projection.py::TestDeterminizeProjectionInvariant::test_clone_and_determinize_inherit_the_parent_projection``,
  and inverting it is only safe because Part B's T9 (determinize does not
  change board occupancy) and T10 (``engine_determinize`` is structurally
  board-free) lock down the engine invariant the old test was hedging against.
- ``test_repeated_calls_hit_the_cache`` (T2) spied on ``view.build_c_board_view``,
  which the adapter stops calling in Part B Phase 2. It is re-pointed at the
  new projection entry point ``_project_board_nodes`` so it cannot pass
  vacuously at ``call_count == 0``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest import mock

import numpy as np
import pyspiel

import openspiel_pyrants  # noqa: F401

_REPO_ROOT = Path(__file__).resolve().parents[2]

_BOARD_MUTATING_MOVE_TYPES = frozenset({"assassinate", "deploy", "return_spy"})


def _load_c_game(num_players: int = 2):
    return pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})


def _mid_game_state(game, shuffle_seed=42, n_moves=40):
    """A state a few plies past the initial chance node, with a live adapter."""
    state = game.new_initial_state()
    state.apply_action(shuffle_seed)
    rng = np.random.RandomState(shuffle_seed)
    for _ in range(n_moves):
        if state.is_terminal():
            break
        cp = state.current_player()
        if cp < 0:
            break
        legal = state.legal_actions()
        if not legal:
            break
        state.apply_action(int(rng.choice(legal)))
    return state


def _board_nodes(state, pid) -> list:
    """The ``public.board_nodes`` component of *pid*'s private view."""
    return json.loads(state._adapter.private_view_json(pid))["public"]["board_nodes"]


class TestBoardViewCache:
    def test_private_view_json_output_unchanged_by_caching(self, requires_c_engine):
        """T1 — control (G1): repeated unmutated calls are byte-identical."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        for pid in state._game.get_player_ids():
            first = state._adapter.private_view_json(pid)
            for _ in range(5):
                assert state._adapter.private_view_json(pid) == first

    def test_cache_invalidates_on_board_mutating_apply(self, requires_c_engine):
        """T3 — control (G2): after ``apply()`` of a board-mutating move the
        very next view reflects the new board, never a stale cached one.

        ``apply()`` invalidates unconditionally (it is the only mutation site on
        an existing adapter — see the fix plan § 1), so the guaranteed
        ``initial_placement`` move is a deterministic board mutation, and any
        ``deploy``/``assassinate``/``return_spy`` move available mid-game is a
        second, faithful-to-the-move-type-set check when present.
        """
        game = _load_c_game(2)
        state = game.new_initial_state()
        state.apply_action(42)
        pids = state._game.get_player_ids()
        p = state.current_player()
        assert p >= 0
        pid = pids[p]

        placements = [int(a) for a in state.legal_actions()]
        assert len(placements) >= 2
        before = _board_nodes(state, pid)
        state.apply_action(placements[0])
        after = _board_nodes(state, pid)
        assert before != after, "initial placement must change the board"

        # Mid-game board-mutating move, when one exists.
        mid = _mid_game_state(game)
        cp = mid.current_player()
        if cp >= 0:
            mid_pid = mid._game.get_player_ids()[cp]
            target = None
            for aid in mid.legal_actions():
                mv = mid.decode_action(int(aid))
                if mv.move_type in _BOARD_MUTATING_MOVE_TYPES:
                    target = int(aid)
                    break
            if target is not None:
                before = _board_nodes(mid, mid_pid)
                mid.apply_action(target)
                after = _board_nodes(mid, mid_pid)
                assert before != after, "board-mutating move must change the board"

    def test_repeated_calls_hit_the_cache(self, requires_c_engine):
        """T2 — the one red test (G3): N unmutated calls trigger exactly one
        underlying board projection.

        F-013 Part B re-points the spy at ``_project_board_nodes``, the fast
        projection entry point the adapter uses from Phase 2 onward. The old
        spy target ``view.build_c_board_view`` would pass vacuously at
        ``call_count == 0`` once the adapter stops calling it.
        """
        game = _load_c_game(2)
        state = _mid_game_state(game)
        adapter = state._adapter
        pids = state._game.get_player_ids()
        cp = state.current_player()
        pid = pids[cp if cp >= 0 else 0]

        with mock.patch.object(
            type(adapter), "_project_board_nodes", wraps=adapter._project_board_nodes
        ) as spy:
            for _ in range(10):
                adapter.private_view_json(pid)
        assert spy.call_count == 1, f"expected 1 board build, got {spy.call_count}"

    # Superseded by Part B T11 (test_board_projection.py): once a parent's
    # projection is warm, its determinize()/deepcopy() children inherit it and
    # perform ZERO fresh projections on first view. That inversion is only safe
    # because Part B T9/T10 pin the engine invariant this test used to hedge
    # against (determinize never touches the board). The original body asserted
    # ``spy.call_count == 2`` for two children — exactly the behaviour Part B
    # Phase 4 removes. See the module docstring.

    def test_apply_is_still_the_only_state_reassignment_site(self, requires_c_engine):
        """T5 — structural trip-wire: ``self._state = `` must appear only in
        ``__init__``/``apply``/``destroy``. A future edit that adds a fourth
        mutation site without a matching cache invalidation is caught here."""
        src = (_REPO_ROOT / "engine_c" / "bindings" / "c_adapter.py").read_text(encoding="utf-8")
        current_method = None
        sites = []
        for line in src.splitlines():
            m = re.match(r"^\s*def\s+(\w+)", line)
            if m:
                current_method = m.group(1)
            if re.search(r"self\._state\s*=", line):
                sites.append((current_method, line.strip()))
        methods = [m for m, _ in sites]
        assert len(sites) == 3, f"expected 3 self._state reassignment sites, got {len(sites)}: {sites}"
        assert set(methods) == {"__init__", "apply", "destroy"}, f"unexpected sites: {sites}"
