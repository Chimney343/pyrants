"""Ghoul card behavior tests: gain 2 power, give Insane Outcast to each opponent."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import make_card_test_session

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "batch_card_generation" / "025_seed_4_ghoul.json"
)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _player_discard(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [_lib.intern_str(ps.discard_pile[j]).decode() for j in range(ps.discard_pile_count)]
    return []


def _player_power(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.power


def test_ghoul_gains_2_power() -> None:
    """Playing Ghoul should grant 2 power to the current player."""
    session = CSession.load(str(SCENARIO_PATH))
    before_power = _player_power(session)

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "ghoul":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    resolve_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    for rm in resolve_moves:
        session.submit_move(rm.move)

    assert _player_power(session) == before_power + 2, (
        f"Expected {before_power + 2} power, got {_player_power(session)}"
    )
    session.destroy()


def test_ghoul_gives_insane_outcast_to_each_opponent() -> None:
    """Ghoul should add an Insane Outcast to every opponent's discard, but NOT to the current player."""
    session = CSession.load(str(SCENARIO_PATH))

    before = {pid: _player_discard(session, pid) for pid in ["p1", "p2", "p3", "p4"]}

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "ghoul":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    resolve_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    for rm in resolve_moves:
        session.submit_move(rm.move)

    after = {pid: _player_discard(session, pid) for pid in ["p1", "p2", "p3", "p4"]}

    # p2 is the current player — must NOT get an Insane Outcast
    assert "insane_outcast" not in after["p2"], f"p2 (current player) should NOT have Insane Outcast: {after['p2']}"
    assert len(after["p2"]) == len(before["p2"]), (
        f"p2 discard should not change size: {len(before['p2'])} → {len(after['p2'])}"
    )

    # p1, p3, p4 are opponents — each must get exactly 1 Insane Outcast
    for opp in ["p1", "p3", "p4"]:
        assert "insane_outcast" in after[opp], f"{opp} (opponent) should have Insane Outcast: {after[opp]}"
        assert after[opp].count("insane_outcast") == before[opp].count("insane_outcast") + 1, (
            f"{opp} should gain exactly 1 Insane Outcast: "
            f"{before[opp].count('insane_outcast')} → {after[opp].count('insane_outcast')}"
        )

    session.destroy()


def test_ghoul_auto_resolves_with_no_pending_choices() -> None:
    """Ghoul's actions (gain_resource + custom_effect) should auto-resolve without pending generic choices."""
    session = CSession.load(str(SCENARIO_PATH))

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "ghoul":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    resolve_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert len(resolve_moves) == 0, (
        f"Ghoul must auto-resolve with no pending generic choices, found {len(resolve_moves)}"
    )
    session.destroy()


def test_ghoul_programmatic_session() -> None:
    """Ghoul should work with a programmatically constructed session, giving IO to opponent only."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["ghoul"]},
        current_player="p1",
    )

    before = {pid: _player_discard(session, pid) for pid in ["p1", "p2"]}

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "ghoul":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    resolve_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    for rm in resolve_moves:
        session.submit_move(rm.move)

    after = {pid: _player_discard(session, pid) for pid in ["p1", "p2"]}

    assert _player_power(session) == 2, f"Expected 2 power, got {_player_power(session)}"
    assert "insane_outcast" not in after["p1"], f"p1 (current player) should NOT have Insane Outcast: {after['p1']}"
    assert after["p2"].count("insane_outcast") == before["p2"].count("insane_outcast") + 1, (
        "p2 (opponent) should gain exactly 1 Insane Outcast"
    )

    session.destroy()
