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


def _move_sort_key(move: Move) -> str:
    return move.model_dump_json(exclude={"player_id"})


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
    move_json = move.model_dump_json(exclude={"player_id"})
    for new_id, (_, m) in enumerate(indexed):
        if m.model_dump_json(exclude={"player_id"}) == move_json:
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
