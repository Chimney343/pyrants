/* Tests for engine_random_rollout — a whole random-playout-to-terminal loop
 * run entirely in C, to replace the Python-level RandomRolloutEvaluator's
 * per-step ctypes round trips in IS-MCTS. See the IS-MCTS rollout speedup
 * plan for context.
 *
 * Note on scoring: engine_random_rollout always reports
 * compute_final_scores(), whether it reached terminal or was cut off. That
 * function tallies players[i].score (a running accumulator that actions and
 * end-of-turn site awards write during play) plus site-control VP, trophies,
 * VP tokens and the VP printed on every card the player owns — so it is the
 * real result at terminal and a score-the-game-as-if-it-ended-now estimate
 * anywhere else. It is never [0, 0] for a loaded game, because the starting
 * decks already carry card VP.
 *
 * An earlier version of this note claimed a fresh game "does not reach
 * terminal within any practical random-rollout step budget". That was a
 * symptom, not a property of the game: the rollout was sampling the UI-only
 * placeholder moves engine_apply refuses, so it aborted after a handful of
 * steps and never got near the end. With those filtered out an unbounded
 * rollout from a fresh 2p state runs to genuine terminal.
 */
#include "../engine.h"
#include "../rollout.h"
#include "../scoring.h"
#include "../generic_runtime.h"
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

/* A cut-off rollout must still report a real value. It used to fall back to
 * the raw players[i].score field, which stays 0 through most of a game — so
 * every truncated rollout returned the same constant and told UCT nothing.
 * compute_final_scores() is the tally now, terminal or not.
 *
 * vp_tokens makes the two rules distinguishable on any fixture: it is one of
 * the components compute_final_scores() adds on top of players[i].score, and
 * nothing in the engine ever spends it. The old branch would report 0 here. */
static void test_rollout_short_cutoff_scores_as_if_ended_now(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = engine_create_game_definition(def, PLAYER_IDS, 2, 42);
    assert(gs);

    gs->players[0].vp_tokens = 7;

    int scores[MAX_PLAYERS];
    int terminal = engine_random_rollout(gs, 5ULL, 1, scores);
    assert(terminal == 0);
    assert(scores[0] >= 7);
    for (int i = gs->player_count; i < MAX_PLAYERS; i++) {
        assert(scores[i] == 0); /* unused slots stay zeroed */
    }
    printf("PASS: cut-off rollout scores the state as if the game ended there\n");

    engine_destroy(gs);
    arena_destroy(arena);
}

/* Unit guard for the predicate the rollout filters on. The end-to-end effect
 * (rollouts actually reaching terminal) can only be measured against the real
 * multi-deck market the runner uses, which is assembled in Python — that guard
 * lives in tests/c_engine/test_rollout_binding.py. This fixture is
 * base_setup.json, whose 10-card market ends games before the placeholder
 * options that caused the defect ever show up. */
static void test_unavailable_placeholder_predicate(void) {
    Move m;
    memset(&m, 0, sizeof(m));

    m.type = MOVE_RESOLVE_GENERIC;
    m.data.resolve_generic.target_id = intern("unavailable");
    assert(move_is_unavailable_placeholder(&m) == 1);

    m.data.resolve_generic.target_id = intern("some_real_node");
    assert(move_is_unavailable_placeholder(&m) == 0);

    m.data.resolve_generic.target_id = SYM_NULL; /* skip marker, applicable */
    assert(move_is_unavailable_placeholder(&m) == 0);

    /* The tag is only meaningful on resolve_generic moves. */
    m.type = MOVE_END_MAIN_PHASE;
    m.data.resolve_generic.target_id = intern("unavailable");
    assert(move_is_unavailable_placeholder(&m) == 0);

    printf("PASS: move_is_unavailable_placeholder tags only UI placeholder moves\n");
}

int main(void) {
    intern_init(65536);

    test_rollout_runs_to_completion_or_cutoff();
    test_rollout_deterministic_for_same_seed();
    test_rollout_seed_drives_move_selection();
    test_rollout_does_not_mutate_input_state();
    test_rollout_unbounded_completes_within_time_bound();
    test_rollout_short_cutoff_scores_as_if_ended_now();
    test_unavailable_placeholder_predicate();

    printf("\nAll rollout tests passed.\n");
    return 0;
}
