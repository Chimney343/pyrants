"""Gauth card behavior tests via the C engine bindings.

Execution model: modal_choice (exactly_one)
  - Option 1 (option_1): gain 2 influence
  - Option 2 (option_2): draw a card, then choose an opponent with 3+ cards
    in hand to discard one random card

Verifies:
  - Execution model metadata (cost, aspect, ops, options structure)
  - Card moves to played_cards and hand count decreases after play
  - Modal choice is pending after play with two options
  - Option 1 grants 2 influence and resolves fully
  - Option 2 draws 1 card (reshuffles when deck is empty)
  - Option 2 shows only opponent targets with 3+ cards
  - Option 2 skips discard when no opponent has 3+ cards
  - Option 2 discard picks a random card from the targeted opponent
  - Multiplayer: only opponents with 3+ cards are targetable
  - Card fully resolves after each option
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload
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


def test_gauth_execution_model() -> None:
    catalog = assemble_catalog_payload(DATA_DIR / "cards")
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


# ---------------------------------------------------------------------------
# Card movement: hand → played zone
# ---------------------------------------------------------------------------


def test_gauth_moves_to_played_cards_and_hand_decreases() -> None:
    session = _build_session()

    hand_before = _hand_count(session, _P1)
    played_before = _played_count(session, _P1)

    _play_card(session)

    assert _hand_count(session, _P1) == hand_before - 1, (
        f"Hand should decrease by 1; before={hand_before}, after={_hand_count(session, _P1)}"
    )
    assert _played_count(session, _P1) == played_before + 1, (
        f"Played cards should increase by 1; before={played_before}, after={_played_count(session, _P1)}"
    )
    assert CARD_ID in _played_card_names(session, _P1), (
        f"Gauth should be in played_cards; got {_played_card_names(session, _P1)}"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Option 2: draw verification
# ---------------------------------------------------------------------------


def test_gauth_option_2_draws_exactly_one_card() -> None:
    session = _build_session()
    _set_deck(session, _P1, "noble", 5)
    _set_opponent_hand(session, _P2, "soldier", 3)

    hand_after_play = 0  # only gauth was in hand, now played

    _play_card(session)
    assert _hand_count(session, _P1) == hand_after_play

    _pick_option(session, "option_2")

    assert _hand_count(session, _P1) == 1, (
        f"P1 should have drawn 1 card; got {_hand_count(session, _P1)}"
    )

    session.destroy()


def test_gauth_option_2_reshuffles_discard_when_deck_empty() -> None:
    session = _build_session()
    _set_discard(session, _P1, ["malice_adept", "noble"])
    _set_opponent_hand(session, _P2, "soldier", 3)

    assert _deck_count(session, _P1) == 0
    assert _discard_count(session, _P1) == 2

    _play_card(session)
    _pick_option(session, "option_2")

    assert _hand_count(session, _P1) == 1, (
        "P1 should have drawn 1 card after reshuffle"
    )
    assert _deck_count(session, _P1) + _discard_count(session, _P1) == 1, (
        "After reshuffle+draw, remaining (deck+discard) should be 1"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Multiplayer: only opponents with 3+ cards are targetable
# ---------------------------------------------------------------------------


def test_gauth_option_2_filters_opponents_by_hand_size_in_multiplayer() -> None:
    _P3 = "p3"
    _P4 = "p4"
    session = _build_session(
        player_ids=[_P1, _P2, _P3, _P4],
        hand={_P1: [CARD_ID]},
        current_player=_P1,
    )
    _set_deck(session, _P1, "noble", 5)
    _set_opponent_hand(session, _P2, "soldier", 4)
    _set_opponent_hand(session, _P3, "noble", 3)
    _set_opponent_hand(session, _P4, "soldier", 2)

    _play_card(session)
    _pick_option(session, "option_2")

    discard_moves = _resolve_generic_moves(session)
    target_pids = {m.data.get("action_id") for m in discard_moves}

    assert _P1 not in target_pids, "Self should never be targetable"
    assert _P2 in target_pids, "P2 (4 cards) should be targetable"
    assert _P3 in target_pids, "P3 (3 cards, threshold) should be targetable"
    assert _P4 not in target_pids, "P4 (2 cards) should not be targetable"
    assert len(target_pids) == 2, (
        f"Expected exactly 2 targetable opponents; got {target_pids}"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Resolved state after each option
# ---------------------------------------------------------------------------


def test_gauth_option_1_clears_pending_and_leaves_no_side_state() -> None:
    session = _build_session()
    s = _sptr(session).contents
    s.resource_pool.influence = 0

    _play_card(session)
    _pick_option(session, "option_1")

    assert not _has_pending_generic(session), "Pending generic must be cleared"
    assert _influence(session) == 2
    assert _hand_count(session, _P2) == 0, "P2 should be unaffected"

    session.destroy()


def test_gauth_option_2_targeted_discard_resolves_and_clears() -> None:
    session = _build_session()
    _set_deck(session, _P1, "noble", 5)
    _set_opponent_hand(session, _P2, "soldier", 3)

    _play_card(session)
    _pick_option(session, "option_2")

    assert _has_pending_generic(session), "Should need discard target selection"

    _pick_target_player(session, _P2)

    assert not _has_pending_generic(session), "Pending generic must be cleared after discard"
    assert _hand_count(session, _P2) == 2, "P2 should have discarded 1 (3→2)"

    session.destroy()


def test_gauth_option_2_only_player_selectable_and_random_card_discarded() -> None:
    """The discard step lets the player pick only the opponent, never a specific
    card; the discarded card is random and lands in the discard pile."""
    session = _build_session()
    _set_deck(session, _P1, "noble", 5)
    _set_opponent_hand(session, _P2, "soldier", 4)

    _play_card(session)
    _pick_option(session, "option_2")

    target_moves = _resolve_generic_moves(session)
    target_ids = [m.data.get("action_id") for m in target_moves]
    assert target_ids == [_P2], (
        f"Only the opponent player id should be selectable, not individual cards; got {target_ids}"
    )

    hand_before = _hand_count(session, _P2)
    discard_before = _discard_count(session, _P2)

    _pick_target_player(session, _P2)

    assert not _has_pending_generic(session), "Pending generic must be cleared after discard"
    assert _hand_count(session, _P2) == hand_before - 1, "Exactly 1 card should leave hand"
    assert _discard_count(session, _P2) == discard_before + 1, "Discarded card should reach discard pile"

    session.destroy()
