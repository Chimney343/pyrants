"""Unit tests for the per-step state-snapshot helpers in scripts/_state_snapshot.py.

Phase 2 of the IS-MCTS observability work: attach a Tier-1 (per-player
public summary) snapshot to every ``steps.jsonl`` ``"step"`` line and a
Tier-2 (board) snapshot to round-boundary and board-mutating steps.

These helpers are deliberately pure — no ``pyspiel`` / engine imports — so
they can be tested with plain test doubles.  The ``NodeOccupancyView``-shaped
doubles here use ``SimpleNamespace`` with ``troop_slots`` / ``spies``
attributes; ``_tier1_snapshot`` takes a real ``CEngineAdapter`` (covered by
the ``requires_c_engine`` tests in this file).

Total-Control interpretation locked in from ``docs/tyrants-rulebook.md``
("Total Control": "all the site's troop spaces are filled only with your
troops and no enemy spies are present") and the C engine's
``is_total_control`` (``engine_c/scoring.c``): an **empty** troop slot
disqualifies total control (the slot is not *filled* with your troops).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts._state_snapshot import (
    _derive_site_controller,
    _derive_total_control,
    _is_board_mutating,
    _tier1_snapshot,
    _tier2_snapshot,
)


def _node(troop_slots, spies=()):
    return SimpleNamespace(troop_slots=tuple(troop_slots), spies=tuple(spies))


@pytest.mark.parametrize(
    ("troop_slots", "spies", "expected_controller", "expected_total_control"),
    [
        (("p1", "p1"), (), "p1", True),
        (("p1", "p2"), (), None, False),
        (("p1", "p1", "p2"), (), "p1", False),
        (("p1", "p1"), ("p2",), "p1", False),
        (("p1", None), (), "p1", False),
        ((), (), None, False),
        (("p1", "p2", "p2"), (), "p2", False),
        (("p1", "p1"), ("p1",), "p1", True),
        (("p1", "p1"), ("p1", "p2"), "p1", False),
    ],
    ids=[
        "two-p1-no-spies-total-control",
        "tied-no-controller",
        "plurality-not-all-slots",
        "enemy-spy-breaks-total-control",
        "empty-slot-breaks-total-control",
        "empty-site-no-controller",
        "p2-plurality",
        "own-spy-does-not-break-total-control",
        "own-and-enemy-spy-still-breaks-total-control",
    ],
)
def test_derive_site_controller_and_total_control(
    troop_slots, spies, expected_controller, expected_total_control
):
    node = _node(troop_slots, spies)
    controller = _derive_site_controller(node)
    assert controller == expected_controller
    assert _derive_total_control(node, controller) == expected_total_control


# ---------------------------------------------------------------------------
# Tier 1 — cheap per-player snapshot
# ---------------------------------------------------------------------------


def _make_adapter():
    """Build a real (not mocked) CEngineAdapter on a fresh minimal session."""
    from engine_c.bindings.c_adapter import CEngineAdapter
    from engine_c.bindings.ce_api import CEngine
    from engine_c.bindings.session import CSession

    eng = CEngine()
    eng.initialize()
    session = CSession(eng, ["p1", "p2"], seed=0)
    adapter = CEngineAdapter(
        session._state,
        eng,
        ["p1", "p2"],
        shuffle_seed=0,
    )
    return adapter


class TestTier1Snapshot:
    def test_tier1_snapshot_has_exactly_the_documented_fields(self, requires_c_engine):
        adapter = _make_adapter()
        snap = _tier1_snapshot(adapter)

        for key in ("resource_power", "resource_influence", "market_row", "public_player_summaries"):
            assert key in snap, f"missing top-level key {key}"

        players = snap["public_player_summaries"]
        assert set(players.keys()) == {"p1", "p2"}
        for pid, summary in players.items():
            for field in (
                "hand_size",
                "deck_size",
                "discard_size",
                "played_size",
                "inner_circle_size",
                "trophy_hall_size",
                "barracks",
                "spies_available",
                "vp_tokens",
                "score",
            ):
                assert field in summary, f"missing per-player field {field} for {pid}"
                assert isinstance(summary[field], int), (
                    f"{pid}.{field} must be an int, got {type(summary[field])}"
                )


# ---------------------------------------------------------------------------
# Tier 2 — board snapshot
# ---------------------------------------------------------------------------


class TestTier2Snapshot:
    def test_tier2_snapshot_maps_board_nodes_through_controller_helpers(
        self, requires_c_engine
    ):
        adapter = _make_adapter()
        snap = _tier2_snapshot(adapter)

        assert "board_nodes" in snap
        assert len(snap["board_nodes"]) > 0

        for node in snap["board_nodes"]:
            for key in (
                "node_id",
                "controller",
                "total_control",
                "troop_slots",
                "spies",
                "control_vp",
                "total_control_vp_per_turn",
                "vp_tokens",
            ):
                assert key in node, f"missing node key {key}"
            assert isinstance(node["total_control"], bool)
            assert isinstance(node["troop_slots"], list)
            assert isinstance(node["spies"], list)

        for key in (
            "current_player_controlled_sites",
            "current_player_total_control_sites",
            "current_player_control_vp",
            "current_player_total_control_vp",
        ):
            assert key in snap, f"missing board-level key {key}"
            assert isinstance(snap[key], int)

        # Cross-check: derive from the raw view and confirm the snapshot's
        # controller matches the pure helper on the same view data.
        from engine_c.bindings.view import build_c_game_view

        view = build_c_game_view(adapter)
        for node, view_node in zip(snap["board_nodes"], view.board_nodes, strict=True):
            expected_controller = _derive_site_controller(view_node)
            assert node["controller"] == expected_controller


# ---------------------------------------------------------------------------
# CEngineAdapter.pending_generic_op — must reflect the pending action's verb,
# not the resolve_generic move's own action_id (which holds the selected
# target, e.g. a site id — see docs/ismcts-generic-resolution-bugs.md and
# tests/c_engine/test_card_wraith.py's `spy_move.data.get("action_id")`
# usage, which is a site id, not "place_spy").
# ---------------------------------------------------------------------------


class TestPendingGenericOp:
    def test_pending_generic_op_reflects_the_active_action_verb(self, requires_c_engine):
        from engine_c.bindings.c_adapter import CEngineAdapter

        from tests.c_engine.card_test_helpers import _make_engine, make_card_test_session

        eng = _make_engine()
        session = make_card_test_session(
            eng,
            ["p1", "p2"],
            hand={"p1": ["mercenary_squad"]},  # single-action card: deploy_troops
            current_player="p1",
        )
        adapter = CEngineAdapter(session._state, eng, ["p1", "p2"], shuffle_seed=0)

        assert adapter.pending_generic_op() is None, (
            "no pending generic choice before the card is played"
        )

        play_move = next(
            m
            for m in adapter.legal_moves()
            if m.move_type == "play_card" and m.data.get("card_id") == "mercenary_squad"
        )
        adapter.apply(play_move)

        op = adapter.pending_generic_op()
        assert op == "deploy_troops", (
            f"expected the pending action's op, got {op!r} "
            f"(this is broken if it instead returns a resolve_generic move's "
            f"action_id, which would be a site id or similar target, never "
            f"the verb)"
        )
        assert _is_board_mutating("resolve_generic_choice", op) is True


# ---------------------------------------------------------------------------
# _is_board_mutating — vocabulary checks
# ---------------------------------------------------------------------------


class TestIsBoardMutating:
    """``pending_op`` is the pending generic action's *op* (e.g. from
    ``CEngineAdapter.pending_generic_op()``) — NOT the ``resolve_generic``
    move's own ``action_id`` field, which holds the selected target (a
    site/route/troop/player id), never the action verb. See
    ``_state_snapshot.py``'s module docstring and
    ``CEngineAdapter.pending_generic_op()`` for why these are different
    fields.
    """

    def test_base_board_mutating_move_types(self):
        for move_type in ("assassinate", "deploy", "return_spy"):
            assert _is_board_mutating(move_type, None) is True, move_type

    def test_non_board_mutating_move_types(self):
        for move_type in ("play_card", "recruit", "end_main_phase", "promote_card"):
            assert _is_board_mutating(move_type, None) is False, move_type

    def test_resolve_generic_choice_board_mutating_ops(self):
        for op in (
            "deploy_troops",
            "assassinate_troop",
            "supplant_troop",
            "place_spy",
            "move_troop",
            "return_unit",
        ):
            assert _is_board_mutating("resolve_generic_choice", op) is True, op

    def test_resolve_generic_choice_non_board_mutating_ops(self):
        for op in ("recruit_card", "devour_cost", "force_discard"):
            assert _is_board_mutating("resolve_generic_choice", op) is False, op

    def test_resolve_generic_choice_missing_pending_op(self):
        assert _is_board_mutating("resolve_generic_choice", None) is False
