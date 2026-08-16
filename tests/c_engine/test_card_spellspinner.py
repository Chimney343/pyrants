"""Spellspinner card behavior tests.

Spellspinner (3-cost, Guile/Drow) — modal, choose exactly one:

  option_1: place a spy.
  option_2: return one of your spies, then supplant a troop at that same site.

The option_2 supplant is constrained to the site the spy was returned from
(`metadata: {"requires_returned_spy_site": true}`, honoured by
`sel_assassinate_supplant` in engine_c/selection.c, which reads the pending
`node_id` selection key). The supplant targets enemy troops only — no
`allow_white_troop` filter, so white troops are excluded.
"""

from __future__ import annotations

import json
from pathlib import Path

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_P1 = "p1"
_P2 = "p2"
_SITE_A = "site_menzoberranzan"
_SITE_B = "site_gauntlgrym"
_SITE_A_NAME = "menzoberranzan"
_SITE_B_NAME = "gauntlgrym"


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _spies_available(session: CSession, pid: str) -> int:
    return _sptr(session).contents.players[_session_player_index(session, pid)].spies_available


def _barracks(session: CSession, pid: str) -> int:
    return _sptr(session).contents.players[_session_player_index(session, pid)].barracks


def _trophy_hall(session: CSession, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.trophy_hall[i]).decode() for i in range(ps.trophy_hall_count)]


def _troops_at_node(session: CSession, node_id: str) -> list[str | None]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            return [
                _lib.intern_str(ns.troop_slots[i]).decode() if ns.troop_slots[i] else None
                for i in range(ns.troop_slot_count)
            ]
    return []


def _play_spellspinner(session: CSession) -> None:
    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "spellspinner"]
    assert playable, "Spellspinner not playable"
    session.submit_move(playable[0])


def _choose_option(session: CSession, option_id: str) -> None:
    opt = [m for m in session.legal_moves()
           if getattr(m, "move_type", "") == "resolve_generic"
           and m.data.get("action_id") == option_id]
    assert opt, f"{option_id} not available, moves: {[m.data for m in session.legal_moves()]}"
    session.submit_move(opt[0])


def _labeled_moves(session: CSession, label_substr: str) -> list:
    view = build_c_game_view(session)
    needle = label_substr.lower()
    return [m for m in view.legal_moves
            if m.move_type == "resolve_generic" and needle in m.label.lower()]


# ---------------------------------------------------------------------------
# Catalog / execution model
# ---------------------------------------------------------------------------

def test_spellspinner_execution_model():
    """The catalog encodes the modal choice and the option_2 supplant signals."""
    catalog = json.loads((DATA_DIR / "cards" / "catalog.json").read_text(encoding="utf-8"))
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    card = next(c for c in cards if c.get("card_id") == "spellspinner")

    em = card["execution_model"]
    assert em["kind"] == "modal_choice"
    assert em["selection"] == "exactly_one"
    assert len(em["options"]) == 2

    opt1 = em["options"][0]["actions"]
    assert [a["op"] for a in opt1] == ["place_spy"]

    opt2 = em["options"][1]["actions"]
    assert [a["op"] for a in opt2] == ["return_spy", "supplant_troop"]
    assert opt2[0]["metadata"] == {"spy_owner": "self"}

    supplant = opt2[1]
    assert supplant["target_scope"] == "board_site"
    assert supplant["filters"] == []
    assert supplant["metadata"] == {"requires_returned_spy_site": True}

    assert card["cost"] == 3
    assert card["aspect"] == "guile"
    assert "drow" in card["secondary_aspects"]


# ---------------------------------------------------------------------------
# option_1: place a spy
# ---------------------------------------------------------------------------

def test_spellspinner_option1_places_spy():
    """Option 1 places a spy, decrementing the player's available spies."""
    session = make_card_test_session(
        _make_engine(), [_P1, _P2],
        hand={_P1: ["spellspinner"]},
        current_player=_P1,
    )
    before = _spies_available(session, _P1)

    _play_spellspinner(session)
    _choose_option(session, "option_1")

    assert _has_pending_generic(session)

    place_moves = _labeled_moves(session, "place spy")
    assert place_moves, f"No place-spy moves, labels: {[m.label for m in place_moves]}"
    session.submit_move(place_moves[0].move)

    assert not _has_pending_generic(session), "Expected card to fully resolve after option_1"
    assert _spies_available(session, _P1) == before - 1, "One spy should have been placed"

    session.destroy()


# ---------------------------------------------------------------------------
# option_2: return a spy, then supplant at that same site
# ---------------------------------------------------------------------------

def test_spellspinner_option2_supplant_constrained_to_returned_spy_site():
    """After returning a spy from site_A, supplant moves only target site_A."""
    session = make_card_test_session(
        _make_engine(), [_P1, _P2],
        hand={_P1: ["spellspinner"]},
        troops={
            _P1: {
                _SITE_A: [_P1, _P2, None, None, None, None],
                _SITE_B: [_P1, _P2, None, None, None, None],
            },
        },
        spies={_SITE_A: [_P1], _SITE_B: [_P1]},
        current_player=_P1,
    )

    _play_spellspinner(session)
    _choose_option(session, "option_2")

    assert _has_pending_generic(session)

    return_moves = _labeled_moves(session, "return spy")
    site_a_return = [m for m in return_moves if _SITE_A_NAME in m.label.lower()]
    assert site_a_return, f"No return-spy move for {_SITE_A_NAME}, labels: {[m.label for m in return_moves]}"
    session.submit_move(site_a_return[0].move)

    assert _has_pending_generic(session)

    supplant_moves = _labeled_moves(session, "supplant")
    assert supplant_moves, "No supplant moves"
    for m in supplant_moves:
        assert _SITE_A_NAME in m.label.lower(), (
            f"Supplant must target {_SITE_A_NAME} (returned spy site), got: {m.label}"
        )
        assert _SITE_B_NAME not in m.label.lower(), (
            f"Supplant must NOT target {_SITE_B_NAME} (wrong site), got: {m.label}"
        )

    session.destroy()


def test_spellspinner_option2_does_not_supplant_white_troop():
    """The supplant at the returned spy's site may NOT target a white troop."""
    session = make_card_test_session(
        _make_engine(), [_P1, _P2],
        hand={_P1: ["spellspinner"]},
        troops={_P1: {_SITE_A: [_P1, "white", None, None, None, None]}},
        spies={_SITE_A: [_P1]},
        current_player=_P1,
    )

    _play_spellspinner(session)
    _choose_option(session, "option_2")

    return_moves = _labeled_moves(session, "return spy")
    assert return_moves, f"No return-spy moves, labels: {[m.label for m in return_moves]}"
    session.submit_move(return_moves[0].move)

    supplant_moves = _labeled_moves(session, "supplant")
    assert not supplant_moves, (
        f"White troop must NOT be a supplant target, labels: {[m.label for m in supplant_moves]}"
    )

    session.destroy()


def test_spellspinner_option2_supplant_offers_enemy_not_white():
    """At the returned spy's site, the supplant offers an enemy troop but NOT a white troop."""
    session = make_card_test_session(
        _make_engine(), [_P1, _P2],
        hand={_P1: ["spellspinner"]},
        troops={_P1: {_SITE_A: [_P1, _P2, "white", None, None, None]}},
        spies={_SITE_A: [_P1]},
        current_player=_P1,
    )

    _play_spellspinner(session)
    _choose_option(session, "option_2")

    return_moves = _labeled_moves(session, "return spy")
    assert return_moves, f"No return-spy moves, labels: {[m.label for m in return_moves]}"
    session.submit_move(return_moves[0].move)

    supplant_moves = _labeled_moves(session, "supplant")
    labels = [m.label.lower() for m in supplant_moves]
    assert any("player 2" in label for label in labels), (
        f"Enemy (p2) troop should be a supplant target, got: {labels}"
    )
    assert not any("white" in label for label in labels), (
        f"White troop must NOT be a supplant target, got: {labels}"
    )

    session.destroy()


def test_spellspinner_option2_full_state_effects():
    """Return a spy, then supplant an enemy troop: spy returns to barracks,
    enemy troop moves to the trophy hall, and an own troop is placed."""
    session = make_card_test_session(
        _make_engine(), [_P1, _P2],
        hand={_P1: ["spellspinner"]},
        troops={_P1: {_SITE_A: [_P1, _P2, None, None, None, None]}},
        spies={_SITE_A: [_P1]},
        current_player=_P1,
    )
    spies_before = _spies_available(session, _P1)
    barracks_before = _barracks(session, _P1)
    assert "p2" not in _trophy_hall(session, _P1), "Trophy hall starts empty of p2"

    _play_spellspinner(session)
    _choose_option(session, "option_2")

    return_moves = _labeled_moves(session, "return spy")
    session.submit_move(return_moves[0].move)

    supplant_moves = _labeled_moves(session, "supplant")
    session.submit_move(supplant_moves[0].move)

    assert not _has_pending_generic(session), "Expected card to fully resolve"

    assert _spies_available(session, _P1) == spies_before + 1, "Returned spy returns to barracks"
    assert "p2" in _trophy_hall(session, _P1), "Supplanted enemy troop enters p1's trophy hall"

    troops = _troops_at_node(session, _SITE_A)
    assert "p2" not in troops, f"Enemy troop should be supplanted, got {troops}"
    assert "p1" in troops, "p1's own troop should replace the enemy troop"
    assert _barracks(session, _P1) == barracks_before - 1, "Placing a troop decrements barracks"

    session.destroy()


def test_spellspinner_option2_return_spy_only_own_spies():
    """Return-spy selection offers only the player's own spies (spy_owner=self),
    even when the player has presence at an enemy spy's site."""
    session = make_card_test_session(
        _make_engine(), [_P1, _P2],
        hand={_P1: ["spellspinner"]},
        troops={
            _P1: {
                _SITE_A: [_P1, _P2, None, None, None, None],
                _SITE_B: [_P1, _P2, None, None, None, None],
            },
        },
        spies={_SITE_A: [_P1], _SITE_B: [_P2]},
        current_player=_P1,
    )

    _play_spellspinner(session)
    _choose_option(session, "option_2")

    return_moves = _labeled_moves(session, "return spy")
    labels = [m.label.lower() for m in return_moves]
    assert any(_SITE_A_NAME in label for label in labels), f"p1's spy site should be offered, got: {labels}"
    assert not any(_SITE_B_NAME in label for label in labels), (
        f"p2's spy site must not be offered, got: {labels}"
    )

    session.destroy()


def test_spellspinner_option2_not_available_without_spies():
    """option_2 is unavailable when the player has no spies on the board."""
    session = make_card_test_session(
        _make_engine(), [_P1, _P2],
        hand={_P1: ["spellspinner"]},
        troops={_P1: {_SITE_A: [_P1, _P2, None, None, None, None]}},
        current_player=_P1,
    )

    _play_spellspinner(session)

    option_moves = [m for m in session.legal_moves()
                    if getattr(m, "move_type", "") == "resolve_generic"]
    opts = {m.data.get("action_id"): m.data for m in option_moves}
    assert "option_1" in opts, f"option_1 should be available, got: {list(opts)}"
    assert "option_2" in opts, "option_2 should be in the list"
    assert opts["option_2"].get("target_id") == "unavailable", (
        f"option_2 should be unavailable (no spies on board), got: {opts['option_2']}"
    )

    session.destroy()
