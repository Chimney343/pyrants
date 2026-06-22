"""Graz'zt card behavior tests — option_2: return spies + supplant at returned sites, repeating."""

from __future__ import annotations

import pytest

from engine_c.bindings.engine_bindings import Sym, _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)


def _node_state(session: CSession, node_id: str):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return s.nodes[ni]
    return None


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    ns = _node_state(session, node_id)
    if ns is None:
        return []
    return [_lib.intern_str(ns.spies[i]).decode() for i in range(ns.spy_count)]


def _troops_at_node(session: CSession, node_id: str) -> list[str | None]:
    ns = _node_state(session, node_id)
    if ns is None:
        return []
    out: list[str | None] = []
    for i in range(ns.troop_slot_count):
        owned = ns.troop_slots[i]
        if owned == Sym(0):
            out.append(None)
        else:
            s = _lib.intern_str(owned)
            out.append(s.decode() if s else str(int(owned)))
    return out


def _spies_available(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].spies_available


def _barracks(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].barracks


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
# Programmatic session helpers
# ---------------------------------------------------------------------------

_SITES = ["site_gauntlgrym", "site_jhachalkhyn", "site_gracklstugh"]
_P1 = "p1"
_P2 = "p2"


def _build_grazzt_session() -> CSession:
    eng = _make_engine()
    spies = {s: [_P1] for s in _SITES}
    troops = {
        _P2: {
            "site_jhachalkhyn": [_P2, None, None, None],
        }
    }
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["grazzt"]},
        spies=spies,
        troops=troops,
        current_player=_P1,
    )
    # Adjust p1's available spies: 5 base − 3 placed = 2 remaining
    s = _sptr(session).contents
    pi = _session_player_index(session, _P1)
    s.players[pi].spies_available -= 3
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_grazzt_option_2_repeats_for_each_spy() -> None:
    """Play Graz'zt option_2 and verify: return spy → supplant at returned site → repeat."""
    session = _build_grazzt_session()

    before_available = _spies_available(session, _P1)
    assert before_available == 2, f"Expected 2 available spies (5−3), got {before_available}"
    for site in _SITES:
        assert _P1 in _spies_at_node(session, site), f"Expected p1 spy at {site}"

    # Play Graz'zt
    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "grazzt":
            session.submit_move(m)
            break
    else:
        pytest.fail("Graz'zt not playable")

    assert _has_pending_generic(session)

    # Modal choice: pick option_2
    modal_moves = session.legal_moves()
    opt2 = [m for m in modal_moves if m.data.get("action_id") == "option_2"]
    assert opt2, f"option_2 not in modal moves: {[m.data for m in modal_moves]}"
    session.submit_move(opt2[0])

    # Now iterate: return spy → supplant → repeat
    for cycle in range(3):
        view = build_c_game_view(session)
        legal = [m for m in view.legal_moves if m.move_type == "resolve_generic"]

        spy_returns = [m for m in legal if "Return spy" in m.label]
        assert spy_returns, f"Cycle {cycle}: no return-spy moves, labels={[m.label for m in legal]}"

        # Each should only show sites with p1's own spies
        spy_sites = [m.move.data.get("action_id") for m in spy_returns]
        for s in spy_sites:
            actual_spies = _spies_at_node(session, s)
            msg = (
                f"Cycle {cycle}: return_spy offered site {s} but p1 spies there are {actual_spies}"
            )
            assert _P1 in actual_spies, msg

        chosen_spy_site = spy_sites[0]
        chosen_move = spy_returns[0].move
        session.submit_move(chosen_move)

        assert _has_pending_generic(session)

        view = build_c_game_view(session)
        supplants = [m for m in view.legal_moves if m.move_type == "resolve_generic"]

        # After returning a spy, supplant must be constrained to that site
        supplant_sites = [m.move.data.get("action_id") for m in supplants]
        assert len(supplant_sites) <= 1 or all(s == chosen_spy_site for s in supplant_sites), (
            f"Cycle {cycle}: supplant should only target {chosen_spy_site}, got {supplant_sites}"
        )
        assert chosen_spy_site in supplant_sites, (
            f"Cycle {cycle}: supplant not offered at {chosen_spy_site}"
        )

        # Verify "Supplant" label, not "Remove"
        for sm in supplants:
            assert "Supplant" in sm.label or "supplant" in sm.label, (
                f"Cycle {cycle}: expected 'Supplant' label, got '{sm.label}'"
            )

        session.submit_move(supplants[0].move)

    # After 3 cycles, card should be fully resolved
    assert not _has_pending_generic(session), "Expected no pending generic after 3 cycles"

    # Final state assertions
    # p1 should have all 3 spies returned
    assert _spies_available(session, _P1) == 5, (
        f"Expected all spies returned (5 available), got {_spies_available(session, _P1)}"
    )
    for site in _SITES:
        assert _P1 not in _spies_at_node(session, site), f"Spy should not remain at {site}"

    # p1 should have supplanted — barracks reduced by 3 for troops placed
    assert _barracks(session, _P1) == 40 - 3, (
        f"Expected 37 barracks (40−3 supplants), got {_barracks(session, _P1)}"
    )

    # Only the p2 troop from jhachalkhyn goes to trophy (white troops do not)
    trophy = _trophy_hall(session, _P1)
    assert trophy.count(_P2) == 1, f"Expected 1 p2 trophy from jhachalkhyn, got {trophy}"

    # p1 troops should now occupy the supplanted slots at each site
    for site in _SITES:
        troops = _troops_at_node(session, site)
        assert _P1 in troops, f"Expected p1 troop at {site} after supplant, got {troops}"

    session.destroy()


def test_grazzt_option_2_spy_owner_filtering() -> None:
    """Return-spy selection respects spy_owner='self' — does not offer sites with only opponent spies."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["grazzt"]},
        spies={"site_jhachalkhyn": [_P2]},
        troops={_P2: {"site_jhachalkhyn": [_P2, None, None, None]}},
        current_player=_P1,
    )

    # Play Graz'zt → option_2
    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "grazzt":
            session.submit_move(m)
            break
    opt2 = [m for m in session.legal_moves() if m.data.get("action_id") == "option_2"]
    assert opt2, "option_2 missing"
    session.submit_move(opt2[0])

    view = build_c_game_view(session)
    legal = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    spy_sites = [m.move.data.get("action_id") for m in legal if "Return spy" in m.label]
    assert "site_jhachalkhyn" not in spy_sites, (
        f"Should not offer p2 spy site for return; got {spy_sites}"
    )

    session.destroy()


def test_grazzt_option_2_supplant_constrained_to_returned_site() -> None:
    """After returning a spy, supplant is only offered at that same site."""
    session = _build_grazzt_session()

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "grazzt":
            session.submit_move(m)
            break
    opt2 = [m for m in session.legal_moves() if m.data.get("action_id") == "option_2"]
    session.submit_move(opt2[0])

    # Return spy from site_gauntlgrym
    view = build_c_game_view(session)
    returns = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    gaunt = [m for m in returns if m.move.data.get("action_id") == "site_gauntlgrym"]
    assert gaunt, f"No return-spy move for gauntlgrym; sites: {[m.move.data for m in returns]}"
    session.submit_move(gaunt[0].move)

    # Now supplant should only be offered at gauntlgrym, not other sites with p1 spies
    view = build_c_game_view(session)
    supplant_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    supplant_sites = [m.move.data.get("action_id") for m in supplant_moves]

    assert "site_gauntlgrym" in supplant_sites, "Should allow supplant at gauntlgrym"
    assert "site_jhachalkhyn" not in supplant_sites, "Should NOT allow supplant at jhachalkhyn"
    assert "site_gracklstugh" not in supplant_sites, "Should NOT allow supplant at gracklstugh"

    session.destroy()
