"""Glabrezu card behavior tests via the C engine bindings.

Verifies:
- Devour a card from hand (cost). The devoured card is removed from hand.
- Then assassinate up to 2 troops at sites where the player has presence.
- Both assassinate actions respect presence and target legality.
- Only non-self troops are valid targets (enemy and white).
- Skips assassinate steps when no legal targets remain.
"""

from __future__ import annotations

from engine_c.bindings.engine_bindings import _lib
from game_setup.loaders import assemble_catalog_payload
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_P1 = "p1"
_P2 = "p2"
_GLABREZU = "glabrezu"
_SITE = "site_gauntlgrym"
_SITE2 = "site_jhachalkhyn"


def _hand_count(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].hand_count


def _trophy_hall_entries(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.trophy_hall[i]).decode() for i in range(ps.trophy_hall_count)]


def _has_pending_generic(session):
    return _sptr(session).contents.pending_generic is not None


def _play_card(session, card_id=_GLABREZU):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    raise AssertionError(f"{card_id} not playable")


def _resolve_generic(session, action_id, target_id=None):
    for m in session.legal_moves():
        if m.move_type != "resolve_generic":
            continue
        d = m.data
        if d.get("action_id") == action_id and (
            target_id is None or str(d.get("target_id")) == target_id
        ):
            session.submit_move(m)
            return
    raise AssertionError(f"No resolve_generic for action_id={action_id} target_id={target_id}")


def _resolve_generic_moves(session):
    """Return all resolve_generic move datas."""
    return [m.data for m in session.legal_moves() if m.move_type == "resolve_generic"]


def _resolve_generic_move_ids(session):
    """Return {(action_id, target_id)} for all resolve_generic moves."""
    return {(d["action_id"], str(d.get("target_id"))) for d in _resolve_generic_moves(session)}


def _resolve_any_generic(session):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic":
            session.submit_move(m)
            return
    raise AssertionError("No resolve_generic move available")


def _troop_slots_at_node(session, node_id):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            result = []
            for si in range(s.nodes[ni].troop_slot_count):
                sym = s.nodes[ni].troop_slots[si]
                owner = _lib.intern_str(sym).decode() if _lib.intern_str(sym) else None
                result.append(owner)
            return result
    return []


def _barracks(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].barracks


def _set_troop_slots(session, node_id, slots):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slot_count = len(slots)
            for si, occ in enumerate(slots):
                if occ is None:
                    s.nodes[ni].troop_slots[si] = 0
                else:
                    s.nodes[ni].troop_slots[si] = _lib.intern(occ.encode())
            break


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_glabrezu_devour_then_assassinate_white():
    """Devour a card, then assassinate a white troop at a site with presence."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["glabrezu", "noble"]},
        troops={
            _P1: {_SITE: [_P1, None, None, None, None]},
        },
        current_player=_P1,
    )

    s = _sptr(session).contents
    nid = _lib.intern(_SITE.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[1] = _lib.intern(b"white")
            break

    hand_before = _hand_count(session, _P1)

    _play_card(session)
    assert _has_pending_generic(session), "Should await devour selection"

    _resolve_generic(session, "noble")

    assert _hand_count(session, _P1) == hand_before - 2, "Glabrezu played, noble devoured"
    assert _has_pending_generic(session), "Should await assassinate selection"

    _resolve_generic(session, _SITE, "1")

    trophy = _trophy_hall_entries(session, _P1)
    assert "white" in trophy, f"White should be in p1 trophy hall, got {trophy}"

    session.destroy()


def test_glabrezu_assassinate_player_troop():
    """Devour a card, then assassinate a player troop at a site with presence."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["glabrezu", "noble"]},
        troops={
            _P1: {_SITE: [_P1, None, None, None, None]},
            _P2: {_SITE: [_P2, None, None, None, None]},
        },
        current_player=_P1,
    )

    s = _sptr(session).contents
    nid = _lib.intern(_SITE.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[0] = _lib.intern(_P1.encode())
            s.nodes[ni].troop_slots[1] = _lib.intern(_P2.encode())
            s.nodes[ni].troop_slot_count = 2
            break

    _play_card(session)
    _resolve_generic(session, "noble")

    assert _has_pending_generic(session), "Should await assassinate selection"

    _resolve_generic(session, _SITE, "1")

    trophy = _trophy_hall_entries(session, _P1)
    assert _P2 in trophy, f"p2 troop should be in p1 trophy hall, got {trophy}"

    session.destroy()


def test_glabrezu_skips_when_no_targets():
    """Devour resolves; second assassinate skips if no legal target remains."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["glabrezu", "noble"]},
        troops={
            _P1: {_SITE: [_P1, None, None, None, None]},
        },
        current_player=_P1,
    )

    s = _sptr(session).contents
    nid = _lib.intern(_SITE.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slots[1] = _lib.intern(b"white")
            break

    _play_card(session)
    _resolve_generic(session, "noble")
    _resolve_generic(session, _SITE, "1")

    moves = session.legal_moves()
    assert not any(m.move_type == "resolve_generic" for m in moves), (
        "No card actions should be pending after both assassinates resolve"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------


def test_glabrezu_execution_model_is_sequence_of_three_actions():
    """Catalog: execution model must be a sequence with devour + 2x assassinate."""
    from pathlib import Path

    catalog = assemble_catalog_payload(Path(__file__).resolve().parents[2] / "data" / "cards")
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    glab = next(c for c in cards if c.get("card_id") == _GLABREZU)

    em = glab["execution_model"]
    assert em["kind"] == "sequence"
    actions = em["actions"]
    assert len(actions) == 3, "Should have devour_cost + 2 assassinate_troop"

    assert actions[0]["op"] == "devour_cost"
    assert actions[0]["target_scope"] == "hand"
    assert actions[0]["timing"] == "immediate"
    assert actions[0]["optional"] is False

    for i in (1, 2):
        assert actions[i]["op"] == "assassinate_troop"
        assert actions[i]["target_scope"] == "board_site"
        assert actions[i]["timing"] == "immediate"
        assert actions[i]["optional"] is False
        assert actions[i]["quantity"] == {"kind": "fixed", "value": 1}

    assert "Devour" in glab["rules_text"]
    assert "assassinate 2" in glab["rules_text"]


def test_glabrezu_full_flow_two_assassinates():
    """Devour noble, then assassinate two separate enemy troops at the same site."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["glabrezu", "noble"]},
        troops={_P1: {_SITE: [_P1, None, None, None, None]}},
        current_player=_P1,
    )

    _set_troop_slots(session, _SITE, [_P1, _P2, "white", None, None])
    hand_before = _hand_count(session, _P1)
    barracks_before = _barracks(session, _P1)

    _play_card(session)
    assert _has_pending_generic(session), "Should await devour selection"
    _resolve_generic(session, "noble")
    assert _hand_count(session, _P1) == hand_before - 2, "Glabrezu + noble removed from hand"

    assert _has_pending_generic(session), "Should await first assassinate"
    moves1 = _resolve_generic_move_ids(session)
    assert (_SITE, "1") in moves1, "Slot 1 (p2 enemy troop) should be a legal target"
    assert (_SITE, "2") in moves1, "Slot 2 (white troop) should be a legal target"
    assert (_SITE, "0") not in moves1, "Slot 0 (own p1 troop) should NOT be targetable"

    _resolve_generic(session, _SITE, "1")

    assert _has_pending_generic(session), "Should await second assassinate"
    moves2 = _resolve_generic_move_ids(session)
    assert (_SITE, "2") in moves2, "Slot 2 (white) should still be targetable"
    assert (_SITE, "1") not in moves2, "Slot 1 (p2) now gone — slot should be empty"

    _resolve_generic(session, _SITE, "2")

    # After all 3 actions, the pending state should be popped.  The
    # existing _has_pending_generic helper uses "is not None" which
    # does not detect ctypes NULL pointers — use truthiness instead.
    assert not _sptr(session).contents.pending_generic, "Card should be fully resolved"
    assert _barracks(session, _P1) == barracks_before, "Assassinate does not cost barracks"

    trophy = _trophy_hall_entries(session, _P1)
    assert _P2 in trophy, "p2 troop should be in trophy hall"
    assert "white" in trophy, "white troop should be in trophy hall"
    assert len(trophy) == 2, "Exactly 2 troops in trophy hall"

    session.destroy()


def test_glabrezu_cannot_assassinate_own_troop():
    """Own troops at presence sites are never valid assassinate targets."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["glabrezu", "noble"]},
        troops={_P1: {_SITE: [_P1, None, None, None, None]}},
        current_player=_P1,
    )

    _set_troop_slots(session, _SITE, [_P1, _P1, None, None, None])

    _play_card(session)
    _resolve_generic(session, "noble")

    moves = _resolve_generic_move_ids(session)
    assert (_SITE, "0") not in moves, "Own troop at slot 0 should not be targetable"
    assert (_SITE, "1") not in moves, "Own troop at slot 1 should not be targetable"

    session.destroy()


def test_glabrezu_requires_presence_for_assassinate():
    """Sites without presence should not appear as assassinate targets."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["glabrezu", "noble"]},
        troops={_P1: {_SITE: [_P1, None, None, None, None]}},
        current_player=_P1,
    )

    _set_troop_slots(session, _SITE, [_P1, _P2, None, None, None])
    _set_troop_slots(session, _SITE2, [_P2, None, None, None, None])

    _play_card(session)
    _resolve_generic(session, "noble")

    moves = _resolve_generic_move_ids(session)
    site_ids = {a for a, _ in moves}
    assert _SITE in site_ids, "Site with presence should be offered"
    assert _SITE2 not in site_ids, "Site without presence should NOT be offered"

    session.destroy()


def test_glabrezu_no_targets_fully_skips():
    """If no legal assassinate targets exist, both actions skip silently."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["glabrezu", "noble"]},
        troops={_P1: {_SITE: [_P1, None, None, None, None]}},
        current_player=_P1,
    )

    _set_troop_slots(session, _SITE, [_P1, None, None, None, None])

    _play_card(session)
    _resolve_generic(session, "noble")

    assert not _sptr(session).contents.pending_generic, (
        "No legal assassinate targets \u2192 card should resolve completely"
    )
    assert not any(m.move_type == "resolve_generic" for m in session.legal_moves())

    session.destroy()


def test_glabrezu_devour_removes_card_from_hand():
    """The devoured card must not remain in hand after devour resolves."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["glabrezu", "noble", "soldier"]},
        troops={_P1: {_SITE: [_P1, None, None, None, None]}},
        current_player=_P1,
    )

    _play_card(session)
    _resolve_generic(session, "noble")

    assert _hand_count(session, _P1) == 1, "Glabrezu played + noble devoured, soldier remains"
    assert _has_pending_generic(session)

    session.destroy()
