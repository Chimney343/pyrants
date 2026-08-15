"""Minotaur Skeleton card behavior tests (C engine).

Modal choice: choose exactly one mode.
- Option 1: deploy 3 troops.
- Option 2: devour this card, then assassinate up to 3 white troops at a single
  site (presence required; each assassination individually declinable).

The second mode reuses the established self-devour rule (Cultist of Myrkul) plus
the Death Tyrant single-site repeated assassinate pattern, restricted to white
troops. These tests lock in that the card is devoured (lands in the devour pile,
not discard), the first assassination may target any site where the player has
presence and a white troop sits, subsequent assassinations are locked to that
site, and each of the three assassinate actions is optional.
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
_CARD = "minotaur_skeleton"


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


def _devour_pile(session):
    s = _sptr(session).contents
    return [_lib.intern_str(s.devour_pile[i]).decode() for i in range(s.devour_pile_count)]


def _discard_pile(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    s = _sptr(session).contents
    ps = s.players[pi]
    return [_lib.intern_str(ps.discard_pile[j]).decode() for j in range(ps.discard_pile_count)]


def _played_ids(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    s = _sptr(session).contents
    ps = s.players[pi]
    return [_lib.intern_str(ps.played_cards[j]).decode() for j in range(ps.played_cards_count)]


def _barracks(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return -1
    return _sptr(session).contents.players[pi].barracks


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


def _pick_option(session, option_id):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == option_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{option_id} not found in resolve_generic moves")


def _select_devour_self(session):
    """Submit the played_self devour target move (action_id == the card id)."""
    assert _has_pending_generic(session), "Should await devour target selection"
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _CARD:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(
        f"No self-devour move for {_CARD}; legal: {[(m.move_type, m.data) for m in session.legal_moves()]}"
    )


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


def test_option_1_deploys_3_troops():
    """Option 1 deploys 3 troops (one selection per troop) at sites with presence."""
    session = _build_session(
        hand={_P1: [_CARD]},
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [None, None, None]}},
    )

    barracks_before = _barracks(session, _P1)
    _play_card(session)
    _pick_option(session, "option_1")

    deploys = 0
    while _has_pending_generic(session):
        move = None
        for m in session.legal_moves():
            if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE_A:
                move = m
                break
        assert move is not None, f"Should be able to deploy to {_SITE_A}, got no deploy move"
        session.submit_move(move)
        deploys += 1
        if deploys > 5:
            break

    assert deploys == 3, f"Should require exactly 3 deploy selections, got {deploys}"
    assert not _has_pending_generic(session), "Option 1 should resolve after 3 deploys"
    assert _barracks(session, _P1) == barracks_before - 3, "Should deploy exactly 3 troops"
    troops = _troops_at_node(session, _SITE_A)
    assert troops.count(_P1) == 3, f"Expected 3 p1 troops at {_SITE_A}, got {troops}"

    session.destroy()


def test_option_2_devours_self_then_assassinates_up_to_3_white():
    """Option 2: devour self, then assassinate up to 3 white troops at one site."""
    session = _build_session(
        hand={_P1: [_CARD]},
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_WHITE, _WHITE, _WHITE]}},
    )

    _play_card(session)
    assert _has_pending_generic(session), "Modal choice should be pending after play"
    _pick_option(session, "option_2")

    # Step 1: devour the played Minotaur Skeleton itself.
    _select_devour_self(session)
    assert _CARD in _devour_pile(session), f"Card should be devoured, pile: {_devour_pile(session)}"
    assert _CARD not in _played_ids(session, _P1), "Devoured card must leave played_cards"
    assert _CARD not in _discard_pile(session, _P1), "Devoured card must NOT go to discard"

    # Step 2: three optional assassinate actions, each declinable. Take all 3.
    for slot in (0, 1, 2):
        assert _has_pending_generic(session), f"Should await assassinate #{slot + 1}"
        assert _submit_assassinate_at(session, _SITE_A, slot), (
            f"Should assassinate white troop at slot {slot}"
        )

    assert not _has_pending_generic(session), "Option 2 should fully resolve after 3 assassinate"
    trophy = _trophy_hall(session, _P1)
    assert trophy.count(_WHITE) == 3, f"Expected 3 assassinated white troops, got {trophy}"
    troops = _troops_at_node(session, _SITE_A)
    assert troops.count(_WHITE) == 0, f"All white troops should be removed, got {troops}"
    assert _CARD in _devour_pile(session), "Card must remain devoured at the end"

    session.destroy()


def test_option_2_can_decline_all_assassinates_after_devour():
    """After devouring, the player may decline every optional assassinate."""
    session = _build_session(
        hand={_P1: [_CARD]},
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_WHITE, _WHITE, _WHITE]}},
    )

    _play_card(session)
    _pick_option(session, "option_2")
    _select_devour_self(session)

    _drain(session)

    assert not _has_pending_generic(session), "Option 2 should resolve after declining all"
    assert _trophy_hall(session, _P1).count(_WHITE) == 0, "No troops should be assassinated"
    assert _CARD in _devour_pile(session), "Card should still be devoured"

    session.destroy()


def test_option_2_first_assassinate_requires_presence():
    """A site with a white troop but no player presence is not offered."""
    session = _build_session(
        hand={_P1: [_CARD]},
        spies={_SITE_A: [_P1]},
        troops={_P1: {
            _SITE_A: [_WHITE, None, None],
            _SITE_B: [_WHITE, None, None],
        }},
    )

    _play_card(session)
    _pick_option(session, "option_2")
    _select_devour_self(session)

    assert _assassinate_sites(session) == {_SITE_A}, (
        f"Only sites with presence should be offered, got {_assassinate_sites(session)}"
    )
    assert not _submit_assassinate_at(session, _SITE_B, 0), "Site B (no presence) must not be targetable"

    _drain(session)
    session.destroy()


def test_option_2_subsequent_assassinates_locked_to_same_site():
    """After the first assassination, later ones are locked to that site."""
    session = _build_session(
        hand={_P1: [_CARD]},
        spies={_SITE_A: [_P1], _SITE_B: [_P1]},
        troops={_P1: {
            _SITE_A: [_WHITE, _WHITE, _WHITE],
            _SITE_B: [_WHITE, None, None],
        }},
    )

    _play_card(session)
    _pick_option(session, "option_2")
    _select_devour_self(session)

    assert _assassinate_sites(session) == {_SITE_A, _SITE_B}, (
        f"First assassinate should offer both sites, got {_assassinate_sites(session)}"
    )
    assert _submit_assassinate_at(session, _SITE_A, 0), "Should assassinate a white troop at site A"

    assert _has_pending_generic(session), "Should await a second assassination"
    assert _assassinate_sites(session) == {_SITE_A}, (
        f"Second assassinate must be locked to {_SITE_A}, got {_assassinate_sites(session)}"
    )
    assert not _submit_assassinate_at(session, _SITE_B, 0), "Site B must not be targetable"

    _drain(session)
    session.destroy()


def test_option_2_assassinates_only_one_when_one_white_present():
    """With a single white troop on the chosen site, assassinate it then skip the rest."""
    session = _build_session(
        hand={_P1: [_CARD]},
        spies={_SITE_A: [_P1]},
        troops={_P1: {_SITE_A: [_WHITE]}},
    )

    _play_card(session)
    _pick_option(session, "option_2")
    _select_devour_self(session)

    assert _submit_assassinate_at(session, _SITE_A, 0), "Should assassinate the lone white troop"
    _drain(session)

    assert not _has_pending_generic(session), "Option 2 should resolve after one assassinate"
    assert _trophy_hall(session, _P1).count(_WHITE) == 1, "Expected exactly 1 white trophy"
    assert _CARD in _devour_pile(session), "Card should still be devoured"

    session.destroy()


def test_catalog_execution_model_devour_then_3_optional_white_assassinate():
    """Catalog encodes: devour(self) then 3 optional white-troop-only assassinate
    with the site locked after the first."""
    import json
    from pathlib import Path

    catalog = json.loads(
        (Path(__file__).resolve().parents[2] / "data" / "cards" / "catalog.json").read_text(encoding="utf-8")
    )
    card = next(c for c in catalog["cards"] if c["card_id"] == _CARD)
    option_2 = next(o for o in card["execution_model"]["options"] if o["option_id"] == "option_2")
    actions = option_2["actions"]

    assert [a["op"] for a in actions] == [
        "devour_cost",
        "assassinate_troop",
        "assassinate_troop",
        "assassinate_troop",
    ]

    assert actions[0]["metadata"].get("source_zone") == "played_self", (
        "First action must be a self-devour from played zone"
    )
    assert actions[0]["optional"] is False, "The self-devour is a required cost"

    assert actions[1]["optional"] is True, "First assassinate must be optional (up to 3)"
    assert "requires_last_selected_node" not in actions[1]["metadata"], (
        "First assassinate must be free to choose any site"
    )
    assert "white_troop_only" in actions[1]["filters"]

    for a in actions[2:]:
        assert a["optional"] is True, "Each subsequent assassinate must be optional"
        assert a["metadata"].get("requires_last_selected_node") is True, (
            "Second and third assassinations must be locked to the first site"
        )
        assert "white_troop_only" in a["filters"]
