"""Mindwitness card behavior test."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view

SCENARIO_PATH = (
    Path(__file__).resolve().parents[1]
    / "data" / "scenarios" / "batch_card_generation" / "013_seed_4_mindwitness.json"
)


def _player_state(session: CSession, player_id: str):
    """Return (hand_count, discard_count, trophy_count) for a player."""
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return (ps.hand_count, ps.discard_pile_count, ps.trophy_hall_count)
    return None


def test_mindwitness_assassinate_labels() -> None:
    """After playing Mindwitness, assassinate targets show owner and site name."""
    session = CSession.load(str(SCENARIO_PATH))

    for mw in session.legal_moves():
        if getattr(mw, "move_type", "") == "play_card" and mw.data.get("card_id") == "mindwitness":
            session.submit_move(mw)
            break
    else:
        pytest.fail("Mindwitness not in hand")

    view = build_c_game_view(session)
    labels = [v.label for v in view.legal_moves]
    assert labels, "No legal assassinate targets"
    for label in labels:
        assert "Remove " in label, f"Label missing 'Remove': {label}"
        assert " troop from " in label, f"Label missing 'troop from': {label}"

    session.destroy()


def test_mindwitness_discards_owners_random_card() -> None:
    """Assassinating a player troop triggers random discard from that owner's hand."""
    session = CSession.load(str(SCENARIO_PATH))

    for mw in session.legal_moves():
        if getattr(mw, "move_type", "") == "play_card" and mw.data.get("card_id") == "mindwitness":
            session.submit_move(mw)
            break

    view = build_c_game_view(session)
    p1_before = _player_state(session, "p1")

    # Pick first legal assassinate target (targets p1 troop)
    target_move = view.legal_moves[0]
    session.submit_move(target_move.move)

    p1_after = _player_state(session, "p1")

    # p1 should have lost 1 card from hand and gained 1 in discard
    assert p1_before[0] == p1_after[0] + 1, (
        f"Expected p1 hand to decrease by 1: {p1_before[0]} -> {p1_after[0]}"
    )
    assert p1_before[1] == p1_after[1] - 1, (
        f"Expected p1 discard to increase by 1: {p1_before[1]} -> {p1_after[1]}"
    )

    # Verify card fully resolved (no pending_generic)
    assert not session._state._ptr.contents.pending_generic, "Card should be fully resolved"

    session.destroy()


def test_mindwitness_no_discard_when_hand_too_small() -> None:
    """Discard does not fire if the troop owner has fewer than 3 cards."""
    session = CSession.load(str(SCENARIO_PATH))

    # Strip p1's hand down to 2 cards so the discard condition fails
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == "p1":
            s.players[i].hand_count = 2
            break

    for mw in session.legal_moves():
        if getattr(mw, "move_type", "") == "play_card" and mw.data.get("card_id") == "mindwitness":
            session.submit_move(mw)
            break

    view = build_c_game_view(session)
    p1_before = _player_state(session, "p1")

    target_move = view.legal_moves[0]
    session.submit_move(target_move.move)

    p1_after = _player_state(session, "p1")

    # p1 hand should NOT have changed (condition not met)
    assert p1_before[0] == p1_after[0], f"p1 hand should not change: {p1_before[0]} -> {p1_after[0]}"
    assert p1_before[1] == p1_after[1], f"p1 discard should not change: {p1_before[1]} -> {p1_after[1]}"

    session.destroy()
