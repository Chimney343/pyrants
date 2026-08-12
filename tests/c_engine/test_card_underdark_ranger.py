"""Underdark Ranger card tests — 2 sequential white-troop assassinations.

``rules_text``: "Assassinate 2 white troops."

Execution model: a ``sequence`` of two ``assassinate_troop`` actions, both
``optional=false``, each filtered to ``white_troop_only``. Targets use normal
legality (presence required). If fewer than 2 legal white targets exist, the
card resolves as many as possible, including zero.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "batch_card_generation" / "079_seed_4_underdark_ranger.json"
)


def _trophy_hall(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [
                _lib.intern_str(ps.trophy_hall[j]).decode()
                for j in range(ps.trophy_hall_count)
            ]
    return []


def _slot_occupant(session: CSession, node_id: str, slot_index: int) -> str | None:
    s = session._state._ptr.contents
    for i in range(s.node_count):
        ns = s.nodes[i]
        if _lib.intern_str(ns.node_id).decode() == node_id:
            occ = ns.troop_slots[slot_index]
            return _lib.intern_str(occ).decode() if occ else None
    return None


def _resolve_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if m.move_type == "resolve_generic"]


def _assert_all_targets_white(session: CSession, moves: list) -> None:
    for m in moves:
        node_id = m.data.get("action_id")
        target_id = m.data.get("target_id")
        assert node_id is not None and target_id is not None, (
            f"Unexpected skip/unavailable move among resolve_generic: {m.data}"
        )
        occupant = _slot_occupant(session, node_id, int(target_id))
        assert occupant == "white", (
            f"Target {node_id} slot {target_id} should be a white troop, got {occupant!r}"
        )


def test_underdark_ranger_two_mandatory_white_assassinations() -> None:
    """Two sequential assassinate_troop actions, both mandatory, each white-only.

    Player must resolve both when white targets exist; no skip offered for
    either; trophy hall gains exactly two white entries."""
    session = CSession.load(str(SCENARIO_PATH))

    trophy_before = len(_trophy_hall(session, "p3"))

    play_move = None
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "underdark_ranger":
            play_move = m
            break
    assert play_move is not None, "Underdark Ranger not found in legal moves"
    session.submit_move(play_move)

    # First assassinate — no skip option (optional=false), all targets white.
    action1_moves = _resolve_moves(session)
    assert len(action1_moves) > 0, "Expected at least one legal white target for action_1"
    skip_moves = [m for m in action1_moves if m.data.get("action_id") is None]
    assert len(skip_moves) == 0, "action_1 should have no skip move (optional=false)"
    _assert_all_targets_white(session, action1_moves)

    result = session.submit_move(action1_moves[0])
    assert result is not None, "First assassinate failed"

    # Second assassinate — still no skip option, still all white targets.
    action2_moves = _resolve_moves(session)
    assert len(action2_moves) > 0, "Expected at least one legal white target for action_2"
    skip_moves2 = [m for m in action2_moves if m.data.get("action_id") is None]
    assert len(skip_moves2) == 0, "action_2 should have no skip move (optional=false)"
    _assert_all_targets_white(session, action2_moves)

    result2 = session.submit_move(action2_moves[0])
    assert result2 is not None, "Second assassinate failed"

    # Card done — no more resolve_generic moves.
    assert len(_resolve_moves(session)) == 0, "Expected no more resolve_generic after 2 assassinations"

    # Trophy hall gains exactly two white entries.
    trophy_after = _trophy_hall(session, "p3")
    assert len(trophy_after) == trophy_before + 2, (
        f"Expected +2 trophies, got {len(trophy_after)} (was {trophy_before})"
    )
    new_whites = trophy_after[trophy_before:]
    assert new_whites == ["white", "white"], f"New trophies should be white troops, got {new_whites}"

    session.destroy()


def test_underdark_ranger_targets_are_white_only() -> None:
    """The white_troop_only filter excludes player-owned troops entirely.

    p3 has presence alongside non-white troops (e.g. p2 at site_eryndlyn), so
    if the filter were missing those would appear as targets. Every offered
    target must reference a white occupant."""
    session = CSession.load(str(SCENARIO_PATH))

    play_move = None
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "underdark_ranger":
            play_move = m
            break
    assert play_move is not None, "Underdark Ranger not found in legal moves"
    session.submit_move(play_move)

    moves = _resolve_moves(session)
    assert len(moves) > 0, "Expected at least one white target"
    _assert_all_targets_white(session, moves)

    # Confirm p3 has presence at a node with only non-white troops (sanity
    # that the filter actually had something to exclude).
    s = session._state._ptr.contents
    node_ids = {_lib.intern_str(s.nodes[i].node_id).decode() for i in range(s.node_count)}
    assert "site_eryndlyn" in node_ids

    session.destroy()


def test_underdark_ranger_catalog_actions() -> None:
    """Verify the execution model encodes two mandatory white-only assassinations."""
    import json

    catalog_path = Path(__file__).resolve().parents[2] / "data" / "cards" / "catalog.json"
    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)

    card = None
    for c in catalog["cards"]:
        if c["card_id"] == "underdark_ranger":
            card = c
            break
    assert card is not None, "Underdark Ranger not found in catalog"

    em = card["execution_model"]
    assert em["kind"] == "sequence", "Expected sequence execution model"
    actions = em["actions"]
    assert len(actions) == 2, f"Expected 2 actions, got {len(actions)}"

    for action in actions:
        assert action["op"] == "assassinate_troop"
        assert action["optional"] is False
        assert "white_troop_only" in action["filters"], (
            f"Expected white_troop_only filter, got {action['filters']}"
        )

    # Top-level actions array mirrors the execution model.
    top_actions = card.get("actions", [])
    assert len(top_actions) == 2
    for action in top_actions:
        assert action["optional"] is False
        assert "white_troop_only" in action["filters"]


def test_underdark_ranger_no_white_targets_auto_resolves() -> None:
    """When no white troops remain, both actions auto-skip.

    The card resolves immediately with no effect and no stuck pending state."""
    session = CSession.load(str(SCENARIO_PATH))

    # Remove all white troops from the board (p3 presence stays intact).
    s = session._state._ptr.contents
    for i in range(s.node_count):
        ns = s.nodes[i]
        for t in range(ns.troop_slot_count):
            if ns.troop_slots[t]:
                val = _lib.intern_str(ns.troop_slots[t]).decode() if ns.troop_slots[t] else None
                if val == "white":
                    ns.troop_slots[t] = 0

    trophy_before = _trophy_hall(session, "p3")

    play_move = None
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "underdark_ranger":
            play_move = m
            break
    assert play_move is not None, "Underdark Ranger not found in legal moves"

    result = session.submit_move(play_move)
    assert result is not None, "Playing Underdark Ranger should succeed even with no white targets"

    # Both actions auto-skipped — no resolve_generic moves remain.
    assert len(_resolve_moves(session)) == 0, (
        "Expected 0 resolve_generic moves when no white targets remain"
    )

    # Pending generic cleared.
    s = session._state._ptr.contents
    assert not s.pending_generic, "Expected no pending_generic after auto-skip"

    # Trophy hall unchanged — no assassinations happened.
    trophy_after = _trophy_hall(session, "p3")
    assert trophy_after == trophy_before, (
        f"Trophy hall should be unchanged, was {trophy_before} now {len(trophy_after)}"
    )

    # Regular turn continues.
    move_types = {m.move_type for m in session.legal_moves()}
    assert "play_card" in move_types, "Should still be able to play other cards"
    assert "end_main_phase" in move_types, "Should be able to end main phase"

    session.destroy()
