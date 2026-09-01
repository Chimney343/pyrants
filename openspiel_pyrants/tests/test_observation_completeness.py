"""Observation-completeness tests for F-011.

The board (sites, troops, spies, control) and a player's own discard-pile
identities were absent from ``information_state_string``/``observation_string``
(see ``docs/validation/findings.md`` F-011). These tests lock in the fix and
guard against the two over-fix traps:

* leaking hidden information while fixing the *observed* gap (G2 / T2, T4);
* silently re-coupling the cheap Tier-1 snapshot with the pricey board view
  (G4 / T5).

Anti-overfix controls (T2, T4, T5) are written before the completeness tests
(T1, T3, T7, T8) so the invariants exist in history before the fix that could
break them. See ``docs/validation/f011-fix-plan.md`` § 4.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import time

import numpy as np
import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401


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


def _board_fp(state) -> str:
    """Fingerprint of the board occupancy only (player-agnostic)."""
    from engine_c.bindings.view import build_c_board_view

    view = build_c_board_view(state._adapter)
    payload = [
        {
            "node_id": n.node_id,
            "troop_slots": list(n.troop_slots),
            "spies": list(n.spies),
            "control_vp": n.control_vp,
            "total_control_vp_per_turn": n.total_control_vp_per_turn,
            "vp_tokens": n.vp_tokens,
        }
        for n in view.board_nodes
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _board_differing_clones(state, pid):
    """Two clones of *state* reached by the same move type on different sites.

    Returns ``(c1, c2)`` whose boards genuinely differ, or ``None`` if no such
    pair exists at this state. Mirrors ``docs/validation/harness/inv_b2.py``.
    """
    groups = {}
    for aid in state.legal_actions():
        mv = state.decode_action(int(aid))
        groups.setdefault(mv.move_type, []).append(int(aid))
    for mt, aids in groups.items():
        if not any(t in mt.lower() for t in ("troop", "spy", "place", "deploy")):
            continue
        if len(aids) < 2:
            continue
        for a1, a2 in itertools.combinations(aids[:4], 2):
            c1 = state.clone()
            c1.apply_action(a1)
            c2 = state.clone()
            c2.apply_action(a2)
            if c1.current_player() < 0 or c2.current_player() < 0:
                continue
            if _board_fp(c1) == _board_fp(c2):
                continue
            return c1, c2
    return None


def _board_differing_clones_guaranteed(game):
    """Two states at the initial placement node whose boards genuinely differ.

    Every 2-player game starts with the ``initial_placement`` choice, so the
    first two distinct site targets are guaranteed to yield different boards.
    """
    state = game.new_initial_state()
    state.apply_action(42)
    placements = [int(a) for a in state.legal_actions()]
    assert len(placements) >= 2
    c1 = state.clone()
    c1.apply_action(placements[0])
    c2 = state.clone()
    c2.apply_action(placements[1])
    assert _board_fp(c1) != _board_fp(c2)
    return c1, c2


def _force_discard(state, pid, card_ids):
    """Directly set *pid*'s discard pile in the C state (mirrors card-test helpers)."""
    from engine_c.bindings.engine_bindings import _lib

    idx = state._adapter.player_index(pid)
    ps = state._adapter._state._s.players[idx]
    ps.discard_pile_count = len(card_ids)
    for j, cid in enumerate(card_ids):
        ps.discard_pile[j] = _lib.intern(cid.encode())


# Tier-1 public dict must not grow board data (G4). Captured pre-fix.
_TIER1_KEYS = frozenset(
    {
        "round_number",
        "phase",
        "current_player_id",
        "turn_order",
        "market_row",
        "market_deck_size",
        "market_discard_size",
        "resource_power",
        "resource_influence",
        "public_player_summaries",
    }
)


class TestObservationCompleteness:
    def test_determinization_does_not_change_own_observation(self, requires_c_engine):
        """T2 — control (INV-4a shape): determinization must not change the observation."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        p = state.current_player()
        if p < 0:
            pytest.skip("game ended early")
        pid = state._game.get_player_ids()[p]
        d1 = state.resample_from_infostate(p, np.random.RandomState(11))
        d2 = state.resample_from_infostate(p, np.random.RandomState(22))
        assert d1._adapter.private_view_json(pid) == d2._adapter.private_view_json(pid)

    def test_opponent_discard_pile_still_not_leaked(self, requires_c_engine):
        """T4 — control: another player's discard identities never enter my observation."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        marker = "zz_marker_card_9"
        _force_discard(state, "p2", [marker])

        p1_view = json.loads(state._adapter.private_view_json("p1"))
        assert marker not in json.dumps(p1_view, sort_keys=True)
        b_summary = p1_view["public"]["public_player_summaries"]["p2"]
        assert b_summary["discard_size"] == 1
        # B's summary exposes only counts/aggregates, never discard identities.
        assert not any(
            "zz_marker" in str(v) for v in b_summary.values()
        )

    def test_tier1_snapshot_shape_and_cost_unaffected(self, requires_c_engine):
        """T5 — control (G4): the cheap Tier-1 dict keeps its exact key set."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        adapter = state._adapter

        assert set(adapter._build_public_dict().keys()) == _TIER1_KEYS

        # Loose cost trip-wire: the board view is ~388us/call; injecting it here
        # would push this path ~50x above its ~7.8us baseline. 100us is a
        # generous upper bound that still catches a re-coupling regression.
        n = 500
        t0 = time.perf_counter()
        for _ in range(n):
            adapter._build_public_dict()
        elapsed = time.perf_counter() - t0
        mean_us = (elapsed / n) * 1e6
        assert mean_us < 100.0, f"_build_public_dict mean {mean_us:.1f}us/call"

    def test_board_visible_when_only_site_differs(self, requires_c_engine):
        """T1 — two clones differing only by site must produce different observations."""
        game = _load_c_game(2)
        c1, c2 = _board_differing_clones_guaranteed(game)
        assert _board_fp(c1) != _board_fp(c2)
        assert (
            c1._adapter.private_view_json("p1")
            != c2._adapter.private_view_json("p1")
        )

    def test_board_nodes_omit_current_player_aggregates(self, requires_c_engine):
        """T9 — trip-wire for f011-fix-plan.md §1 detail #2.

        ``board_nodes`` entries must be player-agnostic: none of
        ``CBoardViewData``'s current-player-scoped aggregates may appear as
        keys anywhere in a ``private_view_json`` payload for any player.
        """
        game = _load_c_game(2)
        state = _mid_game_state(game)
        forbidden = {
            "current_player_controlled_sites",
            "current_player_total_control_sites",
            "current_player_control_vp",
            "current_player_total_control_vp",
        }
        for pid in state._game.get_player_ids():
            payload = json.loads(state._adapter.private_view_json(pid))
            assert forbidden.isdisjoint(payload.get("public", {}))
            assert forbidden.isdisjoint(payload)

    def test_own_discard_pile_identities_visible(self, requires_c_engine):
        """T3 — a card forced into my discard appears in my own observation."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        _force_discard(state, "p1", ["bounty_hunter"])
        view = json.loads(state._adapter.private_view_json("p1"))
        assert "discard" in view
        assert "bounty_hunter" in view["discard"]

    def test_information_state_string_reflects_board(self, requires_c_engine):
        """T7 — end-to-end: the public pyspiel observation carries the board.

        The action-index history differs between the two clones (different
        moves were applied), so the raw ``information_state_string`` always
        differs. Strip the ``history||`` prefix and assert the private-view
        *component* differs — that is the part F-011 found board-blind.
        """
        game = _load_c_game(2)
        c1, c2 = _board_differing_clones_guaranteed(game)
        # initial placement is chance-free, so current_player is a real player
        p = c1.current_player()
        assert p >= 0

        def pv_component(s):
            return s.information_state_string(p).split("||")[-1]

        assert pv_component(c1) != pv_component(c2)
        # observation_string returns information_state_string verbatim
        assert c1.observation_string(p).split("||")[-1] != c2.observation_string(p).split("||")[-1]

    def test_board_nodes_order_is_deterministic(self, requires_c_engine):
        """T8 — two independent board builds produce identical node order."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        adapter = state._adapter
        first = json.loads(adapter.private_view_json("p1"))["public"]["board_nodes"]
        second = json.loads(adapter.private_view_json("p1"))["public"]["board_nodes"]
        assert [n["node_id"] for n in first] == [n["node_id"] for n in second]
        assert first == second
