#include "engine.h"
#include "intern.h"
#include "arena.h"
#include "rng.h"
#include "loader.h"
#include "moves.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

static void test_intern(void) {
    intern_init(1024);
    Sym a = intern("hello");
    Sym b = intern("world");
    Sym c = intern("hello");
    assert(a == c);
    assert(a != b);
    assert(strcmp(intern_str(a), "hello") == 0);
    printf("PASS: intern\n");
}

static void test_arena(void) {
    Arena *arena = arena_create(1024);
    int *p = arena_alloc(arena, sizeof(int));
    *p = 42;
    char *s = arena_strdup(arena, "test string");
    assert(strcmp(s, "test string") == 0);
    assert(*p == 42);
    arena_destroy(arena);
    printf("PASS: arena\n");
}

static void test_rng(void) {
    RNG rng;
    rng_seed(&rng, 12345ULL);
    uint64_t v1 = rng_next(&rng);
    uint64_t v2 = rng_next(&rng);
    assert(v1 != v2);
    uint32_t arr[5] = {0, 1, 2, 3, 4};
    rng_shuffle(&rng, arr, 5);
    printf("PASS: rng\n");
}

static void test_loader_catalog(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);
    GameDefinition *def = engine_load_definition(
        "../data/cards/catalog.json",
        "../data/boards/tyrants_of_the_underdark.json",
        "../data/decks/base_setup.json",
        arena
    );
    if (!def || def->catalog.card_count == 0) {
        def = engine_load_definition(
            "data/cards/catalog.json",
            "data/boards/tyrants_of_the_underdark.json",
            "data/decks/base_setup.json",
            arena
        );
    }
    assert(def);
    printf("definition loaded\n");

    assert(def->catalog.card_count > 0);
    printf("catalog: %d cards\n", def->catalog.card_count);
    assert(strcmp(intern_str(def->catalog.catalog_id), "base_catalog") == 0);

    assert(def->board.node_count > 0);
    printf("board: %d nodes\n", def->board.node_count);

    int sequence_count = 0, modal_count = 0;
    for (int i = 0; i < def->catalog.card_count; i++) {
        CardDefinition *cd = &def->catalog.cards[i];
        assert(cd->card_id != SYM_NULL);
        assert(cd->name != SYM_NULL);
        if (cd->execution.kind == EXEC_SEQUENCE) sequence_count++;
        else if (cd->execution.kind == EXEC_MODAL) modal_count++;
    }
    printf("execution models: sequence=%d modal=%d\n", sequence_count, modal_count);

    CardDefinition *cd = &def->catalog.cards[0];
    printf("first card: %s (cost=%d, aspect=%s)\n",
        intern_str(cd->name), cd->cost, intern_str(cd->aspect));

    arena_destroy(arena);
    printf("PASS: loader catalog\n");
}

static void test_state_creation(void) {
    const char *player_ids[] = {"player_1", "player_2"};
    uint64_t seed = 12345;

    Arena *arena = arena_create(2 * 1024 * 1024);
    GameDefinition *def = engine_load_definition(
        "../data/cards/catalog.json",
        "../data/boards/tyrants_of_the_underdark.json",
        "../data/decks/base_setup.json",
        arena
    );
    if (!def || def->catalog.card_count == 0) {
        def = engine_load_definition(
            "data/cards/catalog.json",
            "data/boards/tyrants_of_the_underdark.json",
            "data/decks/base_setup.json",
            arena
        );
    }
    assert(def);

    GameState *gs = engine_create_game_definition(def, player_ids, 2, seed);
    assert(gs);
    assert(gs->player_count == 2);
    assert(gs->phase == PHASE_SETUP);
    assert(gs->current_player_id == intern("player_1"));
    printf("PASS: state creation\n");
    engine_destroy(gs);
    arena_destroy(arena);
}

static void test_clone(void) {
    const char *player_ids[] = {"player_1", "player_2"};
    Arena *arena = arena_create(2 * 1024 * 1024);
    GameDefinition *def = engine_load_definition(
        "../data/cards/catalog.json",
        "../data/boards/tyrants_of_the_underdark.json",
        "../data/decks/base_setup.json",
        arena
    );
    if (!def || def->catalog.card_count == 0) {
        def = engine_load_definition(
            "data/cards/catalog.json",
            "data/boards/tyrants_of_the_underdark.json",
            "data/decks/base_setup.json",
            arena
        );
    }
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    gs->round_number = 5;
    gs->shuffle_counter = 99;

    GameState *clone = engine_clone(gs);
    assert(clone);
    assert(clone->player_count == 2);
    assert(clone->round_number == 5);
    assert(clone->shuffle_counter == 99);
    assert(clone->definition == gs->definition);
    assert(clone != gs);

    printf("PASS: clone\n");
    engine_destroy(clone);
    engine_destroy(gs);
    arena_destroy(arena);
}

static void test_moves(void) {
    Sym card_id = intern("noble");
    Move m = make_play_card_move(card_id, 0);
    assert(m.type == MOVE_PLAY_CARD);
    assert(m.data.play_card.card_id == card_id);
    assert(m.player_index == 0);

    Move a = make_assassinate_move(intern("site_1"), intern("player_2"), 2, 0);
    assert(a.type == MOVE_ASSASSINATE);
    assert(a.data.assassinate.slot_index == 2);
    assert(a.player_index == 0);

    Move ip = make_initial_placement_move(intern("site_1"), 0);
    assert(ip.type == MOVE_INITIAL_PLACEMENT);
    assert(ip.data.initial_placement.node_id == intern("site_1"));

    printf("PASS: moves\n");
}

extern void test_intern_null_sym(void);
extern void test_intern_round_trip(void);
extern void test_intern_stable_pointer(void);
extern void test_intern_unknown_sym(void);
extern void test_intern_lazy_grow_round_trip(void);
extern void test_intern_destroy_clears(void);

static void test_cow(void) {
    const char *player_ids[] = {"p1", "p2"};
    Arena *arena = arena_create(2 * 1024 * 1024);
    GameDefinition *def = engine_load_definition(
        "../data/cards/catalog.json",
        "../data/boards/tyrants_of_the_underdark.json",
        "../data/decks/base_setup.json",
        arena
    );
    if (!def || def->catalog.card_count == 0) {
        def = engine_load_definition(
            "data/cards/catalog.json",
            "data/boards/tyrants_of_the_underdark.json",
            "data/decks/base_setup.json",
            arena
        );
    }
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);

    NodeState *node = cow_node(gs, gs->nodes[0].node_id);
    assert(node);
    assert(node->cow_dirty);

    PlayerState *player = cow_player(gs, intern("p1"));
    assert(player);
    assert(player->cow_dirty);

    printf("PASS: cow accessors\n");
    engine_destroy(gs);
    arena_destroy(arena);
}

int main(void) {
    test_intern();
    test_intern_null_sym();
    test_intern_round_trip();
    test_intern_stable_pointer();
    test_intern_unknown_sym();
    test_intern_lazy_grow_round_trip();
    test_intern_destroy_clears();
    test_arena();
    test_rng();
    test_loader_catalog();
    test_state_creation();
    test_clone();
    test_moves();
    test_cow();
    printf("\nAll Phase 0 + Phase 1 tests passed.\n");
    return 0;
}
