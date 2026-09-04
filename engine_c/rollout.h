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
 * Moves are sampled only from those the engine will actually accept: the
 * UI-only placeholders engine_legal_moves() reports for non-viable modal
 * options (see move_is_unavailable_placeholder) are filtered out first.
 * Without that filter a uniform pick landed on a placeholder — which
 * engine_apply refuses — at most mid-game positions, cutting the rollout
 * short after a handful of steps.
 *
 * Writes exactly MAX_PLAYERS ints to `scores_out`: always
 * `compute_final_scores()`, which is the real tally at a terminal state and
 * a score-the-game-as-if-it-ended-here estimate at a cut-off one (unused
 * player slots past `player_count` are zeroed). A cut-off rollout therefore
 * still yields a usable leaf value rather than a near-constant zero.
 *
 * Returns 1 if the rollout ended at a terminal state, 0 if it was cut off
 * by max_length (or the hard safety cap) — the score is meaningful either
 * way, so the flag is a diagnostic, not a validity bit.
 */
int engine_random_rollout(const GameState *state, uint64_t seed, int max_length, int *scores_out);

#ifdef __cplusplus
}
#endif

#endif
