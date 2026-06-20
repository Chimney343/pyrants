"""Mindwitness card behavior test."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "test_card_generation" / "013_seed_4_mindwitness.json"
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


def _target_owner_from_label(label: str) -> str:
    """Extract owner id from a resolve_generic label like 'Remove p3 troop from ...'."""
    return label.split()[1]


def test_mindwitness_discards_owners_random_card() -> None:
    """Assassinating a player troop triggers random discard from that owner's hand."""
    session = CSession.load(str(SCENARIO_PATH))

    for mw in session.legal_moves():
        if getattr(mw, "move_type", "") == "play_card" and mw.data.get("card_id") == "mindwitness":
            session.submit_move(mw)
            break

    view = build_c_game_view(session)
    target_move = view.legal_moves[0]
    owner = _target_owner_from_label(target_move.label)
    owner_before = _player_state(session, owner)

    session.submit_move(target_move.move)

    owner_after = _player_state(session, owner)

    assert owner_before[0] == owner_after[0] + 1, (
        f"Expected {owner} hand to decrease by 1: {owner_before[0]} -> {owner_after[0]}"
    )
    assert owner_before[1] == owner_after[1] - 1, (
        f"Expected {owner} discard to increase by 1: {owner_before[1]} -> {owner_after[1]}"
    )

    # Verify card fully resolved (no pending_generic)
    assert not session._state._ptr.contents.pending_generic, "Card should be fully resolved"

    session.destroy()


def test_mindwitness_no_discard_when_hand_too_small() -> None:
    """Discard does not fire if the troop owner has fewer than 3 cards."""
    session = CSession.load(str(SCENARIO_PATH))

    for mw in session.legal_moves():
        if getattr(mw, "move_type", "") == "play_card" and mw.data.get("card_id") == "mindwitness":
            session.submit_move(mw)
            break

    view = build_c_game_view(session)
    target_move = view.legal_moves[0]
    owner = _target_owner_from_label(target_move.label)

    # Strip the targeted player's hand down to 2 cards so the discard condition fails
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == owner:
            s.players[i].hand_count = 2
            break

    owner_before = _player_state(session, owner)

    session.submit_move(target_move.move)

    owner_after = _player_state(session, owner)

    # owner hand should NOT have changed (condition not met)
    assert owner_before[0] == owner_after[0], f"{owner} hand should not change: {owner_before[0]} -> {owner_after[0]}"
    assert owner_before[1] == owner_after[1], f"{owner} discard should not change: {owner_before[1]} -> {owner_after[1]}"

    session.destroy()
