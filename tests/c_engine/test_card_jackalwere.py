import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.session import CSession

BATCH_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "batch_card_generation"
JACKALWERE_SCENARIO = BATCH_DIR / "030_seed_4_jackalwere.json"


def _play_card(session, card_id):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    raise RuntimeError(f"Could not find play_card move for {card_id}")


def _get_option_moves(session):
    result = {}
    for m in session.legal_moves():
        if m.move_type == "resolve_generic":
            aid = m.data.get("action_id")
            tid = m.data.get("target_id")
            result[aid] = tid
    return result


def test_jackalwere_option_2_unavailable_when_no_spies_on_board():
    session = CSession.load(str(JACKALWERE_SCENARIO))
    assert session.state.phase == "main"
    ci = session.state.player_ids.index(session.state.current_player_id)
    assert "jackalwere" in session.state.player_hand(ci)

    _play_card(session, "jackalwere")

    options = _get_option_moves(session)
    assert "option_1" in options
    assert "option_2" in options
    assert options["option_1"] is None, "option_1 should be available"
    assert options["option_2"] == "unavailable", (
        "option_2 should be unavailable when player has no spies on the board"
    )

    session.destroy()
