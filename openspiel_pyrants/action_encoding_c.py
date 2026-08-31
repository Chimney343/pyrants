"""Per-state action encoding for the C engine backend: Move <-> integer bijection.

The C engine produces legal moves in a deterministic order — no sort needed.
"""
from __future__ import annotations

from engine_c.bindings.ce_api import CMoveWrapper
from engine_c.bindings.c_adapter import CEngineAdapter

# generic_runtime.c emits a placeholder resolve_generic move tagged with this
# target_id for every non-viable card option, so the Tkinter viewer can render
# it greyed out.  engine_apply rejects those same moves outright, so they must
# never reach OpenSpiel: every action in legal_actions() has to be applicable.
_UNAVAILABLE_TARGET = "unavailable"


def _is_unavailable(move: CMoveWrapper) -> bool:
    return (
        move.move_type == "resolve_generic"
        and move.data.get("target_id") == _UNAVAILABLE_TARGET
    )


def compute_c_action_map(adapter: CEngineAdapter) -> list[tuple[int, CMoveWrapper]]:
    """Return ``(index, CMoveWrapper)`` pairs in the C engine's native order.

    UI-only placeholder moves are dropped (see ``_is_unavailable``).  Indices are
    recomputed per state and never persist across determinizations, so dropping
    them does not affect action-index stability.
    """
    moves = adapter.legal_moves()
    playable = [m for m in moves if not _is_unavailable(m)]
    # If every option was a placeholder, keep the raw list: an empty
    # legal_actions() at a non-terminal state deadlocks OpenSpiel silently,
    # whereas the raw list fails loudly in engine_apply with full context.
    return list(enumerate(playable if playable else moves))


NUM_DISTINCT_ACTIONS = 1024
