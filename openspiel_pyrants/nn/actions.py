"""Global, stable action encoding (v3) for the NN policy head.

Every legal move maps to exactly one slot in a fixed 2,048-wide space. Moves
that are duplicate-equivalent (two copies of the same card in hand; two troop
slots owned by the same player at one node) collapse to one slot; slot-index
targets collapse to the owner key.

v1 keyed several ``resolve_generic`` shapes on a positional fallback, so
rulebook-distinct moves could share a slot (F-026). v2:

* routes ``assassinate_troop`` / ``supplant_troop`` and ``return_unit``'s
  ``troop:N`` into the existing ``assassinate`` block, and ``return_unit``'s
  ``spy:<owner>`` into the existing ``return_spy`` block;
* rebuilds ``resolve_generic`` (240 slots) on the rulebook's nouns: modal
  option, decline, node, card, player, index;
* raises :class:`UnmappedMoveError` for anything off the explicit allow-lists.

v3 keys every structured trophy *placement* on the deployed troop's colour:
``<source_player>:<trophy_idx>:<node>:<slot>`` routes to
``assassinate[node × owner_slot(colour)]``. v2 dropped the trophy index and
sent ``deploy_from_trophy_hall`` / ``steal_from_selected_trophy`` to
``node[destination]``, merging differently-coloured deploys (F-031).

The C engine's per-state action ids are positional and meaningless across
states (F-001); encoders key on payloads, which is why the signature takes a
structured payload plus an :class:`ActionContext`.

No pyspiel import: stdlib + numpy only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np

from .index import (
    CARD_ID_TO_INDEX,
    NODE_ID_TO_INDEX,
    node_index,
)

ACTION_SPACE_VERSION = 3
NUM_GLOBAL_ACTIONS = 2048

# (name, size) — order defines the contiguous block offsets below. The first
# eight blocks are unchanged from v1 (1,276 slots); ``resolve_generic`` is the
# v2/v3 rebuild (240). Total used: 1,516.
_BLOCKS: list[tuple[str, int]] = [
    ("play_card", 126),
    ("recruit", 126),
    ("promote", 127),
    ("initial_placement", 81),
    ("deploy", 82),
    ("assassinate", 405),
    ("return_spy", 324),
    ("fixed", 5),
    ("resolve_generic", 240),
]

ACTION_LAYOUT: dict[str, tuple[int, int]] = {}
_offset = 0
for _name, _size in _BLOCKS:
    ACTION_LAYOUT[_name] = (_offset, _offset + _size)
    _offset += _size
ACTION_SPACE_USED = _offset
assert ACTION_SPACE_USED <= NUM_GLOBAL_ACTIONS

# resolve_generic v2 sub-blocks, in order. ``index`` holds the allow-listed
# (op, shape) pairs that need a positional key rather than a rules noun; today
# that is ``select_trophy_hall``, keyed as source seat (4) × trophy colour (5).
_RG_SIZES = (("option", 8), ("decline", 1), ("node", 81),
             ("card", 126), ("player", 4), ("index", 20))
RESOLVE_GENERIC_LAYOUT: dict[str, tuple[int, int]] = {}
_rg_cursor = ACTION_LAYOUT["resolve_generic"][0]
for _name, _size in _RG_SIZES:
    RESOLVE_GENERIC_LAYOUT[_name] = (_rg_cursor, _rg_cursor + _size)
    _rg_cursor += _size
assert _rg_cursor == ACTION_LAYOUT["resolve_generic"][1]

_FIXED_TYPES: dict[str, int] = {
    "end_main_phase": 0,
    "resolve_end_of_turn": 1,
    "resolve_cleanup": 2,
    "activate_card_ability": 3,
    "activate_ability": 3,
    "decline_card_ability": 4,
    "decline_ability": 4,
}

_OWNER_WHITE = 4

# resolve_generic routing offsets, derived from the layout so the two can never
# drift (the sizes live in ``_RG_SIZES`` only).
_RG_BASE = ACTION_LAYOUT["resolve_generic"][0]


def _rg_offset(name: str) -> int:
    start, end = RESOLVE_GENERIC_LAYOUT[name]
    return start - _RG_BASE


def _rg_size(name: str) -> int:
    start, end = RESOLVE_GENERIC_LAYOUT[name]
    return end - start


_OPTION_SLOTS = _rg_size("option")
_DECLINE_OFF = _rg_offset("decline")
_NODE_OFF = _rg_offset("node")
_CARD_OFF = _rg_offset("card")
_PLAYER_OFF = _rg_offset("player")
_INDEX_OFF = _rg_offset("index")
_INDEX_SLOTS = _rg_size("index")
_TROPHY_COLOUR_SLOTS = 5  # 4 seats + white

_NODE_SUB_OPS = frozenset({"deploy_troops", "return_spy", "place_spy", "move_troop"})
_CARD_SUB_OPS = frozenset({"recruit_card", "devour", "devour_cost", "play_card"})
_TROOP_OPS = frozenset({"assassinate_troop", "supplant_troop"})

# Only these (op, shape) pairs may consume an ``index`` sub-block slot.
_ALLOW_INDEX_SHAPES = frozenset({("custom_effect", "select_trophy_hall")})


class UnmappedMoveError(ValueError):
    """A legal move has no slot in the global action space."""

    def __init__(self, payload: dict, reason: str = "") -> None:
        self.payload = payload
        detail = f": {reason}" if reason else ""
        super().__init__(f"unmapped move {payload!r}{detail}")


@dataclass(frozen=True)
class ActionContext:
    """Everything ``move_to_global_action`` needs beyond the move payload."""

    acting_player_id: str
    seat_order: tuple[str, ...]
    troop_slots_by_node: dict[str, tuple[str | None, ...]] = field(default_factory=dict)
    pending_op: str | None = None
    option_ids: tuple[str, ...] = ()
    effect_kind: str | None = None
    my_hand: tuple[str, ...] = ()
    my_discard: tuple[str, ...] = ()
    trophy_halls: dict[str, tuple[str, ...]] = field(default_factory=dict)


def seat_order(adapter, pid: str) -> list[str]:
    """Turn order starting from the acting player: ``pid`` first.

    Canonical rotation shared by the action encoder and the observation
    encoder so the two cannot drift.
    """
    player_ids = list(adapter.player_ids)
    n = len(player_ids)
    start = player_ids.index(pid)
    return [player_ids[(start + k) % n] for k in range(n)]


def owner_slot(owner_id: str | None, seat_order_ids, *, allow_white: bool) -> int | None:
    """Return the seat-relative owner slot, or ``None`` when not resolvable.

    ``None`` means the target owner is absent or unknown; callers decide whether
    to fold it (an absent target) or fail loudly (a present-but-unknown owner).
    ``"white"`` is slot 4 only when *allow_white*.
    """
    if owner_id is None:
        return None
    if owner_id == "white":
        return _OWNER_WHITE if allow_white else None
    try:
        index = seat_order_ids.index(owner_id)
    except ValueError:
        return None
    return index if 0 <= index < 4 else None


def _resolve_owner_slot(owner_id: str | None, ctx: ActionContext, *, allow_white: bool) -> int:
    """Action-side owner slot: absent targets fold to the acting seat, but a
    present-but-unknown owner is an unmapped move (fail loudly)."""
    slot = owner_slot(owner_id, ctx.seat_order, allow_white=allow_white)
    if slot is not None:
        return slot
    if owner_id is None:
        return 0
    raise UnmappedMoveError({"owner": owner_id}, "owner not in seat order")


def _block_offset(name: str) -> int:
    return ACTION_LAYOUT[name][0]


def _card_slot(card_id) -> int:
    """Strict card index: unknown ids are a mapping failure, not a bucket."""
    if not isinstance(card_id, str) or card_id not in CARD_ID_TO_INDEX:
        raise UnmappedMoveError({"card_id": card_id}, "unknown card id")
    return CARD_ID_TO_INDEX[card_id]


def action_context(adapter, pid: str, pending=None) -> ActionContext:
    """Build an :class:`ActionContext` from a live ``CEngineAdapter``.

    *pending* is the full ``read_pending_generic_context_full`` dict (a bare op
    string is accepted for callers that only have one).
    """
    if isinstance(pending, str):
        pending = {"op": pending}
    pending = pending or {}
    order = tuple(seat_order(adapter, pid))
    troop_slots_by_node = {
        node["node_id"]: tuple(node.get("troop_slots", ()))
        for node in adapter._ensure_board_nodes()
    }
    view = json.loads(adapter.private_view_json(pid))
    summaries = view.get("public", {}).get("public_player_summaries", {})
    trophy_halls = {
        player_id: tuple(summary.get("trophy_hall") or ())
        for player_id, summary in summaries.items()
    }
    return ActionContext(
        acting_player_id=pid,
        seat_order=order,
        troop_slots_by_node=troop_slots_by_node,
        pending_op=pending.get("op"),
        option_ids=tuple(pending.get("option_ids") or ()),
        effect_kind=pending.get("effect_kind"),
        my_hand=tuple(view.get("hand") or ()),
        my_discard=tuple(view.get("discard") or ()),
        trophy_halls=trophy_halls,
    )


def _node(payload: dict, *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value:
            return value
    return None


def _require_node(node_id, payload: dict) -> int:
    try:
        return node_index(node_id)
    except KeyError as exc:
        raise UnmappedMoveError(payload, f"unknown node {node_id!r}") from exc


def _troop_owner(node_id, slot_index, ctx: ActionContext, payload: dict) -> str:
    if not isinstance(slot_index, str) or not slot_index.isdigit():
        raise UnmappedMoveError(payload, "troop target is not a slot index")
    idx = int(slot_index)
    slots = ctx.troop_slots_by_node.get(node_id or "", ())
    owner = slots[idx] if 0 <= idx < len(slots) else None
    if owner is None:
        raise UnmappedMoveError(payload, "troop target slot is empty")
    return owner


def _option_offset(action_id, ctx: ActionContext, payload: dict) -> int:
    if isinstance(action_id, str) and action_id in ctx.option_ids:
        idx = ctx.option_ids.index(action_id)
        if idx >= _OPTION_SLOTS:
            raise UnmappedMoveError(
                payload, f"option position {idx} exceeds the {_OPTION_SLOTS}-slot block"
            )
        return idx
    raise UnmappedMoveError(payload, f"option {action_id!r} not in option_ids")


def _return_unit_offset(action_id, target_id, ctx: ActionContext, payload: dict) -> int:
    if not isinstance(target_id, str):
        raise UnmappedMoveError(payload, "return_unit without a unit target")
    if target_id.startswith("troop:"):
        node_i = _require_node(action_id, payload)
        owner = _troop_owner(action_id, target_id.split(":", 1)[1], ctx, payload)
        slot = _resolve_owner_slot(owner, ctx, allow_white=True)
        return _block_offset("assassinate") + node_i * (_OWNER_WHITE + 1) + slot
    if target_id.startswith("spy:"):
        node_i = _require_node(action_id, payload)
        owner = target_id.split(":", 1)[1]
        slot = _resolve_owner_slot(owner, ctx, allow_white=False)
        return _block_offset("return_spy") + node_i * 4 + (slot if slot < 4 else 0)
    raise UnmappedMoveError(payload, f"unknown return_unit target {target_id!r}")


def _node_sub_target(op: str, action_id, target_id, payload: dict) -> str:
    if op == "move_troop":
        if not isinstance(target_id, str) or target_id.count(":") < 2:
            raise UnmappedMoveError(payload, "move_troop target is malformed")
        return target_id.split(":", 2)[1]
    if not action_id:
        raise UnmappedMoveError(payload, f"{op} has no target node")
    return action_id


def _promote_card_slot(action_id, target_id, ctx: ActionContext, payload: dict) -> int:
    if target_id in ("played", "hand", "discard"):
        if target_id == "played":
            return _card_slot(action_id)
        source = ctx.my_hand if target_id == "hand" else ctx.my_discard
        if not isinstance(action_id, str) or not action_id.isdigit():
            raise UnmappedMoveError(payload, "promote_card index form without a numeric index")
        idx = int(action_id)
        if not 0 <= idx < len(source):
            raise UnmappedMoveError(payload, f"promote_card {target_id} index {idx} out of range")
        return _card_slot(source[idx])
    return _card_slot(action_id)


def _custom_effect_shape(action_id, target_id, ctx: ActionContext) -> str:
    if not isinstance(action_id, str):
        return "unknown"
    if action_id in CARD_ID_TO_INDEX:
        return "card"
    if action_id in ctx.seat_order:
        return "player"
    if action_id in NODE_ID_TO_INDEX:
        if isinstance(target_id, str) and ":" in target_id:
            return "structured"
        return "node"
    return "unknown"


def _select_trophy_hall_offset(action_id, target_id, ctx: ActionContext, payload: dict) -> int:
    """``select_trophy_hall``: (source seat × trophy colour) into the index block.

    The hall index is a physical slot; the rules choice is the trophy's
    owner/colour, so indices of the same colour merge while distinct colours
    stay separate.
    """
    source_slot = owner_slot(action_id, ctx.seat_order, allow_white=False)
    if source_slot is None:
        raise UnmappedMoveError(
            payload, f"select_trophy_hall source {action_id!r} is not a player"
        )
    if not isinstance(target_id, str) or not target_id.isdigit():
        raise UnmappedMoveError(payload, "select_trophy_hall without a trophy index")
    hall = ctx.trophy_halls.get(action_id, ())
    idx = int(target_id)
    if not 0 <= idx < len(hall):
        raise UnmappedMoveError(
            payload, f"trophy index {idx} out of range for {action_id!r}"
        )
    colour_slot = owner_slot(hall[idx], ctx.seat_order, allow_white=True)
    if colour_slot is None:
        raise UnmappedMoveError(payload, f"unknown trophy colour {hall[idx]!r}")
    key = source_slot * _TROPHY_COLOUR_SLOTS + colour_slot
    if key >= _INDEX_SLOTS:
        raise UnmappedMoveError(payload, f"select_trophy_hall key {key} exceeds the index block")
    return _block_offset("resolve_generic") + _INDEX_OFF + key


def _structured_placement_offset(
    action_id, target_id, ctx: ActionContext, payload: dict
) -> int:
    """A troop of colour C placed at node N: ``assassinate[N × owner_slot(C)]``.

    The target is ``<source_player>:<trophy_idx>:<node>:<slot>``. The rulebook
    noun is the *colour* of the trophy deployed (colour decides control), not
    the physical hall slot, so two trophy indices that deploy the same colour
    to one node merge while distinct colours stay apart (F-031). A trophy
    colour that is neither a current seat nor ``white`` is illegal for this
    game (e.g. ``p3`` in a 2-player game) and raises.
    """
    parts = target_id.split(":") if isinstance(target_id, str) else []
    if len(parts) != 4:
        raise UnmappedMoveError(
            payload, f"custom_effect structured target {target_id!r} is malformed"
        )
    source_player, trophy_idx, _node, _slot = parts
    if not trophy_idx.isdigit():
        raise UnmappedMoveError(
            payload,
            f"custom_effect structured trophy index {trophy_idx!r} is not numeric",
        )
    hall = ctx.trophy_halls.get(source_player)
    if hall is None:
        raise UnmappedMoveError(
            payload,
            f"custom_effect structured source {source_player!r} is not a trophy hall",
        )
    idx = int(trophy_idx)
    if not 0 <= idx < len(hall):
        raise UnmappedMoveError(
            payload,
            f"custom_effect structured trophy index {idx} out of range for "
            f"{source_player!r}",
        )
    colour_slot = owner_slot(hall[idx], ctx.seat_order, allow_white=True)
    if colour_slot is None:
        raise UnmappedMoveError(
            payload,
            f"custom_effect structured trophy colour {hall[idx]!r} is not a seat "
            "or white",
        )
    node_i = _require_node(action_id, payload)
    return _block_offset("assassinate") + node_i * (_OWNER_WHITE + 1) + colour_slot


def _custom_effect_offset(action_id, target_id, ctx, payload) -> int:
    shape = _custom_effect_shape(action_id, target_id, ctx)
    base = _block_offset("resolve_generic")
    if shape == "card":
        return base + _CARD_OFF + _card_slot(action_id)
    if shape == "player":
        if ctx.effect_kind == "select_trophy_hall":
            if ("custom_effect", "select_trophy_hall") not in _ALLOW_INDEX_SHAPES:
                raise UnmappedMoveError(
                    payload, "select_trophy_hall is not on the index allow-list"
                )
            return _select_trophy_hall_offset(action_id, target_id, ctx, payload)
        slot = _resolve_owner_slot(action_id, ctx, allow_white=False)
        return base + _PLAYER_OFF + min(3, slot)
    if shape == "node":
        return base + _NODE_OFF + _require_node(action_id, payload)
    if shape == "structured":
        return _structured_placement_offset(action_id, target_id, ctx, payload)
    raise UnmappedMoveError(
        payload, f"custom_effect target shape {shape!r} is not on the index allow-list"
    )


def _resolve_generic_offset(payload: dict, ctx: ActionContext) -> int:
    base = _block_offset("resolve_generic")
    op = ctx.pending_op
    action_id = payload.get("action_id")
    target_id = payload.get("target_id")

    if action_id is None and target_id is None:
        return base + _DECLINE_OFF

    if op is None:
        return base + _option_offset(action_id, ctx, payload)

    if op in _TROOP_OPS:
        node_i = _require_node(action_id, payload)
        owner = _troop_owner(action_id, target_id, ctx, payload)
        slot = _resolve_owner_slot(owner, ctx, allow_white=True)
        return _block_offset("assassinate") + node_i * (_OWNER_WHITE + 1) + slot

    if op == "return_unit":
        return _return_unit_offset(action_id, target_id, ctx, payload)

    if op in _NODE_SUB_OPS:
        node = _node_sub_target(op, action_id, target_id, payload)
        return base + _NODE_OFF + _require_node(node, payload)

    if op in _CARD_SUB_OPS:
        return base + _CARD_OFF + _card_slot(action_id)

    if op == "force_discard":
        if isinstance(action_id, str) and action_id in ctx.seat_order:
            slot = _resolve_owner_slot(action_id, ctx, allow_white=False)
            return base + _PLAYER_OFF + min(3, slot)
        if isinstance(action_id, str) and action_id in CARD_ID_TO_INDEX:
            return base + _CARD_OFF + _card_slot(action_id)
        raise UnmappedMoveError(
            payload, f"force_discard target {action_id!r} is neither a player nor a card"
        )

    if op == "promote_card":
        return base + _CARD_OFF + _promote_card_slot(action_id, target_id, ctx, payload)

    if op == "custom_effect":
        return _custom_effect_offset(action_id, target_id, ctx, payload)

    raise UnmappedMoveError(payload, f"pending op {op!r} has no v2 slot")


def move_to_global_action(payload: dict, ctx: ActionContext) -> int:
    """Map one structured move payload to its global action id.

    Raises :class:`UnmappedMoveError` (carrying the payload) for an unknown
    move type, card, node or resolve-generic target kind.
    """
    move_type = payload.get("move_type")
    if move_type == "play_card":
        return _block_offset("play_card") + _card_slot(payload.get("card_id"))
    if move_type == "recruit":
        return _block_offset("recruit") + _card_slot(payload.get("card_id"))
    if move_type == "promote_card":
        return _block_offset("promote") + _card_slot(payload.get("card_id"))
    if move_type == "skip_promote":
        return _block_offset("promote") + 126
    if move_type == "initial_placement":
        return _block_offset("initial_placement") + _require_node(
            payload.get("target_node_id"), payload
        )
    if move_type == "deploy":
        target = payload.get("target_node_id")
        if not target:
            return _block_offset("deploy") + 81
        return _block_offset("deploy") + _require_node(target, payload)
    if move_type == "assassinate":
        node = payload.get("target_node_id")
        node_i = _require_node(node, payload)
        slots = ctx.troop_slots_by_node.get(node or "", ())
        slot_index = int(payload.get("target_slot_index") or 0)
        owner = slots[slot_index] if 0 <= slot_index < len(slots) else None
        if owner is None:
            raise UnmappedMoveError(payload, "assassinate target slot is empty")
        slot = _resolve_owner_slot(owner, ctx, allow_white=True)
        return _block_offset("assassinate") + node_i * (_OWNER_WHITE + 1) + slot
    if move_type == "return_spy":
        node = _node(payload, "node_id", "target_node_id")
        owner = payload.get("spy_owner_id")
        node_i = _require_node(node, payload)
        slot = _resolve_owner_slot(owner, ctx, allow_white=False)
        return _block_offset("return_spy") + node_i * 4 + (slot if slot < 4 else 0)
    if move_type in _FIXED_TYPES:
        return _block_offset("fixed") + _FIXED_TYPES[move_type]
    if move_type in ("resolve_generic", "resolve_generic_choice"):
        return _resolve_generic_offset(payload, ctx)
    raise UnmappedMoveError(payload, f"unknown move_type {move_type!r}")


def legal_mask(payloads, ctx: ActionContext) -> np.ndarray:
    """Boolean mask that is True exactly on the mapped global ids."""
    mask = np.zeros(NUM_GLOBAL_ACTIONS, dtype=bool)
    for payload in payloads:
        mask[move_to_global_action(payload, ctx)] = True
    return mask
