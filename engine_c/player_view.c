#include "player_view.h"
#include "scoring.h"
#include <string.h>

void engine_public_view(const GameState *state, PublicView *out) {
    memset(out, 0, sizeof(PublicView));

    out->player_count = state->player_count;
    for (int i = 0; i < state->player_count; i++)
        out->player_ids[i] = state->player_ids[i];

    out->node_count = state->node_count;
    for (int i = 0; i < state->node_count && i < MAX_NODES; i++) {
        PublicNodeView *nv = &out->nodes[i];
        const NodeState *ns = &state->nodes[i];
        nv->node_id = ns->node_id;

        int counts[MAX_PLAYERS + 1] = {0};
        Sym owners[MAX_PLAYERS + 1];
        int oc = 0;
        for (int t = 0; t < ns->troop_slot_count; t++) {
            Sym occ = ns->troop_slots[t];
            if (occ == SYM_NULL) continue;
            int f = -1;
            for (int k = 0; k < oc; k++)
                if (owners[k] == occ) { f = k; break; }
            if (f >= 0) counts[f]++;
            else { owners[oc] = occ; counts[oc++] = 1; }
        }
        nv->troop_owner_count = oc;
        for (int k = 0; k < oc && k < MAX_PLAYERS; k++) {
            nv->troop_counts[k] = counts[k];
            nv->troop_owners[k] = owners[k];
        }
        nv->troop_owner_count = oc;
        if (oc > 0) nv->troop_owner_count = oc;

        int white_troops = 0;
        Sym white = intern("white");
        for (int t = 0; t < ns->troop_slot_count; t++)
            if (ns->troop_slots[t] == white) white_troops++;
        nv->white_troops = white_troops;

        nv->spy_owner_count = ns->spy_count;
        for (int s = 0; s < ns->spy_count && s < MAX_SPY_SLOTS; s++)
            nv->spy_owners[s] = ns->spies[s];
        nv->vp_tokens = ns->vp_tokens;

        int owner = site_control_owner(state, ns->node_id);
        nv->controlled = (owner >= 0);
        nv->controller_id = (owner >= 0) ? (Sym)owner : SYM_NULL;
    }

    out->round_number = state->round_number;
    out->phase = state->phase;
    out->current_player_id = state->current_player_id;
    out->resource_pool = state->resource_pool;
    out->market = state->market;

    if (state->pending_ability) {
        out->has_pending_ability = 1;
        out->pending_ability.ability_key = state->pending_ability->ability_key;
        out->pending_ability.source_card_id = state->pending_ability->card_id;
        out->pending_ability.resolved = state->pending_ability->resolved;
    }

    if (state->pending_generic) {
        out->has_pending_generic = 1;
        out->pending_generic.source_card_id = state->pending_generic->source_card_id;
        out->pending_generic.player_index = 0;
        out->pending_generic.is_pending = 1;
    }
}

void engine_private_view(const GameState *state, Sym player_id, PrivateView *out) {
    memset(out, 0, sizeof(PrivateView));
    engine_public_view(state, &out->public_view);

    int pi = -1;
    for (int i = 0; i < state->player_count; i++)
        if (state->players[i].player_id == player_id) { pi = i; break; }
    if (pi < 0) return;

    out->player = state->players[pi];
    out->player_index = pi;
}

/* ---- A1: 128-bit information-state fingerprint -------------------------
 *
 * Two independent 64-bit FNV-1a-style streams over the same word sequence.
 * Values are fed as fixed-width 64-bit words, never as strings: Syms are
 * stable in-process ids, and the hash is only ever compared inside one run.
 * Constant per-block tags make a structural coincidence (a value sequence
 * that two differently-shaped states happen to share) harder without
 * changing the equivalence classes. */
typedef struct { uint64_t h0, h1; } InfostateHash;

static void ih_init(InfostateHash *h) {
    h->h0 = 0xcbf29ce484222325ULL; /* FNV-1a 64 offset basis */
    h->h1 = 0x9e3779b97f4a7c15ULL; /* golden-ratio seed */
}

static void ih_word(InfostateHash *h, uint64_t x) {
    h->h0 ^= x;
    h->h0 *= 0x00000100000001b3ULL; /* FNV-1a 64 prime */
    h->h1 ^= x + 0x9e3779b97f4a7c15ULL;
    h->h1 *= 0xff51afd7ed558ccdULL; /* murmur3 finalizer constant */
}

void engine_infostate_hash(const GameState *state, Sym player_id, uint64_t out[2]) {
    if (out == NULL) return;
    if (state == NULL) { out[0] = 0; out[1] = 0; return; }

    InfostateHash h;
    ih_init(&h);

    ih_word(&h, 0x0100); /* schema tag */
    ih_word(&h, (uint64_t)(uint32_t)state->round_number);
    ih_word(&h, (uint64_t)(uint32_t)state->phase);
    ih_word(&h, (uint64_t)state->current_player_id);
    ih_word(&h, (uint64_t)(uint32_t)state->player_id_count);
    for (int i = 0; i < state->player_count && i < MAX_PLAYERS; i++)
        ih_word(&h, (uint64_t)state->player_ids[i]);
    ih_word(&h, (uint64_t)(uint32_t)state->resource_pool.power);
    ih_word(&h, (uint64_t)(uint32_t)state->resource_pool.influence);

    ih_word(&h, 0x0200);
    ih_word(&h, (uint64_t)(uint32_t)state->market.row_count);
    for (int i = 0; i < state->market.row_count && i < MAX_ZONE_SIZE; i++)
        ih_word(&h, (uint64_t)state->market.row[i]);
    ih_word(&h, (uint64_t)(uint32_t)state->market.deck_count);
    ih_word(&h, (uint64_t)(uint32_t)state->market.discard_pile_count);

    ih_word(&h, 0x0300);
    ih_word(&h, (uint64_t)(uint32_t)state->devour_pile_count);

    ih_word(&h, 0x0400);
    ih_word(&h, (uint64_t)(uint32_t)state->node_count);
    const BoardDefinition *board = state->definition ? &state->definition->board : NULL;
    for (int i = 0; i < state->node_count && i < MAX_NODES; i++) {
        const NodeState *ns = &state->nodes[i];
        ih_word(&h, (uint64_t)ns->node_id);
        ih_word(&h, (uint64_t)(uint32_t)ns->troop_slot_count);
        for (int j = 0; j < ns->troop_slot_count && j < MAX_TROOP_SLOTS; j++)
            ih_word(&h, (uint64_t)ns->troop_slots[j]);

        /* Mirror _project_board_nodes: keep non-null spy identities, sorted. */
        Sym spies[MAX_SPY_SLOTS];
        int sc = 0;
        for (int j = 0; j < ns->spy_count && j < MAX_SPY_SLOTS; j++)
            if (ns->spies[j] != SYM_NULL) spies[sc++] = ns->spies[j];
        for (int a = 1; a < sc; a++) {
            Sym key = spies[a];
            int b = a - 1;
            while (b >= 0 && spies[b] > key) { spies[b + 1] = spies[b]; b--; }
            spies[b + 1] = key;
        }
        ih_word(&h, (uint64_t)(uint32_t)sc);
        for (int j = 0; j < sc; j++) ih_word(&h, (uint64_t)spies[j]);
        ih_word(&h, (uint64_t)(uint32_t)ns->vp_tokens);
        if (board && i < board->node_count) {
            ih_word(&h, (uint64_t)(uint32_t)board->nodes[i].control_vp);
            ih_word(&h, (uint64_t)(uint32_t)board->nodes[i].total_control_vp_per_turn);
        }
    }

    int pi = -1;
    for (int i = 0; i < state->player_count; i++)
        if (state->players[i].player_id == player_id) { pi = i; break; }

    ih_word(&h, 0x0500);
    for (int i = 0; i < state->player_count && i < MAX_PLAYERS; i++) {
        const PlayerState *p = &state->players[i];
        ih_word(&h, (uint64_t)(uint32_t)p->hand_count);
        ih_word(&h, (uint64_t)(uint32_t)p->deck_count);
        ih_word(&h, (uint64_t)(uint32_t)p->discard_pile_count);
        ih_word(&h, (uint64_t)(uint32_t)p->played_cards_count);
        for (int j = 0; j < p->played_cards_count && j < MAX_ZONE_SIZE; j++)
            ih_word(&h, (uint64_t)p->played_cards[j]);
        ih_word(&h, (uint64_t)(uint32_t)p->inner_circle_count);
        for (int j = 0; j < p->inner_circle_count && j < MAX_ZONE_SIZE; j++)
            ih_word(&h, (uint64_t)p->inner_circle[j]);
        ih_word(&h, (uint64_t)(uint32_t)p->trophy_hall_count);
        for (int j = 0; j < p->trophy_hall_count && j < MAX_ZONE_SIZE; j++)
            ih_word(&h, (uint64_t)p->trophy_hall[j]);
        ih_word(&h, (uint64_t)(uint32_t)p->barracks);
        ih_word(&h, (uint64_t)(uint32_t)p->spies_available);
        ih_word(&h, (uint64_t)(uint32_t)p->vp_tokens);
        ih_word(&h, (uint64_t)(uint32_t)p->score);

        /* Only the observer's hidden zones carry identities. */
        if (i == pi) {
            for (int j = 0; j < p->hand_count && j < MAX_ZONE_SIZE; j++)
                ih_word(&h, (uint64_t)p->hand[j]);
            for (int j = 0; j < p->discard_pile_count && j < MAX_ZONE_SIZE; j++)
                ih_word(&h, (uint64_t)p->discard_pile[j]);
        }
    }

    out[0] = h.h0;
    out[1] = h.h1;
}
