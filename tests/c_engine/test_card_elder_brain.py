"""Elder Brain card behavior tests."""

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
    / "data" / "scenarios" / "batch_card_generation" / "009_seed_4_elder_brain.json"
)

SCENARIO_PATH_127 = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "random_card_generation" / "elder_brain_seed_127.json"
)


def _inner_circle_ids(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [
                _lib.intern_str(ps.inner_circle[j]).decode()
                for j in range(ps.inner_circle_count)
            ]
    return []


def test_elder_brain_promotes_top_deck() -> None:
    """Elder Brain promotes the top card of deck to inner circle."""
    session = CSession.load(str(SCENARIO_PATH))
    ic_before = _inner_circle_ids(session, "p2")

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "elder_brain":
            session.submit_move(m)
            break
    else:
        session.destroy()
        pytest.fail("Elder Brain not in hand")

    # Promote is auto-resolved; inner circle should grow by 1
    ic_after = _inner_circle_ids(session, "p2")
    assert len(ic_after) == len(ic_before) + 1, (
        f"Inner circle should grow by 1: {len(ic_before)} -> {len(ic_after)}"
    )
    assert ic_after[0] == "noble", (
        f"Top deck card should be noble, got {ic_after[0]}"
    )

    session.destroy()


def test_elder_brain_inner_circle_card_is_playable() -> None:
    """After promotion, inner circle cards appear as selectable targets for nested play."""
    session = CSession.load(str(SCENARIO_PATH))

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "elder_brain":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    play_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert play_moves, "No inner circle card selection moves generated"

    action_ids = {m.move.data["action_id"] for m in play_moves}
    assert "noble" in action_ids, (
        f"noble should be selectable from inner circle, got targets: {action_ids}"
    )

    noble_move = next(m for m in play_moves if m.move.data["action_id"] == "noble")
    session.submit_move(noble_move.move)

    ic_after = _inner_circle_ids(session, "p2")
    assert "noble" in ic_after, (
        "noble must remain in inner circle after nested play"
    )

    s = session._state._ptr.contents
    assert not s.pending_generic, (
        "Elder Brain should fully resolve after nested card is played"
    )

    session.destroy()


def test_elder_brain_nested_modal_card_closes_cleanly() -> None:
    """Playing a modal card (Ettin) via Elder Brain must not lock the game.

    Regression for the closing-confirm dead-end: after a nested card with a
    real execution model resolves, Elder Brain is left pending with its
    action list exhausted and offers exactly one closing confirm move
    ("Finish resolving Elder Brain"). Applying that move must end the card,
    not destroy the state.
    """
    session = CSession.load(str(SCENARIO_PATH_127))

    def resolve_moves():
        return [m for m in session.legal_moves() if m.move_type == "resolve_generic"]

    play = next(
        (
            m
            for m in session.legal_moves()
            if m.move_type == "play_card" and m.data.get("card_id") == "elder_brain"
        ),
        None,
    )
    assert play is not None, "Elder Brain should be playable from the scenario"
    session.submit_move(play)

    ettin = next((m for m in resolve_moves() if m.data.get("action_id") == "ettin"), None)
    assert ettin is not None, "Ettin should be selectable from the inner circle"
    session.submit_move(ettin)

    option = next(
        (m for m in resolve_moves() if m.data.get("action_id") in ("option_1", "option_2")),
        None,
    )
    assert option is not None, (
        f"Ettin should offer a modal choice, got {[m.data for m in resolve_moves()]}"
    )
    session.submit_move(option)

    # Resolve as many site picks (deploys/assassinates) as are offered.
    for _ in range(8):
        pick = next(
            (
                m
                for m in resolve_moves()
                if m.data.get("action_id") and m.data["action_id"] not in ("option_1", "option_2")
            ),
            None,
        )
        if pick is None:
            break
        session.submit_move(pick)

    # Nested resolution done: Elder Brain offers exactly the closing confirm.
    confirm = resolve_moves()
    assert len(confirm) == 1 and confirm[0].data.get("action_id") is None, (
        f"Expected exactly one closing confirm move, got {[m.data for m in confirm]}"
    )

    s = session._state._ptr.contents
    assert s.pending_generic, "Elder Brain should still be pending before the closing confirm"
    src = _lib.intern_str(s.pending_generic.contents.source_card_id).decode()
    assert src == "elder_brain", f"Expected elder_brain pending, got {src}"

    # The GUI labels the closing confirm with the card name.
    view = build_c_game_view(session)
    confirm_view = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert len(confirm_view) == 1
    assert confirm_view[0].label == "Finish resolving Elder Brain", (
        f"Closing confirm label mismatch: {confirm_view[0].label!r}"
    )

    result = session.submit_move(confirm[0])
    assert result is not None, (
        "Closing confirm must be accepted (regression: state was destroyed here)"
    )

    result_state = result._ptr.contents
    assert not result_state.pending_generic, (
        "Elder Brain should fully resolve after the closing confirm"
    )

    # Ettin stays in the inner circle per elder_brain's rules_text.
    assert "ettin" in _inner_circle_ids(session, "p3"), (
        "Ettin must remain in inner circle after nested play"
    )

    session.destroy()
