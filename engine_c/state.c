#include "state.h"
#include "arena.h"
#include "pending.h"
#include "rng.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>

void expand_deck(const DeckDefinition *dd, Sym *out, int *out_count) {
    *out_count = 0;
    for (int i = 0; i < dd->entry_count; i++) {
        for (int c = 0; c < dd->entries[i].count; c++) {
            if (*out_count < MAX_ZONE_SIZE) {
                out[(*out_count)++] = dd->entries[i].card_id;
            }
        }
    }
}

void shuffle_deck(Sym *deck, int count, uint64_t seed, int counter, RNG *rng) {
    uint64_t rng_seed_val = (seed << 16) ^ (uint64_t)counter;
    rng_seed(rng, rng_seed_val);
    for (int i = 0; i < count; i++) {
        uint32_t tmp = (uint32_t)deck[i];
        deck[i] = tmp;
    }
    rng_shuffle(rng, (uint32_t *)deck, count);
}

void draw_cards_state(PlayerState *ps, int count, RNG *rng, uint64_t shuffle_seed, int *shuffle_counter) {
    for (int i = 0; i < count; i++) {
        if (ps->deck_count == 0 && ps->discard_pile_count > 0) {
            memcpy(ps->deck, ps->discard_pile, (size_t)ps->discard_pile_count * sizeof(Sym));
            ps->deck_count = ps->discard_pile_count;
            ps->discard_pile_count = 0;
            shuffle_deck(ps->deck, ps->deck_count, shuffle_seed, *shuffle_counter, rng);
            (*shuffle_counter)++;
        }
        if (ps->deck_count == 0) break;
        ps->hand[ps->hand_count++] = ps->deck[--ps->deck_count];
    }
}

void engine_destroy(GameState *state) {
    if (!state) return;
    Arena *arena = (Arena *)state->arena;
    arena_destroy(arena);
}

GameState *engine_create_game(const char *json_path, const char **player_ids, int player_count, uint64_t seed) {
    (void)json_path;
    Arena *arena = arena_create(512 * 1024);
    if (!arena) return NULL;
    GameState *gs = arena_calloc(arena, 1, sizeof(GameState));
    if (!gs) { arena_destroy(arena); return NULL; }
    gs->arena = arena;
    gs->shuffle_seed = seed;
    gs->shuffle_counter = 0;
    gs->phase = PHASE_SETUP;
    gs->round_number = 1;

    for (int i = 0; i < player_count && i < MAX_PLAYERS; i++) {
        Sym pid = intern(player_ids[i]);
        gs->player_ids[i] = pid;
        gs->players[i].player_id = pid;
    }
    gs->player_id_count = player_count;
    gs->player_count = player_count;
    if (player_count > 0) gs->current_player_id = gs->player_ids[0];

    return gs;
}

GameState *engine_create_game_definition(const GameDefinition *def, const char **player_ids,
                                          int player_count, uint64_t seed) {
    if (!def) return NULL;
    RNG rng;
    rng_seed(&rng, seed);

    Arena *arena = arena_create(512 * 1024);
    if (!arena) return NULL;
    GameState *gs = arena_calloc(arena, 1, sizeof(GameState));
    if (!gs) { arena_destroy(arena); return NULL; }
    gs->arena = arena;
    gs->definition = def;
    gs->shuffle_seed = seed;
    gs->shuffle_counter = 0;
    gs->phase = PHASE_SETUP;
    gs->round_number = 1;

    for (int i = 0; i < player_count && i < MAX_PLAYERS; i++) {
        Sym pid = intern(player_ids[i]);
        gs->player_ids[i] = pid;
        gs->players[i].player_id = pid;
        gs->players[i].barracks = def->default_player_troops;
        gs->players[i].spies_available = def->default_player_spies;
    }
    gs->player_id_count = player_count;
    gs->player_count = player_count;
    if (player_count > 0) gs->current_player_id = gs->player_ids[0];

    gs->node_count = def->board.node_count;
    assert(gs->node_count <= MAX_NODES);
    for (int i = 0; i < def->board.node_count && i < MAX_NODES; i++) {
        NodeDefinition *nd = &def->board.nodes[i];
        gs->nodes[i].node_id = nd->node_id;
        if (nd->initial_troop_slots) {
            gs->nodes[i].troop_slot_count = nd->initial_troop_slot_count;
            for (int j = 0; j < nd->initial_troop_slot_count && j < MAX_TROOP_SLOTS; j++) {
                gs->nodes[i].troop_slots[j] = nd->initial_troop_slots[j];
            }
        } else {
            gs->nodes[i].troop_slot_count = nd->troop_capacity;
        }
        gs->nodes[i].vp_tokens = nd->initial_vp_tokens;
    }

    Sym starter_card_ids[MAX_ZONE_SIZE];
    int starter_count = 0;
    expand_deck(&def->setup.starter_deck, starter_card_ids, &starter_count);

    int counter = 0;
    for (int i = 0; i < player_count && i < MAX_PLAYERS; i++) {
        Sym deck[MAX_ZONE_SIZE];
        memcpy(deck, starter_card_ids, (size_t)starter_count * sizeof(Sym));
        shuffle_deck(deck, starter_count, seed, counter, &rng);
        counter++;
        for (int j = 0; j < starter_count && j < MAX_ZONE_SIZE; j++) {
            gs->players[i].deck[j] = deck[j];
        }
        gs->players[i].deck_count = starter_count;
    }

    gs->shuffle_counter = counter;

    Sym market_cards[MAX_ZONE_SIZE];
    int market_count = 0;
    expand_deck(&def->setup.market_deck, market_cards, &market_count);
    Sym shuffled[MAX_ZONE_SIZE];
    memcpy(shuffled, market_cards, (size_t)market_count * sizeof(Sym));
    shuffle_deck(shuffled, market_count, seed, counter, &rng);
    counter++;

    int row_count = def->setup.market_row_size;
    if (row_count > market_count) row_count = market_count;
    for (int i = 0; i < row_count; i++) {
        gs->market.row[i] = shuffled[--market_count];
    }
    gs->market.row_count = row_count;
    for (int i = 0; i < market_count; i++) {
        gs->market.deck[i] = shuffled[i];
    }
    gs->market.deck_count = market_count;
    gs->shuffle_counter = counter;

    return gs;
}

GameState *engine_clone(const GameState *src) {
    if (!src) return NULL;
    Arena *arena = arena_create(512 * 1024);
    if (!arena) return NULL;
    GameState *dst = arena_calloc(arena, 1, sizeof(GameState));
    if (!dst) { arena_destroy(arena); return NULL; }
    dst->arena = arena;
    memcpy(dst, src, sizeof(GameState));
    dst->arena = arena;

    pending_clone(dst, src, arena);
    return dst;
}

void reshuffle_discard_into_deck(GameState *state, Sym player_id) {
    PlayerState *player = cow_player(state, player_id);
    if (!player) return;
    RNG rng;
    shuffle_deck(player->discard_pile, player->discard_pile_count,
                 state->shuffle_seed, state->shuffle_counter, &rng);
    for (int i = 0; i < player->discard_pile_count && i < MAX_ZONE_SIZE; i++) {
        player->deck[i] = player->discard_pile[i];
    }
    player->deck_count = player->discard_pile_count;
    state->shuffle_counter++;
    player->discard_pile_count = 0;
}

NodeState *cow_node(GameState *state, Sym node_id) {
    for (int i = 0; i < state->node_count; i++)
        if (state->nodes[i].node_id == node_id) return &state->nodes[i];
    return NULL;
}

PlayerState *cow_player(GameState *state, Sym player_id) {
    for (int i = 0; i < state->player_count; i++)
        if (state->players[i].player_id == player_id) return &state->players[i];
    return NULL;
}

MarketState *cow_market(GameState *state) {
    return &state->market;
}

ResourcePool *cow_resource_pool(GameState *state) {
    return &state->resource_pool;
}

GameState *engine_determinize(const GameState *src, Sym observing_player_id, uint64_t seed) {
    if (!src) return NULL;
    GameState *clone = engine_clone(src);
    if (!clone) return NULL;

    RNG rng;
    rng_seed(&rng, seed);

    for (int i = 0; i < clone->player_count && i < MAX_PLAYERS; i++) {
        PlayerState *ps = &clone->players[i];
        if (ps->player_id == observing_player_id) continue;

        int total = ps->hand_count + ps->deck_count + ps->discard_pile_count;
        if (total == 0) continue;

        Sym temp[3 * MAX_ZONE_SIZE];
        int pos = 0;
        for (int j = 0; j < ps->hand_count; j++) temp[pos++] = ps->hand[j];
        for (int j = 0; j < ps->deck_count; j++) temp[pos++] = ps->deck[j];
        for (int j = 0; j < ps->discard_pile_count; j++) temp[pos++] = ps->discard_pile[j];

        rng_shuffle(&rng, (uint32_t *)temp, total);

        pos = 0;
        for (int j = 0; j < ps->hand_count; j++) ps->hand[j] = temp[pos++];
        for (int j = 0; j < ps->deck_count; j++) ps->deck[j] = temp[pos++];
        for (int j = 0; j < ps->discard_pile_count; j++) ps->discard_pile[j] = temp[pos++];
    }

    /* Market deck order is hidden to all players (only its size is public):
     * reshuffle it on every determinization so IS-MCTS cannot exploit a single
     * clairvoyant deck order across simulations. The face-up market row and the
     * (unused, non-recycled) market discard are left untouched. */
    if (clone->market.deck_count > 1) {
        rng_shuffle(&rng, (uint32_t *)clone->market.deck, clone->market.deck_count);
    }

    /* F-002: decouple the shared mid-game reshuffle/forced-discard stream
     * across sampled worlds, the same way the market deck already is. Every
     * mid-game random event reseeds from state->shuffle_seed/shuffle_counter;
     * rerolling them here makes each determinized world draw an independent
     * stream. Placed after every prior rng draw so the rerolled seed is a
     * deterministic function of `seed` (F-010 reproducibility). See
     * docs/validation/f002-f003-fix-plan.md Part A. */
    clone->shuffle_seed = rng_next(&rng);
    clone->shuffle_counter = 0;

    return clone;
}

