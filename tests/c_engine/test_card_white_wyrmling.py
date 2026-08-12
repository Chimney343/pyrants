"""White Wyrmling card behavior tests.

Verifies the C engine faithfully executes the card's execution_model:
- Deploy 2 troops (mandatory, fixed quantity 2)
- Then an optional devour of a card in the market

Specifics locked in:
- Playing White Wyrmling immediately enters a pending deploy selection (no skip
  move — the deploy is non-optional)
- Deploying 2 troops moves them from barracks onto a site
- After the 2nd deploy the card advances to the optional market-devour choice
- Devour offers exactly the market cards plus a skip move
- Devouring a market card moves it to the devour pile (self_replace=false, so
  White Wyrmling stays in played_cards and does not re-enter the market row)
- Skipping the devour resolves the card cleanly with an empty devour pile
"""

from __future__ import annotations

from engine_c.bindings.engine_bindings import MAX_ZONE_SIZE, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    make_card_test_session,
)

_CARD_ID = "white_wyrmling"
_P1 = "p1"
_P2 = "p2"
_SITE = "site_gauntlgrym"


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


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


def _played_cards_ids(session: CSession, pid: str = _P1) -> list[str]:
    s = session._state._ptr.contents
    pi = _session_player_index(session, pid)
    ps = s.players[pi]
    return [_lib.intern_str(ps.played_cards[j]).decode() for j in range(ps.played_cards_count)]


def _barracks(session: CSession, pid: str = _P1) -> int:
    s = session._state._ptr.contents
    pi = _session_player_index(session, pid)
    return s.players[pi].barracks


def _node_troop_slots(session: CSession, node_id: str) -> list[str | None]:
    s = session._state._ptr.contents
    for i in range(s.node_count):
        name = _lib.intern_str(s.nodes[i].node_id)
        if name and name.decode() == node_id:
            ns = s.nodes[i]
            slots: list[str | None] = []
            for j in range(ns.troop_slot_count):
                occ = _lib.intern_str(ns.troop_slots[j])
                slots.append(occ.decode() if occ else None)
            return slots
    return []


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


def _make_session(hand: dict[str, list[str]] | None = None,
                  inner_circle: dict[str, list[str]] | None = None) -> CSession:
    engine = _make_engine()
    session = make_card_test_session(
        engine,
        [_P1, _P2],
        hand=hand or {_P1: [_CARD_ID]},
        inner_circle=inner_circle,
        troops={_P1: {_SITE: [_P1, None, None, None, None, None]}},
        current_player=_P1,
    )
    _set_market_row(session, ["noble", "soldier", "advance_scout"])
    _set_market_deck(session, [])
    return session


def _resolve_generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if m.move_type == "resolve_generic"]


def _deploy_two(session: CSession, node_id: str = _SITE) -> None:
    for _ in range(2):
        moves = [
            m for m in _resolve_generic_moves(session)
            if m.data.get("action_id") == node_id
        ]
        if not moves:
            legal = [m.data for m in _resolve_generic_moves(session)]
            raise AssertionError(f"No deploy move for {node_id}; legal: {legal}")
        session.submit_move(moves[0])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_white_wyrmling_deploys_two_troops_then_enters_devour() -> None:
    """Play → mandatory 2-troop deploy → optional market-devour pending choice."""
    session = _make_session()

    _play_card(session, _CARD_ID)

    assert _has_pending_generic(session), "White Wyrmling must enter pending generic"
    assert _pending_source_card_id(session) == _CARD_ID, (
        f"Pending source_card_id should be {_CARD_ID}, "
        f"got {_pending_source_card_id(session)}"
    )

    # Deploy is non-optional: no skip move, only site targets.
    deploy_moves = _resolve_generic_moves(session)
    assert deploy_moves, "Deploy selection should offer site targets"
    assert not any(m.data.get("action_id") is None for m in deploy_moves), (
        "Deploy is mandatory and must not offer a skip move"
    )
    assert any(m.data.get("action_id") == _SITE for m in deploy_moves), (
        f"Deploy should offer {_SITE}; got {[m.data for m in deploy_moves]}"
    )

    barracks_before = _barracks(session)
    troops_before = _node_troop_slots(session, _SITE).count(_P1)

    _deploy_two(session)

    assert _barracks(session) == barracks_before - 2, (
        f"Barracks should decrease by 2: {barracks_before} -> {_barracks(session)}"
    )
    troops_after = _node_troop_slots(session, _SITE).count(_P1)
    assert troops_after == troops_before + 2, (
        f"Expected 2 troops deployed to {_SITE}, "
        f"count went {troops_before} -> {troops_after}"
    )

    # Card must now be pending the optional devour choice.
    assert _has_pending_generic(session), "Card must still be pending (devour) after deploy"
    gen_moves = _resolve_generic_moves(session)
    skip_moves = [m for m in gen_moves if m.data.get("action_id") is None]
    target_moves = [m for m in gen_moves if m.data.get("action_id") is not None]
    assert len(skip_moves) == 1, (
        f"Expected 1 skip move for optional devour, got {len(skip_moves)}"
    )
    assert {m.data.get("action_id") for m in target_moves} == {"noble", "soldier", "advance_scout"}, (
        f"Devour targets should be the market row, got {[m.data for m in target_moves]}"
    )

    session.destroy()


def test_white_wyrmling_devour_removes_market_card_to_devour_pile() -> None:
    """After deploying 2 troops, devouring a market card removes it to the devour pile."""
    session = _make_session()

    _play_card(session, _CARD_ID)
    _deploy_two(session)

    devour_before = len(_devour_pile_ids(session))
    market_before = _market_row_ids(session)

    devour_moves = [
        m for m in _resolve_generic_moves(session)
        if m.data.get("action_id") == "noble"
    ]
    assert devour_moves, f"No devour move for 'noble'; legal: {[m.data for m in _resolve_generic_moves(session)]}"
    session.submit_move(devour_moves[0])

    market_after = _market_row_ids(session)
    assert "noble" not in market_after, f"noble should be removed from market: {market_after}"
    assert len(market_after) == len(market_before) - 1, (
        f"Market row should shrink (no self_replace, empty deck): "
        f"{len(market_before)} -> {len(market_after)}"
    )

    devour_after = _devour_pile_ids(session)
    assert len(devour_after) == devour_before + 1, (
        f"Devour pile should grow: {devour_before} -> {len(devour_after)}"
    )
    assert "noble" in devour_after, f"noble should be in devour pile: {devour_after}"

    assert not _has_pending_generic(session), "Card must fully resolve after devour"

    session.destroy()


def test_white_wyrmling_devour_skip_resolves_card() -> None:
    """Skipping the optional devour resolves the card with an unchanged devour pile."""
    session = _make_session()

    _play_card(session, _CARD_ID)
    _deploy_two(session)

    skip_move = next(
        (m for m in _resolve_generic_moves(session) if m.data.get("action_id") is None),
        None,
    )
    assert skip_move is not None, "Skip move should exist for optional devour"
    session.submit_move(skip_move)

    assert not _has_pending_generic(session), (
        "White Wyrmling should fully resolve after skipping devour"
    )
    assert _devour_pile_ids(session) == [], (
        f"Devour pile should be empty after skipping, got {_devour_pile_ids(session)}"
    )

    session.destroy()


def test_white_wyrmling_devour_targets_only_market() -> None:
    """Devour choices should only include cards in the market row."""
    session = _make_session(
        hand={_P1: [_CARD_ID, "noble"]},
        inner_circle={_P1: ["soldier"]},
    )
    _set_market_row(session, ["advance_scout", "priestess_of_lolth"])

    _play_card(session, _CARD_ID)
    _deploy_two(session)

    devour_targets = {
        m.data["action_id"]
        for m in _resolve_generic_moves(session)
        if m.data.get("action_id")
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


def test_white_wyrmling_stays_in_played_cards_after_devour() -> None:
    """self_replace=false: White Wyrmling stays in played_cards and never re-enters market."""
    session = _make_session()

    _play_card(session, _CARD_ID)
    _deploy_two(session)

    devour_moves = [
        m for m in _resolve_generic_moves(session)
        if m.data.get("action_id") == "noble"
    ]
    assert devour_moves
    session.submit_move(devour_moves[0])

    played = _played_cards_ids(session)
    assert _CARD_ID in played, (
        f"White Wyrmling should stay in played_cards (self_replace=false), got: {played}"
    )
    assert _CARD_ID not in _market_row_ids(session), (
        f"White Wyrmling should NOT re-enter the market row, got: {_market_row_ids(session)}"
    )

    session.destroy()


def test_white_wyrmling_deploy_refills_from_market_deck_on_devour() -> None:
    """When the market deck has cards, devour refills the row from the deck."""
    session = _make_session()
    _set_market_deck(session, ["priestess_of_lolth", "house_guard"])

    _play_card(session, _CARD_ID)
    _deploy_two(session)

    devour_moves = [
        m for m in _resolve_generic_moves(session)
        if m.data.get("action_id") == "noble"
    ]
    assert devour_moves
    session.submit_move(devour_moves[0])

    market_after = _market_row_ids(session)
    assert "noble" not in market_after, "noble should be devoured"
    assert "house_guard" in market_after, (
        f"Top deck card should fill the devoured slot, got: {market_after}"
    )
    assert "noble" in _devour_pile_ids(session), "noble should be in the devour pile"

    session.destroy()
