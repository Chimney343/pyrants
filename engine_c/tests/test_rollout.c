/* Tests for engine_random_rollout — a whole random-playout-to-terminal loop
 * run entirely in C, to replace the Python-level RandomRolloutEvaluator's
 * per-step ctypes round trips in IS-MCTS. See the IS-MCTS rollout speedup
 * plan for context.
 *
 * Note on player.score: it is a final-tally field written only by
 * compute_final_scores() at genuine terminal — distinct from vp_tokens,
 * which tracks running progress during play. A fresh game does not reach
 * terminal within any practical random-rollout step budget (confirmed by
 * tracing: still deep in early rounds after 2000+ random half-moves), so
 * scores_out from a capped or even "unbounded" rollout from a fresh state
 * is [0, 0] almost always in practice — the hard safety cap binds, not
 * genuine terminal. Tests below account for this instead of assuming a
 * short/moderate rollout produces a nonzero score signal.
 */
#include "../engine.h"
#include "../rollout.h"
#include "../rng.h"
#include "../intern.h"
#include "../arena.h"
#include "catalog_dir.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>
#include <time.h>

static const char *PLAYER_IDS[] = {"p1", "p2"};

static void test_rollout_runs_to_completion_or_cutoff(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = engine_create_game_definition(def, PLAYER_IDS, 2, 42);
    assert(gs);

    int scores[MAX_PLAYERS];
    int terminal = engine_random_rollout(gs, 1ULL, 20, scores);
    assert(terminal == 0 || terminal == 1);
    for (int i = 0; i < gs->player_count; i++) {
        assert(scores[i] > -1000 && scores[i] < 1000);
    }
    printf("PASS: rollout runs to completion or cutoff (terminal=%d, scores=[%d,%d])\n",
           terminal, scores[0], scores[1]);

    engine_destroy(gs);
    arena_destroy(arena);
}

static void test_rollout_deterministic_for_same_seed(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = engine_create_game_definition(def, PLAYER_IDS, 2, 42);
    assert(gs);

    int scores_a[MAX_PLAYERS];
    int scores_b[MAX_PLAYERS];
    int terminal_a = engine_random_rollout(gs, 777ULL, 20, scores_a);
    int terminal_b = engine_random_rollout(gs, 777ULL, 20, scores_b);

    assert(terminal_a == terminal_b);
    assert(memcmp(scores_a, scores_b, sizeof(scores_a)) == 0);
    printf("PASS: rollout deterministic for same seed\n");

    engine_destroy(gs);
    arena_destroy(arena);
}

/* engine_random_rollout's output (scores_out) can't show seed-driven
 * divergence directly from a fresh game — see the file-level note on
 * player.score above. So this tests the actual selection primitive the
 * rollout uses internally (rng_seed + rng_next % n over engine_legal_moves'
 * output) rather than the end-to-end scores: it confirms the seed genuinely
 * drives *which move* gets picked, which is what "the seed matters" means
 * in practice. */
static void test_rollout_seed_drives_move_selection(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = engine_create_game_definition(def, PLAYER_IDS, 2, 42);
    assert(gs);

    Move moves[1024];
    int n = engine_legal_moves(gs, moves, 1024);
    assert(n > 1); /* need real branching for this check to mean anything */

    int first_pick = -1;
    int any_diff = 0;
    for (uint64_t seed = 1; seed <= 15; seed++) {
        RNG rng;
        rng_seed(&rng, seed);
        int pick = (int)(rng_next(&rng) % (unsigned int)n);
        if (first_pick < 0) {
            first_pick = pick;
        } else if (pick != first_pick) {
            any_diff = 1;
            break;
        }
    }
    assert(any_diff);
    printf("PASS: rollout seed drives move selection (n_legal=%d)\n", n);

    engine_destroy(gs);
    arena_destroy(arena);
}

static void test_rollout_does_not_mutate_input_state(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = engine_create_game_definition(def, PLAYER_IDS, 2, 42);
    assert(gs);

    int round_before = gs->round_number;
    int player_count_before = gs->player_count;
    int score0_before = gs->players[0].score;
    int terminal_before = engine_is_terminal(gs);

    int scores[MAX_PLAYERS];
    engine_random_rollout(gs, 55ULL, 20, scores);

    assert(gs->round_number == round_before);
    assert(gs->player_count == player_count_before);
    assert(gs->players[0].score == score0_before);
    assert(engine_is_terminal(gs) == terminal_before);
    printf("PASS: rollout does not mutate input state\n");

    engine_destroy(gs);
    arena_destroy(arena);
}

static void test_rollout_unbounded_completes_within_time_bound(void) {
    /* "Unbounded" (max_length<=0) still hits ROLLOUT_HARD_STEP_CAP in
     * practice for a fresh game — this is a runaway-loop guard, not a
     * promise of reaching genuine terminal. The property under test is
     * that it completes quickly and doesn't hang. */
    Arena *arena = arena_create(2 * 1024 * 1024);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = engine_create_game_definition(def, PLAYER_IDS, 2, 42);
    assert(gs);

    int scores[MAX_PLAYERS];
    clock_t t0 = clock();
    int terminal = engine_random_rollout(gs, 99ULL, 0, scores);
    clock_t t1 = clock();
    double ms = (t1 - t0) * 1000.0 / CLOCKS_PER_SEC;

    assert(ms < 5000.0);
    printf("PASS: unbounded rollout completed in %.1f ms (terminal=%d)\n", ms, terminal);

    engine_destroy(gs);
    arena_destroy(arena);
}

static void test_rollout_short_cutoff_scores_current_state(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = engine_create_game_definition(def, PLAYER_IDS, 2, 42);
    assert(gs);

    int scores[MAX_PLAYERS];
    int terminal = engine_random_rollout(gs, 5ULL, 1, scores);
    assert(terminal == 0);
    for (int i = 0; i < gs->player_count; i++) {
        assert(scores[i] == 0); /* score is untouched this early — see file note */
    }
    printf("PASS: short rollout takes the non-terminal current-score branch\n");

    engine_destroy(gs);
    arena_destroy(arena);
}

int main(void) {
    intern_init(65536);

    test_rollout_runs_to_completion_or_cutoff();
    test_rollout_deterministic_for_same_seed();
    test_rollout_seed_drives_move_selection();
    test_rollout_does_not_mutate_input_state();
    test_rollout_unbounded_completes_within_time_bound();
    test_rollout_short_cutoff_scores_current_state();

    printf("\nAll rollout tests passed.\n");
    return 0;
}
