"""Per-state action encoding for the C engine backend: Move <-> integer bijection.

The C engine produces legal moves in a deterministic order — no sort needed.
"""
from __future__ import annotations

from engine_c.bindings.ce_api import CMoveWrapper
from engine_c.bindings.c_adapter import CEngineAdapter


def compute_c_action_map(adapter: CEngineAdapter) -> list[tuple[int, CMoveWrapper]]:
    """Return ``(index, CMoveWrapper)`` pairs in the C engine's native order."""
    moves = adapter.legal_moves()
    return list(enumerate(moves))


NUM_DISTINCT_ACTIONS = 1024
