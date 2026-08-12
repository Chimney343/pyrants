"""Watcher of Thay card behavior tests.

Modal choice: choose exactly one mode.
- Option 1: Place a spy at a board site.
- Option 2: Return one of your spies and gain 3 influence.
"""

from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_SITE = "site_gauntlgrym"
_P1 = "p1"
_P2 = "p2"


def _spies_at_node(session, node_id):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return [_lib.intern_str(s.nodes[ni].spies[i]).decode() for i in range(s.nodes[ni].spy_count)]
    return []


def _spies_available(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].spies_available


def _resource_power(session):
    return _sptr(session).contents.resource_pool.power


def _resource_influence(session):
    return _sptr(session).contents.resource_pool.influence


def _has_pending_generic(session):
    return bool(_sptr(session).contents.pending_generic)


def _build_session(**kwargs):
    defaults = {
        "player_ids": [_P1, _P2],
        "hand": {_P1: ["watcher_of_thay"]},
        "current_player": _P1,
    }
    defaults.update(kwargs)
    eng = _make_engine()
    session = make_card_test_session(eng, defaults.pop("player_ids"), **defaults)
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    return session


def _play_card(session, card_id="watcher_of_thay"):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_option_1_place_spy():
    """Choose option 1: place a spy at a board site."""
    session = _build_session()
    spies_before = _spies_available(session, _P1)

    _play_card(session)

    assert _has_pending_generic(session), "Modal choice should be pending after play"

    assert _P1 not in _spies_at_node(session, _SITE), "No spy at site before placement"

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_1":
            assert m.data.get("target_id") != "unavailable", "option_1 should be available"
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("option_1 not found in resolve_generic moves")

    assert _has_pending_generic(session), "Spy placement target selection should be pending"

    spy_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE:
            spy_move = m
            break
    assert spy_move is not None, f"Place-spy move for {_SITE} not found"
    session.submit_move(spy_move)

    assert not _has_pending_generic(session)
    assert _P1 in _spies_at_node(session, _SITE)
    assert _spies_available(session, _P1) == spies_before - 1

    session.destroy()


def test_option_2_return_spy_gains_3_influence():
    """Choose option 2: return one of your spies and gain 3 influence."""
    session = _build_session(
        spies={_SITE: [_P1]},
    )
    spies_avail_before = _spies_available(session, _P1)
    influence_before = _resource_influence(session)
    power_before = _resource_power(session)

    _play_card(session)

    assert _has_pending_generic(session)

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2":
            assert m.data.get("target_id") != "unavailable", "option_2 should be available when spy exists"
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("option_2 not found in resolve_generic moves")

    assert _has_pending_generic(session), "Spy return target selection should be pending"

    return_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE:
            return_move = m
            break
    assert return_move is not None, f"Return-spy move for {_SITE} not found"
    session.submit_move(return_move)

    assert not _has_pending_generic(session)
    assert _P1 not in _spies_at_node(session, _SITE), "Spy should be returned from board"
    assert _spies_available(session, _P1) == spies_avail_before + 1, "Returned spy should be available"
    assert _resource_influence(session) == influence_before + 3, "Should gain 3 influence"
    assert _resource_power(session) == power_before, "Should NOT gain power (no focus clause)"

    session.destroy()


def test_both_options_available():
    """With a spy on board, both option_1 and option_2 should be available."""
    session = _build_session(
        spies={_SITE: [_P1]},
    )

    _play_card(session)

    assert _has_pending_generic(session)

    options = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    option_ids = {m.data.get("action_id") for m in options}

    assert "option_1" in option_ids, f"option_1 should be available; got {option_ids}"
    assert "option_2" in option_ids, f"option_2 should be available; got {option_ids}"

    opt2_moves = [m for m in options if m.data.get("action_id") == "option_2"]
    assert opt2_moves[0].data.get("target_id") != "unavailable", "option_2 should be viable with spy on board"

    session.destroy()


def test_option_2_unavailable_without_spies():
    """Without any spies on the board, option_2 should be unavailable."""
    session = _build_session()

    _play_card(session)

    assert _has_pending_generic(session)

    options = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    option_ids = {m.data.get("action_id") for m in options}

    assert "option_1" in option_ids, "option_1 should always be available"

    opt2_moves = [m for m in options if m.data.get("action_id") == "option_2"]
    if len(opt2_moves) > 0:
        assert opt2_moves[0].data.get("target_id") == "unavailable", (
            "option_2 should be unavailable when no spies on board"
        )

    session.destroy()


def test_option_2_only_allows_own_spies():
    """When both own and opponent spies at a site, option_2 should only target own spies."""
    session = _build_session(
        spies={_SITE: [_P1, _P2]},
    )

    _play_card(session)

    assert _has_pending_generic(session)

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2":
            assert m.data.get("target_id") != "unavailable", "option_2 should be available when own spy exists"
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("option_2 not found in resolve_generic moves")

    assert _has_pending_generic(session), "Spy return target selection should be pending"

    return_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE
    ]
    assert return_moves, f"Should have return-spy moves for {_SITE}"
    session.submit_move(return_moves[0])

    assert not _has_pending_generic(session)
    remaining_spies = _spies_at_node(session, _SITE)
    assert _P1 not in remaining_spies, "Own spy should be returned"
    assert _P2 in remaining_spies, "Opponent spy should remain"

    session.destroy()


def test_option_1_available_even_without_spies():
    """Option 1 (place spy) should be available even with no spies on board."""
    session = _build_session()

    _play_card(session)

    assert _has_pending_generic(session)

    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_1":
            assert m.data.get("target_id") != "unavailable", "option_1 should be available"
            break
    else:
        session.destroy()
        raise AssertionError("option_1 not found when it should be available")

    session.destroy()
