"""Ogremoch card behavior tests for C engine.

1. Play Ogremoch: gain 2 influence.
2. EOT: promote exactly 1 other played card (cannot self-promote).
3. EOT with Focus: Ambition: promote 2 other played cards (two separate opportunities).
"""
from __future__ import annotations

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import _make_engine, make_card_test_session

AMBITIOUS_CARD = "advocate"


def _inner_circle_ids(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].inner_circle[j]).decode()
                    for j in range(s.players[i].inner_circle_count)]
    return []


def _influence(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.influence


def _end_main_phase(session: CSession) -> None:
    for m in session.legal_moves():
        if m._move_type == "end_main_phase":
            session.submit_move(m)
            return
    raise AssertionError("No end_main_phase move")


def _set_played(session: CSession, pid: str, cards: list[str]) -> None:
    pi = 0
    s = session._state._ptr.contents
    ps = s.players[pi]
    for j, cid in enumerate(cards):
        ps.played_cards[j] = _lib.intern(cid.encode())
    ps.played_cards_count = len(cards)


# ---------------------------------------------------------------------------
# Test: play Ogremoch grants 2 influence
# ---------------------------------------------------------------------------
def test_ogremoch_gain_influence() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["ogremoch"]},
        current_player="p1",
    )
    inf_before = _influence(session)

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "ogremoch":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Ogremoch not playable")

    assert _influence(session) == inf_before + 2, "Should gain 2 influence"


# ---------------------------------------------------------------------------
# Test: EOT promotion without focus — exactly 1 promotion
# ---------------------------------------------------------------------------
def test_ogremoch_eot_one_promotion_no_focus() -> None:
    """Without Focus: Ambition, Ogremoch allows exactly 1 EOT promotion."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["ogremoch"]},
        current_player="p1",
    )
    # Place 2 non-ambition cards in played zone (simulating previous plays)
    _set_played(session, "p1", ["noble", "soldier"])

    # Play Ogremoch
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "ogremoch":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Ogremoch not playable")

    _end_main_phase(session)

    # Collect EOT promote moves
    moves = session.legal_moves()
    promote_moves = [m for m in moves if m._move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}

    # Ogremoch should NOT be a target
    assert "ogremoch" not in promote_targets, f"Ogremoch should not self-target: {promote_targets}"
    # Both noble and soldier should be available
    assert "noble" in promote_targets, f"noble should be a promote target, got: {promote_targets}"
    assert "soldier" in promote_targets, f"soldier should be a promote target, got: {promote_targets}"

    # Promote one card
    session.submit_move(promote_moves[0])
    first_promoted = promote_moves[0].data["card_id"]
    assert first_promoted in _inner_circle_ids(session, "p1")

    # After 1 promotion with no focus, should NOT have more promote moves
    moves2 = session.legal_moves()
    promote_moves2 = [m for m in moves2 if m._move_type == "promote_card"]
    assert len(promote_moves2) == 0, (
        f"After 1 promotion (no focus), expected no more promote; got {promote_moves2}"
    )
    # Should now have resolve_end_of_turn or skip_promote
    move_types2 = {m._move_type for m in moves2}
    assert "resolve_end_of_turn" in move_types2 or "skip_promote" in move_types2, (
        f"Expected resolve_end_of_turn or skip_promote, got: {move_types2}"
    )


# ---------------------------------------------------------------------------
# Test: EOT promotion with Focus: Ambition — 2 separate promotions
# ---------------------------------------------------------------------------
def test_ogremoch_eot_two_promotions_with_focus() -> None:
    """With Focus: Ambition (ambition card in hand), Ogremoch allows 2 EOT promotions."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["ogremoch", AMBITIOUS_CARD]},
        current_player="p1",
    )
    # Place 3 other cards in played zone
    _set_played(session, "p1", ["noble", "soldier", "house_guard"])

    # Play Ogremoch
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "ogremoch":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Ogremoch not playable")

    _end_main_phase(session)

    # --- First promotion ---
    moves = session.legal_moves()
    promote_moves = [m for m in moves if m._move_type == "promote_card"]
    assert len(promote_moves) >= 2, f"Expected at least 2 promote targets, got {len(promote_moves)}"

    # Ogremoch should NOT be a target
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert "ogremoch" not in promote_targets, f"Ogremoch should not self-target: {promote_targets}"

    session.submit_move(promote_moves[0])
    first_promoted = promote_moves[0].data["card_id"]
    assert first_promoted in _inner_circle_ids(session, "p1")

    # --- Second promotion (focus bonus) ---
    moves2 = session.legal_moves()
    promote_moves2 = [m for m in moves2 if m._move_type == "promote_card"]
    assert len(promote_moves2) >= 1, (
        f"With focus, should have second promotion available; got moves: {[m._move_type for m in moves2]}"
    )
    # Already promoted card should not be re-selectable
    promote_targets2 = {m.data.get("card_id") for m in promote_moves2}
    assert first_promoted not in promote_targets2, (
        f"Already-promoted {first_promoted} should not be re-selectable"
    )

    session.submit_move(promote_moves2[0])

    # --- After 2 promotions, should move to resolve_end_of_turn ---
    moves3 = session.legal_moves()
    promote_moves3 = [m for m in moves3 if m._move_type == "promote_card"]
    assert len(promote_moves3) == 0, (
        f"After 2 promotions (focus), expected no more promote; got {promote_moves3}"
    )
    move_types3 = {m._move_type for m in moves3}
    assert "resolve_end_of_turn" in move_types3 or "skip_promote" in move_types3, (
        f"Expected resolve_end_of_turn or skip_promote after 2 promotions, got: {move_types3}"
    )
