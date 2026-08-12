"""Necromancer card behavior tests.

Modal choice: choose exactly one mode.
- Option 1: Gain 3 influence (immediate).
- Option 2: Perform exactly one promote action on exactly one card
  chosen from: this card (played), a card from hand, or a card from discard.
"""

from __future__ import annotations

from tests.c_engine.card_test_helpers import (
    _make_engine,
    _sptr,
    make_card_test_session,
)

_P1 = "p1"
_P2 = "p2"
_CARD = "necromancer"


def _influence(session):
    return _sptr(session).contents.resource_pool.influence


def _hand_ids(session, pid: str) -> list[str]:
    from engine_c.bindings.engine_bindings import _lib
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].hand[j]).decode()
                    for j in range(s.players[i].hand_count)]
    return []


def _played_ids(session, pid: str) -> list[str]:
    from engine_c.bindings.engine_bindings import _lib
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].played_cards[j]).decode()
                    for j in range(s.players[i].played_cards_count)]
    return []


def _discard_ids(session, pid: str) -> list[str]:
    from engine_c.bindings.engine_bindings import _lib
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].discard_pile[j]).decode()
                    for j in range(s.players[i].discard_pile_count)]
    return []


def _inner_circle_ids(session, pid: str) -> list[str]:
    from engine_c.bindings.engine_bindings import _lib
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].inner_circle[j]).decode()
                    for j in range(s.players[i].inner_circle_count)]
    return []


def _has_pending_generic(session):
    return bool(_sptr(session).contents.pending_generic)


def _build_session(**kwargs):
    discard = kwargs.pop("discard", None)
    defaults = {
        "player_ids": [_P1, _P2],
        "hand": {_P1: [_CARD, "noble"]},
        "current_player": _P1,
    }
    defaults.update(kwargs)
    eng = _make_engine()
    session = make_card_test_session(eng, defaults.pop("player_ids"), **defaults)
    if discard:
        _set_discard(session, discard)
    return session


def _set_discard(session, discard_map: dict[str, list[str]]):
    from engine_c.bindings.engine_bindings import MAX_ZONE_SIZE, _lib
    s = _sptr(session).contents
    for pid, cards in discard_map.items():
        for i in range(s.player_count):
            if _lib.intern_str(s.players[i].player_id).decode() == pid:
                ps = s.players[i]
                ps.discard_pile_count = min(len(cards), MAX_ZONE_SIZE)
                for j, cid in enumerate(cards[:MAX_ZONE_SIZE]):
                    ps.discard_pile[j] = _lib.intern(cid.encode())
                break


def _play_card(session, card_id=_CARD):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


def _resolve_option(session, option_id: str):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == option_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{option_id} not found in resolve_generic moves")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_both_options_offered_as_modal_choice():
    session = _build_session()
    _play_card(session)

    assert _has_pending_generic(session), "Modal choice should be pending after play"

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    action_ids = {m.data.get("action_id") for m in gen_moves}
    assert "option_1" in action_ids, f"option_1 should be offered, got: {action_ids}"
    assert "option_2" in action_ids, f"option_2 should be offered, got: {action_ids}"

    session.destroy()


def test_option_1_gains_3_influence():
    session = _build_session()
    influence_before = _influence(session)

    _play_card(session)
    _resolve_option(session, "option_1")

    assert _influence(session) == influence_before + 3, (
        f"Should gain 3 influence. Before: {influence_before}, After: {_influence(session)}"
    )
    assert not _has_pending_generic(session), "No pending generic after immediate action"

    session.destroy()


def test_option_2_offers_promote_from_played_hand_discard():
    session = _build_session(
        hand={_P1: [_CARD, "noble"]},
        discard={"p1": ["soldier"]},
    )
    _play_card(session)
    _resolve_option(session, "option_2")

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    target_ids = {m.data.get("target_id") for m in gen_moves}

    assert "played" in target_ids, f"played zone should be a promotion source, got: {target_ids}"
    assert "hand" in target_ids, f"hand zone should be a promotion source, got: {target_ids}"
    assert "discard" in target_ids, f"discard zone should be a promotion source, got: {target_ids}"

    played_moves = [m for m in gen_moves if m.data.get("target_id") == "played"]
    assert len(played_moves) == 1, f"Exactly one played target (self), got: {len(played_moves)}"
    assert played_moves[0].data.get("action_id") == _CARD

    hand_indices = {m.data.get("action_id") for m in gen_moves if m.data.get("target_id") == "hand"}
    assert len(hand_indices) == 1, f"One card in hand (noble), got hand indices: {hand_indices}"

    discard_indices = {m.data.get("action_id") for m in gen_moves
                       if m.data.get("target_id") == "discard"}
    assert len(discard_indices) == 1, f"One card in discard (soldier), got discard indices: {discard_indices}"

    session.destroy()


def test_option_2_self_promote_from_played():
    session = _build_session(hand={_P1: [_CARD]})

    _play_card(session)
    _resolve_option(session, "option_2")

    played_moves = [m for m in session.legal_moves()
                    if m.move_type == "resolve_generic" and m.data.get("target_id") == "played"]
    assert len(played_moves) == 1, f"Self should be available in played: {played_moves}"
    assert played_moves[0].data.get("action_id") == _CARD

    session.submit_move(played_moves[0])

    ic = _inner_circle_ids(session, _P1)
    played = _played_ids(session, _P1)
    assert _CARD in ic, f"Self-promote: necromancer should be in inner_circle, got: {ic}"
    assert _CARD not in played, f"Self-promote: necromancer should be removed from played, got: {played}"
    assert not _has_pending_generic(session), "No pending after self-promote"

    session.destroy()


def test_option_2_promote_from_hand():
    session = _build_session(hand={_P1: [_CARD, "noble"]})
    hand_before = _hand_ids(session, _P1)
    assert "noble" in hand_before

    _play_card(session)
    _resolve_option(session, "option_2")

    hand_moves = [m for m in session.legal_moves()
                  if m.move_type == "resolve_generic" and m.data.get("target_id") == "hand"]
    assert len(hand_moves) >= 1, f"Cards in hand should be selectable, got: {hand_moves}"

    noble_move = None
    for m in hand_moves:
        idx = int(m.data.get("action_id", "-1"))
        if idx < len(hand_before) and hand_before[idx] == "noble":
            noble_move = m
            break
    if noble_move is None:
        hand_after_play = _hand_ids(session, _P1)
        noble_move = next(
            (m for m in hand_moves
             if int(m.data.get("action_id", "-1")) < len(hand_after_play)
             and hand_after_play[int(m.data.get("action_id", "0"))] == "noble"),
            None,
        )
    assert noble_move is not None, f"noble should be selectable from hand via: {hand_moves}"
    session.submit_move(noble_move)

    ic = _inner_circle_ids(session, _P1)
    hand_after = _hand_ids(session, _P1)
    assert "noble" in ic, f"noble should be in inner_circle, got: {ic}"
    assert "noble" not in hand_after, f"noble should be removed from hand, got: {hand_after}"
    assert not _has_pending_generic(session)

    session.destroy()


def test_option_2_promote_from_discard():
    session = _build_session(
        hand={_P1: [_CARD]},
        discard={"p1": ["soldier"]},
    )
    discard_before = _discard_ids(session, _P1)
    assert "soldier" in discard_before

    _play_card(session)
    _resolve_option(session, "option_2")

    discard_moves = [m for m in session.legal_moves()
                     if m.move_type == "resolve_generic" and m.data.get("target_id") == "discard"]
    assert len(discard_moves) >= 1, f"Cards in discard should be selectable, got: {discard_moves}"

    soldier_move = None
    for m in discard_moves:
        idx = int(m.data.get("action_id", "-1"))
        if idx < len(discard_before) and discard_before[idx] == "soldier":
            soldier_move = m
            break
    assert soldier_move is not None, f"soldier should be selectable from discard via: {discard_moves}"
    session.submit_move(soldier_move)

    ic = _inner_circle_ids(session, _P1)
    discard_after = _discard_ids(session, _P1)
    assert "soldier" in ic, f"soldier should be promoted to inner_circle, got: {ic}"
    assert "soldier" not in discard_after, f"soldier should be removed from discard, got: {discard_after}"
    assert not _has_pending_generic(session)

    session.destroy()
