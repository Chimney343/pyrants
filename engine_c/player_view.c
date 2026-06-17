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
