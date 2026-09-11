"""Perspective-relative observation encoding (v3).

The tensor is built only from information the acting player may know: the
engine private view, the public board, the allow-listed public multisets
(:mod:`openspiel_pyrants.nn.public`) and the pending generic-choice context.
Seat 0 is always the acting player, followed by the other seats in turn order,
so 2-, 3- and 4-player games share one network.

No pyspiel import: stdlib + numpy + ctypes bindings only.
"""

from __future__ import annotations

import ctypes
import json

import numpy as np

from engine_c.bindings.engine_bindings import CGameView, _lib

from .actions import UnmappedMoveError, owner_slot, seat_order
from .index import (
    EFFECT_KINDS,
    NODE_ADJACENT,
    NODE_ID_TO_INDEX,
    NODE_IDS,
    NODE_IS_SITE,
    NODE_TROOP_CAPACITY,
    NUM_CARD_IDS,
    OP_OPTION,
    OP_SLOTS,
    OP_UNKNOWN,
    card_index,
)
from .public import public_multisets

ENCODER_VERSION = 3

MAX_SEATS = 4
BOARD_FEATURES = 24
MARKET_ROW_SLOTS = 6
PENDING_OP_SLOTS = len(OP_SLOTS)
PENDING_OPTION_SLOTS = 8
PENDING_EFFECT_SLOTS = len(EFFECT_KINDS) + 1

# Offsets within the ``pending_flags`` block, after the 8 option-position slots.
PENDING_FLAG_AWAITING_OPTION = PENDING_OPTION_SLOTS
PENDING_FLAG_OPTIONAL = PENDING_OPTION_SLOTS + 1
PENDING_FLAG_ALLOW_REPEAT = PENDING_OPTION_SLOTS + 2
PENDING_FLAG_REMAINING_REPEATS = PENDING_OPTION_SLOTS + 3

PHASES = ("setup", "main", "end_of_turn", "cleanup")


def op_index(op: str | None, *, awaiting_option: bool = False) -> int:
    """Slot for the pending op one-hot; option/unknown get their own slots."""
    if awaiting_option:
        return OP_SLOTS.index(OP_OPTION)
    try:
        return OP_SLOTS.index(op)  # type: ignore[arg-type]
    except ValueError:
        return OP_SLOTS.index(OP_UNKNOWN)


def effect_kind_index(effect_kind: str | None) -> int:
    """Slot for the pending ``custom_effect`` kind one-hot (unknown last)."""
    if effect_kind in EFFECT_KINDS:
        return EFFECT_KINDS.index(effect_kind)
    return len(EFFECT_KINDS)


def node_features(troop_slots, spies, capacity, order, adjacency) -> dict:
    """Rulebook semantics for one board node (see ``tyrants-rulebook.md``).

    * ``controller``: the colour with a *strict* majority of troops (ties flag
      no one), seats 0-3 then white (rulebook :267, :279).
    * ``total_control``: every troop space filled with *my* troops and no enemy
      spies present (rulebook :281).
    * ``presence``: a troop or spy of mine at the node, or my troop at an
      adjacent node (rulebook :248-252).

    ``troop_slots`` / ``spies`` are this node's owner ids; ``order`` is the
    seat-relative player list (``order[0]`` is me); ``adjacency`` is an iterable
    of the adjacent nodes' troop-slot tuples.
    """
    counts = [0] * 5
    for owner in troop_slots:
        slot = owner_slot(owner, order, allow_white=True)
        if slot is not None:
            counts[slot] += 1
    spies_here = list(spies)
    me = order[0] if order else None

    controller = [0] * 5
    max_troops = max(counts) if counts else 0
    if max_troops > 0 and counts.count(max_troops) == 1:
        controller[counts.index(max_troops)] = 1

    total_control = int(
        capacity > 0 and counts[0] == capacity and all(owner == me for owner in spies_here)
    )
    adjacent_my_troop = any(me in slots for slots in adjacency)
    presence = int(counts[0] > 0 or me in spies_here or adjacent_my_troop)
    return {
        "controller": controller,
        "total_control": total_control,
        "presence": presence,
    }


def _card_vector(counter) -> np.ndarray:
    vec = np.zeros(NUM_CARD_IDS, dtype=np.int32)
    for cid, count in counter.items():
        vec[card_index(cid)] += int(count)
    return vec


def _build_layout() -> dict[str, tuple[int, int]]:
    layout: dict[str, tuple[int, int]] = {}
    offset = 0

    def add(name: str, size: int) -> None:
        nonlocal offset
        layout[name] = (offset, offset + size)
        offset += size

    add("board", len(NODE_IDS) * BOARD_FEATURES)
    add("my_hand", NUM_CARD_IDS)
    add("my_played", NUM_CARD_IDS)
    add("my_discard", NUM_CARD_IDS)
    add("my_inner_circle", NUM_CARD_IDS)
    add("my_deck_remainder", NUM_CARD_IDS)
    for slot in range(3):
        add(f"opp_bag_{slot}", NUM_CARD_IDS)
    for slot in range(3):
        add(f"opp_played_{slot}", NUM_CARD_IDS)
    for slot in range(3):
        add(f"opp_inner_circle_{slot}", NUM_CARD_IDS)
    add("market_row", MARKET_ROW_SLOTS * NUM_CARD_IDS)
    add("market_remaining", NUM_CARD_IDS)
    add("special_stacks", 3)
    add("pending_source_card", NUM_CARD_IDS)
    add("pending_op", PENDING_OP_SLOTS)
    add("pending_effect_kind", PENDING_EFFECT_SLOTS)
    add("pending_flags", PENDING_OPTION_SLOTS + 4)
    add("scalars_core", 7)
    add("seat_present", MAX_SEATS)
    add("seat_is_current", MAX_SEATS)
    add("seat_features", MAX_SEATS * 8)
    add("global_scalars", 2)
    return layout


OBS_LAYOUT = _build_layout()
OBS_SIZE = max(end for _, end in OBS_LAYOUT.values())

# Feature order within one board node's BOARD_FEATURES entries.
BOARD_FEATURE_NAMES = (
    "my_troops",
    "opp1_troops",
    "opp2_troops",
    "opp3_troops",
    "white_troops",
    "empty_slots",
    "capacity",
    "my_spies",
    "opp1_spies",
    "opp2_spies",
    "opp3_spies",
    "controller_me",
    "controller_opp1",
    "controller_opp2",
    "controller_opp3",
    "controller_white",
    "total_control",
    "my_presence",
    "control_vp",
    "total_control_vp_per_turn",
    "vp_tokens",
    "is_site",
    "total_troops",
    "total_spies",
)
assert len(BOARD_FEATURE_NAMES) == BOARD_FEATURES


def _engine_view_scalars(adapter):
    c_view = CGameView()
    _lib.engine_build_view(adapter.state.ptr, ctypes.byref(c_view))
    return c_view


def encode_observation(adapter, pid: str, pending_ctx: dict | None) -> np.ndarray:
    """Encode the acting player's information state into an ``int16`` vector."""
    view = json.loads(adapter.private_view_json(pid))
    pub = view["public"]
    summaries = pub["public_player_summaries"]
    player_ids = list(adapter.player_ids)
    n = len(player_ids)
    order = tuple(seat_order(adapter, pid))
    pm = public_multisets(adapter, pid)

    obs = np.zeros(OBS_SIZE, dtype=np.int16)

    def put(block: str, start_offset: int, values) -> None:
        start = OBS_LAYOUT[block][0] + start_offset
        for i, value in enumerate(values):
            obs[start + i] = max(0, min(32767, int(value)))

    # ── board ──────────────────────────────────────────────────────────────
    board_start = OBS_LAYOUT["board"][0]
    pub_nodes = {n.get("node_id"): n for n in pub["board_nodes"]}
    troop_by_node = {nid: tuple(n.get("troop_slots", ())) for nid, n in pub_nodes.items()}
    spy_by_node = {nid: tuple(n.get("spies", ())) for nid, n in pub_nodes.items()}
    for node in pub["board_nodes"]:
        node_id = node.get("node_id", "")
        node_i = NODE_ID_TO_INDEX.get(node_id)
        if node_i is None:
            continue
        slots = list(node.get("troop_slots", ()))
        counts = [0] * 5
        for owner in slots:
            slot = owner_slot(owner, order, allow_white=True)
            if slot is not None:
                counts[slot] += 1
        spies = list(node.get("spies", ()))
        spy_counts = [0] * 5
        for owner in spies:
            slot = owner_slot(owner, order, allow_white=True)
            if slot is not None:
                spy_counts[slot] += 1
        capacity = len(slots) or NODE_TROOP_CAPACITY.get(node_id, 0)
        empty = capacity - sum(1 for s in slots if s)
        total_troops = sum(counts)
        adjacent = [
            troop_by_node[neighbor]
            for neighbor in NODE_ADJACENT.get(node_id, ())
            if neighbor in troop_by_node
        ]
        semantics = node_features(slots, spy_by_node.get(node_id, ()), capacity, order, adjacent)
        controller = semantics["controller"]
        features = (
            counts[0], counts[1], counts[2], counts[3], counts[4],
            empty, capacity,
            spy_counts[0], spy_counts[1], spy_counts[2], spy_counts[3],
            controller[0], controller[1], controller[2], controller[3], controller[4],
            semantics["total_control"], semantics["presence"],
            node.get("control_vp", 0),
            node.get("total_control_vp_per_turn", 0),
            node.get("vp_tokens", 0),
            1 if NODE_IS_SITE.get(node_id, False) else 0,
            total_troops, sum(spy_counts),
        )
        base = board_start + node_i * BOARD_FEATURES
        for j, value in enumerate(features):
            obs[base + j] = max(0, min(32767, int(value)))

    # ── my cards + opponent cards ──────────────────────────────────────────
    def fill_cards(block: str, counter) -> None:
        start = OBS_LAYOUT[block][0]
        vec = _card_vector(counter)
        obs[start:start + NUM_CARD_IDS] = np.clip(vec, 0, 32767).astype(np.int16)

    fill_cards("my_hand", pm.hand)
    fill_cards("my_played", pm.played)
    fill_cards("my_discard", pm.discard)
    fill_cards("my_inner_circle", pm.inner_circle)
    fill_cards("my_deck_remainder", pm.deck)

    for slot in range(3):
        if slot + 1 < n:
            seat_index = player_ids.index(order[slot + 1])
            fill_cards(f"opp_bag_{slot}", pm.bags[seat_index])
            fill_cards(f"opp_played_{slot}", pm.played_by_seat[seat_index])
            fill_cards(f"opp_inner_circle_{slot}", pm.inner_circle_by_seat[seat_index])

    # ── market ─────────────────────────────────────────────────────────────
    market_row_start = OBS_LAYOUT["market_row"][0]
    for slot, cid in enumerate(pm.market_row[:MARKET_ROW_SLOTS]):
        obs[market_row_start + slot * NUM_CARD_IDS + card_index(cid)] = 1
    fill_cards("market_remaining", pm.market_remaining)

    c_view = _engine_view_scalars(adapter)
    put("special_stacks", 0, [c_view.priestess_remaining, c_view.house_guard_remaining, c_view.insane_outcast_remaining])

    # ── pending choice ─────────────────────────────────────────────────────
    if pending_ctx is not None:
        src = pending_ctx.get("source_card_id")
        obs[OBS_LAYOUT["pending_source_card"][0] + card_index(src)] = 1
        awaiting = bool(pending_ctx.get("awaiting_option"))
        op = pending_ctx.get("op")
        obs[OBS_LAYOUT["pending_op"][0] + op_index(op, awaiting_option=awaiting)] = 1

        flags_start = OBS_LAYOUT["pending_flags"][0]
        if awaiting:
            option_ids = pending_ctx.get("option_ids") or []
            option_id = pending_ctx.get("current_option_id")
            idx = option_ids.index(option_id) if option_id in option_ids else 0
            if idx >= PENDING_OPTION_SLOTS:
                raise UnmappedMoveError(
                    pending_ctx,
                    f"option position {idx} exceeds the {PENDING_OPTION_SLOTS}-slot block",
                )
            obs[flags_start + idx] = 1
        obs[flags_start + PENDING_FLAG_AWAITING_OPTION] = 1 if awaiting else 0
        obs[flags_start + PENDING_FLAG_OPTIONAL] = 1 if pending_ctx.get("optional") else 0
        obs[flags_start + PENDING_FLAG_ALLOW_REPEAT] = 1 if pending_ctx.get("allow_repeat") else 0
        obs[flags_start + PENDING_FLAG_REMAINING_REPEATS] = max(
            0, min(32767, int(pending_ctx.get("remaining_repeats") or 0))
        )
        if op == "custom_effect":
            effect_start = OBS_LAYOUT["pending_effect_kind"][0]
            obs[effect_start + effect_kind_index(pending_ctx.get("effect_kind"))] = 1

    # ── scalars ────────────────────────────────────────────────────────────
    core = [pub.get("round_number", 0), 0, 0, 0, 0,
            pub.get("resource_power", 0), pub.get("resource_influence", 0)]
    phase = pub.get("phase", "")
    if phase in PHASES:
        core[1 + PHASES.index(phase)] = 1
    put("scalars_core", 0, core)

    current_id = pub.get("current_player_id")
    present = [1 if i < n else 0 for i in range(MAX_SEATS)]
    # Both seat blocks are perspective-relative: slot 0 is the acting player,
    # then the other seats in turn order (the same ``order`` the board block
    # and the value target rotate through). The encoder is called from the
    # acting player's seat for every training sample, so ``is_current`` is the
    # constant ``[1, 0, 0, 0]``; the block is kept (and pinned by a test) rather
    # than shrunk, so OBS_LAYOUT does not churn.
    is_current = [
        1 if i < n and order[i] == current_id else 0 for i in range(MAX_SEATS)
    ]
    put("seat_present", 0, present)
    put("seat_is_current", 0, is_current)

    seat_features = []
    barracks_present = []
    for i in range(MAX_SEATS):
        if i >= n:
            seat_features.extend([0] * 8)
            continue
        summary = summaries.get(order[i], {})
        barracks = int(summary.get("barracks", 0))
        barracks_present.append(barracks)
        seat_features.extend([
            summary.get("score", 0),
            summary.get("vp_tokens", 0),
            barracks,
            summary.get("spies_available", 0),
            summary.get("hand_size", 0),
            summary.get("deck_size", 0),
            summary.get("discard_size", 0),
            summary.get("trophy_hall_size", 0),
        ])
    put("seat_features", 0, seat_features)

    min_barracks = min(barracks_present) if barracks_present else 0
    put("global_scalars", 0, [pub.get("market_deck_size", 0), min_barracks])

    return obs
