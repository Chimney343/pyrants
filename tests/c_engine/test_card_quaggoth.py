"""Quaggoth card behaviour tests via the C engine bindings.

Quaggoth — "Assassinate a white troop for each site you control."

Execution model (``data/cards/quaggoth.json``): a ``sequence`` with one
``assassinate_troop`` action whose ``quantity`` is ``variable_repeat`` with
``count_from: controlled_sites`` and a ``white_troop_only`` filter.

Traced through the C engine:

- ``resolve_runtime_action_count`` resolves ``controlled_sites`` to
  ``count_controlled_sites`` (``helpers.c``), which counts sites where the
  player holds a *majority* (``site_majority_owner``: strict majority, no
  tie, occupant not ``white``).
- ``sel_assassinate_supplant`` (``selection.c``) emits one resolve move per
  white troop at a site where the player has presence.
- ``apply_free_assassinate`` (``helpers.c``) removes the white troop and adds
  it to the player's trophy hall.
- ``auto_resolve_pending_generic`` skips remaining repeats when legal white
  targets run short, so the card never stalls.

These tests lock in that behaviour.
"""

from __future__ import annotations

import ctypes
from pathlib import Path

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
_QUAGGOTH = "quaggoth"

_SITE_A = "site_gauntlgrym"    # troop_capacity 3
_SITE_B = "site_jhachalkhyn"   # troop_capacity 4
_SITE_C = "site_gracklstugh"   # troop_capacity 4 (starts with 2 white troops)

_CATALOG = Path(__file__).resolve().parents[2] / "data" / "cards"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(session, node_id: str):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return s.nodes[ni]
    raise ValueError(f"Node {node_id} not found")


def _reset_board(session) -> None:
    """Clear every node's troop slots and spies for a deterministic board."""
    s = _sptr(session).contents
    for ni in range(s.node_count):
        s.nodes[ni].troop_slot_count = 0
        s.nodes[ni].spy_count = 0


def _set_troops(session, node_id: str, slots: list[str | None]) -> None:
    ns = _node(session, node_id)
    ns.troop_slot_count = len(slots)
    for si, occ in enumerate(slots):
        ns.troop_slots[si] = 0 if occ is None else _lib.intern(occ.encode())


def _troop_owners(session, node_id: str) -> list[str | None]:
    ns = _node(session, node_id)
    out = []
    for si in range(ns.troop_slot_count):
        sym = ns.troop_slots[si]
        out.append(None if sym == 0 else _lib.intern_str(sym).decode())
    return out


def _trophies(session, pid: str) -> list[str]:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.trophy_hall[i]).decode() for i in range(ps.trophy_hall_count)]


def _controlled_sites(session, pid: str) -> int:
    """Direct call to the C engine's count_controlled_sites."""
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    player_sym = _sptr(session).contents.players[pi].player_id
    _lib.count_controlled_sites.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    _lib.count_controlled_sites.restype = ctypes.c_int
    return _lib.count_controlled_sites(_sptr(session), player_sym)


def _play_card(session, card_id: str = _QUAGGOTH) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    raise AssertionError(f"{card_id} not playable")


def _resolve_targets(session) -> set[tuple[str, str]]:
    return {
        (m.data["action_id"], str(m.data.get("target_id")))
        for m in session.legal_moves()
        if m.move_type == "resolve_generic"
    }


def _submit(session, action_id: str, target_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type != "resolve_generic":
            continue
        d = m.data
        if d.get("action_id") == action_id and str(d.get("target_id")) == str(target_id):
            session.submit_move(m)
            return
    raise AssertionError(f"No resolve_generic for {action_id}/{target_id}")


def _resolve_all(session) -> int:
    count = 0
    while True:
        gens = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
        if not gens:
            return count
        session.submit_move(gens[0])
        count += 1


def _make_session(hand=None, current_player=_P1):
    return make_card_test_session(
        _make_engine(),
        [_P1, _P2],
        hand=hand or {_P1: [_QUAGGOTH]},
        current_player=current_player,
    )


# ---------------------------------------------------------------------------
# Catalog encoding
# ---------------------------------------------------------------------------

def test_quaggoth_execution_model_encoding():
    """The catalog must encode a single variable_repeat assassinate_troop."""
    catalog = assemble_catalog_payload(_CATALOG)
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    q = next(c for c in cards if c.get("card_id") == _QUAGGOTH)

    assert q["rules_text"] == "Assassinate a white troop for each site you control."

    em = q["execution_model"]
    assert em["kind"] == "sequence"
    actions = em["actions"]
    assert len(actions) == 1

    a = actions[0]
    assert a["op"] == "assassinate_troop"
    assert a["target_scope"] == "board_site"
    assert a["timing"] == "immediate"
    assert a["optional"] is False
    assert a["filters"] == ["white_troop_only"]
    assert a["quantity"] == {"kind": "variable_repeat", "value": None}
    assert a["metadata"] == {"count_from": "controlled_sites"}


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------

def test_quaggoth_count_is_majority_not_total_control():
    """controlled_sites counts strict-majority sites, not exclusive control."""
    session = _make_session()
    _reset_board(session)
    _set_troops(session, _SITE_A, [_P1, _P1, "white"])       # majority (2 vs 1)
    _set_troops(session, _SITE_B, [_P1, "white", None, None])  # tie (1 vs 1)
    _set_troops(session, _SITE_C, ["white", "white", None, None])  # white majority

    assert _controlled_sites(session, _P1) == 1, (
        "Only site_gauntlgrym is majority-controlled"
    )
    session.destroy()


def test_quaggoth_assassinates_one_white_per_controlled_site():
    """Two majority sites with one white each yield two assassinations."""
    session = _make_session()
    _reset_board(session)
    _set_troops(session, _SITE_A, [_P1, _P1, "white"])
    _set_troops(session, _SITE_B, [_P1, _P1, "white", None])

    assert _controlled_sites(session, _P1) == 2

    _play_card(session)
    assert _resolve_all(session) == 2

    trophies = _trophies(session, _P1)
    assert trophies == ["white", "white"], f"Two white trophies expected, got {trophies}"
    assert not _sptr(session).contents.pending_generic, "Card must fully resolve"
    session.destroy()


def test_quaggoth_only_white_troops_are_targets():
    """Own and enemy-player troops are never targetable; only white is."""
    session = _make_session()
    _reset_board(session)
    # p1 majority (2 p1 vs 1 p2 vs 1 white).
    _set_troops(session, _SITE_B, [_P1, _P1, _P2, "white"])

    assert _controlled_sites(session, _P1) == 1

    _play_card(session)
    targets = _resolve_targets(session)
    assert (_SITE_B, "3") in targets, "White troop must be targetable"
    assert (_SITE_B, "0") not in targets, "Own troop must not be targetable"
    assert (_SITE_B, "1") not in targets, "Own troop must not be targetable"
    assert (_SITE_B, "2") not in targets, "Enemy player troop must not be targetable"

    _submit(session, _SITE_B, "3")
    assert _trophies(session, _P1) == ["white"]
    session.destroy()


def test_quaggoth_requires_presence():
    """White troops at sites without presence are not offered."""
    session = _make_session()
    _reset_board(session)
    _set_troops(session, _SITE_A, [_P1, _P1, "white"])  # presence + majority
    _set_troops(session, _SITE_C, ["white", "white", None, None])  # no presence

    assert _controlled_sites(session, _P1) == 1

    _play_card(session)
    targets = _resolve_targets(session)
    assert (_SITE_A, "2") in targets, "White at presence site must be targetable"
    assert not any(a == _SITE_C for a, _ in targets), (
        "White at no-presence site must not be offered"
    )
    session.destroy()


def test_quaggoth_resolves_as_many_as_possible_when_targets_run_short():
    """Three controlled sites but one white troop -> one assassination, no stall."""
    session = _make_session()
    _reset_board(session)
    _set_troops(session, _SITE_A, [_P1, _P1, "white"])     # majority, 1 white
    _set_troops(session, _SITE_B, [_P1, _P1, None, None])  # majority, 0 white
    _set_troops(session, _SITE_C, [_P1, _P1, None, None])  # majority, 0 white

    assert _controlled_sites(session, _P1) == 3

    _play_card(session)
    resolved = _resolve_all(session)

    assert resolved == 1, f"Expected 1 assassination (only 1 white target), got {resolved}"
    assert _trophies(session, _P1) == ["white"]
    assert not _sptr(session).contents.pending_generic, "Card must fully resolve"
    session.destroy()


def test_quaggoth_no_targets_fully_skips():
    """Controlled sites with no white troops resolve with zero assassinations."""
    session = _make_session()
    _reset_board(session)
    _set_troops(session, _SITE_A, [_P1, _P1, None])
    _set_troops(session, _SITE_B, [_P1, _P1, None, None])

    assert _controlled_sites(session, _P1) == 2

    _play_card(session)
    assert not _sptr(session).contents.pending_generic, (
        "No white targets -> card resolves immediately"
    )
    assert not any(m.move_type == "resolve_generic" for m in session.legal_moves())
    assert _trophies(session, _P1) == []
    session.destroy()


def test_quaggoth_white_assassinate_adds_trophy():
    """Assassinating a white troop adds 'white' to the trophy hall."""
    session = _make_session()
    _reset_board(session)
    _set_troops(session, _SITE_A, [_P1, _P1, "white"])

    _play_card(session)
    _submit(session, _SITE_A, "2")

    assert "white" in _trophies(session, _P1)
    assert _troop_owners(session, _SITE_A) == [_P1, _P1, None]
    session.destroy()
