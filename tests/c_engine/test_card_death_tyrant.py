"""Death Tyrant card behavior tests (C engine).

Death Tyrant: Assassinate up to 3 troops at a single site.
Gain 1 influence for each troop removed by this effect.

Execution model (sequence):
  1. assassinate_troop (optional) — first assassination may target any site
     where the player has presence and an enemy/white troop sits.
  2. assassinate_troop (optional, requires_last_selected_node) — locked to the
     site chosen in the first assassination.
  3. assassinate_troop (optional, requires_last_selected_node) — locked to the
     same site.
  4. gain_resource influence (count = assassinations_by_source_effect).

These tests lock in that (a) the first assassination offers any legal site,
(b) every subsequent assassination is restricted to the site chosen first, and
(c) influence equals the number of troops actually removed.
"""

from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_MAIN, _lib
from game_setup.loaders import assemble_catalog_payload
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


def _assassinate_moves(session):
    """Moves that pick a troop slot to assassinate (action_id=site, target_id=slot)."""
    return [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("target_id") is not None
    ]


def _assassinate_sites(session):
    return {m.data.get("action_id") for m in _assassinate_moves(session)}


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


def _drain(session):
    """Decline any remaining optional actions until the card fully resolves."""
    while _has_pending_generic(session):
        assert _submit_skip(session), (
            f"Should be able to skip remaining actions; "
            f"legal: {[(m.move_type, m.data) for m in session.legal_moves()]}"
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_first_assassinate_offers_any_site_subsequent_locked_to_same_site():
    """First assassination may target any legal site; later ones only the chosen site."""
    session = _build_session(
        spies={_SITE_A: [_P1], _SITE_B: [_P1]},
        troops={_P1: {
            _SITE_A: [_P2, _P2, _P2],
            _SITE_B: [_P2, _P2, _P2],
        }},
    )

    _play_card(session)
    assert _has_pending_generic(session), "Should await the first assassination"

    # First assassination: both sites with presence + enemy troops are offered.
    assert _assassinate_sites(session) == {_SITE_A, _SITE_B}, (
        f"First assassinate should offer both sites, got {_assassinate_sites(session)}"
    )

    assert _submit_assassinate_at(session, _SITE_A, 0), "Should assassinate a troop at site A"

    # Subsequent assassinations must be locked to site A.
    assert _has_pending_generic(session), "Should await a second assassination"
    assert _assassinate_sites(session) == {_SITE_A}, (
        f"Second assassinate must be locked to {_SITE_A}, got {_assassinate_sites(session)}"
    )

    _drain(session)
    session.destroy()


def test_assassinates_3_troops_and_gains_3_influence():
    """Assassinate all 3 troops at one site; influence increases by exactly 3."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_P2, _P2, _P2]}},
    )

    inf_before = _influence(session)
    _play_card(session)

    for slot in (0, 1, 2):
        assert _has_pending_generic(session), f"Should await assassinate #{slot + 1}"
        assert _submit_assassinate_at(session, _SITE_A, slot), (
            f"Should assassinate troop at slot {slot}"
        )

    assert not _has_pending_generic(session), "Should resolve after all assassinations"
    assert _troops_at_node(session, _SITE_A) == [None, None, None], "All troops removed"
    assert _influence(session) == inf_before + 3, (
        f"Influence should be +3, got {_influence(session) - inf_before}"
    )
    assert _trophy_hall(session, _P1).count(_P2) == 3, "3 troops should enter the trophy hall"

    session.destroy()


def test_can_stop_after_one_assassination():
    """Assassinate 1 troop, decline the rest; influence increases by exactly 1."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_P2, _P2, _P2]}},
    )

    inf_before = _influence(session)
    _play_card(session)

    assert _submit_assassinate_at(session, _SITE_A, 0), "Should assassinate first troop"
    _drain(session)

    assert not _has_pending_generic(session)
    assert _troops_at_node(session, _SITE_A) == [None, _P2, _P2]
    assert _influence(session) == inf_before + 1, (
        f"Influence should be +1, got {_influence(session) - inf_before}"
    )

    session.destroy()


def test_decline_all_assassinations_gains_no_influence():
    """Declining every assassination removes nothing and gains no influence."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_P2, _P2, _P2]}},
    )

    inf_before = _influence(session)
    _play_card(session)
    assert _has_pending_generic(session)

    _drain(session)

    assert not _has_pending_generic(session)
    assert _troops_at_node(session, _SITE_A) == [_P2, _P2, _P2], "No troops removed"
    assert _influence(session) == inf_before, "Influence unchanged"

    session.destroy()


def test_no_enemy_troops_resolves_with_zero_influence():
    """With no enemy troops anywhere, the card resolves immediately with no influence."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [None, None, None]}},
    )

    inf_before = _influence(session)
    _play_card(session)

    assert not _has_pending_generic(session), "Should auto-resolve when no targets exist"
    assert _influence(session) == inf_before, "Influence unchanged"

    session.destroy()


def test_assassinates_white_troop():
    """Death Tyrant may assassinate a white troop (standard free-assassinate semantics)."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_WHITE, _P2, None]}},
    )

    inf_before = _influence(session)
    _play_card(session)

    assert _submit_assassinate_at(session, _SITE_A, 0), "Should assassinate the white troop"
    _drain(session)

    assert not _has_pending_generic(session)
    assert _troops_at_node(session, _SITE_A) == [None, _P2, None]
    assert _influence(session) == inf_before + 1
    assert _WHITE in _trophy_hall(session, _P1), "White troop should land in the trophy hall"

    session.destroy()


def test_gains_influence_equal_to_actual_count():
    """Influence equals troops actually removed (2 of a possible 3)."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_P2, _P2, None]}},
    )

    inf_before = _influence(session)
    _play_card(session)

    assert _submit_assassinate_at(session, _SITE_A, 0)
    assert _submit_assassinate_at(session, _SITE_A, 1)
    _drain(session)

    assert not _has_pending_generic(session)
    assert _troops_at_node(session, _SITE_A) == [None, None, None]
    assert _influence(session) == inf_before + 2, (
        f"Influence should be +2 (2 troops removed), got {_influence(session) - inf_before}"
    )

    session.destroy()


def test_second_assassinate_cannot_switch_site_after_first():
    """The chosen site is sticky across all three assassinations."""
    session = _build_session(
        spies={_SITE_A: [_P1], _SITE_B: [_P1]},
        troops={_P1: {
            _SITE_A: [_P2, _P2, _P2],
            _SITE_B: [_P2, None, None],
        }},
    )

    _play_card(session)
    assert _submit_assassinate_at(session, _SITE_A, 0)

    # A troop still remains at site B, but the second assassination may not target it.
    assert _assassinate_sites(session) == {_SITE_A}, (
        f"Second assassinate must not offer {_SITE_B}, got {_assassinate_sites(session)}"
    )
    assert not _submit_assassinate_at(session, _SITE_B, 0), "Site B must not be targetable"

    _drain(session)
    session.destroy()


def test_first_assassinate_requires_presence():
    """A site with enemy troops but no player presence is not offered."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {
            _SITE_A: [_P2, _P2, None],
            _SITE_B: [_P2, _P2, _P2],
        }},
    )

    _play_card(session)
    assert _has_pending_generic(session)

    assert _assassinate_sites(session) == {_SITE_A}, (
        f"Only sites where the player has presence should be offered, got {_assassinate_sites(session)}"
    )
    assert not _submit_assassinate_at(session, _SITE_B, 0), "Site B (no presence) must not be targetable"

    _drain(session)
    session.destroy()


def test_cannot_assassinate_own_troop():
    """The player's own troops at a site are not valid assassination targets."""
    session = _build_session(
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_P1, _P2, None]}},
    )

    _play_card(session)
    assert _has_pending_generic(session)

    slots = {
        m.data.get("target_id")
        for m in _assassinate_moves(session)
        if m.data.get("action_id") == _SITE_A
    }
    assert slots == {"1"}, f"Only the enemy troop slot should be targetable, got {slots}"
    assert not _submit_assassinate_at(session, _SITE_A, 0), "Own troop (slot 0) must not be targetable"

    session.destroy()


def test_catalog_execution_model_locks_subsequent_assassinations():
    """The catalog encodes the site-lock: first assassinate free, later ones locked."""
    from pathlib import Path

    catalog = assemble_catalog_payload(Path(__file__).resolve().parents[2] / "data" / "cards")
    card = next(c for c in catalog["cards"] if c["card_id"] == _CARD)
    actions = card["execution_model"]["actions"]

    assert [a["op"] for a in actions] == [
        "assassinate_troop",
        "assassinate_troop",
        "assassinate_troop",
        "gain_resource",
    ]

    assert actions[0]["optional"] is True, "First assassination must be optional"
    assert "requires_last_selected_node" not in actions[0]["metadata"], (
        "First assassination must be free to choose any site"
    )
    for a in actions[1:3]:
        assert a["optional"] is True, "Each subsequent assassination must be optional"
        assert a["metadata"].get("requires_last_selected_node") is True, (
            "Second and third assassinations must be locked to the first site"
        )

    gain = actions[3]
    assert gain["metadata"].get("resource") == "influence"
    assert gain["metadata"].get("count_from") == "assassinations_by_source_effect"
