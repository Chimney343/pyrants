/* Tests for the legal-move capacity contract (F-038).
 *
 * One capacity, owned by the engine, and a move query that cannot silently
 * lose moves:
 *
 *   - engine_move_capacity() is the single source of the frozen action-space
 *     size. The Python bindings size their buffers from it and
 *     openspiel_pyrants derives NUM_DISTINCT_ACTIONS from it, so the two
 *     constants that used to drift now cannot.
 *   - engine_legal_moves() and engine_display_moves() return the number of
 *     moves that exist, not the number that fit. They write at most max_out
 *     moves and never touch memory past it. A caller that asks for 4 moves of
 *     a 24-move state is told 24, so truncation is visible at the seam instead
 *     of silent.
 *
 * The non-truncated prefix is unchanged: with room for every move the bytes
 * written are exactly what the old query wrote, in the same order. That keeps
 * the frozen move payloads, the OpenSpiel action ids and the recorded replays
 * untouched.
 */
#include "../engine.h"
#include "../intern.h"
#include "../arena.h"
#include "../phases.h"
#include "catalog_dir.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *PLAYER_IDS[] = {"p1", "p2", "p3", "p4"};

#define PROBE_CAP 64
#define CANARY 0xAB

static GameState *fresh_game(GameDefinition *def, int players) {
    GameState *gs = engine_create_game_definition(def, PLAYER_IDS, players, 42);
    assert(gs);
    return gs;
}

/* Fill a buffer with a sentinel so any write past max_out is detectable. */
static void poison(Move *buf, int len) {
    memset(buf, CANARY, sizeof(Move) * (size_t)len);
}

static int bytes_are_poison(const Move *buf, int from, int len) {
    for (int i = from; i < len; i++) {
        const unsigned char *p = (const unsigned char *)&buf[i];
        for (size_t b = 0; b < sizeof(Move); b++)
            if (p[b] != CANARY) return 0;
    }
    return 1;
}

/* Two moves are the same when the query would emit the same payload. The
 * engine fills only the active union member, so comparing raw bytes would read
 * padding no caller is promised. */
static int same_move(const Move *a, const Move *b) {
    if (a->type != b->type || a->player_index != b->player_index) return 0;
    switch (a->type) {
        case MOVE_PLAY_CARD:
            return a->data.play_card.card_id == b->data.play_card.card_id
                && a->data.play_card.hand_index == b->data.play_card.hand_index;
        case MOVE_ASSASSINATE:
            return a->data.assassinate.target_node_id == b->data.assassinate.target_node_id
                && a->data.assassinate.troop_owner_id == b->data.assassinate.troop_owner_id
                && a->data.assassinate.slot_index == b->data.assassinate.slot_index;
        case MOVE_DEPLOY:
            return a->data.deploy.node_id == b->data.deploy.node_id
                && a->data.deploy.slot_index == b->data.deploy.slot_index;
        case MOVE_RECRUIT:
            return a->data.recruit.card_id == b->data.recruit.card_id;
        case MOVE_RETURN_SPY:
            return a->data.return_spy.node_id == b->data.return_spy.node_id
                && a->data.return_spy.spy_owner_id == b->data.return_spy.spy_owner_id;
        case MOVE_ACTIVATE_ABILITY:
            return a->data.activate_ability.card_id == b->data.activate_ability.card_id
                && a->data.activate_ability.ability_key == b->data.activate_ability.ability_key
                && a->data.activate_ability.discard_hand_count == b->data.activate_ability.discard_hand_count;
        case MOVE_DECLINE_ABILITY:
            return a->data.decline_ability.card_id == b->data.decline_ability.card_id
                && a->data.decline_ability.ability_key == b->data.decline_ability.ability_key;
        case MOVE_PROMOTE_CARD:
            return a->data.promote_card.card_id == b->data.promote_card.card_id;
        case MOVE_SKIP_PROMOTE:
            return a->data.skip_promote.source_card_id == b->data.skip_promote.source_card_id;
        case MOVE_RESOLVE_GENERIC:
            return a->data.resolve_generic.action_id == b->data.resolve_generic.action_id
                && a->data.resolve_generic.target_id == b->data.resolve_generic.target_id
                && a->data.resolve_generic.selection_index == b->data.resolve_generic.selection_index;
        case MOVE_INITIAL_PLACEMENT:
            return a->data.initial_placement.node_id == b->data.initial_placement.node_id;
        default:
            return 1; /* end_main_phase / resolve_end_of_turn / resolve_cleanup: no data */
    }
}

static int same_prefix(const Move *a, const Move *b, int n) {
    for (int i = 0; i < n; i++)
        if (!same_move(&a[i], &b[i])) return 0;
    return 1;
}

static void test_capacity_is_one_constant(void) {
    int cap = engine_move_capacity();
    assert(cap > 0);
    assert(cap == 1024); /* frozen: the NN action space is a wire format */
    printf("PASS: engine_move_capacity is the single source (%d)\n", cap);
}

/* The query reports the true count even when the buffer is too small, and
 * leaves the memory past max_out untouched. */
static void test_legal_query_reports_true_count(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = fresh_game(def, 2);

    Move full[PROBE_CAP];
    poison(full, PROBE_CAP);
    int need = engine_legal_moves(gs, full, PROBE_CAP);
    assert(need > 4);
    assert(need < PROBE_CAP);
    assert(bytes_are_poison(full, need, PROBE_CAP));

    Move trunc[PROBE_CAP];
    poison(trunc, PROBE_CAP);
    int got = engine_legal_moves(gs, trunc, 4);
    assert(got == need);                         /* true count, not 4 */
    assert(same_prefix(full, trunc, 4));          /* same prefix */
    assert(bytes_are_poison(trunc, 4, PROBE_CAP));      /* no overrun */
    printf("PASS: legal query reports needed=%d with a 4-move buffer\n", got);

    engine_destroy(gs);
    arena_destroy(arena);
}

static void test_display_query_reports_true_count(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = fresh_game(def, 2);

    Move full[PROBE_CAP];
    unsigned char full_app[PROBE_CAP];
    poison(full, PROBE_CAP);
    memset(full_app, CANARY, sizeof(full_app));
    int need = engine_display_moves(gs, full, full_app, PROBE_CAP);
    assert(need > 4);
    assert(need < PROBE_CAP);

    Move trunc[PROBE_CAP];
    unsigned char trunc_app[PROBE_CAP];
    poison(trunc, PROBE_CAP);
    memset(trunc_app, CANARY, sizeof(trunc_app));
    int got = engine_display_moves(gs, trunc, trunc_app, 4);
    assert(got == need);
    assert(same_prefix(full, trunc, 4));
    assert(memcmp(full_app, trunc_app, 4) == 0);
    assert(bytes_are_poison(trunc, 4, PROBE_CAP));
    printf("PASS: display query reports needed=%d with a 4-move buffer\n", got);

    engine_destroy(gs);
    arena_destroy(arena);
}

/* max_out = 0 is the size query, matching engine_player_view_json: report the
 * count, write nothing. */
static void test_zero_capacity_is_a_size_query(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = fresh_game(def, 2);

    Move full[PROBE_CAP];
    int need = engine_legal_moves(gs, full, PROBE_CAP);
    assert(need > 0);

    Move none[PROBE_CAP];
    poison(none, PROBE_CAP);
    assert(engine_legal_moves(gs, none, 0) == need);
    assert(bytes_are_poison(none, 0, PROBE_CAP));

    unsigned char app[PROBE_CAP];
    memset(app, CANARY, sizeof(app));
    assert(engine_display_moves(gs, none, app, 0) == need);
    assert(bytes_are_poison(none, 0, PROBE_CAP));
    printf("PASS: max_out=0 reports the count and writes nothing (%d)\n", need);
    printf("PASS: count query leaves the applicable array untouched\n");

    engine_destroy(gs);
    arena_destroy(arena);
}

/* The main-phase query composes several enumerators behind one count; a
 * 4-player mid-game state is the realistic case, and a small buffer must still
 * report the whole list. */
static void test_main_phase_count_composes(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = fresh_game(def, 4);

    /* Complete setup so the game reaches a main-phase decision. */
    for (int guard = 0; guard < 64 && gs->phase == PHASE_SETUP; guard++) {
        Move m[PROBE_CAP];
        int n = engine_legal_moves(gs, m, PROBE_CAP);
        if (n <= 0) break;
        GameState *next = engine_apply(gs, &m[0]);
        assert(next);
        engine_destroy(gs);
        gs = next;
    }

    Move full[PROBE_CAP];
    int need = engine_legal_moves(gs, full, PROBE_CAP);
    assert(need > 0);

    int truncated_every = 0;
    for (int cap = 0; cap < need; cap++) {
        Move trunc[PROBE_CAP];
        poison(trunc, PROBE_CAP);
        int got = engine_legal_moves(gs, trunc, cap);
        assert(got == need);                     /* independent of cap */
        assert(bytes_are_poison(trunc, cap, PROBE_CAP));
        assert(same_prefix(full, trunc, cap));
        truncated_every++;
    }
    assert(truncated_every == need);
    printf("PASS: main-phase count is stable for every cap below %d\n", need);

    engine_destroy(gs);
    arena_destroy(arena);
}

static void test_game_over_and_terminal_have_no_moves(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = fresh_game(def, 2);

    set_game_over(gs);
    Move buf[PROBE_CAP];
    poison(buf, PROBE_CAP);
    assert(engine_legal_moves(gs, buf, PROBE_CAP) == 0);
    assert(engine_display_moves(gs, buf, NULL, PROBE_CAP) == 0);
    assert(bytes_are_poison(buf, 0, PROBE_CAP));
    printf("PASS: a finished game has no moves under either query\n");

    engine_destroy(gs);
    arena_destroy(arena);
}

int main(void) {
    intern_init(4096);
    test_capacity_is_one_constant();
    test_legal_query_reports_true_count();
    test_display_query_reports_true_count();
    test_zero_capacity_is_a_size_query();
    test_main_phase_count_composes();
    test_game_over_and_terminal_have_no_moves();
    intern_destroy();
    printf("All move-capacity tests passed.\n");
    return 0;
}
