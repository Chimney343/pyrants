"""Bounty Hunter: Gain 3 power. Cost 5, 2 deck VP, 4 inner-circle VP."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

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


def test_bounty_hunter_grants_three_power():
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["bounty_hunter"]},
        current_player="p1",
    )

    power_before = _power(session)
    _play_card(session, "bounty_hunter")

    power_after = _power(session)
    assert power_after == power_before + 3, (
        f"Expected +3 power, got {power_after - power_before}"
    )

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not gen, f"Expected no pending generic moves, got {len(gen)}"

    session.destroy()
