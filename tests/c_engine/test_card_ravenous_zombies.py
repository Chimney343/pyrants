"""Ravenous Zombies card behavior tests.

Verifies:
- Gain 1 power (always happens first)
- Assassinate targets are white troop only (not player troops)
- Assassinating a white troop moves it to trophy hall
- Full resolution leaves no pending generic moves
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

CARD_ID = "ravenous_zombies"
_SITE = "site_gauntlgrym"
_P1 = "p1"
_P2 = "p2"


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _resource(session: CSession, field: str) -> int:
    s = _sptr(session).contents
    if field == "power":
        return s.resource_pool.power
    if field == "influence":
        return s.resource_pool.influence
    return 0


def _trophy_hall(session: CSession, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.trophy_hall[j]).decode() for j in range(ps.trophy_hall_count)]


def _play_card(session: CSession, card_id: str = CARD_ID) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    raise AssertionError(f"{card_id} not playable")


def _resolve_generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if m.move_type == "resolve_generic"]


def test_ravenous_zombies_gains_1_power():
    """Playing Ravenous Zombies grants 1 power immediately before the assassinate prompt."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID, "noble"]},
        troops={_P1: {_SITE: [_P1, "white", None]}},
        current_player=_P1,
    )

    power_before = _resource(session, "power")
    _play_card(session)
    power_after = _resource(session, "power")

    assert power_after == power_before + 1, (
        f"Expected +1 power, got {power_before} -> {power_after}"
    )
    assert _has_pending_generic(session), "Should have pending assassinate after power gain"

    session.destroy()


def test_ravenous_zombies_assassinate_targets_white_troops_only():
    """Assassinate should only target white troops, never own or other player troops."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID, "noble"]},
        troops={_P1: {_SITE: [_P1, _P2, "white", None]}},
        current_player=_P1,
    )

    _play_card(session)

    assert _has_pending_generic(session), "Should have pending assassinate after play"

    moves = _resolve_generic_moves(session)
    target_ids = {m.data.get("target_id") for m in moves}

    assert len(moves) >= 1, "Should have at least one assassinate target"
    assert "2" in target_ids, "Slot 2 (white troop) should be a target"
    assert "0" not in target_ids, "Slot 0 (own troop) should NOT be a target"
    assert "1" not in target_ids, "Slot 1 (other player troop) should NOT be a target"

    session.destroy()


def test_ravenous_zombies_resolves_when_no_white_troops():
    """When no white troops exist on board, the assassinate is auto-skipped and card resolves."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID, "noble"]},
        troops={_P1: {_SITE: [_P1, _P2, None]}},
        current_player=_P1,
    )

    _play_card(session)

    assert _resource(session, "power") == 1, "Should still gain 1 power"

    assert not _has_pending_generic(session), (
        "Should auto-resolve when no valid white troop targets exist"
    )

    session.destroy()


def test_ravenous_zombies_assassinate_moves_white_to_trophy_hall():
    """Assassinating a white troop with Ravenous Zombies adds 'white' to the trophy hall."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID, "noble"]},
        troops={_P1: {_SITE: [_P1, "white", None]}},
        current_player=_P1,
    )

    _play_card(session)

    assert _resource(session, "power") == 1, "Should have gained 1 power"

    moves = _resolve_generic_moves(session)
    assert len(moves) >= 1, "Should have at least one assassinate target"

    session.submit_move(moves[0])

    trophy = _trophy_hall(session, _P1)
    assert "white" in trophy, f"Expected 'white' in p1 trophy hall, got {trophy}"
    assert not _has_pending_generic(session), "Should have no pending generics after resolution"

    session.destroy()


def test_ravenous_zombies_power_before_assassinate():
    """Power is gained before the assassinate choice is resolved."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID, "noble"]},
        troops={_P1: {_SITE: [_P1, "white", None]}},
        current_player=_P1,
    )

    _play_card(session)

    power = _resource(session, "power")
    assert power == 1, f"Power should be 1 before resolving assassinate, got {power}"

    # Now resolve assassinate
    moves = _resolve_generic_moves(session)
    session.submit_move(moves[0])

    assert _resource(session, "power") == 1, "Power should remain 1 after assassinate"
    assert not _has_pending_generic(session)

    session.destroy()


def test_ravenous_zombies_multiple_white_targets():
    """When multiple white troops exist at a site, each slot is offered as a distinct target."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID, "noble"]},
        troops={_P1: {_SITE: ["white", "white", _P1, None]}},
        current_player=_P1,
    )

    _play_card(session)

    assert _resource(session, "power") == 1

    moves = _resolve_generic_moves(session)
    target_ids = {m.data.get("target_id") for m in moves}

    assert "0" in target_ids, "Slot 0 (white troop) should be a target"
    assert "1" in target_ids, "Slot 1 (white troop) should be a target"
    assert "2" not in target_ids, "Slot 2 (own troop) should NOT be a target"
    assert len(target_ids) == 2, f"Expected 2 white targets, got {len(target_ids)}: {target_ids}"

    session.destroy()
