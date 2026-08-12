"""Masters of Sorcere card behavior tests.

Modal choice: choose exactly one mode.
- Option 1: place 2 spies.
- Option 2: return one of your spies and gain 4 power.
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _session_player_index,
    _sptr,
    make_card_test_session,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_CARD = "masters_of_sorcere"
_P1 = "p1"
_P2 = "p2"
_SITE_A = "site_gauntlgrym"
_SITE_B = "site_blingdenfire"
_SITE_C = "site_chaulssin"


def _power(session: CSession) -> int:
    return _sptr(session).contents.resource_pool.power


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


def _has_pending_generic(session: CSession) -> bool:
    return any(m.move_type == "resolve_generic" for m in session.legal_moves())


def _play_card(session: CSession) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == _CARD:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{_CARD} not in hand")


def _resolve_option(session: CSession, option_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == option_id:
            session.submit_move(m)
            return
    available = [m.data for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.destroy()
    raise AssertionError(f"{option_id} not found in resolve_generic moves, available: {available}")


def _resolve_spy_placement(session: CSession, node_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == node_id:
            session.submit_move(m)
            return
    available = [m.data for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.destroy()
    raise AssertionError(f"Place-spy move for {node_id} not found, available: {available}")


def _build_session(**kwargs) -> CSession:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    defaults = {
        "player_ids": [_P1, _P2],
        "hand": {_P1: [_CARD]},
        "current_player": _P1,
    }
    defaults.update(kwargs)
    return make_card_test_session(eng, defaults.pop("player_ids"), **defaults)


# ---------------------------------------------------------------------------
# Modal choice
# ---------------------------------------------------------------------------


def test_modal_has_two_options():
    """After playing card, modal choice presents both option_1 and option_2."""
    session = _build_session(spies={_SITE_A: [_P1]})
    _play_card(session)
    assert _has_pending_generic(session)

    options = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    option_ids = {m.data.get("action_id") for m in options}

    assert option_ids == {"option_1", "option_2"}, f"Expected both options; got {option_ids}"

    session.destroy()


# ---------------------------------------------------------------------------
# Option 1 — place two spies
# ---------------------------------------------------------------------------


def test_option_1_places_two_spies():
    """Choose option_1, place 2 spies at different sites."""
    session = _build_session()
    spies_avail = _spies_available(session, _P1)

    _play_card(session)
    assert _has_pending_generic(session), "Modal choice should be pending"

    _resolve_option(session, "option_1")
    assert _has_pending_generic(session), "First spy placement should be pending"

    _resolve_spy_placement(session, _SITE_A)
    assert _has_pending_generic(session), "Second spy placement should be pending"

    _resolve_spy_placement(session, _SITE_B)

    assert not _has_pending_generic(session)
    assert _P1 in _spies_at_node(session, _SITE_A)
    assert _P1 in _spies_at_node(session, _SITE_B)
    assert _spies_available(session, _P1) == spies_avail - 2

    session.destroy()


def test_option_1_cannot_place_two_spies_on_same_node():
    """Engine enforces at-most-one-spy-per-node."""
    session = _build_session()
    spies_avail = _spies_available(session, _P1)

    _play_card(session)
    _resolve_option(session, "option_1")
    _resolve_spy_placement(session, _SITE_A)

    assert _has_pending_generic(session), "Second spy placement should be pending"
    assert _P1 in _spies_at_node(session, _SITE_A), "First spy should be placed"

    legal_nodes = [m.data.get("action_id") for m in session.legal_moves()
                   if m.move_type == "resolve_generic"]

    assert _SITE_A not in legal_nodes, (
        f"SITE_A should be excluded (already has p1 spy); got {legal_nodes}"
    )

    _resolve_spy_placement(session, _SITE_B)

    assert not _has_pending_generic(session)
    assert _spies_available(session, _P1) == spies_avail - 2

    session.destroy()


def test_option_1_can_place_at_node_with_enemy_spy():
    """Placing a spy at a site already occupied by an enemy spy is legal."""
    session = _build_session(spies={_SITE_A: [_P2]})
    spies_avail = _spies_available(session, _P1)

    _play_card(session)
    _resolve_option(session, "option_1")

    legal_nodes = [m.data.get("action_id") for m in session.legal_moves()
                   if m.move_type == "resolve_generic"]
    assert _SITE_A in legal_nodes, (
        f"SITE_A with enemy spy should be legal; got {legal_nodes}"
    )

    _resolve_spy_placement(session, _SITE_A)
    _resolve_spy_placement(session, _SITE_B)

    assert _P1 in _spies_at_node(session, _SITE_A)
    assert _P2 in _spies_at_node(session, _SITE_A), "Enemy spy should remain"
    assert _spies_available(session, _P1) == spies_avail - 2

    session.destroy()


def test_option_1_unavailable_when_spies_exhausted():
    """When spies_available is 0, option_1 is unavailable even with a spy on board."""
    session = _build_session(spies={_SITE_A: [_P1]})
    s = _sptr(session).contents
    for pi in range(s.player_count):
        if _lib.intern_str(s.players[pi].player_id).decode() == _P1:
            s.players[pi].spies_available = 0
            break

    _play_card(session)

    opt1 = [m for m in session.legal_moves()
            if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_1"]
    assert opt1, "option_1 should still be listed"
    assert opt1[0].data.get("target_id") == "unavailable", (
        f"option_1 should be unavailable with 0 spies_available; got {opt1[0].data}"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Option 2 — return spy + gain 4 power
# ---------------------------------------------------------------------------


def test_option_2_returns_spy_and_grants_4_power():
    """Choose option_2, return your spy, gain 4 power."""
    session = _build_session(spies={_SITE_A: [_P1]})
    _play_card(session)

    _resolve_option(session, "option_2")

    targets = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(targets) == 1, f"Expected 1 return_spy target, got {len(targets)}"
    assert targets[0].data.get("action_id") == _SITE_A, (
        f"Expected target site {_SITE_A}, got {targets[0].data.get('action_id')}"
    )

    spy_available_before = _spies_available(session, _P1)
    session.submit_move(targets[0])

    assert _power(session) == 4, f"Expected 4 power after option_2, got {_power(session)}"
    assert _spies_at_node(session, _SITE_A) == [], "Site should have no p1 spies after return"
    assert _spies_available(session, _P1) == spy_available_before + 1, (
        f"Expected spies_available +1, got {spy_available_before} -> {_spies_available(session, _P1)}"
    )

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not gen, f"Expected no pending generic moves after full resolution, got {len(gen)}"

    session.destroy()


def test_option_2_unavailable_without_spy_on_board():
    """Option_2 is unavailable when player has no spy on board."""
    session = _build_session()
    _play_card(session)

    opt2 = [m for m in session.legal_moves()
            if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2"]
    assert opt2, "option_2 should still be listed"
    assert opt2[0].data.get("target_id") == "unavailable", (
        f"option_2 should be unavailable without a spy; got {opt2[0].data}"
    )

    session.destroy()


def test_option_2_available_with_spy_on_board():
    """Option_2 is available when player has a spy on board."""
    session = _build_session(spies={_SITE_A: [_P1]})
    _play_card(session)

    opt2 = [m for m in session.legal_moves()
            if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2"]
    assert opt2, "option_2 should be listed"
    assert opt2[0].data.get("target_id") != "unavailable", (
        f"option_2 should be available with a spy; got {opt2[0].data}"
    )

    session.destroy()


def test_option_2_only_returns_own_spy_not_enemy():
    """Return_spy target selection only shows sites with own spies, not enemy spies."""
    session = _build_session(spies={_SITE_A: [_P2]})
    _play_card(session)

    _resolve_option(session, "option_2")

    targets = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    target_node_ids = [m.data.get("action_id") for m in targets]
    assert _SITE_A not in target_node_ids, (
        f"Should not be able to return enemy spy; got targets {target_node_ids}"
    )

    session.destroy()


def test_option_2_resolves_fully_after_spy_return():
    """After returning the spy, the card fully resolves (no extra choices)."""
    session = _build_session(spies={_SITE_A: [_P1]})
    _play_card(session)

    _resolve_option(session, "option_2")

    targets = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(targets) == 1
    session.submit_move(targets[0])

    assert _power(session) == 4
    assert not _has_pending_generic(session), "Card should fully resolve"
    move_types = {m.move_type for m in session.legal_moves()}
    assert "end_main_phase" in move_types, "Should be able to end main phase"

    session.destroy()
