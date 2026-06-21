"""Zuggtmoy card behavior tests for C engine.

1. Devour targets inner_circle cards, NOT hand cards.
2. End-of-turn promotes up to 2 OTHER played cards, cannot self-promote Zuggtmoy.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib, MAX_ZONE_SIZE, PHASE_MAIN, PHASE_END_OF_TURN
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

def _engine() -> CEngine:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return eng

def _hand_ids(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].hand[j]).decode() for j in range(s.players[i].hand_count)]
    return []

def _inner_circle_ids(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].inner_circle[j]).decode() for j in range(s.players[i].inner_circle_count)]
    return []

def _played_ids(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].played_cards[j]).decode() for j in range(s.players[i].played_cards_count)]
    return []

def _devour_pile_ids(session: CSession) -> list[str]:
    s = session._state._ptr.contents
    return [_lib.intern_str(s.devour_pile[j]).decode() for j in range(s.devour_pile_count)]

def _influence(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.influence

def _legal_move_types(session: CSession) -> list[str]:
    return [m._move_type for m in session.legal_moves()]

def _end_main_phase(session: CSession):
    for m in session.legal_moves():
        if m._move_type == "end_main_phase":
            session.submit_move(m)
            return
    raise AssertionError("No end_main_phase move")

def _enter_eot(session: CSession):
    """Resolve end-of-turn phase entry."""
    for m in session.legal_moves():
        if m._move_type == "resolve_end_of_turn":
            session.submit_move(m)
            return
    # May need promote moves first
    while True:
        moves = session.legal_moves()
        types = {m._move_type for m in moves}
        if "promote_card" in types:
            # Promote the first available card
            pm = [m for m in moves if m._move_type == "promote_card"]
            session.submit_move(pm[0])
        elif "skip_promote" in types:
            session.submit_move([m for m in moves if m._move_type == "skip_promote"][0])
        elif "resolve_end_of_turn" in types:
            session.submit_move([m for m in moves if m._move_type == "resolve_end_of_turn"][0])
            return
        else:
            raise AssertionError(f"Unexpected EOT moves: {types}")


# ---------------------------------------------------------------------------
# Test: devour targets inner_circle, NOT hand
# ---------------------------------------------------------------------------
def test_zuggtmoy_devour_targets_inner_circle_not_hand():
    """Playing Zuggtmoy should present only inner_circle cards as devour
    targets, never hand cards."""
    eng = _engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["zuggtmoy", "noble"]},
        current_player="p1",
    )
    s = session._state._ptr.contents
    p1_idx = 0
    # Place a card in p1's inner_circle
    s.players[p1_idx].inner_circle[0] = _lib.intern(b"soldier")
    s.players[p1_idx].inner_circle_count = 1

    # Play Zuggtmoy
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "zuggtmoy":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Zuggtmoy not playable")

    # Should have pending generic for devour selection
    moves = session.legal_moves()
    rg_moves = [m for m in moves if m._move_type == "resolve_generic"]
    target_ids = {m.data.get("action_id") for m in rg_moves}

    # Only soldier (inner_circle) should be selectable, NOT noble (hand)
    assert "soldier" in target_ids, f"inner_circle soldier should be a devour target, got: {target_ids}"
    assert "noble" not in target_ids, f"hand card noble should NOT be a devour target, got: {target_ids}"
    assert "zuggtmoy" not in target_ids, f"zuggtmoy itself should NOT be a devour target, got: {target_ids}"

    session.destroy()


# ---------------------------------------------------------------------------
# Test: devouring inner_circle card removes it and grants 3 influence
# ---------------------------------------------------------------------------
def test_zuggtmoy_devour_from_inner_circle_grants_influence():
    """Devouring a card from inner_circle removes it to devour pile and
    grants 3 influence."""
    eng = _engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["zuggtmoy"]},
        current_player="p1",
    )
    s = session._state._ptr.contents
    p1_idx = 0
    s.players[p1_idx].inner_circle[0] = _lib.intern(b"soldier")
    s.players[p1_idx].inner_circle_count = 1

    assert "soldier" in _inner_circle_ids(session, "p1")
    assert _devour_pile_ids(session) == []
    inf_before = _influence(session)

    # Play Zuggtmoy
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "zuggtmoy":
            session.submit_move(m)
            break

    # Resolve devour: select soldier
    devour_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    assert len(devour_moves) == 1, f"Expected 1 devour target, got {len(devour_moves)}"
    session.submit_move(devour_moves[0])

    # Verify soldier moved from inner_circle to devour pile
    assert _inner_circle_ids(session, "p1") == [], f"soldier should be removed from inner_circle"
    assert "soldier" in _devour_pile_ids(session), f"soldier should be in devour pile"
    assert _influence(session) == inf_before + 3, f"Influence should be +3, got {_influence(session) - inf_before}"

    session.destroy()


# ---------------------------------------------------------------------------
# Test: EOT promote offers up to 2 other cards, excludes Zuggtmoy
# ---------------------------------------------------------------------------
def test_zuggtmoy_eot_promote_two_other_cards_excludes_self():
    """At end of turn with Zuggtmoy and 3 other played cards, promote
    should allow up to 2 promotions and exclude Zuggtmoy itself."""
    eng = _engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["zuggtmoy"]},
        current_player="p1",
    )
    s = session._state._ptr.contents
    p1_idx = 0
    # Place 3 other cards in played zone + zuggtmoy will be played
    s.players[p1_idx].played_cards[0] = _lib.intern(b"noble")
    s.players[p1_idx].played_cards[1] = _lib.intern(b"soldier")
    s.players[p1_idx].played_cards[2] = _lib.intern(b"house_guard")
    s.players[p1_idx].played_cards_count = 3

    # Play Zuggtmoy (devour first — we need something in inner_circle)
    s.players[p1_idx].inner_circle[0] = _lib.intern(b"noble")
    s.players[p1_idx].inner_circle_count = 1

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "zuggtmoy":
            session.submit_move(m)
            break

    # Devour the inner_circle card
    devour_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    session.submit_move(devour_moves[0])

    # Advance to end of turn
    _end_main_phase(session)

    # EOT: should have promote moves for played cards (excluding zuggtmoy)
    s = session._state._ptr.contents
    assert s.phase == PHASE_END_OF_TURN

    # Collect promote targets
    moves = session.legal_moves()
    promote_moves = [m for m in moves if m._move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}

    assert "zuggtmoy" not in promote_targets, f"Zuggtmoy should NOT be a promote target: {promote_targets}"
    assert "noble" in promote_targets, f"noble should be a promote target"
    assert "soldier" in promote_targets, f"soldier should be a promote target"
    assert "house_guard" in promote_targets, f"house_guard should be a promote target"

    # Promote first card
    session.submit_move(promote_moves[0])
    first_promoted = promote_moves[0].data["card_id"]

    # Should still have promote options (repeat_while_targets)
    moves2 = session.legal_moves()
    promote_moves2 = [m for m in moves2 if m._move_type == "promote_card"]
    assert len(promote_moves2) >= 1, f"Should still have promote options after first promotion: {[m._move_type for m in moves2]}"

    # The promoted card should no longer be selectable
    promote_targets2 = {m.data.get("card_id") for m in promote_moves2}
    assert first_promoted not in promote_targets2, f"Already-promoted {first_promoted} should not be re-selectable"

    # Promote second card
    session.submit_move(promote_moves2[0])

    # After second promotion (cap of 2), should move to resolve_end_of_turn
    moves3 = session.legal_moves()
    assert "resolve_end_of_turn" in {m._move_type for m in moves3}, (
        f"After 2 promotions, expected resolve_end_of_turn, got: {[m._move_type for m in moves3]}"
    )

    session.destroy()
