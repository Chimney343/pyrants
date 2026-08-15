"""Wight card behavior tests.

Wight (3-cost, Malice/Undead): modal choice.
- Option 1: gain 2 power (immediate).
- Option 2: devour a card from hand, then supplant an enemy troop at a site
  where the player has presence (standard supplant: enemy troop only).

Locks in:
- Option 2 is legal only when the player has another card in hand to devour
  AND an enemy troop at a presence site; neutral white troops alone do not
  satisfy the supplant requirement.
- The devoured card is the card the player selected (not the first card).
- Supplant targets enemy player troops, not white troops.
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.engine_bindings import _lib
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _sptr,
    make_card_test_session,
)

P1 = "p1"
P2 = "p2"
CARD = "wight"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SCENARIO_PATH = DATA_DIR / "scenarios" / "batch_card_generation" / "124_seed_4_wight.json"


def _player_index(session, pid: str) -> int:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.player_ids[i]).decode() == pid:
            return i
    return -1


def _hand_ids(session, pid: str) -> list[str]:
    pi = _player_index(session, pid)
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.hand[j]).decode() for j in range(ps.hand_count)]


def _devour_pile_ids(session) -> list[str]:
    s = _sptr(session).contents
    return [_lib.intern_str(s.devour_pile[j]).decode() for j in range(s.devour_pile_count)]


def _trophy_hall_ids(session, pid: str) -> list[str]:
    pi = _player_index(session, pid)
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.trophy_hall[j]).decode() for j in range(ps.trophy_hall_count)]


def _node_slots(session, node_id: str) -> list[str | None]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            out = []
            for si in range(ns.troop_slot_count):
                occ = ns.troop_slots[si]
                out.append(_lib.intern_str(occ).decode() if occ else None)
            return out
    return []


def _has_pending_generic(session) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _play_wight(session):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == CARD:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError("Wight not playable")


def _option_moves(session):
    return [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic"
        and m.data.get("action_id") in ("option_1", "option_2")
    ]


def _select_option(session, option_id: str):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == option_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{option_id} not selectable")


def _build_session(**kwargs):
    defaults = {
        "player_ids": [P1, P2],
        "hand": {P1: [CARD, "noble", "soldier", "priestess_of_lolth"]},
        "troops": {P1: {"site_gauntlgrym": [P1, P2, None, None]}},
        "current_player": P1,
    }
    defaults.update(kwargs)
    eng = _make_engine()
    session = make_card_test_session(eng, defaults.pop("player_ids"), **defaults)
    return session


# ---------------------------------------------------------------------------
# Modal legality
# ---------------------------------------------------------------------------


def test_option_2_available_with_enemy_troop_and_cards_in_hand():
    """Option 2 is selectable when the player has a card to devour and an
    enemy troop at a site where they have presence."""
    session = _build_session()

    _play_wight(session)

    opts = {m.data["action_id"]: m.data["target_id"] for m in _option_moves(session)}
    assert "option_2" in opts, f"option_2 should be offered, got {list(opts)}"
    assert opts["option_2"] != "unavailable", (
        "option_2 must be available with a card in hand and an enemy troop at presence"
    )

    session.destroy()


def test_option_2_unavailable_without_enemy_troop_at_presence():
    """Option 2 is unavailable when the player has cards in hand but no enemy
    troop at a presence site — neutral white troops do not satisfy it."""
    session = _build_session(
        troops={P1: {"site_gauntlgrym": [P1, "white", None, None]}},
    )

    _play_wight(session)

    opts = {m.data["action_id"]: m.data["target_id"] for m in _option_moves(session)}
    assert opts.get("option_2") == "unavailable", (
        "option_2 must be unavailable without an enemy troop at presence, "
        f"got {opts}"
    )

    session.destroy()


def test_option_2_unavailable_when_wight_is_last_card():
    """Option 2 must be unavailable when Wight is the only card in hand."""
    session = _build_session(hand={P1: [CARD]})

    _play_wight(session)

    opts = {m.data["action_id"]: m.data["target_id"] for m in _option_moves(session)}
    assert opts.get("option_2") == "unavailable", (
        "option_2 must be unavailable when there is no other card in hand to devour"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Devour behaviour
# ---------------------------------------------------------------------------


def test_devour_devours_selected_card_not_first():
    """Devouring a non-first hand card must remove the selected card, not hand[0]."""
    session = _build_session()

    _play_wight(session)
    _select_option(session, "option_2")

    hand_before = _hand_ids(session, P1)
    assert "soldier" in hand_before

    devour_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "soldier"
    ]
    assert devour_moves, f"soldier should be a devour target, got {[m.data for m in session.legal_moves()]}"
    session.submit_move(devour_moves[0])

    hand_after = _hand_ids(session, P1)
    assert "soldier" not in hand_after, f"soldier should be devoured, hand={hand_after}"
    assert "noble" in hand_after, f"noble should still be in hand (was not selected), hand={hand_after}"
    assert "soldier" in _devour_pile_ids(session), "soldier should be in the devour pile"

    session.destroy()


def test_devour_offers_every_other_hand_card():
    """Devour targets should be every hand card except the played Wight."""
    session = _build_session()

    _play_wight(session)
    _select_option(session, "option_2")

    targets = {
        m.data["action_id"] for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    }
    assert targets == {"noble", "soldier", "priestess_of_lolth"}, (
        f"devour should offer exactly the remaining hand cards, got {targets}"
    )
    assert CARD not in targets, "Wight itself must not be a devour target"

    session.destroy()


# ---------------------------------------------------------------------------
# Supplant behaviour
# ---------------------------------------------------------------------------


def test_supplant_targets_enemy_troop_at_presence():
    """Option 2 supplant accepts an enemy player troop at a presence site."""
    session = _build_session()

    _play_wight(session)
    _select_option(session, "option_2")

    devour = [m for m in session.legal_moves()
              if m.move_type == "resolve_generic" and m.data.get("action_id") == "soldier"][0]
    session.submit_move(devour)

    supplant_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "site_gauntlgrym"
    ]
    enemy_slot = [m for m in supplant_moves if m.data.get("target_id") == "1"]
    assert enemy_slot, f"enemy troop slot should be offered, got {[m.data for m in supplant_moves]}"

    session.submit_move(enemy_slot[0])

    assert P2 in _trophy_hall_ids(session, P1), "supplanted enemy troop goes to trophy hall"
    assert _node_slots(session, "site_gauntlgrym")[1] == P1, "enemy slot replaced by p1"
    assert not _has_pending_generic(session), "card should fully resolve"

    session.destroy()


def test_supplant_excludes_white_troop():
    """Standard supplant targets enemy troops only; a white troop in the same
    site must not be offered as a supplant target."""
    session = _build_session(
        troops={P1: {"site_gauntlgrym": [P1, "white", P2, None]}},
    )

    _play_wight(session)
    _select_option(session, "option_2")

    devour = [m for m in session.legal_moves()
              if m.move_type == "resolve_generic" and m.data.get("action_id") == "soldier"][0]
    session.submit_move(devour)

    supplant_moves = [
        m for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "site_gauntlgrym"
    ]
    slot_ids = {m.data.get("target_id") for m in supplant_moves}
    assert "2" in slot_ids, f"enemy slot 2 should be offered, got {[m.data for m in supplant_moves]}"
    assert "1" not in slot_ids, (
        f"white slot 1 must NOT be offered (standard supplant is enemy-only), "
        f"got {[m.data for m in supplant_moves]}"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Scenario integration
# ---------------------------------------------------------------------------


def test_wight_scenario_option_2_resolves_end_to_end():
    """Play the shipped Wight scenario: option_2 is legal and resolves fully."""
    from engine_c.bindings.session import CSession

    session = CSession.load(str(SCENARIO_PATH))

    playable = [m for m in session.legal_moves()
                if m.move_type == "play_card" and m.data.get("card_id") == CARD]
    assert playable, "Wight should be playable in its scenario"
    session.submit_move(playable[0])

    opts = {m.data["action_id"]: m.data["target_id"] for m in _option_moves(session)}
    assert opts.get("option_2") != "unavailable", (
        f"option_2 must be available in the scenario, got {opts}"
    )

    _select_option(session, "option_2")
    devour = [m for m in session.legal_moves()
              if m.move_type == "resolve_generic" and m.data.get("action_id") == "soldier"][0]
    session.submit_move(devour)

    supplant = [m for m in session.legal_moves()
                if m.move_type == "resolve_generic" and m.data.get("action_id") == "site_ch_chitl"][0]
    session.submit_move(supplant)

    assert not _has_pending_generic(session), "Wight should fully resolve in its scenario"

    session.destroy()
