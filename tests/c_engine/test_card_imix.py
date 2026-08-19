"""Imix card behavior tests.

Imix (6-cost, Malice): Gain 4 power. If Malice focus condition is met, gain +2 power.
"""

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


def test_imix_gains_four_power_without_malice_focus():
    """Without a Malice card in hand, Imix gives only 4 power."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["imix", "noble"]},
        current_player="p1",
    )

    power_before = _power(session)
    _play_card(session, "imix")

    power_after = _power(session)
    assert power_after == power_before + 4, (
        f"Expected +4 power, got {power_after - power_before}"
    )

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not gen, f"Expected no pending generic moves, got {len(gen)}"

    session.destroy()


def test_imix_gains_six_power_with_malice_focus():
    """With a Malice card (blackguard) in hand, Imix gives 6 power."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["imix", "blackguard"]},
        current_player="p1",
    )

    power_before = _power(session)
    _play_card(session, "imix")

    power_after = _power(session)
    assert power_after == power_before + 6, (
        f"Expected +6 power (4 base + 2 focus), got {power_after - power_before}"
    )

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not gen, f"Expected no pending generic moves, got {len(gen)}"

    session.destroy()
