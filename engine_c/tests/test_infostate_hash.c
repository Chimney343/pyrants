/* Tests for engine_infostate_hash — the A1 IS-MCTS tree-key shortcut.
 *
 * The key must be an exact fingerprint of the fields
 * ``CEngineAdapter.private_view_json`` serialises for one observing player,
 * because the tree keys nodes by it. Two failure modes matter:
 *
 *   * false split — hashing a hidden field (deck identities, devour identity,
 *     opponents' hands) that the observation string omits. The tree stops
 *     sharing equal info sets and IS-MCTS degrades toward per-world PIMC.
 *   * false merge — omitting a public field (board occupancy, own hand/discard
 *     identity, market row) the string includes. Two distinct info sets share
 *     a node and the search pools visit statistics across them.
 *
 * These tests pin both directions at the C level; the Python equivalence test
 * (tests/test_infostate_key.py) then checks hash == string classes end to end.
 */
#include "../engine.h"
#include "../player_view.h"
#include "../intern.h"
#include "../arena.h"
#include "catalog_dir.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

static const char *PLAYER_IDS[] = {"p1", "p2"};

static int hashes_equal(const uint64_t a[2], const uint64_t b[2]) {
    return a[0] == b[0] && a[1] == b[1];
}

static GameState *fresh_game(Arena **arena_out) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    GameDefinition *def = test_load_definition(arena);
    assert(def);
    GameState *gs = engine_create_game_definition(def, PLAYER_IDS, 2, 42);
    assert(gs);
    *arena_out = arena;
    return gs;
}

/* Same state hashed twice must agree (pure function of state + observer). */
static void test_hash_is_deterministic(void) {
    Arena *arena;
    GameState *gs = fresh_game(&arena);
    uint64_t a[2], b[2];
    engine_infostate_hash(gs, intern("p1"), a);
    engine_infostate_hash(gs, intern("p1"), b);
    assert(hashes_equal(a, b));
    engine_infostate_hash(gs, intern("p2"), b);
    engine_infostate_hash(gs, intern("p2"), a);
    assert(hashes_equal(a, b));
    printf("PASS: infostate hash is deterministic\n");
    engine_destroy(gs);
    arena_destroy(arena);
}

/* A clone of the same state must hash identically (tree sharing depends on it). */
static void test_clone_hashes_equal(void) {
    Arena *arena;
    GameState *gs = fresh_game(&arena);
    GameState *clone = engine_clone(gs);
    assert(clone);
    uint64_t a[2], b[2];
    engine_infostate_hash(gs, intern("p1"), a);
    engine_infostate_hash(clone, intern("p1"), b);
    assert(hashes_equal(a, b));
    printf("PASS: cloned state hashes equal\n");
    engine_destroy(clone);
    engine_destroy(gs);
    arena_destroy(arena);
}

/* Own hand *identity* is in the observation, so a same-count substitution
 * must split the key for the owner and only the owner. */
static void test_own_hand_identity_splits_owner_only(void) {
    Arena *arena;
    GameState *gs = fresh_game(&arena);
    PlayerState *me = &gs->players[0];
    me->hand_count = 1;
    me->hand[0] = intern("noble");

    Sym other = intern("bounty_hunter");

    uint64_t before_me[2], before_them[2], after_me[2], after_them[2];
    engine_infostate_hash(gs, intern("p1"), before_me);
    engine_infostate_hash(gs, intern("p2"), before_them);

    me->hand[0] = other;

    engine_infostate_hash(gs, intern("p1"), after_me);
    engine_infostate_hash(gs, intern("p2"), after_them);

    assert(!hashes_equal(before_me, after_me));   /* own hand identity visible */
    assert(hashes_equal(before_them, after_them)); /* opponent sees only count */
    printf("PASS: own hand identity splits only the owner's key\n");
    engine_destroy(gs);
    arena_destroy(arena);
}

/* Own discard identity is in the observation; same-count substitution splits. */
static void test_own_discard_identity_splits(void) {
    Arena *arena;
    GameState *gs = fresh_game(&arena);
    PlayerState *me = &gs->players[0];
    me->discard_pile_count = 1;
    me->discard_pile[0] = intern("noble");

    Sym other = intern("bounty_hunter");

    uint64_t before[2], after[2];
    engine_infostate_hash(gs, intern("p1"), before);
    me->discard_pile[0] = other;
    engine_infostate_hash(gs, intern("p1"), after);
    assert(!hashes_equal(before, after));
    printf("PASS: own discard identity splits the key\n");
    engine_destroy(gs);
    arena_destroy(arena);
}

/* Hidden deck identities and the devour pile are NOT in the observation, so
 * a same-count substitution must not split the key (false-split guard). */
static void test_hidden_deck_identity_does_not_split(void) {
    Arena *arena;
    GameState *gs = fresh_game(&arena);
    PlayerState *me = &gs->players[0];
    PlayerState *them = &gs->players[1];
    me->deck_count = 1;
    them->deck_count = 1;
    me->deck[0] = intern("noble");
    them->deck[0] = intern("noble");

    uint64_t before[2], after[2];
    engine_infostate_hash(gs, intern("p1"), before);
    me->deck[0] = intern("bounty_hunter");
    them->deck[0] = intern("soldier");
    engine_infostate_hash(gs, intern("p1"), after);
    assert(hashes_equal(before, after));
    printf("PASS: hidden deck identity is excluded from the key\n");
    engine_destroy(gs);
    arena_destroy(arena);
}

/* Board occupancy is public: a troop change must split every observer's key. */
static void test_board_occupancy_splits(void) {
    Arena *arena;
    GameState *gs = fresh_game(&arena);
    assert(gs->node_count >= 1);
    NodeState *n = &gs->nodes[0];
    n->troop_slot_count = 1;

    Sym a = intern("p1");
    Sym b = intern("p2");
    n->troop_slots[0] = a;

    uint64_t before1[2], before2[2], after1[2], after2[2];
    engine_infostate_hash(gs, intern("p1"), before1);
    engine_infostate_hash(gs, intern("p2"), before2);
    n->troop_slots[0] = b;
    engine_infostate_hash(gs, intern("p1"), after1);
    engine_infostate_hash(gs, intern("p2"), after2);

    assert(!hashes_equal(before1, after1));
    assert(!hashes_equal(before2, after2));
    printf("PASS: board occupancy splits every observer's key\n");
    engine_destroy(gs);
    arena_destroy(arena);
}

/* Spy order must not matter: private_view_json sorts node spies, so two states
 * differing only by spy slot order are one info set (false-split guard). */
static void test_spy_order_does_not_split(void) {
    Arena *arena;
    GameState *gs = fresh_game(&arena);
    NodeState *n = &gs->nodes[0];
    n->spy_count = 2;
    n->spies[0] = intern("p1");
    n->spies[1] = intern("p2");

    uint64_t before[2], after[2];
    engine_infostate_hash(gs, intern("p1"), before);
    Sym tmp = n->spies[0];
    n->spies[0] = n->spies[1];
    n->spies[1] = tmp;
    engine_infostate_hash(gs, intern("p1"), after);
    assert(hashes_equal(before, after));
    printf("PASS: spy slot order does not split the key\n");
    engine_destroy(gs);
    arena_destroy(arena);
}

/* Public scalars and the market row are in the observation. */
static void test_public_fields_split(void) {
    Arena *arena;
    GameState *gs = fresh_game(&arena);
    uint64_t base[2], other[2];

    engine_infostate_hash(gs, intern("p1"), base);

    gs->round_number += 1;
    engine_infostate_hash(gs, intern("p1"), other);
    assert(!hashes_equal(base, other));
    gs->round_number -= 1;

    gs->resource_pool.power += 1;
    engine_infostate_hash(gs, intern("p1"), other);
    assert(!hashes_equal(base, other));
    gs->resource_pool.power -= 1;

    gs->players[0].score += 1;
    engine_infostate_hash(gs, intern("p1"), other);
    assert(!hashes_equal(base, other));
    gs->players[0].score -= 1;

    gs->market.row_count = 1;
    gs->market.row[0] = intern("noble");
    engine_infostate_hash(gs, intern("p1"), base);
    gs->market.row[0] = intern("bounty_hunter");
    engine_infostate_hash(gs, intern("p1"), other);
    assert(!hashes_equal(base, other));
    gs->market.row[0] = intern("noble");

    printf("PASS: public round/resource/score/market fields split the key\n");
    engine_destroy(gs);
    arena_destroy(arena);
}

/* A count-only change is public and must split even when identities do not. */
static void test_counts_split(void) {
    Arena *arena;
    GameState *gs = fresh_game(&arena);
    uint64_t base[2], other[2];
    engine_infostate_hash(gs, intern("p1"), base);

    gs->devour_pile_count += 1;
    engine_infostate_hash(gs, intern("p1"), other);
    assert(!hashes_equal(base, other));
    gs->devour_pile_count -= 1;

    gs->players[1].deck_count = 2;
    engine_infostate_hash(gs, intern("p1"), base);
    gs->players[1].deck_count = 1;
    engine_infostate_hash(gs, intern("p1"), other);
    assert(!hashes_equal(base, other));
    gs->players[1].deck_count = 0;

    printf("PASS: public size counts split the key\n");
    engine_destroy(gs);
    arena_destroy(arena);
}

int main(void) {
    intern_init(65536);

    test_hash_is_deterministic();
    test_clone_hashes_equal();
    test_own_hand_identity_splits_owner_only();
    test_own_discard_identity_splits();
    test_hidden_deck_identity_does_not_split();
    test_board_occupancy_splits();
    test_spy_order_does_not_split();
    test_public_fields_split();
    test_counts_split();

    printf("\nAll infostate-hash tests passed.\n");
    return 0;
}
