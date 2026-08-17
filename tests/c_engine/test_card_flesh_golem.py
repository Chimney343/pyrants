"""Flesh Golem card behavior tests.

Verifies:
- Gain 2 power (always happens)
- Optional devour of self (played_self)
- If devour taken → assassinate a troop
- If devour skipped → no assassinate (skip_advance_to_index)
"""

from __future__ import annotations

from engine_c.bindings.engine_bindings import _lib
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

CARD_ID = "flesh_golem"


def _build_session(*, with_p1_presence: bool = False) -> CSession:
    eng = _make_engine()
    troops: dict[str, dict[str, list[str | None]]] = {}
    if with_p1_presence:
        troops[_P1] = {_SITE: [_P1, _P2, None, None]}
    else:
        troops[_P2] = {_SITE: [_P2, None, None, None]}
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        troops=troops,
        current_player=_P1,
    )
    return session


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _barracks(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].barracks


def _resource(session: CSession, field: str) -> int:
    s = _sptr(session).contents
    if field == "power":
        return s.resource_pool.power
    if field == "influence":
        return s.resource_pool.influence
    return 0


def _devour_pile(session: CSession) -> list[str]:
    s = _sptr(session).contents
    return [_lib.intern_str(s.devour_pile[i]).decode() for i in range(s.devour_pile_count)]


def _trophy_hall(session: CSession, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    s = _sptr(session).contents
    ps = s.players[pi]
    return [_lib.intern_str(ps.trophy_hall[j]).decode() for j in range(ps.trophy_hall_count)]


def _play_card(session: CSession) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == CARD_ID:
            session.submit_move(m)
            return
    raise AssertionError(f"{CARD_ID} not playable")


def test_flesh_golem_gains_2_power() -> None:
    """Playing Flesh Golem grants 2 power immediately."""
    session = _build_session(with_p1_presence=True)

    power_before = _resource(session, "power")
    _play_card(session)
    power_after = _resource(session, "power")

    assert power_after == power_before + 2, (
        f"Expected +2 power, got {power_before} → {power_after}"
    )

    assert _has_pending_generic(session), "Should prompt for devour choice"

    session.destroy()


def test_flesh_golem_skip_devour_no_assassinate() -> None:
    """Skipping devour should NOT offer an assassinate — skip_advance_to_index jumps past it."""
    session = _build_session(with_p1_presence=True)

    barracks_before = _barracks(session, _P1)
    _play_card(session)

    assert _resource(session, "power") == 2, "Should have gained 2 power"

    # Find the skip move for the devour optional action
    skip_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") is None:
            skip_move = m
            break
    assert skip_move is not None, "Should have a skip/decline move for devour"

    session.submit_move(skip_move)

    # Card should be fully resolved — no assassinate pending
    assert not _has_pending_generic(session), (
        "Expected no pending generic after skipping devour; assassinate should be skipped"
    )

    # Barracks should not have changed (no troop was deployed)
    assert _barracks(session, _P1) == barracks_before, "Barracks should not change"

    session.destroy()


def test_flesh_golem_assassinate_targets_includes_white_troops() -> None:
    """Assassinate after devour should target both enemy player troops and white troops."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        troops={_P1: {_SITE: [_P1, "white", _P2, None]}},
        current_player=_P1,
    )

    _play_card(session)

    devour_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == CARD_ID:
            devour_move = m
            break
    assert devour_move is not None, "Should have devour move"
    session.submit_move(devour_move)

    assert _has_pending_generic(session), "Should have assassinate prompt"

    assassinate_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    ]
    target_ids = [m.data.get("target_id") for m in assassinate_moves]

    assert "1" in target_ids, f"White troop at slot 1 should be targetable, got targets: {target_ids}"
    assert "2" in target_ids, f"Enemy troop at slot 2 should be targetable, got targets: {target_ids}"
    assert "0" not in target_ids, f"Own troop at slot 0 should NOT be targetable, got targets: {target_ids}"

    session.destroy()


def test_flesh_golem_devour_then_assassinate() -> None:
    """Devouring Flesh Golem should offer an assassinate, and executing it works."""
    session = _build_session(with_p1_presence=True)

    _play_card(session)

    assert _has_pending_generic(session), "Expected devour prompt"

    # Find the devour self move
    devour_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == CARD_ID:
            devour_move = m
            break
    assert devour_move is not None, f"Should have devour move for {CARD_ID}; got: {[(m.move_type, m.data) for m in session.legal_moves()]}"

    session.submit_move(devour_move)

    # Flesh Golem should be in devour pile
    assert CARD_ID in _devour_pile(session), f"{CARD_ID} should be in devour pile"

    # Now should have assassinate prompt
    assert _has_pending_generic(session), "Should have assassinate move after devour"

    assassinate_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    ]
    assert len(assassinate_moves) > 0, "Should have at least one assassination target"

    # Pick the first assassination target and execute
    session.submit_move(assassinate_moves[0])

    # Card should be fully resolved
    assert not _has_pending_generic(session), "Expected no pending generic after full resolution"

    # p2 troop should be in p1's trophy hall
    trophy = _trophy_hall(session, _P1)
    assert _P2 in trophy, f"Expected {_P2} in p1 trophy hall after assassinate, got {trophy}"

    session.destroy()
