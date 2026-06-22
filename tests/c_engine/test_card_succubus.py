"""Succubus card behavior tests.

Verifies:
- Devour a card from hand (cost)
- Place a spy at a chosen board site
- Assassinate a troop at the same site (requires_last_selected_node)
- Assassinate targets both white and player troops (allow_white_troop)
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

_SITE = "site_gauntlgrym"
_P1 = "p1"
_P2 = "p2"
_WHITE = "white"


def _build_succubus_session() -> CSession:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["succubus", "noble"]},
        troops={
            _P2: {_SITE: [_P2, _WHITE, None, None]},
        },
        current_player=_P1,
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    return session


def _spies_available(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].spies_available


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return [_lib.intern_str(s.nodes[ni].spies[i]).decode() for i in range(s.nodes[ni].spy_count)]
    return []


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


def test_succubus_full_sequence() -> None:
    """Play Succubus end-to-end: devour → place spy → assassinate at same site."""
    session = _build_succubus_session()

    spies_before = _spies_available(session, _P1)
    assert spies_before >= 1, f"Need at least 1 spy, got {spies_before}"

    # --- Play Succubus ---
    play_move = None
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "succubus":
            play_move = m
            break
    assert play_move is not None, "Succubus not found in hand"
    session.submit_move(play_move)

    assert _has_pending_generic(session), "Expected pending generic after playing Succubus"

    # --- Step 1: Devour a card from hand ---
    devour_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "noble"
    ]
    if not devour_moves:
        all_moves = [(m.move_type, m.data) for m in session.legal_moves()]
        session.destroy()
        raise AssertionError(f"No devour move for 'noble'; legal moves: {all_moves}")

    session.submit_move(devour_moves[0])
    assert _has_pending_generic(session), "Expected pending generic after devour"

    # noble should be gone from hand (devoured)
    s = _sptr(session).contents
    pi = _session_player_index(session, _P1)
    hand_cards = [_lib.intern_str(s.players[pi].hand[i]).decode() for i in range(s.players[pi].hand_count)]
    assert "noble" not in hand_cards, "Devoured card should be removed from hand"

    # --- Step 2: Place a spy at a site ---
    spy_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE
    ]
    if not spy_moves:
        all_moves = [(m.move_type, m.data) for m in session.legal_moves()]
        session.destroy()
        raise AssertionError(f"No place-spy move for {_SITE}; legal moves: {all_moves}")

    session.submit_move(spy_moves[0])
    assert _has_pending_generic(session), "Expected pending generic after placing spy"

    # Spy should be at the site
    assert _P1 in _spies_at_node(session, _SITE), f"Expected p1 spy at {_SITE}"
    assert _spies_available(session, _P1) == spies_before - 1, (
        f"spies_available should decrease: {spies_before} → {spies_before - 1}"
    )

    # --- Step 3: Assassinate a troop at the same site ---
    assassinate_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    ]
    if not assassinate_moves:
        session.destroy()
        raise AssertionError("No assassinate moves available")

    # All assassinate moves must be constrained to the spy site
    for am in assassinate_moves:
        assert am.data.get("action_id") == _SITE, (
            f"Assassinate should be constrained to {_SITE}, got {am.data}"
        )

    # Find moves targeting p2 and white troops
    target_ids = [am.data.get("target_id") for am in assassinate_moves]
    has_p2 = any(t == "0" for t in target_ids if t is not None)
    has_white = any(t == "1" for t in target_ids if t is not None)

    assert has_p2, f"p2 troop (slot 0) should be targetable; targets: {target_ids}"
    assert has_white, f"white troop (slot 1) should be targetable; targets: {target_ids}"

    # Execute the assassination — pick the p2 troop (slot 0)
    p2_move = None
    for am in assassinate_moves:
        if am.data.get("target_id") == "0":
            p2_move = am
            break
    assert p2_move is not None, "Could not find move for p2 troop (slot 0)"

    session.submit_move(p2_move)

    # Card should be fully resolved
    assert not _has_pending_generic(session), "Expected no pending generic after full resolution"

    # p2 troop should be in p1's trophy hall
    trophy = _trophy_hall(session, _P1)
    assert _P2 in trophy, f"Expected {_P2} in p1 trophy hall, got {trophy}"

    session.destroy()


def test_succubus_assassinate_white_troop() -> None:
    """Succubus assassination should allow targeting white troops."""
    session = _build_succubus_session()

    # Play Succubus
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "succubus":
            session.submit_move(m)
            break

    # Devour
    for m in session.legal_moves():
        if m.move_type == "resolve_generic":
            session.submit_move(m)
            break

    # Place spy at the site
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE:
            session.submit_move(m)
            break

    # Verify white troop is targetable for assassination
    assassinate_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    ]
    target_ids = [am.data.get("target_id") for am in assassinate_moves]
    has_white = any(t == "1" for t in target_ids if t is not None)
    assert has_white, f"white troop should be targetable; targets: {target_ids}"

    # Execute assassination on white troop (slot 1)
    white_move = None
    for am in assassinate_moves:
        if am.data.get("target_id") == "1":
            white_move = am
            break
    assert white_move is not None, "Could not find move for white troop (slot 1)"

    session.submit_move(white_move)

    # White troop goes to p1's trophy hall
    trophy = _trophy_hall(session, _P1)
    assert _WHITE in trophy, f"Expected white in p1 trophy hall, got {trophy}"

    session.destroy()


def test_succubus_assassinate_constrained_to_spy_site() -> None:
    """Assassination must be offered only at the site where the spy was placed."""
    session = _build_succubus_session()

    # Play Succubus
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "succubus":
            session.submit_move(m)
            break

    # Devour
    for m in session.legal_moves():
        if m.move_type == "resolve_generic":
            session.submit_move(m)
            break

    # Place spy at _SITE
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE:
            session.submit_move(m)
            break

    # All assassination moves must target _SITE only
    assassinate_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    ]
    assert len(assassinate_moves) > 0, "Should have at least one assassination target"

    for am in assassinate_moves:
        assert am.data.get("action_id") == _SITE, (
            f"Assassinate should only target {_SITE}, got {am.data.get('action_id')}"
        )

    session.destroy()
