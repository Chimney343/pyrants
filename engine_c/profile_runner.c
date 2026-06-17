#include "engine.h"
#include "intern.h"
#include "arena.h"
#include "rng.h"
#include "loader.h"
#include "moves.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <assert.h>

#define ROLLOUT_COUNT    500
#define MAX_MOVES        128
#define MAX_DEPTH          15
#define NUM_PLAYERS         2
#define CLONE_COUNT      5000

static const char *PLAYER_IDS[] = {"p1", "p2"};

static void run_rollout(const GameDefinition *def, uint64_t seed, RNG *pick_rng) {
    GameState *state = engine_create_game_definition(
        def, (const char **)PLAYER_IDS, NUM_PLAYERS, seed);
    if (!state) {
        fprintf(stderr, "Failed to create game state for seed %llu\n", (unsigned long long)seed);
        return;
    }

    Move moves[MAX_MOVES];
    int depth = 0;
    while (depth < MAX_DEPTH) {
        if (engine_is_terminal(state)) break;

        int n = engine_legal_moves(state, moves, MAX_MOVES);
        if (n <= 0) break;

        int pick = (int)(rng_next(pick_rng) % (unsigned int)n);

        GameState *next = engine_apply(state, &moves[pick]);
        if (!next) break;

        engine_destroy(state);
        state = next;
        depth++;
    }
    engine_destroy(state);
}

static void run_benchmark(const GameDefinition *def, uint64_t base_seed) {
    RNG rng;
    rng_seed(&rng, base_seed);

    for (int i = 0; i < ROLLOUT_COUNT; i++) {
        uint64_t seed = rng_next(&rng);
        run_rollout(def, seed, &rng);
    }
}

static void run_clone_benchmark(const GameDefinition *def, uint64_t seed) {
    GameState *state = engine_create_game_definition(
        def, (const char **)PLAYER_IDS, NUM_PLAYERS, seed);
    if (!state) return;

    for (int i = 0; i < CLONE_COUNT; i++) {
        GameState *cloned = engine_clone(state);
        engine_destroy(cloned);
    }
    engine_destroy(state);
}

static void test_intern_throughput(void) {
    intern_init(1024);
    char buf[32];
    Sym *syms = (Sym *)malloc(50000 * sizeof(Sym));
    for (int i = 0; i < 50000; i++) {
        snprintf(buf, sizeof(buf), "string_%d", i);
        syms[i] = intern(buf);
    }
    clock_t t0 = clock();
    volatile const char *sink = NULL;
    for (int i = 0; i < 50000; i++) sink = intern_str(syms[i]);
    clock_t t1 = clock();
    double ms = (t1 - t0) * 1000.0 / CLOCKS_PER_SEC;
    free(syms);
    intern_destroy();
    (void)sink;
    printf("intern_throughput: 50k resolves in %.1f ms\n", ms);
    fflush(stdout);
    assert(ms < 500.0);
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    printf("Running intern throughput benchmark...\n");
    test_intern_throughput();

    intern_init(65536);

    Arena *arena = arena_create(16 * 1024 * 1024);
    if (!arena) {
        fprintf(stderr, "Failed to create arena\n");
        return 1;
    }

    const char *catalog_path = "../../data/cards/catalog.json";
    const char *board_path   = "../../data/boards/tyrants_of_the_underdark.json";
    const char *setup_path   = "../../data/decks/base_setup.json";

    GameDefinition *def = engine_load_definition(catalog_path, board_path, setup_path, arena);
    if (!def) {
        catalog_path = "../data/cards/catalog.json";
        board_path   = "../data/boards/tyrants_of_the_underdark.json";
        setup_path   = "../data/decks/base_setup.json";
        def = engine_load_definition(catalog_path, board_path, setup_path, arena);
    }

    if (!def || def->catalog.card_count == 0) {
        fprintf(stderr, "Failed to load game definition\n");
        arena_destroy(arena);
        return 1;
    }

    printf("Loaded: %d cards, %d nodes, %d players\n",
           def->catalog.card_count, def->board.node_count, NUM_PLAYERS);

    printf("Running %d rollouts (max depth %d)...\n", ROLLOUT_COUNT, MAX_DEPTH);
    run_benchmark(def, 42ULL);

    printf("Running clone benchmark (%d iterations)...\n", CLONE_COUNT);
    run_clone_benchmark(def, 42ULL);

    printf("Done.\n");
    arena_destroy(arena);
    return 0;
}
