"""Minimal test: Earth Elemental + black_earth_cultist in hand → focus draw."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib, MAX_ZONE_SIZE, PHASE_MAIN
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _hand_size(session: CSession, pid: str = "p1") -> int:
    s = session._state._ptr.contents
    name_bytes = pid.encode()
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname == name_bytes:
            return s.players[i].hand_count
    return -1


def test_earth_elemental_focus_from_hand():
    """Black earth cultist (ambition) in hand should satisfy focus."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
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

    hand_before = _hand_size(session)
    assert hand_before == 3, f"Expected 3, got {hand_before}"

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "earth_elemental":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("earth_elemental not playable")

    rg_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert rg_moves, "No resolve_generic after playing earth_elemental"
    session.submit_move(rg_moves[0])

    gen_after = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not gen_after, f"Expected card done, got {len(gen_after)} generic moves"

    hand_after = _hand_size(session)
    assert hand_after == hand_before, (
        f"Should net 0 (play 1, draw 1). Before={hand_before}, after={hand_after}"
    )

    session.destroy()
