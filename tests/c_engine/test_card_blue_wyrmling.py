"""Blue Wyrmling card behavior tests: gain 3 influence + return opponent unit."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def test_blue_wyrmling_return_spy_label():
    """Returning a spy should show 'Return Player 2's spy from <site>' label."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["blue_wyrmling"]},
        spies={"site_gauntlgrym": ["p2"]},
        current_player="p1",
    )

    _play_card(session, "blue_wyrmling")

    view = build_c_game_view(session, node_names={"site_gauntlgrym": "Gauntlgrym"})
    rg_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    return_moves = [m for m in rg_moves if "Return" in (m.label or "")]

    assert len(return_moves) >= 1, f"No return moves found, labels={[m.label for m in rg_moves]}"
    for m in return_moves:
        label = m.label or ""
        assert "Return" in label, f"Label should contain 'Return': {label}"
        assert "Player 2" in label, f"Label should contain 'Player 2': {label}"
        assert "spy" in label, f"Label should contain unit type 'spy': {label}"
        assert "from" in label, f"Label should contain 'from': {label}"
        assert "Gauntlgrym" in label, f"Label should contain site name: {label}"

    session.destroy()


def test_blue_wyrmling_return_troop_label():
    """Returning a troop should show 'Return p2's troop from <site>' label."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["blue_wyrmling"]},
        troops={"p2": {"site_gauntlgrym": ["p2", None, None]}},
        current_player="p1",
    )

    _play_card(session, "blue_wyrmling")

    view = build_c_game_view(session, node_names={"site_gauntlgrym": "Gauntlgrym"})
    rg_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    return_moves = [m for m in rg_moves if "Return" in (m.label or "")]

    assert len(return_moves) >= 1, f"No return moves found, labels={[m.label for m in rg_moves]}"
    for m in return_moves:
        label = m.label or ""
        assert "Return" in label, f"Label should contain 'Return': {label}"
        assert "Player 2" in label, f"Label should contain 'Player 2': {label}"
        assert "troop" in label, f"Label should contain unit type 'troop': {label}"
        assert "from" in label, f"Label should contain 'from': {label}"
        assert "Gauntlgrym" in label, f"Label should contain site name: {label}"

    session.destroy()
