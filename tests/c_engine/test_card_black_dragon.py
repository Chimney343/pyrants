"""Black Dragon card behavior tests.

Black Dragon: "Supplant a white troop anywhere. Gain 1 VP token for every
3 white trophies."

Two mechanics are validated end-to-end through the C engine bindings:

1. ``supplant_troop`` with the ``white_troop_only`` filter and
   ``ignore_presence_requirement`` metadata can supplant a white troop at any
   site (no presence required) and adds that white troop to the current
   player's trophy hall.
2. ``grant_vp`` with ``count_from=trophy_hall_white``, ``per=3`` and
   ``as=vp_tokens`` awards VP *tokens* (not score), floored to groups of 3.
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.engine_bindings import Sym, _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from game_setup.loaders import assemble_catalog_payload
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _player_vp_tokens,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_P1 = "p1"
_P2 = "p2"
_SITE = "site_gauntlgrym"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _player_score(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].score


def _trophy_hall(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == pid:
            ps = s.players[i]
            return [
                _lib.intern_str(ps.trophy_hall[j]).decode()
                for j in range(ps.trophy_hall_count)
            ]
    return []


def _add_trophies(session: CSession, pid: str, count: int, label: str) -> None:
    s = _sptr(session).contents
    pi = _session_player_index(session, pid)
    ps = s.players[pi]
    for _ in range(count):
        if ps.trophy_hall_count < 50:
            ps.trophy_hall[ps.trophy_hall_count] = _lib.intern(label.encode())
            ps.trophy_hall_count += 1


def _clear_board(session: CSession) -> None:
    s = _sptr(session).contents
    for ni in range(s.node_count):
        ns = s.nodes[ni]
        for si in range(ns.troop_slot_count):
            ns.troop_slots[si] = Sym(0)
        ns.spy_count = 0


def _set_troops(session: CSession, node_id: str, slots: list) -> None:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        ns = s.nodes[ni]
        if ns.node_id == nid:
            ns.troop_slot_count = len(slots)
            for si, occ in enumerate(slots):
                ns.troop_slots[si] = Sym(0) if occ is None else _lib.intern(occ.encode())
            return
    raise ValueError(f"Node {node_id} not found")


def _node_troops(session: CSession, node_id: str) -> list:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        ns = s.nodes[ni]
        if ns.node_id == nid:
            out = []
            for si in range(ns.troop_slot_count):
                occ = ns.troop_slots[si]
                if occ == Sym(0):
                    out.append(None)
                else:
                    raw = _lib.intern_str(occ)
                    out.append(raw.decode() if raw else None)
            return out
    raise ValueError(f"Node {node_id} not found")


def _build_session(white_trophies: int) -> CSession:
    """Session with Black Dragon in hand and a single white troop on the board."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["black_dragon"]},
        current_player=_P1,
    )
    _clear_board(session)
    _set_troops(session, _SITE, ["white", None, None])
    if white_trophies:
        _add_trophies(session, _P1, white_trophies, "white")
    return session


def _play_black_dragon(session: CSession) -> None:
    playable = [m for m in session.legal_moves()
                if m.move_type == "play_card"
                and m.data.get("card_id") == "black_dragon"]
    assert playable, "Black Dragon not playable"
    session.submit_move(playable[0])


def _supplant_moves(session: CSession, node_id: str = _SITE) -> list:
    return [m for m in session.legal_moves()
            if m.move_type == "resolve_generic"
            and m.data.get("action_id") == node_id]


# ---------------------------------------------------------------------------
# Catalog structure
# ---------------------------------------------------------------------------


def test_black_dragon_catalog_encodes_vp_tokens():
    """The catalog must encode the white-troop supplant and VP-token award."""
    catalog = assemble_catalog_payload(DATA_DIR / "cards")

    card = None
    for entry in catalog["cards"]:
        if entry["card_id"] == "black_dragon":
            card = entry
            break
    assert card is not None, "Black Dragon not found in catalog"
    assert card["name"] == "Black Dragon"
    assert card["cost"] == 8
    assert card["aspect"] == "conquest"
    assert "dragon" in card["secondary_aspects"]

    em = card["execution_model"]
    assert em["kind"] == "sequence"
    actions = em["actions"]
    assert len(actions) == 2, f"Expected 2 actions, got {len(actions)}"

    a1 = actions[0]
    assert a1["op"] == "supplant_troop"
    assert a1["target_scope"] == "board_site"
    assert "white_troop_only" in a1["filters"]
    assert a1["metadata"]["ignore_presence_requirement"] is True

    a2 = actions[1]
    assert a2["op"] == "grant_vp"
    assert a2["metadata"]["count_from"] == "trophy_hall_white"
    assert a2["metadata"]["per"] == 3
    assert a2["metadata"]["as"] == "vp_tokens", (
        "Black Dragon must award VP *tokens*, not score"
    )

    top_actions = card.get("actions", [])
    assert len(top_actions) == 2
    assert top_actions[1]["metadata"]["as"] == "vp_tokens", (
        "Top-level actions array must mirror the vp_tokens award"
    )


# ---------------------------------------------------------------------------
# Supplant behaviour
# ---------------------------------------------------------------------------


def test_black_dragon_supplants_white_troop_without_presence():
    """A white troop can be supplanted anywhere, even with no presence there."""
    session = _build_session(white_trophies=0)

    trophies_before = _trophy_hall(session, _P1).count("white")

    _play_black_dragon(session)
    assert bool(_sptr(session).contents.pending_generic), "Expected pending generic"

    supplant = _supplant_moves(session)
    assert supplant, f"No supplant moves for {_SITE}"
    white = [m for m in supplant if m.data.get("target_id") == "0"]
    assert white, f"Slot 0 (white) should be supplantable, targets={[m.data for m in supplant]}"
    session.submit_move(white[0])

    assert not bool(_sptr(session).contents.pending_generic), (
        "Card should fully resolve after supplant"
    )

    hall = _trophy_hall(session, _P1)
    assert hall.count("white") == trophies_before + 1, (
        f"Supplanting a white troop should add it to the trophy hall, hall={hall}"
    )
    assert _node_troops(session, _SITE)[0] == _P1, (
        "Supplanting should place the player's troop in the vacated slot"
    )

    session.destroy()


def test_black_dragon_only_targets_white_troops():
    """white_troop_only must exclude enemy player troops from supplant targets."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: ["black_dragon"]},
        current_player=_P1,
    )
    _clear_board(session)
    _set_troops(session, _SITE, ["white", _P2, None])

    _play_black_dragon(session)

    supplant = _supplant_moves(session)
    target_ids = {m.data.get("target_id") for m in supplant}
    assert target_ids == {"0"}, (
        f"Only the white troop (slot 0) should be supplantable, got {target_ids}"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# VP-token award
# ---------------------------------------------------------------------------


def test_black_dragon_awards_vp_tokens_not_score():
    """5 white trophies + 1 supplanted = 6 -> 2 VP tokens; score unchanged."""
    session = _build_session(white_trophies=5)

    before_tokens = _player_vp_tokens(session, _P1)
    before_score = _player_score(session, _P1)

    _play_black_dragon(session)
    white = [m for m in _supplant_moves(session) if m.data.get("target_id") == "0"]
    assert white, "Expected a white troop to supplant"
    session.submit_move(white[0])

    assert _player_vp_tokens(session, _P1) == before_tokens + 2, (
        f"Expected 2 VP tokens (6 white trophies // 3), "
        f"got {_player_vp_tokens(session, _P1)} (was {before_tokens})"
    )
    assert _player_score(session, _P1) == before_score, (
        f"Score must not change (VP goes to vp_tokens), "
        f"was {before_score}, now {_player_score(session, _P1)}"
    )

    session.destroy()


def test_black_dragon_rounds_down():
    """4 white trophies + 1 supplanted = 5 -> 1 VP token (5 // 3)."""
    session = _build_session(white_trophies=4)

    before_tokens = _player_vp_tokens(session, _P1)

    _play_black_dragon(session)
    white = [m for m in _supplant_moves(session) if m.data.get("target_id") == "0"]
    session.submit_move(white[0])

    assert _player_vp_tokens(session, _P1) == before_tokens + 1, (
        f"Expected 1 VP token (5 white trophies // 3), "
        f"got {_player_vp_tokens(session, _P1)} (was {before_tokens})"
    )

    session.destroy()


def test_black_dragon_zero_trophies_zero_vp():
    """0 white trophies + 1 supplanted = 1 -> 0 VP tokens, score unchanged."""
    session = _build_session(white_trophies=0)

    before_tokens = _player_vp_tokens(session, _P1)
    before_score = _player_score(session, _P1)

    _play_black_dragon(session)
    white = [m for m in _supplant_moves(session) if m.data.get("target_id") == "0"]
    session.submit_move(white[0])

    assert _player_vp_tokens(session, _P1) == before_tokens, (
        "Expected zero VP tokens when fewer than 3 white trophies"
    )
    assert _player_score(session, _P1) == before_score, (
        "Score must not change"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# CGameView projection
# ---------------------------------------------------------------------------


def test_c_game_view_control_vp_fields():
    """CGameView should populate current_player_control_vp and total_control_vp."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        troops={
            _P1: {
                _SITE: [_P1, None, None, None],
                "site_jhachalkhyn": [_P1, None, None, None],
            }
        },
        current_player=_P1,
    )

    view = build_c_game_view(session)
    assert hasattr(view, "current_player_control_vp"), "CGameViewData missing current_player_control_vp"
    assert hasattr(view, "current_player_total_control_vp"), "CGameViewData missing current_player_total_control_vp"

    assert view.current_player_controlled_sites >= 1, (
        f"Expected p1 to control at least one site, got {view.current_player_controlled_sites}"
    )
    assert view.current_player_control_vp > 0, (
        f"Expected positive control_vp, got {view.current_player_control_vp}"
    )

    session.destroy()
