"""Death Tyrant card behavior tests (C engine).

Death Tyrant: Assassinate up to 3 troops at a single site.
Gain 1 influence for each troop removed by this effect.

Execution model:
  1. select_site (mandatory, requires presence)
  2. assassinate_troop x3 (each optional, allow_white_troop, locked to selected site)
  3. gain_resource influence (count = assassinations_by_source_effect)
"""

from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_SITE_A = "site_gauntlgrym"
_SITE_B = "site_blingdenfire"
_P1 = "p1"
_P2 = "p2"
_WHITE = "white"
_CARD = "death_tyrant"


def _influence(session):
    return _sptr(session).contents.resource_pool.influence


def _has_pending_generic(session):
    return bool(_sptr(session).contents.pending_generic)


def _trophy_hall(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    s = _sptr(session).contents
    ps = s.players[pi]
    return [_lib.intern_str(ps.trophy_hall[j]).decode() for j in range(ps.trophy_hall_count)]


def _troops_at_node(session, node_id):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            return [
                _lib.intern_str(ns.troop_slots[i]).decode()
                if ns.troop_slots[i] != 0 else None
                for i in range(ns.troop_slot_count)
            ]
    return []


def _build_session(**kwargs):
    defaults = {
        "player_ids": [_P1, _P2],
        "hand": {_P1: [_CARD]},
        "current_player": _P1,
    }
    defaults.update(kwargs)
    eng = _make_engine()
    session = make_card_test_session(eng, defaults.pop("player_ids"), **defaults)
    _sptr(session).contents.phase = PHASE_MAIN
    return session


def _play_card(session, card_id=_CARD):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


def _select_site(session, node_id):
    for m in session.legal_moves():
        if (m.move_type == "resolve_generic"
                and m.data.get("action_id") == node_id
                and m.data.get("target_id") is None):
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(
        f"Site {node_id} not selectable; legal: {[(m.move_type, m.data) for m in session.legal_moves()]}"
    )


def _site_selection_moves(session):
    return [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
        and m.data.get("action_id") is not None
        and m.data.get("target_id") is None
    ]


def _assassinate_moves(session):
    return [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("target_id") is not None
    ]


def _submit_assassinate_at(session, node_id, slot_index):
    slot_str = str(slot_index)
    for m in _assassinate_moves(session):
        if m.data.get("action_id") == node_id and m.data.get("target_id") == slot_str:
            session.submit_move(m)
            return True
    return False


def _submit_skip(session):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") is None:
            session.submit_move(m)
            return True
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_assassinates_3_troops_and_gains_3_influence():
    """Play Death Tyrant, select a site, assassinate all 3 troops, verify influence=3."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_P2, _P2, _P2]}},
    )

    inf_before = _influence(session)
    _play_card(session)

    assert _has_pending_generic(session), "Should await site selection after playing Death Tyrant"
    _select_site(session, _SITE_A)

    for slot in (0, 1, 2):
        assert _has_pending_generic(session), f"Should await assassinate #{slot + 1}"
        assert _submit_assassinate_at(session, _SITE_A, slot), (
            f"Should be able to assassinate troop at slot {slot}"
        )

    assert not _has_pending_generic(session), "Should resolve after all assassinations"
    assert _troops_at_node(session, _SITE_A) == [None, None, None], "All troops should be removed"
    assert _influence(session) == inf_before + 3, f"Influence should increase by 3, got {_influence(session) - inf_before}"
    assert _P2 in _trophy_hall(session, _P1), "Assassinated troops should go to active player's trophy hall"

    session.destroy()


def test_can_stop_after_one_assassination():
    """Assassinate 1 troop then skip; skip_advance_to_index jumps to gain_resource. Influence=1."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_P2, _P2, _P2]}},
    )

    inf_before = _influence(session)
    _play_card(session)
    _select_site(session, _SITE_A)

    assert _submit_assassinate_at(session, _SITE_A, 0), "Should assassinate first troop"

    if _has_pending_generic(session):
        assert _submit_skip(session), "Should be able to skip remaining"

    assert not _has_pending_generic(session)
    assert _troops_at_node(session, _SITE_A) == [None, _P2, _P2]
    assert _influence(session) == inf_before + 1, f"Influence should be +1, got {_influence(session) - inf_before}"

    session.destroy()


def test_decline_all_assassinations_after_site_selection():
    """Skip the first assassinate; skip_advance_to_index:4 jumps to gain_resource (auto-resolves). Influence=0."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_P2, _P2, _P2]}},
    )

    inf_before = _influence(session)
    _play_card(session)
    _select_site(session, _SITE_A)

    assert _submit_skip(session), "Should be able to skip the assassinate action"

    assert not _has_pending_generic(session)
    assert _troops_at_node(session, _SITE_A) == [_P2, _P2, _P2], "No troops should be removed"
    assert _influence(session) == inf_before, f"Influence should be unchanged, got delta {_influence(session) - inf_before}"

    session.destroy()


def test_no_targets_at_selected_site_resolves_with_zero_influence():
    """Site with no troops: card resolves immediately after site selection, no influence gained."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [None, None, None]}},
    )

    inf_before = _influence(session)
    _play_card(session)

    assert _has_pending_generic(session)
    _select_site(session, _SITE_A)

    assert not _has_pending_generic(session), "Should auto-resolve when no troops at site"
    assert _influence(session) == inf_before, f"Influence should remain {inf_before}, got {_influence(session)}"

    session.destroy()


def test_assassinates_white_troops():
    """Death Tyrant can assassinate white troops (allow_white_troop filter)."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_WHITE, _P2, None]}},
    )

    inf_before = _influence(session)
    _play_card(session)
    _select_site(session, _SITE_A)

    assert _submit_assassinate_at(session, _SITE_A, 0), "Should assassinate white troop at slot 0"

    if _has_pending_generic(session):
        assert _submit_skip(session)

    assert not _has_pending_generic(session)
    assert _troops_at_node(session, _SITE_A) == [None, _P2, None]
    assert _influence(session) == inf_before + 1, f"Influence should be +1, got {_influence(session) - inf_before}"
    trophy = _trophy_hall(session, _P1)
    assert _WHITE in trophy, f"White troop should be in trophy hall, got {trophy}"

    session.destroy()


def test_assassinate_moves_locked_to_selected_site():
    """Assassinate moves after site selection must only target the chosen site."""
    session = _build_session(
        spies={_SITE_A: [_P1], _SITE_B: [_P1]},
        troops={_P1: {
            _SITE_A: [_P2, _P2, None],
            _SITE_B: [_P2, None, None],
        }},
    )

    _play_card(session)
    _select_site(session, _SITE_A)

    targets = {m.data.get("action_id") for m in _assassinate_moves(session)}
    assert targets == {_SITE_A}, f"All assassinate targets must be {_SITE_A}, got {targets}"

    session.destroy()


def test_site_selection_requires_presence():
    """Only sites where the player has presence are offered for selection."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P2: {_SITE_A: [_P2, _P2, _P2]}},
    )

    _play_card(session)

    offered = {m.data.get("action_id") for m in _site_selection_moves(session)}
    assert _SITE_A in offered, f"Site with spy presence must be offered: {offered}"

    session.destroy()


def test_cannot_select_site_without_presence():
    """Site without p1 presence and without p1 troops should not be offered."""
    session = _build_session(
        spies={},
        troops={_P2: {_SITE_A: [_P2, _P2, _P2]}},
    )

    _play_card(session)

    offered = {m.data.get("action_id") for m in _site_selection_moves(session)}
    assert _SITE_A not in offered, f"Site without presence must not be offered: {offered}"

    session.destroy()


def test_gains_influence_equal_to_assassinated_count():
    """Influence gain matches actual number of troops removed, not the max 3."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_P2, _P2, None]}},
    )

    inf_before = _influence(session)
    _play_card(session)
    _select_site(session, _SITE_A)

    assert _submit_assassinate_at(session, _SITE_A, 0)
    assert _submit_assassinate_at(session, _SITE_A, 1)

    if _has_pending_generic(session):
        assert _submit_skip(session)

    assert not _has_pending_generic(session)
    assert _troops_at_node(session, _SITE_A) == [None, None, None]
    assert _influence(session) == inf_before + 2, f"Influence should be +2 (2 troops removed), got {_influence(session) - inf_before}"

    session.destroy()
