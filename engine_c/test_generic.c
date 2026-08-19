#include "engine.h"
#include "moves.h"
#include "helpers.h"
#include "phases.h"
#include "scoring.h"
#include "rules.h"
#include "generic_runtime.h"
#include "tests/catalog_dir.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

static GameDefinition *g_def = NULL;
static Arena *g_def_arena = NULL;

static void setup(void) {
    if (g_def) return;
    g_def_arena = arena_create(2 * 1024 * 1024);
    g_def = test_load_definition(g_def_arena);
    assert(g_def);
    register_default_effects();
}

static void test_player_hand_has_cards(void) {
    setup();
    const char *pids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(g_def, pids, 2, 42);

    Move legal[64]; GameState *tmp;

    int n = engine_legal_moves(gs, legal, 64);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
    n = engine_legal_moves(gs, legal, 64);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;

    advance_phase(gs);
    assert(gs->phase == PHASE_MAIN);

    int pi = -1;
    for (int i = 0; i < gs->player_count; i++)
        if (gs->players[i].player_id == intern("p1")) pi = i;
    assert(pi >= 0);
    assert(gs->players[pi].hand_count == 5);

    printf("  hand size: %d\n", gs->players[pi].hand_count);
    engine_destroy(gs);
}

static void test_play_card_no_instant_crash(void) {
    setup();
    const char *pids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(g_def, pids, 2, 42);

    Move legal[64]; GameState *tmp;
    int n = engine_legal_moves(gs, legal, 64);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
    n = engine_legal_moves(gs, legal, 64);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;

    advance_phase(gs);
    assert(gs->phase == PHASE_MAIN);

    n = engine_legal_moves(gs, legal, 64);
    int played = 0;
    for (int i = 0; i < n && !played; i++) {
        if (legal[i].type == MOVE_PLAY_CARD) {
            tmp = engine_apply(gs, &legal[i]); engine_destroy(gs); gs = tmp;
            played = 1;
        }
    }
    assert(played);
    printf("  card played, new phase: %d\n", gs->phase);
    engine_destroy(gs);
}

static void test_generic_runtime_dispatch(void) {
    setup();

    const char *pids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(g_def, pids, 2, 42);
    GameState *tmp;

    Move legal[64]; int n;
    n = engine_legal_moves(gs, legal, 64);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
    n = engine_legal_moves(gs, legal, 64);
    tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
    advance_phase(gs);

    int before_power = gs->resource_pool.power;
    int before_influence = gs->resource_pool.influence;

    n = engine_legal_moves(gs, legal, 64);
    int played = 0;
    for (int i = 0; i < n && !played; i++) {
        if (legal[i].type == MOVE_PLAY_CARD) {
            tmp = engine_apply(gs, &legal[i]); engine_destroy(gs); gs = tmp;
            played = 1;
        }
    }
    assert(played);

    int pwr_gained = gs->resource_pool.power - before_power;
    int inf_gained = gs->resource_pool.influence - before_influence;
    printf("  power: %d -> %d (+%d)  influence: %d -> %d (+%d)\n",
           before_power, gs->resource_pool.power, pwr_gained,
           before_influence, gs->resource_pool.influence, inf_gained);
    assert(pwr_gained > 0 || inf_gained > 0);
    assert(gs->pending_generic == NULL);

    engine_destroy(gs);
}

static void test_view_projection(void) {
    setup();
    const char *pids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(g_def, pids, 2, 42);

    PublicView pv;
    engine_public_view(gs, &pv);
    assert(pv.player_count == 2);
    assert(pv.node_count > 0);
    assert(pv.phase == PHASE_SETUP);

    PrivateView prv;
    engine_private_view(gs, intern("p1"), &prv);
    assert(prv.player_index >= 0);
    assert(prv.player.player_id == intern("p1"));

    engine_destroy(gs);
}

int main(void) {
    printf("Phase 3 generic runtime tests:\n");
    test_player_hand_has_cards();
    test_play_card_no_instant_crash();
    test_generic_runtime_dispatch();
    test_view_projection();
    printf("\nAll Phase 3 tests passed.\n");
    if (g_def_arena) arena_destroy(g_def_arena);
    return 0;
}
