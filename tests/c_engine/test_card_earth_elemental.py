"""Earth Elemental card behavior: gain influence, return unit, focus draw."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
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


def _hand_size(session: CSession, pid: str) -> int:
    s = session._state._ptr.contents
    name_bytes = pid.encode()
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname == name_bytes:
            return s.players[i].hand_count
    return -1


def _influence(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.influence


def test_earth_elemental_focus_draw_from_hand():
    """With an Ambition card (black_earth_cultist) in hand, the draw should fire."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["earth_elemental", "black_earth_cultist", "cleric_of_laogzed"]},
        deck={"p1": ["noble", "noble", "noble"]},
        troops={"p2": {"site_gauntlgrym": ["p2", None]}},
        current_player="p1",
    )

    hand_before = _hand_size(session, "p1")
    assert hand_before == 3

    _play_card(session, "earth_elemental")

    inf_after = _influence(session)
    assert inf_after == 1

    return_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert return_moves, "Expected return_unit moves"
    session.submit_move(return_moves[0])

    gen_after = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not gen_after, f"Expected card fully resolved, got {len(gen_after)} generic moves"

    hand_after = _hand_size(session, "p1")
    assert hand_after == hand_before, (
        f"Hand should net 0 (play 1, draw 1). Before={hand_before}, after={hand_after}"
    )

    session.destroy()


def test_earth_elemental_no_focus_draw_without_ambition():
    """Without an Ambition card in hand or played, draw should be skipped."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["earth_elemental", "noble"]},
        deck={"p1": ["noble", "noble", "noble"]},
        troops={"p2": {"site_gauntlgrym": ["p2", None]}},
        current_player="p1",
    )

    hand_before = _hand_size(session, "p1")
    inf_before = _influence(session)

    _play_card(session, "earth_elemental")

    inf_after = _influence(session)
    assert inf_after == inf_before + 1

    return_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert return_moves
    session.submit_move(return_moves[0])

    gen_after = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not gen_after, f"Expected card fully resolved, got {len(gen_after)} generic moves"

    hand_after = _hand_size(session, "p1")
    assert hand_after == hand_before - 1, (
        f"Hand should net -1 (played card, no draw). Before={hand_before}, after={hand_after}"
    )

    session.destroy()
