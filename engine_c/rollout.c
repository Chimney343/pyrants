#include "rollout.h"
#include "engine.h"
#include "rng.h"
#include "scoring.h"

#define ROLLOUT_MOVE_BUFFER   1024
#define ROLLOUT_HARD_STEP_CAP 2000

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

        int pick = (int)(rng_next(&rng) % (unsigned int)n);
        GameState *next = engine_apply(view, &moves[pick]);
        if (!next) break;

        if (owned) engine_destroy(owned);
        owned = next;
        view = owned;
        depth++;
    }

    int terminal = engine_is_terminal(view);

    for (int i = 0; i < MAX_PLAYERS; i++) scores_out[i] = 0;
    if (terminal) {
        compute_final_scores(view, scores_out);
    } else {
        for (int i = 0; i < view->player_count; i++) {
            scores_out[i] = view->players[i].score;
        }
    }

    if (owned) engine_destroy(owned);
    return terminal;
}
