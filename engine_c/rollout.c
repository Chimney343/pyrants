#include "rollout.h"
#include "engine.h"
#include "generic_runtime.h"
#include "rng.h"
#include "scoring.h"

#define ROLLOUT_MOVE_BUFFER   1024

/* Runaway-loop guard for max_length <= 0, not a tuning knob — it should sit
 * clear of the longest rollout the game actually produces. Measured terminal
 * rate against max_length on the runner's real 74-card market setup, 60
 * rollouts per cell, from both a fresh state and a 40-ply position:
 *
 *     cap      500   1000   1500   2000   3000
 *     2p       35%   100%   100%   100%   100%
 *     3p        0%    92%   100%   100%   100%
 *     4p        0%    20%    87%    98%   100%
 *
 * 4 players is the supported maximum (run_ismcts caps --num-players at 4), so
 * 4000 clears the worst case with room to spare. The previous 2000 predates
 * the placeholder-move fix below: rollouts died after a handful of steps back
 * then, so nothing ever approached the cap and its value was never tested. */
#define ROLLOUT_HARD_STEP_CAP 4000

int engine_random_rollout(const GameState *state, uint64_t seed, int max_length, int *scores_out) {
    RNG rng;
    rng_seed(&rng, seed);

    int cap = (max_length > 0) ? max_length : ROLLOUT_HARD_STEP_CAP;

    Move moves[ROLLOUT_MOVE_BUFFER];
    const GameState *view = state; /* read-only view; caller still owns `state` */
    GameState *owned = NULL;       /* first state we own, once we take a step */
    int depth = 0;

    while (depth < cap) {
        if (engine_is_terminal(view)) break;

        int n = engine_legal_moves(view, moves, ROLLOUT_MOVE_BUFFER);
        if (n <= 0) break;

        /* engine_legal_moves() reports UI-only placeholders for non-viable
         * modal options alongside real moves; engine_apply refuses them.
         * Sampling uniformly over the raw list picked one most of the time at
         * a mid-game position, which aborted the rollout on the spot and left
         * it scoring a non-terminal state — so compact them out first and
         * sample only over what the engine will actually accept. */
        int playable = 0;
        for (int i = 0; i < n; i++) {
            if (move_is_unavailable_placeholder(&moves[i])) continue;
            if (playable != i) moves[playable] = moves[i];
            playable++;
        }
        if (playable <= 0) break; /* every option was a placeholder */

        int pick = (int)(rng_next(&rng) % (unsigned int)playable);
        GameState *next = engine_apply(view, &moves[pick]);
        if (!next) break;

        if (owned) engine_destroy(owned);
        owned = next;
        view = owned;
        depth++;
    }

    int terminal = engine_is_terminal(view);

    /* Score the same way whether or not the rollout got there: compute_final_scores
     * is the real tally at a terminal state and "the score if the game ended here"
     * anywhere else.  The raw players[i].score field this used to fall back to on a
     * cut-off rollout omits site-control VP, trophies, VP tokens and deck card VP —
     * it is 0 for most of a game, which handed UCT a constant instead of a value. */
    for (int i = 0; i < MAX_PLAYERS; i++) scores_out[i] = 0;
    compute_final_scores(view, scores_out);

    if (owned) engine_destroy(owned);
    return terminal;
}
