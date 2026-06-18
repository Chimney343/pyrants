"""Python wrapper around engine_build_view — projects CGameView into Python dataclasses.

Maps Sym→str via the DLL's intern_str and enriches card IDs with catalog
metadata (name, cost, aspect, rules) loaded once from data/cards/catalog.json.

Usage:
    from engine_c.bindings.view import build_c_game_view
    view = build_c_game_view(session, node_names={"site_1": "Menzoberranzan"})
"""

from __future__ import annotations

import ctypes
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

from .engine_bindings import (
    _lib, Sym, GameStateStruct, CGameView,
    MAX_PLAYERS, MAX_NODES, MAX_ZONE_SIZE, MAX_TROOP_SLOTS, MAX_SPY_SLOTS,
    PHASE_SETUP, PHASE_DRAW, PHASE_MAIN, PHASE_END_OF_TURN,
    PHASE_CLEANUP, PHASE_GAME_OVER,
)
from .label_enrich import enrich_label

_PHASE_MAP = {
    PHASE_SETUP: "setup",
    PHASE_DRAW: "draw",
    PHASE_MAIN: "main",
    PHASE_END_OF_TURN: "end_of_turn",
    PHASE_CLEANUP: "cleanup",
    PHASE_GAME_OVER: "game_over",
}


def _sym_str(sym) -> Optional[str]:
    if sym == 0:
        return None
    return _lib.intern_str(sym).decode()


@dataclass(frozen=True)
class CardView:
    card_id: str
    name: str
    cost: int
    aspect: str
    deck_vp: int
    inner_circle_vp: int
    rules_text: str
    notes: str
    secondary_aspects: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlayerSummaryView:
    player_id: str
    is_current: bool
    hand_count: int
    deck_count: int
    discard_count: int
    played_count: int
    inner_circle_count: int
    trophy_hall_count: int
    barracks: int
    spies_available: int
    vp_tokens: int
    score: int


@dataclass(frozen=True)
class NodeOccupancyView:
    node_id: str
    kind: str
    adjacent_to: tuple[str, ...]
    control_vp: int
    total_control_vp_per_turn: int
    troop_slots: tuple[Optional[str], ...]
    spies: tuple[str, ...]
    vp_tokens: int


@dataclass(frozen=True)
class CGameViewData:
    round_number: int
    phase: str
    current_player_id: str
    resource_power: int
    resource_influence: int
    hand: tuple[CardView, ...]
    current_player_played: tuple[CardView, ...]
    current_player_deck_count: int
    current_player_discard: tuple[CardView, ...]
    current_player_inner_circle: tuple[CardView, ...]
    current_player_trophy_hall: tuple[str, ...]
    current_player_controlled_sites: int
    current_player_total_control_sites: int
    market_row: tuple[CardView, ...]
    market_deck_count: int
    market_discard_count: int
    player_summaries: tuple[PlayerSummaryView, ...]
    board_nodes: tuple[NodeOccupancyView, ...]
    prompts: tuple[str, ...] = ()
    legal_moves: tuple = ()
    is_terminal: bool = False
    winner_id: Optional[str] = None
    final_scores: dict[str, int] = field(default_factory=dict)

    @property
    def board_nodes_by_id(self) -> dict[str, NodeOccupancyView]:
        return {node.node_id: node for node in self.board_nodes}


class CLegalMoveView:
    """Lightweight LegalMoveView-compatible wrapper for C engine moves."""

    __slots__ = ("move", "move_type", "label", "payload", "available")

    def __init__(self, move, move_type: str, label: str, *, available: bool = True):
        self.move = move
        self.move_type = move_type
        self.label = label
        self.payload = {}
        self.available = available


def _load_catalog() -> dict[str, dict]:
    catalog_path = Path(__file__).parent.parent.parent / "data" / "cards" / "catalog.json"
    with open(catalog_path, encoding="utf-8") as f:
        raw = json.load(f)
    cards = raw.get("cards", raw) if isinstance(raw, dict) else raw
    result: dict[str, dict] = {}
    for entry in cards:
        cid = entry.get("card_id", "")
        if cid:
            result[cid] = entry
    return result


@lru_cache(maxsize=1)
def _catalog_cache() -> dict[str, dict]:
    return _load_catalog()


def _make_card_view(card_id: str) -> CardView:
    cat = _catalog_cache()
    entry = cat.get(card_id)
    if entry is None:
        return CardView(
            card_id=card_id, name="Unknown Card", cost=0, aspect="unknown",
            deck_vp=0, inner_circle_vp=0, rules_text="", notes="",
        )
    return CardView(
        card_id=entry.get("card_id", card_id),
        name=entry.get("name", "Unknown Card"),
        cost=entry.get("cost", 0),
        aspect=entry.get("aspect", "unknown"),
        deck_vp=entry.get("deck_vp", 0),
        inner_circle_vp=entry.get("inner_circle_vp", 0),
        rules_text=entry.get("rules_text", ""),
        notes=entry.get("notes", ""),
        secondary_aspects=tuple(entry.get("secondary_aspects", ())),
    )


def _build_c_legal_moves(session, state_ptr, *, node_names=None, player_spy_count=0) -> tuple:
    try:
        moves = session.legal_moves()
    except Exception:
        return ()

    from .engine_bindings import _lib as _elib

    result = []
    for mw in moves:
        raw_label = _describe_c_move(state_ptr, mw, node_names_dict=node_names)
        source_card_id = ""
        card_action_id = ""
        is_option_choice = False
        if mw.move_type == "resolve_generic":
            try:
                pg_ptr = state_ptr.contents.pending_generic
                if pg_ptr:
                    pg = pg_ptr.contents
                    source_card_id = _elib.intern_str(pg.source_card_id).decode()
                    is_option_choice = bool(pg.awaiting_option)
                    if not is_option_choice:
                        idx = pg.next_action_index
                        if 0 <= idx < pg.current_action_count:
                            current_action = pg.current_actions[idx]
                            if current_action.action_id:
                                card_action_id = _elib.intern_str(current_action.action_id).decode()
            except Exception:
                pass
        promotion_source_card_id = ""
        if mw.move_type == "promote_card":
            try:
                s = state_ptr.contents
                if s.pending_eot_count > 0:
                    promotion_source_card_id = _elib.intern_str(
                        s.pending_eot[0].source_card_id
                    ).decode()
                elif s.pending_immediate_count > 0:
                    promotion_source_card_id = _elib.intern_str(
                        s.pending_immediate[0].source_card_id
                    ).decode()
            except Exception:
                pass
        final_label = enrich_label(
            mw.move_type, raw_label, mw.data,
            source_card_id=source_card_id,
            card_action_id=card_action_id,
            is_option_choice=is_option_choice,
            player_spy_count=player_spy_count,
            promotion_source_card_id=promotion_source_card_id,
        )
        available = mw.data.get("target_id") != "unavailable"
        if not available:
            final_label += " [ILLEGAL MOVE]"
        result.append(CLegalMoveView(mw, mw.move_type, final_label, available=available))
    return tuple(result)


def _describe_c_move(state_ptr, move_wrapper, *, node_names_dict=None) -> str:
    c_move = move_wrapper._c_move
    buf = ctypes.create_string_buffer(256)

    node_ids_arr = None
    node_labels_arr = None
    pair_count = 0
    if node_names_dict:
        ids = []
        labels = []
        for k, v in node_names_dict.items():
            ids.append(k.encode("utf-8"))
            labels.append(v.encode("utf-8"))
        pair_count = len(ids)
        if pair_count > 0:
            node_ids_arr = (ctypes.c_char_p * pair_count)(*ids)
            node_labels_arr = (ctypes.c_char_p * pair_count)(*labels)

    _lib.engine_describe_move(
        state_ptr, ctypes.byref(c_move),
        node_ids_arr or None,
        node_labels_arr or None,
        pair_count,
        buf, 256,
    )
    return buf.value.decode()


def build_c_game_view(
    session,
    *,
    node_names: Optional[dict[str, str]] = None,
) -> CGameViewData:
    """Project a CSession or CState into a client-friendly view model.

    Args:
        session: CSession instance or CState pointer (ctypes).
        node_names: Optional friendly-name override for node IDs.
    """
    from .ce_api import CState

    state_ptr = None
    if isinstance(session, ctypes.c_void_p) or (hasattr(session, "_ptr") and hasattr(session, "round_number")):
        state_ptr = session._ptr if hasattr(session, "_ptr") else session
    elif hasattr(session, "_state"):
        inner = session._state
        if isinstance(inner, CState):
            state_ptr = inner._ptr
        else:
            state_ptr = inner
    else:
        raise TypeError(f"Unsupported session type: {type(session)}")

    c_view = CGameView()
    _lib.engine_build_view(state_ptr, ctypes.byref(c_view))

    # Count current player's spies on the board for label enrichment
    player_spy_count = 0
    current_player_sym = c_view.current_player_id
    for i in range(c_view.node_count):
        nv = c_view.nodes[i]
        for j in range(nv.spy_count):
            if nv.spies[j] == current_player_sym:
                player_spy_count += 1

    current_player_id = _sym_str(c_view.current_player_id) or ""

    hand: list[CardView] = []
    played: list[CardView] = []
    discard: list[CardView] = []
    inner_circle: list[CardView] = []
    trophy_hall: list[str] = []
    current_player_deck_count = 0

    player_summaries: list[PlayerSummaryView] = []
    for i in range(c_view.player_count):
        zv = c_view.players[i]
        pid = _sym_str(c_view.player_ids[i]) or f"p{i}"
        is_current = pid == current_player_id

        player_summaries.append(PlayerSummaryView(
            player_id=pid,
            is_current=is_current,
            hand_count=zv.hand_count,
            deck_count=zv.deck_count,
            discard_count=zv.discard_count,
            played_count=zv.played_count,
            inner_circle_count=zv.inner_circle_count,
            trophy_hall_count=zv.trophy_hall_count,
            barracks=zv.barracks,
            spies_available=zv.spies_available,
            vp_tokens=zv.vp_tokens,
            score=zv.score,
        ))

        if is_current:
            for j in range(zv.hand_count):
                cid = _sym_str(zv.hand[j])
                if cid:
                    hand.append(_make_card_view(cid))
            for j in range(zv.played_count):
                cid = _sym_str(zv.played[j])
                if cid:
                    played.append(_make_card_view(cid))
            for j in range(zv.discard_count):
                cid = _sym_str(zv.discard[j])
                if cid:
                    discard.append(_make_card_view(cid))
            for j in range(zv.inner_circle_count):
                cid = _sym_str(zv.inner_circle[j])
                if cid:
                    inner_circle.append(_make_card_view(cid))
            for j in range(zv.trophy_hall_count):
                t = _sym_str(zv.trophy_hall[j])
                if t:
                    trophy_hall.append(t)
            current_player_deck_count = zv.deck_count

    market_row: list[CardView] = []
    for j in range(c_view.market_row_count):
        cid = _sym_str(c_view.market_row[j])
        if cid:
            market_row.append(_make_card_view(cid))

    board_nodes: list[NodeOccupancyView] = []
    for i in range(c_view.node_count):
        nv = c_view.nodes[i]
        nid = _sym_str(nv.node_id) or f"node_{i}"

        adjacent: list[str] = []
        for j in range(nv.adjacent_count):
            a = _sym_str(nv.adjacent_to[j])
            if a:
                adjacent.append(a)

        troop_slots: list[Optional[str]] = []
        for j in range(nv.troop_slot_count):
            t = _sym_str(nv.troop_slots[j])
            troop_slots.append(t)

        spies: list[str] = []
        for j in range(nv.spy_count):
            s = _sym_str(nv.spies[j])
            if s:
                spies.append(s)

        board_nodes.append(NodeOccupancyView(
            node_id=nid,
            kind="site" if nv.kind == 0 else "route",
            adjacent_to=tuple(adjacent),
            control_vp=nv.control_vp,
            total_control_vp_per_turn=nv.total_control_vp_per_turn,
            troop_slots=tuple(troop_slots),
            spies=tuple(sorted(spies)),
            vp_tokens=nv.vp_tokens,
        ))

    return CGameViewData(
        round_number=c_view.round_number,
        phase=_PHASE_MAP.get(c_view.phase, "unknown"),
        current_player_id=current_player_id,
        resource_power=c_view.resource_power,
        resource_influence=c_view.resource_influence,
        hand=tuple(hand),
        current_player_played=tuple(played),
        current_player_deck_count=current_player_deck_count,
        current_player_discard=tuple(discard),
        current_player_inner_circle=tuple(inner_circle),
        current_player_trophy_hall=tuple(trophy_hall),
        current_player_controlled_sites=c_view.controlled_sites,
        current_player_total_control_sites=c_view.total_control_sites,
        market_row=tuple(market_row),
        market_deck_count=c_view.market_deck_count,
        market_discard_count=c_view.market_discard_count,
        player_summaries=tuple(player_summaries),
        board_nodes=tuple(board_nodes),
        prompts=(f"{current_player_id} is acting in {_PHASE_MAP.get(c_view.phase, 'unknown').replace('_', ' ')}.",),
        legal_moves=_build_c_legal_moves(session, state_ptr, node_names=node_names, player_spy_count=player_spy_count),
    )
