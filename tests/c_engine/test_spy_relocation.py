"""Spy relocation when all of a player's spies are already placed.

Rulebook 337-338: "If you take this action while all your spies are already
placed, you may either do nothing or first return one of your spies and then
place it."

The engine previously emitted zero targets in that state, soft-locking any
``place_spy`` action (e.g. Air Elemental option_1). These tests lock in the new
behavior: a decline move plus (source, destination) relocation pairs.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_P1 = "p1"
_P2 = "p2"
_SITE_A = "site_gauntlgrym"
_SITE_B = "site_blingdenfire"
_SITE_C = "site_menzoberranzan"

_UNAVAILABLE = "unavailable"


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return [_lib.intern_str(s.nodes[ni].spies[i]).decode() for i in range(s.nodes[ni].spy_count)]
    return []


def _board_spy_count(session: CSession, pid: str) -> int:
    s = _sptr(session).contents
    count = 0
    for ni in range(s.node_count):
        for i in range(s.nodes[ni].spy_count):
            if s.nodes[ni].spies[i] == _lib.intern(pid.encode()):
                count += 1
    return count


def _spies_available(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].spies_available


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _resolve_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if m.move_type == "resolve_generic"]


def _decline_moves(session: CSession) -> list:
    return [m for m in _resolve_moves(session) if m.data.get("action_id") is None]


def _relocation_moves(session: CSession) -> list:
    return [
        m for m in _resolve_moves(session)
        if m.data.get("action_id") is not None and m.data.get("target_id") is not None
    ]


def _supply_moves(session: CSession) -> list:
    return [
        m for m in _resolve_moves(session)
        if m.data.get("action_id") is not None and m.data.get("target_id") is None
    ]


def _build_session(*, spies: dict[str, list[str]] | None = None,
                   spies_available: int | None = None,
                   card: str = "rath_modar") -> CSession:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [card]},
        deck={_P1: ["soldier", "noble", "priestess_of_lolth"]},
        spies=spies,
        current_player=_P1,
    )
    s = _sptr(session).contents
    s.phase = PHASE_MAIN
    if spies_available is not None:
        pi = _session_player_index(session, _P1)
        s.players[pi].spies_available = spies_available
    return session


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


def _submit_move_matching(session: CSession, pred) -> None:
    for m in session.legal_moves():
        if pred(m):
            session.submit_move(m)
            return
    available = [m.data for m in _resolve_moves(session)]
    session.destroy()
    raise AssertionError(f"no matching move; available: {available}")


# ---------------------------------------------------------------------------
# Relocation move generation
# ---------------------------------------------------------------------------


def test_spy_relocation_offers_moves_with_no_unavailable_tag():
    """spies_available=0 with own spies on board → relocation moves, no placeholder."""
    session = _build_session(spies={_SITE_A: [_P1], _SITE_B: [_P1]}, spies_available=0)
    _play_card(session, "rath_modar")
    assert _has_pending_generic(session)

    moves = _resolve_moves(session)
    assert len(_relocation_moves(session)) > 0, f"expected relocation moves; got {[m.data for m in moves]}"
    assert not any(m.data.get("target_id") == _UNAVAILABLE for m in moves), (
        f"no move may be tagged unavailable; got {[m.data for m in moves]}"
    )
    session.destroy()


def test_spy_relocation_applies_source_to_destination():
    """Applying a relocation removes the spy from source and adds it to destination."""
    session = _build_session(spies={_SITE_A: [_P1], _SITE_B: [_P1]}, spies_available=0)
    spies_before = _board_spy_count(session, _P1)
    _play_card(session, "rath_modar")

    relocation = _relocation_moves(session)[0]
    source = relocation.data["target_id"]
    dest = relocation.data["action_id"]
    assert source != dest

    session.submit_move(relocation)

    assert not _has_pending_generic(session), "card should resolve after relocation"
    assert _P1 not in _spies_at_node(session, source), f"source {source} should lose the spy"
    assert _P1 in _spies_at_node(session, dest), f"destination {dest} should gain the spy"
    assert _spies_available(session, _P1) == 0, "spies_available must stay 0"
    assert _board_spy_count(session, _P1) == spies_before, "total board spy count unchanged"
    session.destroy()


def test_spy_relocation_excludes_destination_with_own_spy():
    """A destination that already holds one of the player's spies is never offered."""
    session = _build_session(spies={_SITE_A: [_P1], _SITE_B: [_P1]}, spies_available=0)
    _play_card(session, "rath_modar")

    destinations = {m.data["action_id"] for m in _relocation_moves(session)}
    assert _SITE_A not in destinations, f"{_SITE_A} must be excluded (has own spy)"
    assert _SITE_B not in destinations, f"{_SITE_B} must be excluded (has own spy)"
    assert _SITE_C in destinations, f"{_SITE_C} should be a legal destination; got {sorted(destinations)}"
    session.destroy()


def test_spy_supply_placement_regression():
    """spies_available>0 keeps placing from supply: decrements and grows the board."""
    session = _build_session(spies_available=5)
    spies_before = _board_spy_count(session, _P1)
    avail_before = _spies_available(session, _P1)
    _play_card(session, "rath_modar")

    assert len(_supply_moves(session)) > 0, "expected supply-placement moves"
    assert len(_relocation_moves(session)) == 0, "no relocation moves when supply is available"
    supply = _supply_moves(session)[0]
    dest = supply.data["action_id"]

    session.submit_move(supply)

    assert not _has_pending_generic(session)
    assert _P1 in _spies_at_node(session, dest)
    assert _spies_available(session, _P1) == avail_before - 1
    assert _board_spy_count(session, _P1) == spies_before + 1
    session.destroy()


def test_spy_relocation_decline_only_when_no_spies_on_board():
    """spies_available=0 and no own spies → exactly one move (decline), no dead end."""
    session = _build_session(spies_available=0)
    _play_card(session, "rath_modar")

    moves = _resolve_moves(session)
    assert len(moves) == 1, f"expected exactly one decline move; got {[m.data for m in moves]}"
    decline = moves[0]
    assert decline.data.get("action_id") is None
    assert decline.data.get("target_id") is None

    session.submit_move(decline)

    assert not _has_pending_generic(session), "card should resolve after declining"
    assert _board_spy_count(session, _P1) == 0, "state unchanged"
    session.destroy()


def test_spy_relocation_decline_present_alongside_relocations():
    """The decline is present in every spies_available=0 state, next to relocations."""
    session = _build_session(spies={_SITE_A: [_P1], _SITE_B: [_P1]}, spies_available=0)
    _play_card(session, "rath_modar")

    assert len(_decline_moves(session)) == 1, "exactly one decline move"
    assert len(_relocation_moves(session)) > 0, "relocations present alongside decline"
    session.destroy()


# ---------------------------------------------------------------------------
# Air Elemental soft-lock regression
# ---------------------------------------------------------------------------


def test_air_elemental_option_1_selectable_when_all_spies_placed():
    """Air Elemental option_1 (place_spy) is selectable end to end when all
    spies are placed and own spies sit on the board."""
    session = _build_session(
        spies={_SITE_A: [_P1], _SITE_B: [_P1]}, spies_available=0, card="air_elemental"
    )
    _play_card(session, "air_elemental")

    options = _resolve_moves(session)
    option_1 = next((m for m in options if m.data.get("action_id") == "option_1"), None)
    assert option_1 is not None, f"option_1 not offered; got {[m.data for m in options]}"
    assert option_1.data.get("target_id") != _UNAVAILABLE, "option_1 must not be unavailable"

    session.submit_move(option_1)

    # Now selecting the spy placement (decline + relocation pairs).
    assert _has_pending_generic(session)
    relocations = _relocation_moves(session)
    assert len(relocations) > 0, f"expected relocation moves; got {[m.data for m in _resolve_moves(session)]}"

    relocation = relocations[0]
    source = relocation.data["target_id"]
    dest = relocation.data["action_id"]
    session.submit_move(relocation)

    assert _P1 not in _spies_at_node(session, source)
    assert _P1 in _spies_at_node(session, dest)
    assert not _has_pending_generic(session), "Air Elemental should fully resolve"
    session.destroy()
