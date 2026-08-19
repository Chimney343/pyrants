"""Cult Fanatic card behavior tests.

Verifies:
- Gain 2 influence immediately on play
- Enters optional devour choice for a market card
- Devoured card is removed from market and placed in devour pile
- Devour is optional: skip move exists and skips cleanly
- Cult Fanatic stays in played_cards (self_replace=false)
- Only market cards are offered as devour targets
- Card fully resolves after devour or skip
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import MAX_ZONE_SIZE, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_CARD_ID = "cult_fanatic"


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _influence(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.influence


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
    return [_lib.intern_str(s.market.row[j]).decode() for j in range(s.market.row_count)]


def _devour_pile_ids(session: CSession) -> list[str]:
    s = session._state._ptr.contents
    return [_lib.intern_str(s.devour_pile[j]).decode() for j in range(s.devour_pile_count)]


def _played_cards_ids(session: CSession, player_index: int = 0) -> list[str]:
    s = session._state._ptr.contents
    ps = s.players[player_index]
    return [_lib.intern_str(ps.played_cards[j]).decode() for j in range(ps.played_cards_count)]


def _player_hand(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == pid:
            ps = s.players[i]
            return [_lib.intern_str(ps.hand[j]).decode() for j in range(ps.hand_count)]
    return []


def _player_inner_circle(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == pid:
            ps = s.players[i]
            return [_lib.intern_str(ps.inner_circle[j]).decode() for j in range(ps.inner_circle_count)]
    return []


def _init_engine() -> CEngine:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
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


def _set_market_deck(session: CSession, card_ids: list[str]) -> None:
    s = session._state._ptr.contents
    ms = s.market
    ms.deck_count = min(len(card_ids), MAX_ZONE_SIZE)
    for j, cid in enumerate(card_ids[:MAX_ZONE_SIZE]):
        ms.deck[j] = _lib.intern(cid.encode())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cult_fanatic_gain_2_influence_on_play() -> None:
    """Playing Cult Fanatic grants 2 influence immediately."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])
    _set_market_deck(session, [])

    s = session._state._ptr.contents
    s.resource_pool.influence = 0
    influence_before = _influence(session)

    _play_card(session, _CARD_ID)

    assert _influence(session) == influence_before + 2, (
        f"Expected +2 influence, got {_influence(session) - influence_before}"
    )
    session.destroy()


def test_cult_fanatic_devour_is_pending_after_play() -> None:
    """After playing Cult Fanatic, a pending generic choice exists for devour."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])
    _set_market_deck(session, [])

    _play_card(session, _CARD_ID)

    assert _has_pending_generic(session), (
        "Cult Fanatic must enter pending generic choice for devour"
    )
    assert _pending_source_card_id(session) == _CARD_ID, (
        f"Pending source_card_id should be {_CARD_ID}, "
        f"got {_pending_source_card_id(session)}"
    )
    session.destroy()


def test_cult_fanatic_devour_optional_skip_move_exists() -> None:
    """Devour is optional: a skip move with action_id=None exists."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])
    _set_market_deck(session, [])

    _play_card(session, _CARD_ID)

    gen_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    skip_moves = [m for m in gen_moves if m.data.get("action_id") is None]
    target_moves = [m for m in gen_moves if m.data.get("action_id") is not None]

    assert len(skip_moves) == 1, (
        f"Expected 1 skip move for optional devour, got {len(skip_moves)}"
    )
    assert len(target_moves) == 3, (
        f"Expected 3 market card targets, got {len(target_moves)}: "
        f"{[m.data for m in target_moves]}"
    )
    session.destroy()


def test_cult_fanatic_devour_removes_market_card_to_devour_pile() -> None:
    """Devouring a market card removes it from market and adds it to devour pile."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])
    _set_market_deck(session, [])

    _play_card(session, _CARD_ID)

    devour_before = len(_devour_pile_ids(session))
    market_before = _market_row_ids(session)

    devour_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "noble"
    ]
    assert devour_moves, f"No devour move for 'noble'; legal moves: {[m.data for m in session.legal_moves()]}"
    session.submit_move(devour_moves[0])

    market_after = _market_row_ids(session)
    assert "noble" not in market_after, f"Noble should be removed from market, got: {market_after}"
    assert len(market_after) == len(market_before) - 1, (
        f"Market row should shrink after devour (no self_replace, empty deck): "
        f"{len(market_before)} -> {len(market_after)}"
    )

    devour_after = _devour_pile_ids(session)
    assert len(devour_after) == devour_before + 1, (
        f"Devour pile should grow: {devour_before} -> {len(devour_after)}"
    )
    assert "noble" in devour_after, f"Devoured noble should be in devour pile: {devour_after}"

    session.destroy()


def test_cult_fanatic_devour_refills_from_deck() -> None:
    """When market deck has cards, devour replaces the slot from the deck."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])
    _set_market_deck(session, ["priestess_of_lolth", "house_guard"])

    _play_card(session, _CARD_ID)

    market_before = _market_row_ids(session)

    devour_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "noble"
    ]
    assert devour_moves
    session.submit_move(devour_moves[0])

    market_after = _market_row_ids(session)
    assert "noble" not in market_after, "noble should be devoured"
    assert len(market_after) == len(market_before), (
        f"Market row size should stay same when deck refills: "
        f"{len(market_before)} -> {len(market_after)}"
    )
    assert "house_guard" in market_after, (
        f"Top deck card should fill devoured slot, got: {market_after}"
    )

    session.destroy()


def test_cult_fanatic_devour_skip_resolves_card() -> None:
    """Skipping the optional devour resolves the card with no pending state."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])
    _set_market_deck(session, [])

    _play_card(session, _CARD_ID)

    gen_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    skip_move = next((m for m in gen_moves if m.data.get("action_id") is None), None)
    assert skip_move is not None, "Skip move should exist for optional devour"

    session.submit_move(skip_move)

    assert not _has_pending_generic(session), (
        "Cult Fanatic should fully resolve after skipping devour"
    )

    devour_after = _devour_pile_ids(session)
    assert len(devour_after) == 0, (
        f"Devour pile should be empty after skipping, got: {devour_after}"
    )

    session.destroy()


def test_cult_fanatic_stays_in_played_cards() -> None:
    """Cult Fanatic stays in played_cards (self_replace=false, unlike Carrion Crawler)."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])
    _set_market_deck(session, [])

    _play_card(session, _CARD_ID)

    devour_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "noble"
    ]
    assert devour_moves
    session.submit_move(devour_moves[0])

    played = _played_cards_ids(session)
    assert _CARD_ID in played, (
        f"Cult Fanatic should stay in played_cards (self_replace=false), got: {played}"
    )

    market_after = _market_row_ids(session)
    assert _CARD_ID not in market_after, (
        f"Cult Fanatic should NOT be in market row (no self_replace), got: {market_after}"
    )

    session.destroy()


def test_cult_fanatic_devour_targets_only_market() -> None:
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
    _set_market_deck(session, [])

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


def test_cult_fanatic_resolves_after_devour() -> None:
    """After devouring, Cult Fanatic fully resolves with no pending state."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier"])
    _set_market_deck(session, [])

    _play_card(session, _CARD_ID)

    devour_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "noble"
    ]
    assert devour_moves
    session.submit_move(devour_moves[0])

    assert not _has_pending_generic(session), (
        "Cult Fanatic should fully resolve after devour"
    )

    move_types = {m.move_type for m in session.legal_moves()}
    assert "end_main_phase" in move_types, "Should be able to end main phase"

    session.destroy()


def test_cult_fanatic_gain_influence_then_skip_devour() -> None:
    """Gain 2 influence then skip devour: influence gained, card resolved, devour pile empty."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_market_row(session, ["noble", "soldier"])
    _set_market_deck(session, [])

    s = session._state._ptr.contents
    s.resource_pool.influence = 5

    _play_card(session, _CARD_ID)

    assert _influence(session) == 7, f"Expected 7 influence after gain, got {_influence(session)}"

    gen_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    skip_move = next((m for m in gen_moves if m.data.get("action_id") is None), None)
    assert skip_move is not None
    session.submit_move(skip_move)

    assert not _has_pending_generic(session)
    assert _influence(session) == 7, "Influence should not change after skipping devour"

    session.destroy()
