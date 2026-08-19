"""Water Elemental card behavior: deploy 2 troops, draw card if Conquest focus met."""

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


def _hand_size(session: CSession, pid: str) -> int:
    s = session._state._ptr.contents
    name_bytes = pid.encode()
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname == name_bytes:
            return s.players[i].hand_count
    return -1


def _deck_size(session: CSession, pid: str) -> int:
    s = session._state._ptr.contents
    name_bytes = pid.encode()
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname == name_bytes:
            return s.players[i].deck_count
    return -1


def _barracks(session: CSession, pid: str) -> int:
    s = session._state._ptr.contents
    name_bytes = pid.encode()
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname == name_bytes:
            return s.players[i].barracks
    return -1


def _site_troops(session: CSession, node_id: str, player_id: str) -> int:
    s = session._state._ptr.contents
    node_sym = _lib.intern(node_id.encode())
    player_sym = _lib.intern(player_id.encode())
    for i in range(s.node_count):
        if s.nodes[i].node_id == node_sym:
            return sum(1 for j in range(s.nodes[i].troop_slot_count) if s.nodes[i].troop_slots[j] == player_sym)
    return 0


def test_water_elemental_deploys_two_troops_no_focus():
    """Without a Conquest card in hand (other than Water Elemental itself),
    playing it should deploy 2 troops and NOT draw a card."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["water_elemental", "noble"]},
        deck={"p1": ["noble", "noble", "noble"]},
        troops={"p1": {"site_gauntlgrym": [None, None, None]}},
        current_player="p1",
    )

    barracks_before = _barracks(session, "p1")
    troops_before = _site_troops(session, "site_gauntlgrym", "p1")
    deck_before = _deck_size(session, "p1")
    hand_before = _hand_size(session, "p1")
    assert troops_before == 0

    _play_card(session, "water_elemental")

    for _ in range(2):
        gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
        assert gen_moves, "Expected deploy move"
        session.submit_move(gen_moves[0])

    troops_after = _site_troops(session, "site_gauntlgrym", "p1")
    assert troops_after == 2, f"Expected 2 troops deployed, got {troops_after}"
    assert _barracks(session, "p1") == barracks_before - 2

    remaining = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not remaining, f"Expected card fully resolved, got {len(remaining)} generic moves"

    deck_after = _deck_size(session, "p1")
    assert deck_after == deck_before, (
        f"Deck should be unchanged (no focus draw). Before={deck_before}, after={deck_after}"
    )

    hand_after = _hand_size(session, "p1")
    assert hand_after == hand_before - 1, (
        f"Hand should lose 1 (play card, no draw). Before={hand_before}, after={hand_after}"
    )

    session.destroy()


def test_water_elemental_deploys_two_troops_with_focus():
    """With a Conquest card (grimlock) in hand alongside Water Elemental,
    playing it should deploy 2 troops AND draw 1 card."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["water_elemental", "grimlock"]},
        deck={"p1": ["noble", "noble", "noble"]},
        troops={"p1": {"site_gauntlgrym": [None, None, None]}},
        current_player="p1",
    )

    barracks_before = _barracks(session, "p1")
    troops_before = _site_troops(session, "site_gauntlgrym", "p1")
    deck_before = _deck_size(session, "p1")
    assert troops_before == 0

    _play_card(session, "water_elemental")

    for _ in range(2):
        gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
        assert gen_moves, "Expected deploy move"
        session.submit_move(gen_moves[0])

    troops_after = _site_troops(session, "site_gauntlgrym", "p1")
    assert troops_after == 2, f"Expected 2 troops deployed, got {troops_after}"
    assert _barracks(session, "p1") == barracks_before - 2

    remaining = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not remaining, f"Expected card fully resolved, got {len(remaining)} generic moves"

    deck_after = _deck_size(session, "p1")
    assert deck_after == deck_before - 1, (
        f"Expected 1 card drawn (deck {deck_before} -> {deck_before - 1}), got {deck_after}"
    )

    session.destroy()
