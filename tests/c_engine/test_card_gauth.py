"""Gauth card behavior tests via the C engine bindings.

Execution model: modal_choice (exactly_one)
  - Option 1 (option_1): gain 2 influence
  - Option 2 (option_2): draw a card, then choose an opponent with 3+ cards
    in hand to discard one random card

Verifies:
  - Modal choice is pending after play with two options
  - Option 1 grants 2 influence
  - Option 2 draws 1 card, then shows opponent targets with 3+ cards
  - Option 2 discard picks a random card from the targeted opponent
  - Option 2 skips discard when no opponent has 3+ cards
  - Card fully resolves after each option
"""

from __future__ import annotations

import json
from pathlib import Path

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

CARD_ID = "gauth"
_P1 = "p1"
_P2 = "p2"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _hand_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].hand_count


def _influence(session: CSession) -> int:
    return _sptr(session).contents.resource_pool.influence


def _resolve_generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if m.move_type == "resolve_generic"]


def _play_card(session: CSession, card_id: str = CARD_ID) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


def _pick_option(session: CSession, option_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == option_id:
            session.submit_move(m)
            return
    available = [m.data for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.destroy()
    raise AssertionError(f"{option_id} not found; available: {available}")


def _pick_target_player(session: CSession, pid: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == pid:
            session.submit_move(m)
            return
    available = [m.data for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.destroy()
    raise AssertionError(f"target player {pid} not found; available: {available}")


def _set_opponent_hand(session: CSession, pid: str, card: str, count: int) -> None:
    s = _sptr(session).contents
    pi = _session_player_index(session, pid)
    if pi < 0:
        return
    s.players[pi].hand_count = min(count, 40)
    for j in range(min(count, 40)):
        s.players[pi].hand[j] = _lib.intern(card.encode())


def _set_deck(session: CSession, pid: str, card: str, count: int) -> None:
    s = _sptr(session).contents
    pi = _session_player_index(session, pid)
    if pi < 0:
        return
    s.players[pi].deck_count = min(count, 40)
    for j in range(min(count, 40)):
        s.players[pi].deck[j] = _lib.intern(card.encode())


def _build_session(**kwargs) -> CSession:
    defaults = {
        "player_ids": [_P1, _P2],
        "hand": {_P1: [CARD_ID]},
        "current_player": _P1,
    }
    defaults.update(kwargs)
    eng = _make_engine()
    session = make_card_test_session(eng, defaults.pop("player_ids"), **defaults)
    return session


# ---------------------------------------------------------------------------
# Execution model validation
# ---------------------------------------------------------------------------


def test_gauth_execution_model() -> None:
    catalog = json.loads((DATA_DIR / "cards" / "catalog.json").read_text(encoding="utf-8"))
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    card = next(c for c in cards if c.get("card_id") == CARD_ID)

    assert card["cost"] == 3
    assert card["aspect"] == "malice"
    assert "aberration" in card["secondary_aspects"]
    assert card["deck_vp"] == 2
    assert card["inner_circle_vp"] == 3

    em = card["execution_model"]
    assert em["kind"] == "modal_choice"
    assert em["selection"] == "exactly_one"
    assert len(em["options"]) == 2

    opt1 = em["options"][0]
    assert opt1["option_id"] == "option_1"
    assert len(opt1["actions"]) == 1
    assert opt1["actions"][0]["op"] == "gain_resource"
    assert opt1["actions"][0]["metadata"]["resource"] == "influence"
    assert opt1["actions"][0]["quantity"] == {"kind": "fixed", "value": 2}

    opt2 = em["options"][1]
    assert opt2["option_id"] == "option_2"
    assert len(opt2["actions"]) == 2
    assert opt2["actions"][0]["op"] == "draw_cards"
    assert opt2["actions"][0]["target_scope"] == "self"

    discard = opt2["actions"][1]
    assert discard["op"] == "force_discard"
    assert discard["target_scope"] == "opponent"
    assert discard["source_fragment"] == "targeted_discard"
    assert discard["filters"] == []

    assert "Choose one mode" in card["rules_text"]
    assert "discard a card" in card["rules_text"]
    assert "3 or more" in card["rules_text"]


# ---------------------------------------------------------------------------
# Modal choice behaviour
# ---------------------------------------------------------------------------


def test_gauth_modal_choice_pending_after_play() -> None:
    session = _build_session()

    _play_card(session)
    assert _has_pending_generic(session), "Modal choice should be pending after play"

    moves = _resolve_generic_moves(session)
    option_ids = {m.data["action_id"] for m in moves}
    assert option_ids == {"option_1", "option_2"}, f"Expected both options; got {option_ids}"

    session.destroy()


# ---------------------------------------------------------------------------
# Option 1: gain 2 influence
# ---------------------------------------------------------------------------


def test_gauth_option_1_grants_two_influence() -> None:
    session = _build_session()
    s = _sptr(session).contents
    s.resource_pool.influence = 0

    _play_card(session)
    _pick_option(session, "option_1")

    assert not _has_pending_generic(session), "Should resolve after option_1"
    assert _influence(session) == 2, f"Expected 2 influence; got {_influence(session)}"

    session.destroy()


# ---------------------------------------------------------------------------
# Option 2: draw + targeted discard
# ---------------------------------------------------------------------------


def test_gauth_option_2_draws_card_and_targets_opponent() -> None:
    session = _build_session()
    _set_deck(session, _P1, "noble", 5)
    _set_opponent_hand(session, _P2, "soldier", 4)

    hand_before = _hand_count(session, _P2)

    _play_card(session)
    _pick_option(session, "option_2")

    assert _has_pending_generic(session), "Should be pending for discard after draw"

    target_moves = _resolve_generic_moves(session)
    target_pids = [m.data.get("action_id") for m in target_moves]
    assert _P2 in target_pids, f"P2 (4 cards) should be targetable; got {target_pids}"

    _pick_target_player(session, _P2)

    assert not _has_pending_generic(session), "Should resolve after discard"
    assert _hand_count(session, _P2) == hand_before - 1, (
        f"P2 should lose 1 card; before={hand_before}, after={_hand_count(session, _P2)}"
    )

    session.destroy()


def test_gauth_option_2_skips_discard_when_no_opponent_has_three_cards() -> None:
    session = _build_session()
    _set_deck(session, _P1, "noble", 5)
    _set_opponent_hand(session, _P2, "soldier", 2)

    hand_before = _hand_count(session, _P2)

    _play_card(session)
    _pick_option(session, "option_2")

    assert not _has_pending_generic(session), (
        "Should resolve fully when no opponent has 3+ cards"
    )
    assert _hand_count(session, _P2) == hand_before, (
        "P2 with 2 cards should not have been discarded from"
    )

    session.destroy()


def test_gauth_option_2_opponent_not_targetable_with_under_three_cards() -> None:
    session = _build_session()
    _set_deck(session, _P1, "noble", 5)
    _set_opponent_hand(session, _P2, "soldier", 2)

    _play_card(session)
    _pick_option(session, "option_2")

    discard_moves = _resolve_generic_moves(session)
    target_pids = [m.data.get("action_id") for m in discard_moves]
    assert _P2 not in target_pids, (
        f"P2 with 2 cards should not be targetable; got {target_pids}"
    )

    session.destroy()


def test_gauth_option_2_only_opponent_targetable_not_self() -> None:
    session = _build_session()
    _set_deck(session, _P1, "noble", 5)
    _set_opponent_hand(session, _P2, "soldier", 4)

    _play_card(session)
    _pick_option(session, "option_2")

    discard_moves = _resolve_generic_moves(session)
    target_pids = [m.data.get("action_id") for m in discard_moves]
    assert _P1 not in target_pids, (
        f"Self (P1) should not be targetable; got {target_pids}"
    )
    assert _P2 in target_pids, f"P2 (4 cards) should be targetable; got {target_pids}"

    session.destroy()
