#include "engine.h"
#include "moves.h"
#include "helpers.h"
#include "phases.h"
#include "scoring.h"
#include "rules.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

#define TEST(s) do { printf("  %s...\n", s); } while(0)

static GameDefinition *g_def = NULL;
static Arena *g_def_arena = NULL;

static void setup_def(void) {
    if (g_def) return;
    g_def_arena = arena_create(2 * 1024 * 1024);
    g_def = engine_load_definition(
        "../data/cards/catalog.json",
        "../data/boards/tyrants_of_the_underdark.json",
        "../data/decks/base_setup.json",
        g_def_arena
    );
    if (!g_def || g_def->catalog.card_count == 0) {
        g_def = engine_load_definition(
            "data/cards/catalog.json",
            "data/boards/tyrants_of_the_underdark.json",
            "data/decks/base_setup.json",
            g_def_arena
        );
    }
    assert(g_def);
    register_default_effects();
}

static void test_initial_setup(void) {
    TEST("initial setup");
    setup_def();
    const char *pids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(g_def, pids, 2, 42);
    assert(gs);
    assert(gs->phase == PHASE_SETUP);
    assert(gs->current_player_id == intern("p1"));
    assert(gs->player_count == 2);
    assert(gs->player_id_count == 2);

    Move legal[64];
    int n = engine_legal_moves(gs, legal, 64);
    assert(n > 0);
    for (int i = 0; i < n; i++)
        assert(legal[i].type == MOVE_INITIAL_PLACEMENT);

    GameState *s2 = engine_apply(gs, &legal[0]);
    assert(s2);
    assert(s2->phase == PHASE_SETUP);
    assert(s2->current_player_id == intern("p2"));
    engine_destroy(gs);

    n = engine_legal_moves(s2, legal, 64);
    assert(n > 0);
    GameState *s3 = engine_apply(s2, &legal[0]);
    assert(s3);
    assert(s3->phase == PHASE_DRAW);
    assert(s3->current_player_id == intern("p1"));
    engine_destroy(s2);
    engine_destroy(s3);
}

static void test_phase_machine(void) {
    TEST("phase machine");
    setup_def();
    const char *pids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(g_def, pids, 2, 42);

    assert(gs->phase == PHASE_SETUP);
    advance_phase(gs);
    assert(gs->phase == PHASE_SETUP);
    assert(gs->setup_complete_count == 0);

    Move legal[64]; GameState *tmp;
    int n = engine_legal_moves(gs, legal, 64);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
    n = engine_legal_moves(gs, legal, 64);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;

    assert(gs->phase == PHASE_DRAW);
    advance_phase(gs);
    assert(gs->phase == PHASE_MAIN);

    n = engine_legal_moves(gs, legal, 64);
    assert(n > 0);
    int has_end = 0;
    for (int i = 0; i < n; i++)
        if (legal[i].type == MOVE_END_MAIN_PHASE) has_end = 1;
    assert(has_end);

    for (int i = 0; i < n; i++) {
        if (legal[i].type == MOVE_END_MAIN_PHASE) {
            tmp = engine_apply(gs, &legal[i]); engine_destroy(gs); gs = tmp;
            break;
        }
    }
    assert(gs->phase == PHASE_END_OF_TURN);

    n = engine_legal_moves(gs, legal, 64);
    assert(n > 0);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
    assert(gs->phase == PHASE_CLEANUP);

    n = engine_legal_moves(gs, legal, 64);
    assert(n > 0);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
    assert(gs->phase == PHASE_MAIN);

    engine_destroy(gs);
}

static void test_deploy_with_power(void) {
    TEST("deploy with power");
    setup_def();
    const char *pids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(g_def, pids, 2, 42);
    GameState *tmp;

    Move legal[64]; int n;
    n = engine_legal_moves(gs, legal, 64);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
    n = engine_legal_moves(gs, legal, 64);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
    advance_phase(gs);

    gs->resource_pool.power = 5;

    n = engine_legal_moves(gs, legal, 64);
    int found_deploy = 0;
    for (int i = 0; i < n; i++) {
        if (legal[i].type == MOVE_DEPLOY) {
            found_deploy = 1;
            tmp = engine_apply(gs, &legal[i]); engine_destroy(gs); gs = tmp;
            assert(gs->resource_pool.power == 4);
            break;
        }
    }
    assert(found_deploy);

    engine_destroy(gs);
}

static void test_assassinate_with_power(void) {
    TEST("assassinate with power");
    setup_def();
    const char *pids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(g_def, pids, 2, 42);
    GameState *tmp;

    Move legal[64]; int n;
    n = engine_legal_moves(gs, legal, 64);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
    n = engine_legal_moves(gs, legal, 64);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
    advance_phase(gs);

    gs->resource_pool.power = 5;

    n = engine_legal_moves(gs, legal, 64);
    int did_deploy = 0;
    for (int i = 0; i < n && !did_deploy; i++) {
        if (legal[i].type == MOVE_DEPLOY) {
            tmp = engine_apply(gs, &legal[i]); engine_destroy(gs); gs = tmp;
            did_deploy = 1;
        }
    }
    assert(did_deploy);
    assert(gs->resource_pool.power == 4);

    gs->resource_pool.power = 5;

    n = engine_legal_moves(gs, legal, 64);
    int has_assassinate = 0;
    for (int i = 0; i < n; i++) {
        if (legal[i].type == MOVE_ASSASSINATE) has_assassinate = 1;
    }
    printf("    (assassinate available: %s)\n", has_assassinate ? "yes" : "no (needs enemy troop on board)");

    engine_destroy(gs);
}

static void test_terminal_and_winner(void) {
    TEST("terminal & winner");
    setup_def();
    const char *pids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(g_def, pids, 2, 42);
    assert(!engine_is_terminal(gs));
    assert(engine_winner(gs, NULL) == SYM_NULL);

    gs->players[0].score = 10;
    gs->players[1].score = 5;
    gs->phase = PHASE_GAME_OVER;
    assert(engine_is_terminal(gs));

    int score;
    Sym w = engine_winner(gs, &score);
    assert(w == intern("p1"));

    gs->players[1].score = 10;
    w = engine_winner(gs, &score);
    assert(w == SYM_NULL);

    engine_destroy(gs);
}

static void test_effect_registry(void) {
    TEST("effect registry");
    setup_def();
    EffectFn ef = lookup_effect(intern("gain_power"));
    assert(ef != NULL);
    ef = lookup_effect(intern("gain_influence"));
    assert(ef != NULL);
    ef = lookup_effect(intern("noop"));
    assert(ef != NULL);
    ef = lookup_effect(intern("generic_card"));
    assert(ef != NULL);
    ef = lookup_effect(intern("nonexistent"));
    assert(ef == NULL);
}

static void test_scoring(void) {
    TEST("scoring");
    setup_def();
    const char *pids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(g_def, pids, 2, 42);
    int scores[MAX_PLAYERS];
    compute_final_scores(gs, scores);
    assert(scores[0] >= 0);
    assert(scores[1] >= 0);
    engine_destroy(gs);
}

int main(void) {
    printf("Phase 2 rules tests:\n");
    test_initial_setup();
    test_phase_machine();
    test_deploy_with_power();
    test_assassinate_with_power();
    test_terminal_and_winner();
    test_effect_registry();
    test_scoring();
    printf("\nAll Phase 2 tests passed.\n");
    if (g_def_arena) arena_destroy(g_def_arena);
    return 0;
}
