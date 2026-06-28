"""Carrion Crawler card behavior tests.

Verifies:
- Gain 3 power immediately on play
- Enter devour choice for a market card
- Devoured card is removed from market and placed in devour pile
- Carrion Crawler self-replaces into the emptied market slot
- Only market cards (not hand/played/inner_circle) are offered as devour targets
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import MAX_ZONE_SIZE, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_CARD_ID = "carrion_crawler"


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _power(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.power


def _has_pending_generic(session: CSession) -> bool:
    return bool(session._state._ptr.contents.pending_generic)


def _pending_source_card_id(session: CSession) -> str:
    pg = session._state._ptr.contents.pending_generic
    if not pg:
        return ""
    sym = _lib.intern_str(pg.contents.source_card_id)
    return sym.decode() if sym else ""


def _market_row_ids(session: CSession) -> list[str]:
    s = session._state._ptr.contents
    return [
        _lib.intern_str(s.market.row[j]).decode()
        for j in range(s.market.row_count)
    ]


def _devour_pile_ids(session: CSession) -> list[str]:
    s = session._state._ptr.contents
    return [
        _lib.intern_str(s.devour_pile[j]).decode()
        for j in range(s.devour_pile_count)
    ]


def _played_cards_ids(session: CSession, player_index: int = 0) -> list[str]:
    s = session._state._ptr.contents
    ps = s.players[player_index]
    return [
        _lib.intern_str(ps.played_cards[j]).decode()
        for j in range(ps.played_cards_count)
    ]


def _init_engine() -> CEngine:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return eng


def _set_market_row(session: CSession, card_ids: list[str]) -> None:
    s = session._state._ptr.contents
    ms = s.market
    ms.row_count = min(len(card_ids), MAX_ZONE_SIZE)
    for j, cid in enumerate(card_ids[:MAX_ZONE_SIZE]):
        ms.row[j] = _lib.intern(cid.encode())

# ---------------------------------------------------------------------------
# RED — Tests expecting specific behavior (feature exists in C engine)
# ---------------------------------------------------------------------------


def test_carrion_crawler_grants_3_power_on_play():
    """Playing Carrion Crawler grants 3 power immediately."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])

    power_before = _power(session)
    _play_card(session, _CARD_ID)

    assert _power(session) == power_before + 3, (
        f"Expected +3 power, got {_power(session) - power_before}"
    )
    session.destroy()


def test_carrion_crawler_enters_pending_generic_after_play():
    """After playing Carrion Crawler, a pending generic choice exists for devour."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])

    _play_card(session, _CARD_ID)

    assert _has_pending_generic(session), (
        "Carrion Crawler must enter pending generic choice for devour"
    )
    assert _pending_source_card_id(session) == _CARD_ID, (
        f"Pending source_card_id should be {_CARD_ID}, "
        f"got {_pending_source_card_id(session)}"
    )
    session.destroy()


def test_carrion_crawler_devour_removes_market_card_to_devour_pile():
    """Devouring a market card removes it from market and adds it to devour pile."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])

    _play_card(session, _CARD_ID)

    devour_before = len(_devour_pile_ids(session))
    market_before = _market_row_ids(session)

    # Find and submit the devour resolve move for "noble"
    devour_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "noble"
    ]
    assert devour_moves, f"No devour move for 'noble'; legal moves: {[m.data for m in session.legal_moves()]}"
    session.submit_move(devour_moves[0])

    # Noble should be gone from market
    market_after = _market_row_ids(session)
    assert "noble" not in market_after, f"Noble should be removed from market, got: {market_after}"
    assert len(market_after) == len(market_before), (
        f"Market row size unchanged (self-replace): {len(market_before)} -> {len(market_after)}"
    )

    # Noble should be in devour pile
    devour_after = _devour_pile_ids(session)
    assert len(devour_after) == devour_before + 1, (
        f"Devour pile should grow: {devour_before} -> {len(devour_after)}"
    )
    assert "noble" in devour_after, f"Devoured noble should be in devour pile: {devour_after}"

    session.destroy()


def test_carrion_crawler_self_replaces_into_market():
    """After devouring a market card, Carrion Crawler replaces it in the market row."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])

    _play_card(session, _CARD_ID)

    # Devour noble
    devour_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "noble"
    ]
    assert devour_moves
    session.submit_move(devour_moves[0])

    market_after = _market_row_ids(session)
    assert _CARD_ID in market_after, (
        f"Carrion Crawler should be in market row after self-replace, got: {market_after}"
    )

    # Carrion Crawler should NOT be in played_cards (it moved to market)
    played = _played_cards_ids(session)
    assert _CARD_ID not in played, (
        f"Carrion Crawler should not be in played_cards after self-replace, got: {played}"
    )

    session.destroy()


def test_carrion_crawler_self_replace_preserves_other_market_cards():
    """When Carrion Crawler self-replaces, other market cards are unchanged."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])

    _play_card(session, _CARD_ID)

    # Devour noble (index 0)
    devour_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "noble"
    ]
    assert devour_moves
    session.submit_move(devour_moves[0])

    market_after = _market_row_ids(session)
    assert "soldier" in market_after, "soldier should still be in market"
    assert "advance_scout" in market_after, "advance_scout should still be in market"
    assert _CARD_ID in market_after, "Carrion Crawler should be in market"

    session.destroy()


def test_carrion_crawler_devour_targets_only_market_cards():
    """Devour choices should only include cards in the market row."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID, "noble"]},
        inner_circle={"p1": ["soldier"]},
        current_player="p1",
    )
    _set_market_row(session, ["advance_scout", "priestess_of_lolth"])

    _play_card(session, _CARD_ID)

    devour_targets = {
        m.data["action_id"]
        for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id")
    }

    assert "advance_scout" in devour_targets, (
        f"advance_scout (market) should be a devour target, got: {devour_targets}"
    )
    assert "priestess_of_lolth" in devour_targets, (
        f"priestess_of_lolth (market) should be a devour target, got: {devour_targets}"
    )
    assert "noble" not in devour_targets, (
        f"noble (hand) should NOT be a devour target, got: {devour_targets}"
    )
    assert "soldier" not in devour_targets, (
        f"soldier (inner_circle) should NOT be a devour target, got: {devour_targets}"
    )

    session.destroy()


def test_carrion_crawler_no_pending_after_full_resolution():
    """After devouring, Carrion Crawler should fully resolve with no pending state."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier"])

    _play_card(session, _CARD_ID)

    devour_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "noble"
    ]
    assert devour_moves
    session.submit_move(devour_moves[0])

    assert not _has_pending_generic(session), (
        "Carrion Crawler should fully resolve after devour"
    )

    session.destroy()


def test_carrion_crawler_devour_second_market_slot():
    """Devour a market card from a non-first slot; self-replace still works."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout", "priestess_of_lolth"])

    _play_card(session, _CARD_ID)

    # Devour advance_scout (index 2)
    devour_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "advance_scout"
    ]
    assert devour_moves, f"No devour move for advance_scout; targets: {[m.data.get('action_id') for m in session.legal_moves() if m._move_type == 'resolve_generic']}"
    session.submit_move(devour_moves[0])

    market_after = _market_row_ids(session)
    assert "advance_scout" not in market_after, "advance_scout should be devoured"
    assert _CARD_ID in market_after, "Carrion Crawler should self-replace into market"

    devour_pile = _devour_pile_ids(session)
    assert "advance_scout" in devour_pile, "advance_scout should be in devour pile"

    session.destroy()
