"""Ambassador: End of turn promotes another played card. If discarded from hand, promotes to inner circle instead.

The discard-replacement mechanic: when Ambassador would move from hand to
discard pile (cleanup, force_discard, ability cost), it goes to inner_circle
instead. This is a passive replacement effect.
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.engine_bindings import PHASE_END_OF_TURN, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session, _sptr

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _submit_move_of_type(session: CSession, move_type: str):
    for m in session.legal_moves():
        if m._move_type == move_type:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"No move of type {move_type}")


def _player_hand(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].hand[j]).decode()
                    for j in range(s.players[i].hand_count)]
    return []


def _player_discard(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].discard_pile[j]).decode()
                    for j in range(s.players[i].discard_pile_count)]
    return []


def _player_inner_circle(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].inner_circle[j]).decode()
                    for j in range(s.players[i].inner_circle_count)]
    return []


def _make_engine():
    from engine_c.bindings.ce_api import CEngine
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return eng


def test_ambassador_in_hand_promotes_to_inner_circle_on_cleanup():
    """Ambassador unplayed in hand during cleanup goes to inner_circle, not discard."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["noble", "ambassador"]},
        current_player="p1",
    )

    hand_before = _player_hand(session, "p1")
    assert "ambassador" in hand_before

    _play_card(session, "noble")

    _submit_move_of_type(session, "end_main_phase")
    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}
    assert "promote_card" not in move_types, f"Nothing to promote (Ambassador wasn't played)"

    _submit_move_of_type(session, "resolve_end_of_turn")
    _submit_move_of_type(session, "resolve_cleanup")

    discard = _player_discard(session, "p1")
    inner = _player_inner_circle(session, "p1")

    assert "ambassador" not in discard, (
        f"Ambassador should NOT be in discard pile. Got: {discard}"
    )
    assert "ambassador" in inner, (
        f"Ambassador should be in inner_circle (discard redirect). Got: {inner}"
    )

    session.destroy()


def test_ambassador_eot_promote_another_card():
    """Play Ambassador and another card — Ambassador promotes the other at EOT."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["noble", "ambassador"]},
        current_player="p1",
    )

    _play_card(session, "noble")
    _play_card(session, "ambassador")

    _submit_move_of_type(session, "end_main_phase")
    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}
    assert "promote_card" in move_types, f"Should have promote_card at EOT, got: {move_types}"

    promote_moves = [m for m in moves if m._move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert "noble" in promote_targets, f"Noble should be a promote target, got: {promote_targets}"
    assert "ambassador" not in promote_targets, (
        f"Ambassador promotes another card, not itself. Got: {promote_targets}"
    )

    noble_move = [m for m in promote_moves if m.data.get("card_id") == "noble"][0]
    session.submit_move(noble_move)

    assert "noble" in _player_inner_circle(session, "p1"), "Noble should be in inner_circle"

    _submit_move_of_type(session, "resolve_end_of_turn")
    _submit_move_of_type(session, "resolve_cleanup")

    inner = _player_inner_circle(session, "p1")
    assert "noble" in inner, "Noble should remain in inner_circle after cleanup"

    session.destroy()
