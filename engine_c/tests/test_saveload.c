#include "saveload.h"
#include "engine.h"
#include "loader.h"
#include "intern.h"
#include "arena.h"
#include "catalog_dir.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

static void test_serialize_basic(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    char json[128 * 1024];
    int needed = engine_serialize_state(gs, "data/cards",
                                         "data/boards/tyrants_of_the_underdark.json",
                                         "data/decks/base_setup.json",
                                         0, 0, json, sizeof(json));
    assert(needed > 0);
    assert(needed < (int)sizeof(json));
    assert(strstr(json, "\"scenario_id\"") != NULL);
    assert(strstr(json, "\"move_count\"") != NULL);
    assert(strstr(json, "\"state\"") != NULL);
    printf("serialize needed=%d, starts: %.80s...\n", needed, json);

    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_deserialize_round_trip(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    const char *board_path, *setup_path;
    test_board_setup_paths(&board_path, &setup_path);

    char json[128 * 1024];
    int needed = engine_serialize_state(gs, "data/cards", board_path, setup_path,
                                         0, 0, json, sizeof(json));
    assert(needed > 0);

    Arena *arena2 = arena_create(2 * 1024 * 1024);
    assert(arena2);
    char *catalog_json = test_load_catalog_json_both();
    assert(catalog_json);
    int restored_move_count = -1;
    GameState *restored = engine_deserialize_state(json, catalog_json, arena2, &restored_move_count);
    free(catalog_json);
    assert(restored);
    assert(restored_move_count == 0);
    assert(restored->player_count == gs->player_count);
    assert(restored->round_number == gs->round_number);
    assert(restored->phase == gs->phase);
    assert(restored->node_count == gs->node_count);

    printf("PASS: deserialize_round_trip (move_count=%d, player_count=%d)\n",
           restored_move_count, restored->player_count);

    engine_destroy(restored);
    arena_destroy(arena2);
    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_serialize_needed_size(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    int needed = engine_serialize_state(gs, "data/cards",
                                         "data/boards/tyrants_of_the_underdark.json",
                                         "data/decks/base_setup.json",
                                         0, 0, NULL, 0);
    assert(needed > 0);
    printf("needed buffer size: %d\n", needed);

    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

int main(void) {
    test_serialize_basic();
    test_deserialize_round_trip();
    test_serialize_needed_size();
    printf("All saveload tests passed.\n");
    return 0;
}
