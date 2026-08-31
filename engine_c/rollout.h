#ifndef ENGINE_ROLLOUT_H
#define ENGINE_ROLLOUT_H

#include <stdint.h>
#include "state.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Run a uniform-random rollout from `state` to a terminal state (or until
 * `max_length` steps have been applied, if positive) entirely in C — no
 * Python/ctypes round trip per step, unlike driving legal_moves()/apply()
 * one step at a time from Python. `state` is never mutated or freed; the
 * rollout advances its own private chain of clones.
 *
 * `max_length <= 0` means unbounded, but is still capped internally by a
 * runaway-loop safety limit — a defensive bound, not a tuning knob.
 *
 * Writes exactly MAX_PLAYERS ints to `scores_out`: `compute_final_scores()`
 * if the rollout reached a real terminal state, otherwise each player's
 * current `score` field (unused player slots past `player_count` are
 * zeroed). This mirrors PyrantsCState.returns()'s terminal/non-terminal
 * branching on the Python side, so results are comparable regardless of
 * which rollout implementation produced them.
 *
 * Returns 1 if the rollout ended at a terminal state, 0 if it was cut off
 * by max_length (or the hard safety cap).
 */
int engine_random_rollout(const GameState *state, uint64_t seed, int max_length, int *scores_out);

#ifdef __cplusplus
}
#endif

#endif
