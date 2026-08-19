"""Severin Silrajin card behavior tests: gain 5 power."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CATALOG_PATH = DATA_DIR / "cards"


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _power(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.power


def test_severin_silrajin_execution_model_gains_five_power() -> None:
    catalog = assemble_catalog_payload(CATALOG_PATH)
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    severin = next(c for c in cards if c.get("card_id") == "severin_silrajin")

    em = severin["execution_model"]
    assert em["kind"] == "sequence"
    actions = em["actions"]
    assert len(actions) == 1, "Severin Silrajin should have exactly 1 action"

    gain = actions[0]
    assert gain["op"] == "gain_resource"
    assert gain["target_scope"] == "self"
    assert gain["timing"] == "immediate"
    assert gain["optional"] is False
    assert gain["quantity"] == {"kind": "fixed", "value": 5}
    assert gain["filters"] == []
    assert gain["metadata"] == {"resource": "power"}

    assert severin["rules_text"] == "Gain 5 power."
    assert severin["cost"] == 7
    assert severin["aspect"] == "malice"
    assert "human" in severin["secondary_aspects"]


def test_severin_silrajin_grants_five_power() -> None:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["severin_silrajin"]},
        current_player="p1",
    )

    power_before = _power(session)
    _play_card(session, "severin_silrajin")

    power_after = _power(session)
    assert power_after == power_before + 5, (
        f"Expected +5 power, got {power_after - power_before}"
    )

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not gen, f"Expected no pending generic moves, got {len(gen)}"

    session.destroy()
