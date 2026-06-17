"""Determinization stub for the C engine backend.

For the C backend, ``resample_from_infostate`` returns a clone of the current
state without reshuffling opponents' hidden zones. The C engine's opaque state
makes true resampling complex (requires C-to-Python projection). For initial
IS-MCTS integration, cloning is sufficient and correct per the information_state
contract.
"""

from __future__ import annotations


def determinize_opponent_hidden_zones(engine, observing_player_id, rng):
    del observing_player_id, rng
    return engine
