"""Banshee card behavior tests: place spy + conditional 3 power if another spy present."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session, _make_engine

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


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
    return any(m._move_type == "resolve_generic" for m in session.legal_moves())


def _submit_spy_placement(session: CSession, node_id: str) -> None:
    rg = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    site_moves = [m for m in rg if m.data.get("action_id") == node_id]
    assert site_moves, f"No resolve_generic move for {node_id}, moves: {[m.data for m in rg]}"
    session.submit_move(site_moves[0])


def test_banshee_gains_3_power_when_spy_placed_on_site_with_existing_enemy_spy():
    """Place spy on site with another player's spy → gain 3 power."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["banshee"]},
        spies={"site_gauntlgrym": ["p2"]},
        current_player="p1",
    )

    before = _power(session)

    _play_card(session, "banshee")
    _submit_spy_placement(session, "site_gauntlgrym")

    assert not _has_pending_generic(session), "Card should be fully resolved"
    assert _power(session) == before + 3, "Should gain 3 power"
    session.destroy()


def test_banshee_no_power_when_no_other_spy_present():
    """Place spy on site with no existing spy → no power gained."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["banshee"]},
        spies={},
        current_player="p1",
    )

    before = _power(session)

    _play_card(session, "banshee")
    _submit_spy_placement(session, "site_gauntlgrym")

    assert not _has_pending_generic(session), "Card should be fully resolved"
    assert _power(session) == before, "Should NOT gain power"
    session.destroy()


def test_banshee_gains_exactly_3_power_with_multiple_enemy_spies():
    """Place spy on site with 2 existing enemy spies → still gain exactly 3 power, not more."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2", "p3"],
        hand={"p1": ["banshee"]},
        spies={"site_gauntlgrym": ["p2", "p3"]},
        current_player="p1",
    )

    before = _power(session)

    _play_card(session, "banshee")
    _submit_spy_placement(session, "site_gauntlgrym")

    assert not _has_pending_generic(session), "Card should be fully resolved"
    assert _power(session) == before + 3, "Should gain exactly 3 power regardless of spy count"
    session.destroy()
