"""Per-state action encoding: Move <-> integer bijection for OpenSpiel.

The mapping is rebuilt every call from ``engine.rules.legal_moves(state)``.
Ids are assigned 0..N-1 (sorted deterministically) and are valid only for
the specific state.  ``num_distinct_actions`` (1024) is a fixed upper bound
computed once at game construction.

Encoding scheme (reserved id-spaces by move kind, documented for reference):

    0..4           PlayCardMove          (by hand order)
    5              EndMainPhaseMove
    6..?           AssassinateMove       (node × slot)
    ...            DeployMove
    ...            RecruitMove
    ...            ReturnSpyMove
    ...            ActivateCardAbilityMove
    ...            DeclineCardAbilityMove
    ...            PromoteCardMove
    ...            SkipPromoteMove
    ...            ResolveEndOfTurnMove
    ...            ResolveCleanupMove
    ...            ResolveGenericChoiceMove

Note: the actual id assignment is flat per-state, not segmented.  The segment
comment is only for the upper-bound computation.
"""

from __future__ import annotations

from engine.moves import Move
from engine.rules import legal_moves as get_legal_moves
from engine.state import GameState


def _flatten(obj: object) -> object:
    """Recursively convert a dict/list tree into hashable nested tuples."""
    if isinstance(obj, dict):
        return tuple((k, _flatten(v)) for k, v in sorted(obj.items()))
    if isinstance(obj, list):
        return tuple(_flatten(v) for v in obj)
    return obj


def _move_sort_key(move: Move) -> tuple:
    """Return a deterministic sort key for move ordering.

    Uses direct field access (no model_dump serialization) to build a
    sortable tuple.  The keys are lexicographically comparable: string,
    int, tuple fields in canonical order per move type.
    """
    mt = move.move_type
    if mt == "play_card":
        return (mt, move.card_id, move.hand_index)
    if mt == "end_main_phase":
        return (mt,)
    if mt == "resolve_end_of_turn":
        return (mt,)
    if mt == "resolve_cleanup":
        return (mt,)
    if mt == "assassinate":
        return (mt, move.target_node_id, move.target_slot_index)
    if mt == "deploy":
        return (mt, move.target_node_id, move.troop_count)
    if mt == "recruit":
        return (mt, move.market_slot)
    if mt == "return_spy":
        return (mt, move.node_id, move.spy_owner_id)
    if mt == "activate_card_ability":
        return (mt, move.card_id, move.ability_key, tuple(move.discard_hand_indices))
    if mt == "decline_card_ability":
        return (mt, move.card_id, move.ability_key)
    if mt == "promote_card":
        return (mt, move.card_id)
    if mt == "skip_promote":
        return (mt, move.card_id)
    if mt == "resolve_generic_choice":
        sel = _flatten(move.selection) if move.selection else ()
        return (mt, move.source_card_id, move.option_id or "", sel)
    if mt == "initial_placement":
        return (mt, move.target_node_id)
    return (mt,)


def enumerate_legal_actions(state: GameState) -> list[int]:
    """Return sorted action ids for all currently legal moves.

    Ids are 0..N-1 and correspond one-to-one with ``engine.rules.legal_moves(state)``,
    sorted deterministically by their JSON representation (excluding player_id).
    """
    moves = get_legal_moves(state)
    indexed = sorted(enumerate(moves), key=lambda item: _move_sort_key(item[1]))
    return list(range(len(indexed)))


def action_to_move(state: GameState, action_id: int) -> Move:
    """Decode an action id back to an engine Move.

    Raises ``IndexError`` if the id is out of range.
    """
    moves = get_legal_moves(state)
    indexed = sorted(enumerate(moves), key=lambda item: _move_sort_key(item[1]))
    return indexed[action_id][1]


def move_to_action_id(state: GameState, move: Move) -> int:
    """Encode an engine Move to its action id.

    Raises ``ValueError`` if the move is not currently legal.
    """
    moves = get_legal_moves(state)
    indexed = sorted(enumerate(moves), key=lambda item: _move_sort_key(item[1]))
    move_key = _move_sort_key(move)
    for new_id, (_, m) in enumerate(indexed):
        if _move_sort_key(m) == move_key:
            return new_id
    raise ValueError(f"Move is not currently legal: {move}")


def compute_action_map(state: GameState) -> list[tuple[int, Move]]:
    """Compute the full sorted (index, move) mapping for the current state.

    Returns a list of (original_index, Move) pairs sorted deterministically
    by ``_move_sort_key``.  Callers that need both ``enumerate_legal_actions``
    and ``action_to_move`` can reuse this result to avoid re-enumerating the
    legal moves list.
    """
    moves = get_legal_moves(state)
    return sorted(enumerate(moves), key=lambda item: _move_sort_key(item[1]))


NUM_DISTINCT_ACTIONS = 1024
"""Fixed upper bound on the number of distinct actions across all states.

Computed as:
    max hand size 5          →  5 PlayCardMove ids
    1 EndMainPhase           →  1
    max deploy targets = 81  → 81
    max assassinate = 81×6   → 486
    max return-spy = 81×2    → 162
    max recruit = 9          →  9
    1 Activate + 1 Decline   →  2
    1 Promote + 1 Skip       →  2
    1 ResolveEOT + 1 ResolveCleanup + 1 ResolveGenericChoice → 3
    chance outcomes (5)      →  5
    TOTAL                    → ~756  → round up to 1024 (power of 2)
"""
