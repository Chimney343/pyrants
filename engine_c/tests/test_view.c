#include "view.h"
#include "engine.h"
#include "loader.h"
#include "intern.h"
#include "arena.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

static void test_build_view_round_and_phase(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = engine_load_definition(
        "../data/cards/catalog.json",
        "../data/boards/tyrants_of_the_underdark.json",
        "../data/decks/base_setup.json",
        arena
    );
    if (!def || def->catalog.card_count == 0) {
        arena_destroy(arena);
        arena = arena_create(2 * 1024 * 1024);
        def = engine_load_definition(
            "data/cards/catalog.json",
            "data/boards/tyrants_of_the_underdark.json",
            "data/decks/base_setup.json",
            arena
        );
    }
    assert(def);
    assert(def->catalog.card_count > 0);

    const char *player_ids[] = {"player_1", "player_2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    CGameView view;
    memset(&view, 0, sizeof(view));
    engine_build_view(gs, &view);

    assert(view.round_number == 1);
    assert(view.phase == PHASE_SETUP);
    assert(view.player_count == 2);
    assert(view.current_player_id == intern("player_1"));
    assert(view.resource_power == 0);
    assert(view.resource_influence == 0);

    printf("PASS: build_view_round_and_phase\n");
    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_build_view_player_zones(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = engine_load_definition(
        "../data/cards/catalog.json",
        "../data/boards/tyrants_of_the_underdark.json",
        "../data/decks/base_setup.json",
        arena
    );
    if (!def || def->catalog.card_count == 0) {
        arena_destroy(arena);
        arena = arena_create(2 * 1024 * 1024);
        def = engine_load_definition(
            "data/cards/catalog.json",
            "data/boards/tyrants_of_the_underdark.json",
            "data/decks/base_setup.json",
            arena
        );
    }
    assert(def);

    const char *player_ids[] = {"player_1", "player_2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    CGameView view;
    memset(&view, 0, sizeof(view));
    engine_build_view(gs, &view);

    assert(view.players[0].barracks == gs->players[0].barracks);
    assert(view.players[0].spies_available == gs->players[0].spies_available);
    assert(view.players[0].vp_tokens == 0);
    assert(view.players[0].score == 0);

    printf("PASS: build_view_player_zones\n");
    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_build_view_board_nodes(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = engine_load_definition(
        "../data/cards/catalog.json",
        "../data/boards/tyrants_of_the_underdark.json",
        "../data/decks/base_setup.json",
        arena
    );
    if (!def || def->catalog.card_count == 0) {
        arena_destroy(arena);
        arena = arena_create(2 * 1024 * 1024);
        def = engine_load_definition(
            "data/cards/catalog.json",
            "data/boards/tyrants_of_the_underdark.json",
            "data/decks/base_setup.json",
            arena
        );
    }
    assert(def);

    const char *player_ids[] = {"player_1", "player_2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    CGameView view;
    memset(&view, 0, sizeof(view));
    engine_build_view(gs, &view);

    assert(view.node_count == def->board.node_count);
    for (int i = 0; i < view.node_count && i < def->board.node_count; i++) {
        assert(view.nodes[i].node_id == def->board.nodes[i].node_id);
        assert(view.nodes[i].vp_tokens == def->board.nodes[i].initial_vp_tokens);
    }

    printf("PASS: build_view_board_nodes\n");
    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

int main(void) {
    test_build_view_round_and_phase();
    test_build_view_player_zones();
    test_build_view_board_nodes();
    printf("All view tests passed.\n");
    return 0;
}
