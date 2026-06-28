"""Yan-C-Bin card behavior tests.

Verifies:
- Place a spy at a chosen board site
- Assassinate a troop at the same site (requires_last_selected_node)
- Assassinate targets both player and white troops (allow_white_troop)
- If Guile focus is met, offer a bonus spy placement after assassination
- Bonus spy can be placed at any valid site (not constrained to assassination site)
"""
from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_SITE_A = "site_gauntlgrym"
_SITE_B = "site_menzoberranzan"
_P1 = "p1"
_P2 = "p2"
_WHITE = "white"


def _build_yan_session(*, focus_met: bool = True) -> CSession:
    """Build a session with Yan-C-Bin in hand.

    If focus_met=True, night_hag (Guile) is already played.
    The test site _SITE_A has p2 and white troops for assassination.
    """
    eng = _make_engine()
    played = ["night_hag"] if focus_met else []
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["yan_c_bin"]},
        troops={
            _P2: {
                _SITE_A: [_P2, _WHITE, None, None],
                _SITE_B: [_WHITE, _WHITE, _P2, _P2],
            },
        },
        current_player=_P1,
    )
    s = _sptr(session).contents
    s.phase = PHASE_MAIN
    pi = _session_player_index(session, _P1)
    ps = s.players[pi]
    ps.played_cards_count = min(len(played), 20)
    for j, cid in enumerate(played):
        ps.played_cards[j] = _lib.intern(cid.encode())
    return session


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return [_lib.intern_str(s.nodes[ni].spies[i]).decode() for i in range(s.nodes[ni].spy_count)]
    return []


def _spies_available(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].spies_available


def _trophy_hall(session: CSession, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    s = _sptr(session).contents
    ps = s.players[pi]
    return [_lib.intern_str(ps.trophy_hall[j]).decode() for j in range(ps.trophy_hall_count)]


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_yan_c_bin_full_sequence_with_focus() -> None:
    """Full Yan-C-Bin sequence: spy → assassinate at same site → bonus spy."""
    session = _build_yan_session(focus_met=True)

    spies_before = _spies_available(session, _P1)
    assert spies_before >= 2, f"Need at least 2 spies (one for base, one for bonus), got {spies_before}"

    # --- Play Yan-C-Bin ---
    play_move = None
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "yan_c_bin":
            play_move = m
            break
    assert play_move is not None, "Yan-C-Bin not found in hand"
    session.submit_move(play_move)
    assert _has_pending_generic(session), "Expected pending generic after playing Yan-C-Bin"

    # --- Step 1: Place a spy at _SITE_A ---
    spy_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE_A
    ]
    if not spy_moves:
        all_moves = [(m.move_type, m.data) for m in session.legal_moves()]
        session.destroy()
        raise AssertionError(f"No place-spy move for {_SITE_A}; legal moves: {all_moves}")

    session.submit_move(spy_moves[0])
    assert _has_pending_generic(session), "Expected pending generic after placing spy"

    # Spy should be at the site
    assert _P1 in _spies_at_node(session, _SITE_A), f"Expected {_P1} spy at {_SITE_A}"
    assert _spies_available(session, _P1) == spies_before - 1, (
        f"spies_available should decrease: {spies_before} → {spies_before - 1}"
    )

    # --- Step 2: Assassinate — must be constrained to _SITE_A only ---
    assassinate_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    ]
    if not assassinate_moves:
        session.destroy()
        raise AssertionError("No assassinate moves available")

    # All assassinate moves must be constrained to the spy site
    for am in assassinate_moves:
        assert am.data.get("action_id") == _SITE_A, (
            f"Assassinate should be constrained to {_SITE_A}, got {am.data}"
        )

    # Verify both player (slot 0 = p2) and white (slot 1) troops are targetable
    target_ids = [am.data.get("target_id") for am in assassinate_moves]
    has_p2 = any(t == "0" for t in target_ids if t is not None)
    has_white = any(
        t is not None and _spy_at_slot_is_white(session, _SITE_A, int(t))
        for t in target_ids if t is not None
    )
    assert has_p2, f"p2 troop should be targetable (slot 0); targets: {target_ids}"
    assert has_white, f"white troop should be targetable (slot 1); targets: {target_ids}"

    # --- Execute assassination on p2 troop (slot 0) ---
    p2_move = None
    for am in assassinate_moves:
        if am.data.get("target_id") == "0":
            p2_move = am
            break
    assert p2_move is not None, "Could not find move for p2 troop (slot 0)"
    session.submit_move(p2_move)

    # p2 troop should be in p1's trophy hall
    trophy = _trophy_hall(session, _P1)
    assert _P2 in trophy, f"Expected {_P2} in {_P1} trophy hall after assassination, got {trophy}"

    # --- Step 3: Bonus spy placement (focus met) ---
    assert _has_pending_generic(session), "Expected pending generic for bonus spy placement"

    bonus_spy_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    ]
    assert len(bonus_spy_moves) > 0, "Bonus spy placement should be available"

    # Bonus spy should be placeable at any valid site (not constrained to assassination site)
    bonus_sites = {m.data.get("action_id") for m in bonus_spy_moves}
    assert len(bonus_sites) > 1, (
        f"Bonus spy should be placeable at multiple sites, got only: {bonus_sites}"
    )

    # Place bonus spy at _SITE_B (different from assassination site)
    bonus_move = next(
        (m for m in bonus_spy_moves if m.data.get("action_id") == _SITE_B),
        None,
    )
    if bonus_move is None:
        all_bonus = [(m.data.get("action_id"), m.data.get("target_id")) for m in bonus_spy_moves]
        session.destroy()
        raise AssertionError(f"No bonus spy move for {_SITE_B}; bonus moves: {all_bonus}")
    session.submit_move(bonus_move)

    # Bonus spy should be at _SITE_B
    assert _P1 in _spies_at_node(session, _SITE_B), f"Expected {_P1} bonus spy at {_SITE_B}"
    assert _spies_available(session, _P1) == spies_before - 2, (
        f"After bonus spy, spies_available should be {spies_before - 2}"
    )

    # Card should be fully resolved
    assert not _has_pending_generic(session), "Card should be fully resolved"

    session.destroy()


def test_yan_c_bin_assassinate_constrained_to_spy_site() -> None:
    """Assassination moves must target only the site where the spy was placed."""
    session = _build_yan_session(focus_met=True)

    # Play card
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "yan_c_bin":
            session.submit_move(m)
            break

    # Place spy at _SITE_A
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE_A:
            session.submit_move(m)
            break

    # Check assassination constraint
    assassinate_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    ]
    assert len(assassinate_moves) > 0, "Should have at least one assassination target"

    for am in assassinate_moves:
        assert am.data.get("action_id") == _SITE_A, (
            f"Assassinate should only target {_SITE_A}, got {am.data.get('action_id')}"
        )

    session.destroy()


def test_yan_c_bin_no_bonus_spy_without_focus() -> None:
    """Without Guile focus, the bonus spy placement should not be offered."""
    session = _build_yan_session(focus_met=False)

    # Play card
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "yan_c_bin":
            session.submit_move(m)
            break

    # Place spy
    for m in session.legal_moves():
        if m.move_type == "resolve_generic":
            session.submit_move(m)
            break

    # Assassinate
    for m in session.legal_moves():
        if m.move_type == "resolve_generic":
            session.submit_move(m)
            break

    # No bonus spy — card should be fully resolved
    assert not _has_pending_generic(session), (
        "Card should be resolved without bonus spy when focus is not met"
    )

    # Only 1 spy total (the base one)
    p1_spy_count = 0
    s = _sptr(session).contents
    for ni in range(s.node_count):
        for si in range(s.nodes[ni].spy_count):
            if s.nodes[ni].spies[si] == _lib.intern(_P1.encode()):
                p1_spy_count += 1
    assert p1_spy_count == 1, f"Without focus, only 1 spy should be placed, got {p1_spy_count}"

    session.destroy()


def test_yan_c_bin_assassinate_targets_white_troops() -> None:
    """Yan-C-Bin assassination should allow targeting white troops (allow_white_troop)."""
    session = _build_yan_session(focus_met=True)

    # Play card
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "yan_c_bin":
            session.submit_move(m)
            break

    # Place spy at _SITE_A (has white troop in slot 1)
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE_A:
            session.submit_move(m)
            break

    # Find and execute assassination on white troop (slot 1)
    ass_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    white_move = next((m for m in ass_moves if m.data.get("target_id") == "1"), None)
    assert white_move is not None, f"White troop (slot 1) should be targetable; moves: {[m.data for m in ass_moves]}"

    session.submit_move(white_move)

    # White troop should be in p1's trophy hall
    trophy = _trophy_hall(session, _P1)
    assert _WHITE in trophy, f"Expected white in {_P1} trophy hall, got {trophy}"

    session.destroy()


def _spy_at_slot_is_white(session: CSession, node_id: str, slot: int) -> bool:
    """Check if slot `slot` at `node_id` contains a white troop."""
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            if slot < 0 or slot >= s.nodes[ni].troop_slot_count:
                return False
            occ = s.nodes[ni].troop_slots[slot]
            occ_str = _lib.intern_str(occ)
            return occ_str is not None and occ_str.decode() == _WHITE
    return False
