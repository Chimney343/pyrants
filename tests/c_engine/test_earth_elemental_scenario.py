"""Direct test: load earth_elemental_seed_1.json and verify draw after play + return."""

from __future__ import annotations

import json
from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _find_move_by_type(session: CSession, move_type: str):
    return [m for m in session.legal_moves() if m.move_type == move_type]


def _hand_size(session: CSession) -> int:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid_bytes = _lib.intern_str(s.player_ids[i])
        cpid_bytes = _lib.intern_str(s.current_player_id)
        if pid_bytes == cpid_bytes:
            return s.players[i].hand_count
    return -1


def test_earth_elemental_seed_1_scenario():
    """Load the specific scenario and verify the focus draw fires."""
    scen_path = DATA_DIR / "scenarios" / "random_card_generation" / "earth_elemental_seed_1.json"
    raw = scen_path.read_text(encoding="utf-8")
    scen = json.loads(raw)

    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = CSession.load(str(scen_path), eng)

    hand_before = _hand_size(session)
    assert hand_before == 3, f"Expected 3 cards in hand, got {hand_before}"

    play_moves = _find_move_by_type(session, "play_card")
    assert play_moves, "No play_card moves found"
    earth_move = next((m for m in play_moves if m.data.get("card_id") == "earth_elemental"), None)
    assert earth_move, "Earth Elemental not playable"
    session.submit_move(earth_move)

    gen_moves = _find_move_by_type(session, "resolve_generic")
    assert gen_moves, "No resolve_generic moves after playing Earth Elemental"

    session.submit_move(gen_moves[0])

    gen_after = _find_move_by_type(session, "resolve_generic")
    assert not gen_after, (
        f"Expected card fully resolved. Remaining generic moves ({len(gen_after)}): "
        f"{[(m.label, m.data) for m in gen_after]}"
    )

    hand_after = _hand_size(session)
    assert hand_after == hand_before, (
        f"Hand should net 0: played 1, drew 1. Before={hand_before}, after={hand_after}"
    )

    session.destroy()
