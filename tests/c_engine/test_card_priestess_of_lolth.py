"""Priestess of Lolth card behavior tests.

Priestess of Lolth (2-cost, Obedience): Gain 2 influence. Auto-resolve.
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


def _influence(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.influence


def test_priestess_of_lolth_gains_two_influence():
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["priestess_of_lolth", "noble"]},
        current_player="p1",
    )

    influence_before = _influence(session)
    _play_card(session, "priestess_of_lolth")
    influence_after = _influence(session)

    assert influence_after == influence_before + 2, (
        f"Expected +2 influence, got {influence_after - influence_before}"
    )

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not gen, f"Expected no pending generic moves, got {len(gen)}"

    session.destroy()


def test_priestess_of_lolth_appears_in_legal_play_moves():
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["priestess_of_lolth", "noble"]},
        current_player="p1",
    )

    play_moves = [
        m for m in session.legal_moves()
        if m._move_type == "play_card"
    ]
    card_ids = {m.data.get("card_id") for m in play_moves}

    assert "priestess_of_lolth" in card_ids, (
        f"Priestess of Lolth should be playable, got: {card_ids}"
    )

    session.destroy()


def test_playing_multiple_priestesses_stacks_influence():
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["priestess_of_lolth", "priestess_of_lolth", "noble"]},
        current_player="p1",
    )

    influence_before = _influence(session)
    _play_card(session, "priestess_of_lolth")
    _play_card(session, "priestess_of_lolth")
    influence_after = _influence(session)

    assert influence_after == influence_before + 4, (
        f"Expected +4 influence from two Priestesses, got {influence_after - influence_before}"
    )

    session.destroy()
