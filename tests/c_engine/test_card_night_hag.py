"""Night Hag card behavior tests via the C engine bindings.

Execution model: modal_choice (exactly_one)
  - Option 1 (option_1): place a spy at a board site
  - Option 2 (option_2): return one of your own spies from the board to your
    barracks, then draw 2 cards

Verifies:
  - Execution model metadata (cost, aspect, ops, options structure)
  - Card moves to played_cards and hand count decreases after play
  - Modal choice is pending after play with two options
  - Option 1 places spy at eligible site, spies_available decreases
  - Option 1 blocks placement at sites where spy already exists
  - Option 2 returns own spy and draws 2 cards from deck
  - Option 2 reshuffles discard into deck when deck is empty
  - Option 2 only shows sites with own spies as targets
  - Option 2 draws cards and returns spy count correctly
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

CARD_ID = "night_hag"
_P1 = "p1"
_P2 = "p2"
_SITE_A = "site_gauntlgrym"
_SITE_B = "site_menzoberranzan"
_SITE_C = "site_blingdenfire"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _hand_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].hand_count


def _deck_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].deck_count


def _discard_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].discard_pile_count


def _played_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].played_cards_count


def _played_card_names(session: CSession, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    s = _sptr(session).contents
    return [
        _lib.intern_str(s.players[pi].played_cards[j]).decode()
        for j in range(s.players[pi].played_cards_count)
    ]


def _spies_available(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].spies_available


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            return [_lib.intern_str(ns.spies[i]).decode() for i in range(ns.spy_count)]
    return []


def _spy_count_at_node(session: CSession, node_id: str) -> int:
    return len(_spies_at_node(session, node_id))


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


def _pick_target_node(session: CSession, node_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == node_id:
            session.submit_move(m)
            return
    available = [m.data for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.destroy()
    raise AssertionError(f"node {node_id} not targetable; available: {available}")


def _set_deck(session: CSession, pid: str, card: str, count: int) -> None:
    s = _sptr(session).contents
    pi = _session_player_index(session, pid)
    if pi < 0:
        return
    s.players[pi].deck_count = min(count, 40)
    for j in range(min(count, 40)):
        s.players[pi].deck[j] = _lib.intern(card.encode())


def _set_discard(session: CSession, pid: str, cards: list[str]) -> None:
    s = _sptr(session).contents
    pi = _session_player_index(session, pid)
    if pi < 0:
        return
    s.players[pi].discard_pile_count = min(len(cards), 40)
    for j, cid in enumerate(cards[:40]):
        s.players[pi].discard_pile[j] = _lib.intern(cid.encode())


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


def test_night_hag_execution_model() -> None:
    catalog = json.loads((DATA_DIR / "cards" / "catalog.json").read_text(encoding="utf-8"))
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    card = next(c for c in cards if c.get("card_id") == CARD_ID)

    assert card["cost"] == 3
    assert card["aspect"] == "guile"
    assert "fiend" in card["secondary_aspects"]
    assert card["deck_vp"] == 1
    assert card["inner_circle_vp"] == 3

    em = card["execution_model"]
    assert em["kind"] == "modal_choice"
    assert em["selection"] == "exactly_one"
    assert len(em["options"]) == 2

    opt1 = em["options"][0]
    assert opt1["option_id"] == "option_1"
    assert len(opt1["actions"]) == 1
    assert opt1["actions"][0]["op"] == "place_spy"
    assert opt1["actions"][0]["target_scope"] == "board_site"
    assert opt1["actions"][0]["optional"] is False

    opt2 = em["options"][1]
    assert opt2["option_id"] == "option_2"
    assert len(opt2["actions"]) == 2
    assert opt2["actions"][0]["op"] == "return_spy"
    assert opt2["actions"][0]["target_scope"] == "board_site"
    assert opt2["actions"][0]["metadata"]["spy_owner"] == "self"
    assert opt2["actions"][1]["op"] == "draw_cards"
    assert opt2["actions"][1]["target_scope"] == "self"
    assert opt2["actions"][1]["quantity"] == {"kind": "fixed", "value": 2}

    assert "Choose exactly one mode" in card["rules_text"]
    assert "place a spy" in card["rules_text"]
    assert "return one of your own spies" in card["rules_text"]
    assert "draw 2 cards" in card["rules_text"]


# ---------------------------------------------------------------------------
# Modal choice behaviour
# ---------------------------------------------------------------------------


def test_night_hag_modal_choice_pending_after_play() -> None:
    session = _build_session()

    _play_card(session)
    assert _has_pending_generic(session), "Modal choice should be pending after play"

    moves = _resolve_generic_moves(session)
    option_ids = {m.data["action_id"] for m in moves}
    assert option_ids == {"option_1", "option_2"}, f"Expected both options; got {option_ids}"

    session.destroy()


def test_night_hag_both_options_viable_when_spies_present() -> None:
    session = _build_session(
        spies={_SITE_A: [_P1]},
    )

    _play_card(session)
    moves = _resolve_generic_moves(session)
    option_ids = {m.data["action_id"] for m in moves}
    assert option_ids == {"option_1", "option_2"}, f"Both options should be viable; got {option_ids}"

    session.destroy()


# ---------------------------------------------------------------------------
# Option 1: place_spy
# ---------------------------------------------------------------------------


def test_night_hag_option_1_places_spy_and_decreases_available() -> None:
    session = _build_session()
    spies_before = _spies_available(session, _P1)
    assert _spy_count_at_node(session, _SITE_A) == 0

    _play_card(session)
    _pick_option(session, "option_1")

    assert _has_pending_generic(session), "Should be pending for site selection"

    target_moves = _resolve_generic_moves(session)
    node_ids = {m.data["action_id"] for m in target_moves}
    assert _SITE_A in node_ids, f"{_SITE_A} should be a valid target"

    _pick_target_node(session, _SITE_A)
    assert not _has_pending_generic(session), "Should resolve after spy placement"

    assert _spies_available(session, _P1) == spies_before - 1, (
        f"spies_available should decrease by 1; before={spies_before}"
    )
    assert _P1 in _spies_at_node(session, _SITE_A), "P1's spy should be at site"
    session.destroy()


def test_night_hag_option_1_cannot_place_spy_at_occupied_site() -> None:
    session = _build_session(
        spies={_SITE_A: [_P1], _SITE_B: [_P2]},
    )

    _play_card(session)
    _pick_option(session, "option_1")

    target_moves = _resolve_generic_moves(session)
    node_ids = {m.data["action_id"] for m in target_moves}
    assert _SITE_A not in node_ids, (
        f"Should not allow placement where P1 already has a spy; got {node_ids}"
    )
    assert _SITE_B in node_ids, (
        "P2's spy at _SITE_B should not block P1 from placing there"
    )

    _pick_target_node(session, _SITE_B)
    assert not _has_pending_generic(session)
    assert _P1 in _spies_at_node(session, _SITE_B)
    session.destroy()


# ---------------------------------------------------------------------------
# Option 2: return_spy + draw_cards
# ---------------------------------------------------------------------------


def test_night_hag_option_2_returns_own_spy() -> None:
    session = _build_session(
        spies={_SITE_A: [_P1, _P2]},
    )
    spies_before_field = len(_spies_at_node(session, _SITE_A))
    spies_avail_before = _spies_available(session, _P1)

    _play_card(session)
    _pick_option(session, "option_2")

    assert _has_pending_generic(session), "Should be pending for return_spy site selection"

    target_moves = _resolve_generic_moves(session)
    node_ids = {m.data["action_id"] for m in target_moves}
    assert _SITE_A in node_ids, f"Should be able to return spy from {_SITE_A}"

    _pick_target_node(session, _SITE_A)
    assert not _has_pending_generic(session), "Should resolve after return + draw"

    assert _spy_count_at_node(session, _SITE_A) == spies_before_field - 1, (
        f"Site should have one fewer spy; was {spies_before_field}"
    )
    assert _P1 not in _spies_at_node(session, _SITE_A), "P1's spy should be returned"
    assert _P2 in _spies_at_node(session, _SITE_A), "P2's spy should remain"
    assert _spies_available(session, _P1) == spies_avail_before + 1, (
        f"spies_available should increase by 1 after return; before={spies_avail_before}"
    )
    session.destroy()


def test_night_hag_option_2_returns_spy_and_draws_two_cards() -> None:
    session = _build_session(
        spies={_SITE_A: [_P1]},
        deck={_P1: ["noble", "soldier", "house_guard"]},
    )
    deck_before = _deck_count(session, _P1)

    _play_card(session)
    hand_after_play = _hand_count(session, _P1)
    _pick_option(session, "option_2")
    _pick_target_node(session, _SITE_A)

    assert _hand_count(session, _P1) == hand_after_play + 2, (
        f"Hand should increase by 2 from post-play count; was {hand_after_play}"
    )
    assert _deck_count(session, _P1) == deck_before - 2, (
        f"Deck should decrease by 2; before={deck_before}"
    )
    assert not _has_pending_generic(session)
    session.destroy()


def test_night_hag_option_2_reshuffles_discard_when_deck_empty() -> None:
    session = _build_session(
        spies={_SITE_A: [_P1]},
        deck={_P1: []},
    )
    _set_discard(session, _P1, ["malice_adept", "noble", "soldier"])

    assert _deck_count(session, _P1) == 0
    assert _discard_count(session, _P1) == 3

    _play_card(session)
    hand_after_play = _hand_count(session, _P1)
    _pick_option(session, "option_2")
    _pick_target_node(session, _SITE_A)

    assert _hand_count(session, _P1) == hand_after_play + 2, (
        f"Should draw 2 after reshuffle from post-play count; was {hand_after_play}"
    )
    assert not _has_pending_generic(session)
    session.destroy()


def test_night_hag_option_2_only_shows_sites_with_own_spies() -> None:
    session = _build_session(
        spies={_SITE_A: [_P1], _SITE_B: [_P2], _SITE_C: [_P1, _P2]},
    )

    _play_card(session)
    _pick_option(session, "option_2")

    target_moves = _resolve_generic_moves(session)
    node_ids = {m.data["action_id"] for m in target_moves}
    assert _SITE_A in node_ids, "P1's spy at _SITE_A should be targetable"
    assert _SITE_C in node_ids, "P1's spy at _SITE_C should be targetable"
    assert _SITE_B not in node_ids, (
        f"P2-only spy site should not be targetable; got {node_ids}"
    )
    session.destroy()


def test_night_hag_option_2_skips_return_when_no_own_spies_present() -> None:
    engine = _make_engine()
    session = make_card_test_session(
        engine, [_P1, _P2],
        hand={_P1: [CARD_ID]},
        deck={_P1: ["noble", "soldier"]},
        spies={_SITE_A: [_P2]},
        current_player=_P1,
    )

    _play_card(session)
    moves = _resolve_generic_moves(session)
    option_ids = {m.data["action_id"] for m in moves}
    assert "option_1" in option_ids, "option_1 should always be viable"
    assert "option_2" in option_ids, "option_2 appears even without own spies on board"
    session.destroy()


# ---------------------------------------------------------------------------
# Card movement: hand -> played zone
# ---------------------------------------------------------------------------


def test_night_hag_moves_to_played_cards_and_hand_decreases() -> None:
    session = _build_session()

    hand_before = _hand_count(session, _P1)
    played_before = _played_count(session, _P1)

    _play_card(session)

    assert _hand_count(session, _P1) == hand_before - 1, (
        f"Hand should decrease by 1; before={hand_before}, after={_hand_count(session, _P1)}"
    )
    assert _played_count(session, _P1) == played_before + 1, (
        f"Played cards should increase by 1; before={played_before}"
    )
    assert CARD_ID in _played_card_names(session, _P1), (
        f"Night Hag should be in played_cards; got {_played_card_names(session, _P1)}"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Resolved state after each option
# ---------------------------------------------------------------------------


def test_night_hag_option_1_clears_pending_and_leaves_no_side_state() -> None:
    session = _build_session()

    _play_card(session)
    _pick_option(session, "option_1")
    _pick_target_node(session, _SITE_A)

    assert not _has_pending_generic(session), "Pending generic must be cleared"
    assert _P1 in _spies_at_node(session, _SITE_A)
    session.destroy()


def test_night_hag_option_2_clears_pending_after_return_and_draw() -> None:
    session = _build_session(
        spies={_SITE_A: [_P1]},
        deck={_P1: ["noble", "soldier", "house_guard"]},
    )

    _play_card(session)
    _pick_option(session, "option_2")
    _pick_target_node(session, _SITE_A)

    assert not _has_pending_generic(session), "Pending generic must be cleared"
    assert _P1 not in _spies_at_node(session, _SITE_A), "P1's spy should be gone"
    session.destroy()


def test_night_hag_option_2_draws_partial_when_deck_insufficient() -> None:
    session = _build_session(
        spies={_SITE_A: [_P1]},
        deck={_P1: ["soldier"]},
    )
    _set_discard(session, _P1, [])

    _play_card(session)
    hand_after_play = _hand_count(session, _P1)
    _pick_option(session, "option_2")
    _pick_target_node(session, _SITE_A)

    assert _hand_count(session, _P1) == hand_after_play + 1, (
        f"Should draw only 1 when deck has <2 and discard is empty; was {hand_after_play}"
    )
    assert not _has_pending_generic(session)
    session.destroy()
