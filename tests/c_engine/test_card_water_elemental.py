"""Water Elemental card behavior: deploy 2 troops, focus-draw card.

Core mechanics:
  1. Deploy 2 troops to a board site.
  2. If a Conquest-aspect card is present (hand or played), draw 1 card.
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _barracks(session: CSession, pid: str) -> int:
    pi = session.state.player_index(pid)
    return session.state.player_barracks(pi)


def _deck_count(session: CSession, pid: str) -> int:
    pi = session.state.player_index(pid)
    return len(session.state.player_deck(pi))


def _hand_size(session: CSession, pid: str) -> int:
    pi = session.state.player_index(pid)
    return len(session.state.player_hand(pi))


def _resolve_all_generics(session: CSession) -> list[dict]:
    """Resolve all pending generic moves; return their data dicts."""
    resolved = []
    while True:
        gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
        if not gen:
            break
        resolved.append(gen[0].data)
        session.submit_move(gen[0])
    return resolved


def test_water_elemental_deploy_no_focus():
    """2 troops deployed. Without a Conquest card in hand, no draw."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["water_elemental", "noble", "soldier"]},
        deck={"p1": ["noble", "noble", "noble"]},
        troops={"p1": {"site_gauntlgrym": [None, None, None]}},
        current_player="p1",
    )

    hand_before = _hand_size(session, "p1")
    barracks_before = _barracks(session, "p1")
    assert barracks_before >= 2

    _play_card(session, "water_elemental")
    generics = _resolve_all_generics(session)

    barracks_after = _barracks(session, "p1")
    assert barracks_after == barracks_before - 2, (
        f"Expected 2 troops deployed (barracks {barracks_before} -> {barracks_before - 2}), got {barracks_after}"
    )

    hand_after = _hand_size(session, "p1")
    assert hand_after == hand_before - 1, (
        f"No draw without focus: hand should net -1. Before={hand_before}, after={hand_after}"
    )

    assert len(generics) == 2, f"Expected 2 deploy-site selections (one per troop), got {len(generics)}: {generics}"
    for g in generics:
        assert g.get("action_id"), f"Generic move missing action_id: {g}"

    session.destroy()


def test_water_elemental_deploy_with_focus():
    """2 troops deployed. With Conquest card in hand, 1 card drawn."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["water_elemental", "noble", "soldier", "black_wyrmling"]},
        deck={"p1": ["noble", "noble", "noble"]},
        troops={"p1": {"site_gauntlgrym": [None, None, None]}},
        current_player="p1",
    )

    hand_before = _hand_size(session, "p1")
    barracks_before = _barracks(session, "p1")
    deck_before = _deck_count(session, "p1")

    _play_card(session, "water_elemental")
    generics = _resolve_all_generics(session)

    barracks_after = _barracks(session, "p1")
    assert barracks_after == barracks_before - 2, (
        f"Expected 2 troops deployed (barracks {barracks_before} -> {barracks_before - 2}), got {barracks_after}"
    )

    deck_after = _deck_count(session, "p1")
    assert deck_after == deck_before - 1, (
        f"With Conquest focus, 1 card should be drawn. Deck before={deck_before}, after={deck_after}"
    )

    hand_after = _hand_size(session, "p1")
    assert hand_after == hand_before, (
        f"With focus draw: play 1, draw 1 → net 0. Before={hand_before}, after={hand_after}"
    )

    assert len(generics) == 2, f"Expected 2 deploy-site selections (one per troop), got {len(generics)}: {generics}"
    for g in generics:
        assert g.get("action_id"), f"Generic move missing action_id: {g}"

    session.destroy()


def test_water_elemental_focus_met_with_played_card():
    """Focus draw triggers when a Conquest card is in played_cards zone."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["water_elemental", "noble", "soldier"]},
        deck={"p1": ["noble", "noble", "noble"]},
        troops={"p1": {"site_gauntlgrym": [None, None, None]}},
        current_player="p1",
    )

    s = session.state._ptr.contents
    ps = s.players[0]
    ps.played_cards_count = 1
    ps.played_cards[0] = _lib.intern(b"black_wyrmling")

    deck_before = _deck_count(session, "p1")
    hand_before = _hand_size(session, "p1")

    _play_card(session, "water_elemental")
    _resolve_all_generics(session)

    deck_after = _deck_count(session, "p1")
    assert deck_after == deck_before - 1, (
        f"With Conquest focus from played zone, 1 card should be drawn. Deck before={deck_before}, after={deck_after}"
    )

    hand_after = _hand_size(session, "p1")
    assert hand_after == hand_before, (
        f"Net 0: played card, drew 1. Before={hand_before}, after={hand_after}"
    )

    session.destroy()


def test_water_elemental_focus_not_met_wrong_aspect():
    """Focus draw does NOT trigger with a non-Conquest card in hand."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["water_elemental", "noble", "priestess_of_lolth"]},
        deck={"p1": ["noble", "noble", "noble"]},
        troops={"p1": {"site_gauntlgrym": [None, None, None]}},
        current_player="p1",
    )

    hand_before = _hand_size(session, "p1")
    deck_before = _deck_count(session, "p1")

    _play_card(session, "water_elemental")
    _resolve_all_generics(session)

    deck_after = _deck_count(session, "p1")
    assert deck_after == deck_before, (
        f"No draw without Conquest focus. Deck should not change: before={deck_before}, after={deck_after}"
    )

    hand_after = _hand_size(session, "p1")
    assert hand_after == hand_before - 1, (
        f"No focus: net -1 hand. Before={hand_before}, after={hand_after}"
    )

    session.destroy()
