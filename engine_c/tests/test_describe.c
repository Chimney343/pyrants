#include "describe.h"
#include "engine.h"
#include "loader.h"
#include "intern.h"
#include "arena.h"
#include "moves.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

static void test_describe_play_card(void) {
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

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    Sym noble = intern("noble");
    Move m = make_play_card_move(noble, 0);

    char buf[256];
    int needed = engine_describe_move(gs, &m, NULL, NULL, 0, buf, sizeof(buf));
    assert(needed > 0);
    assert(strstr(buf, "Play") != NULL);
    printf("describe play_card: %s\n", buf);

    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_describe_end_main_phase(void) {
    intern_init(4096);
    Move m = make_end_main_phase_move(0);
    char buf[256];
    int needed = engine_describe_move(NULL, &m, NULL, NULL, 0, buf, sizeof(buf));
    assert(needed > 0);
    assert(strcmp(buf, "End main phase") == 0);
    printf("describe end_main_phase: %s\n", buf);
    intern_destroy();
}

static void test_describe_deploy(void) {
    intern_init(4096);
    Sym node_id = intern("site_1");
    Move m = make_deploy_move(node_id, 0, 0);

    const char *node_ids[] = {"site_1"};
    const char *node_labels[] = {"Site One"};
    char buf[256];
    int needed = engine_describe_move(NULL, &m, node_ids, node_labels, 1, buf, sizeof(buf));
    assert(needed > 0);
    assert(strstr(buf, "Deploy") != NULL);
    printf("describe deploy: %s\n", buf);

    intern_destroy();
}

static void test_describe_deploy_no_labels(void) {
    intern_init(4096);
    Sym node_id = intern("site_1");
    Move m = make_deploy_move(node_id, 0, 0);

    char buf[256];
    int needed = engine_describe_move(NULL, &m, NULL, NULL, 0, buf, sizeof(buf));
    assert(needed > 0);
    assert(strstr(buf, "Site 1") != NULL);
    printf("describe deploy no labels: %s\n", buf);

    intern_destroy();
}

static void test_describe_assassinate(void) {
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

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    Sym node_id = intern("site_gauntlgrym");
    Sym owner = intern("white");
    Move m = make_assassinate_move(node_id, owner, 0, 0);

    char buf[256];
    int needed = engine_describe_move(gs, &m, NULL, NULL, 0, buf, sizeof(buf));
    assert(needed > 0);
    assert(strstr(buf, "Remove") != NULL);
    assert(strstr(buf, "white") != NULL);
    assert(strstr(buf, "slot") == NULL);
    printf("describe assassinate: %s\n", buf);

    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_describe_assassinate_no_slot_index(void) {
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

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    Sym node_id = intern("site_gauntlgrym");
    Sym owner = intern("white");
    Move m = make_assassinate_move(node_id, owner, 2, 0);

    char buf[256];
    int needed = engine_describe_move(gs, &m, NULL, NULL, 0, buf, sizeof(buf));
    assert(needed > 0);
    char idx_str[8];
    snprintf(idx_str, sizeof(idx_str), "%d", 2);
    assert(strstr(buf, idx_str) == NULL);
    printf("describe assassinate no slot: %s\n", buf);

    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_describe_recruit(void) {
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

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    Sym card_id = gs->market.row[0];
    Move m = make_recruit_move(card_id, 0);

    char buf[256];
    int needed = engine_describe_move(gs, &m, NULL, NULL, 0, buf, sizeof(buf));
    assert(needed > 0);
    assert(strstr(buf, "Recruit") != NULL);
    printf("describe recruit: %s\n", buf);

    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_describe_needed_size(void) {
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

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    Sym card_id = gs->market.row[0];
    Move m = make_recruit_move(card_id, 0);

    int needed = engine_describe_move(gs, &m, NULL, NULL, 0, NULL, 0);
    assert(needed > 0);
    assert(needed < 256);
    printf("describe needed_size: %d\n", needed);

    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_describe_unknown_move_type(void) {
    intern_init(4096);
    Move m;
    memset(&m, 0, sizeof(m));
    m.type = (MoveType)99;
    m.player_index = 0;

    char buf[256];
    int needed = engine_describe_move(NULL, &m, NULL, NULL, 0, buf, sizeof(buf));
    assert(needed > 0);
    assert(strstr(buf, "99") != NULL);
    printf("describe unknown type: %s\n", buf);

    intern_destroy();
}

static void test_describe_node_name_lookup(void) {
    intern_init(4096);
    Sym node_id = intern("site_gauntlgrym");
    Move m = make_deploy_move(node_id, 0, 0);

    const char *node_ids[] = {"site_gauntlgrym", "site_luskan"};
    const char *node_labels[] = {"Gauntlgrym", "Luskan"};
    char buf[256];
    int needed = engine_describe_move(NULL, &m, node_ids, node_labels, 2, buf, sizeof(buf));
    assert(needed > 0);
    assert(strstr(buf, "Gauntlgrym") != NULL);
    assert(strstr(buf, "site_gauntlgrym") == NULL);
    printf("describe node name lookup: %s\n", buf);

    intern_destroy();
}

static void test_describe_node_name_miss_fallback(void) {
    intern_init(4096);
    Sym node_id = intern("site_missing");
    Move m = make_deploy_move(node_id, 0, 0);

    const char *node_ids[] = {"site_gauntlgrym"};
    const char *node_labels[] = {"Gauntlgrym"};
    char buf[256];
    int needed = engine_describe_move(NULL, &m, node_ids, node_labels, 1, buf, sizeof(buf));
    assert(needed > 0);
    assert(strstr(buf, "Site missing") != NULL);
    printf("describe node name miss: %s\n", buf);

    intern_destroy();
}

int main(void) {
    test_describe_play_card();
    test_describe_end_main_phase();
    test_describe_deploy();
    test_describe_deploy_no_labels();
    test_describe_assassinate();
    test_describe_assassinate_no_slot_index();
    test_describe_recruit();
    test_describe_needed_size();
    test_describe_unknown_move_type();
    test_describe_node_name_lookup();
    test_describe_node_name_miss_fallback();
    printf("All describe tests passed.\n");
    return 0;
}
