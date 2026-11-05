"""The legal/display move split and the deferred-promotion end-main rule."""

from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from tests.c_engine.card_test_helpers import _make_engine, _sptr, make_card_test_session


def _blackguard_session():
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p2": ["blackguard", "noble"]},
        current_player="p2",
    )
    _sptr(session).contents.phase = PHASE_MAIN
    for move in session.legal_moves():
        if move.move_type == "play_card" and move.data.get("card_id") == "blackguard":
            session.submit_move(move)
            break
    return session


def _payloads(moves) -> list[dict]:
    return [move.to_payload() for move in moves]


def test_legal_moves_exclude_display_placeholders():
    session = _blackguard_session()
    legal = session.legal_moves()
    assert all(move.data.get("target_id") != "unavailable" for move in legal)
    assert not any(
        move.move_type == "resolve_generic" and move.data.get("action_id") == "option_2"
        for move in legal
    )
    session.destroy()


def test_display_moves_flag_placeholders_and_match_legal_order():
    session = _blackguard_session()
    display = session.display_moves()
    option_2 = [
        (move, applicable)
        for move, applicable in display
        if move.move_type == "resolve_generic"
        and move.data.get("action_id") == "option_2"
    ]
    assert len(option_2) == 1
    placeholder, applicable = option_2[0]
    assert placeholder.data.get("target_id") == "unavailable"
    assert applicable is False

    applicable_moves = [move for move, ok in display if ok]
    assert _payloads(applicable_moves) == _payloads(session.legal_moves())
    session.destroy()


def _deferred_promotion_session(*, played_other: bool):
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"], hand={"p1": ["noble"]}, current_player="p1"
    )
    state = _sptr(session).contents
    state.phase = PHASE_MAIN

    source = _lib.intern(b"source_card")
    state.pending_eot_count = 1
    pending = state.pending_eot[0]
    pending.requires_another_played_card = True
    pending.deferred_choice = True
    pending.repeat_while_targets = False
    pending.source_card_id = source

    p1 = _lib.intern(b"p1")
    for i in range(state.player_count):
        if state.players[i].player_id == p1:
            player = state.players[i]
            player.played_cards_count = 2 if played_other else 1
            player.played_cards[0] = source
            if played_other:
                player.played_cards[1] = _lib.intern(b"other_card")
            break
    return session


def test_end_main_display_flag_follows_deferred_promotion_rule():
    # End-main stays engine-legal (the player may end main and then skip the
    # promotion); the display flag is the UI's deferred-promotion warning.
    blocked = _deferred_promotion_session(played_other=False)
    display = blocked.display_moves()
    end_main = [(move, ok) for move, ok in display if move.move_type == "end_main_phase"]
    assert len(end_main) == 1
    assert end_main[0][1] is False
    assert any(move.move_type == "end_main_phase" for move in blocked.legal_moves())
    blocked.destroy()

    allowed = _deferred_promotion_session(played_other=True)
    display = allowed.display_moves()
    end_main = [(move, ok) for move, ok in display if move.move_type == "end_main_phase"]
    assert len(end_main) == 1
    assert end_main[0][1] is True
    assert any(move.move_type == "end_main_phase" for move in allowed.legal_moves())
    allowed.destroy()
