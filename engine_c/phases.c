#include "phases.h"
#include "rng.h"
#include <string.h>

Sym next_player_id(const GameState *state) {
    Sym current = state->current_player_id;
    for (int i = 0; i < state->player_id_count; i++) {
        if (state->player_ids[i] == current) {
            return state->player_ids[(i + 1) % state->player_id_count];
        }
    }
    return current;
}

int advance_phase(GameState *state) {
    if (state->phase == PHASE_SETUP) {
        if (state->setup_complete_count >= state->player_id_count) {
            state->phase = PHASE_DRAW;
            if (state->player_id_count > 0) state->current_player_id = state->player_ids[0];
        } else {
            state->current_player_id = next_player_id(state);
            return 0;
        }
    }

    if (state->phase == PHASE_DRAW) {
        RNG rng;
        for (int i = 0; i < state->player_id_count; i++) {
            PlayerState *ps = cow_player(state, state->player_ids[i]);
            if (ps) {
                draw_cards_state(ps, 5, &rng, state->shuffle_seed, &state->shuffle_counter);
            }
        }
        state->phase = PHASE_MAIN;
        memset(&state->resource_pool, 0, sizeof(ResourcePool));
        return 0;
    }

    if (state->phase == PHASE_MAIN) {
        state->phase = PHASE_END_OF_TURN;
        memset(&state->resource_pool, 0, sizeof(ResourcePool));
        return 0;
    }

    if (state->phase == PHASE_END_OF_TURN) {
        state->phase = PHASE_CLEANUP;
        memset(&state->resource_pool, 0, sizeof(ResourcePool));
        return 0;
    }

    if (state->phase == PHASE_CLEANUP) {
        Sym next = next_player_id(state);
        if (next == state->player_ids[0]) state->round_number++;
        state->phase = PHASE_MAIN;
        state->current_player_id = next;
        memset(&state->resource_pool, 0, sizeof(ResourcePool));
        return 0;
    }

    return -1;
}

void set_game_over(GameState *state) {
    state->phase = PHASE_GAME_OVER;
    memset(&state->resource_pool, 0, sizeof(ResourcePool));
}
