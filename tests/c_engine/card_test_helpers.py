"""Helpers for C-engine card tests that build state programmatically."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import (
    MAX_TROOP_SLOTS,
    MAX_ZONE_SIZE,
    PHASE_MAIN,
    Sym,
    _lib,
)
from engine_c.bindings.session import CSession

DATA_DIR = _project_root / "data"


def _sptr(session: CSession):
    return session._state._ptr


def _session_player_index(session: CSession, pid: str) -> int:
    s = _sptr(session).contents
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == pid:
            return i
    return -1


def _player_vp_tokens(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].vp_tokens


def _make_engine(catalog_path: str | None = None,
                 board_path: str | None = None,
                 setup_path: str | None = None) -> CEngine:
    eng = CEngine()
    eng.initialize(
        catalog_path=catalog_path or str(DATA_DIR / "cards"),
        board_path=board_path or str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=setup_path or str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return eng
def make_card_test_session(
    engine: CEngine,
    player_ids: list[str],
    *,
    hand: dict[str, list[str]] | None = None,
    inner_circle: dict[str, list[str]] | None = None,
    deck: dict[str, list[str]] | None = None,
    troops: dict[str, dict[str, list[str | None]]] | None = None,
    spies: dict[str, list[str]] | None = None,
    current_player: str | None = None,
    seed: int = 0,
) -> CSession:
    session = CSession(engine, list(player_ids), seed)
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    s.round_number = 1
    if current_player:
        s.current_player_id = _lib.intern(current_player.encode())
    for i in range(s.player_count):
        ps = s.players[i]
        ps.hand_count = 0
        ps.deck_count = 0
        ps.discard_pile_count = 0
        ps.played_cards_count = 0
        ps.inner_circle_count = 0
        ps.trophy_hall_count = 0
        ps.barracks = 40
        ps.spies_available = 5
        ps.vp_tokens = 0
        ps.score = 0
    if hand:
        for pid, cards in hand.items():
            pi = _player_index(s, pid)
            if pi < 0: continue
            ps = s.players[pi]
            ps.hand_count = min(len(cards), MAX_ZONE_SIZE)
            for j, cid in enumerate(cards[:MAX_ZONE_SIZE]):
                ps.hand[j] = _lib.intern(cid.encode())
    if inner_circle:
        for pid, cards in inner_circle.items():
            pi = _player_index(s, pid)
            if pi < 0: continue
            ps = s.players[pi]
            ps.inner_circle_count = min(len(cards), MAX_ZONE_SIZE)
            for j, cid in enumerate(cards[:MAX_ZONE_SIZE]):
                ps.inner_circle[j] = _lib.intern(cid.encode())
    if deck:
        for pid, cards in deck.items():
            pi = _player_index(s, pid)
            if pi < 0: continue
            ps = s.players[pi]
            ps.deck_count = min(len(cards), MAX_ZONE_SIZE)
            for j, cid in enumerate(cards[:MAX_ZONE_SIZE]):
                ps.deck[j] = _lib.intern(cid.encode())
    if troops:
        for _pid, node_map in troops.items():
            for node_id, slots in node_map.items():
                ns = _node_state(s, node_id)
                ns.troop_slot_count = min(len(slots), MAX_TROOP_SLOTS)
                for si, occ in enumerate(slots[:MAX_TROOP_SLOTS]):
                    if occ is None: ns.troop_slots[si] = Sym(0)
                    else: ns.troop_slots[si] = _lib.intern(occ.encode())
    if spies:
        for node_id, spy_list in spies.items():
            ns = _node_state(s, node_id)
            ns.spy_count = 0
            for sp in spy_list:
                if ns.spy_count < MAX_TROOP_SLOTS:
                    ns.spies[ns.spy_count] = _lib.intern(sp.encode())
                    ns.spy_count += 1
    return session
def _player_index(s, pid: str) -> int:
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == pid: return i
    return -1
def _node_state(s, node_id: str):
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid: return s.nodes[ni]
    raise ValueError(f"Node {node_id} not found")
