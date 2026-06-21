#include "view.h"
#include "scoring.h"
#include <string.h>

void engine_build_view(const GameState *state, CGameView *out) {
    memset(out, 0, sizeof(CGameView));

    out->round_number = state->round_number;
    out->phase = state->phase;
    out->current_player_id = state->current_player_id;

    out->player_count = state->player_count;
    for (int i = 0; i < state->player_count && i < MAX_PLAYERS; i++) {
        out->player_ids[i] = state->player_ids[i];
        const PlayerState *ps = &state->players[i];
        CPlayerZoneView *zv = &out->players[i];

        for (int j = 0; j < ps->hand_count && j < MAX_ZONE_SIZE; j++)
            zv->hand[j] = ps->hand[j];
        zv->hand_count = ps->hand_count;

        for (int j = 0; j < ps->discard_pile_count && j < MAX_ZONE_SIZE; j++)
            zv->discard[j] = ps->discard_pile[j];
        zv->discard_count = ps->discard_pile_count;

        for (int j = 0; j < ps->played_cards_count && j < MAX_ZONE_SIZE; j++)
            zv->played[j] = ps->played_cards[j];
        zv->played_count = ps->played_cards_count;

        for (int j = 0; j < ps->inner_circle_count && j < MAX_ZONE_SIZE; j++)
            zv->inner_circle[j] = ps->inner_circle[j];
        zv->inner_circle_count = ps->inner_circle_count;

        for (int j = 0; j < ps->trophy_hall_count && j < MAX_ZONE_SIZE; j++)
            zv->trophy_hall[j] = ps->trophy_hall[j];
        zv->trophy_hall_count = ps->trophy_hall_count;

        zv->barracks = ps->barracks;
        zv->spies_available = ps->spies_available;
        zv->vp_tokens = ps->vp_tokens;
        zv->score = ps->score;
        zv->deck_count = ps->deck_count;
    }

    for (int i = 0; i < state->market.row_count && i < MAX_ZONE_SIZE; i++)
        out->market_row[i] = state->market.row[i];
    out->market_row_count = state->market.row_count;
    out->market_deck_count = state->market.deck_count;
    out->market_discard_count = state->market.discard_pile_count;

    out->resource_power = state->resource_pool.power;
    out->resource_influence = state->resource_pool.influence;

    for (int i = 0; i < state->devour_pile_count && i < MAX_ZONE_SIZE; i++)
        out->devour_pile[i] = state->devour_pile[i];
    out->devour_pile_count = state->devour_pile_count;

    const BoardDefinition *board = &state->definition->board;
    out->node_count = state->node_count;
    for (int i = 0; i < state->node_count && i < MAX_NODES; i++) {
        const NodeState *ns = &state->nodes[i];
        const NodeDefinition *nd = &board->nodes[i];
        CNodeOccupancyView *nv = &out->nodes[i];

        nv->node_id = ns->node_id;
        nv->kind = (nd->kind == intern("site")) ? 0 : 1;

        for (int j = 0; j < nd->adjacent_count && j < MAX_NODES; j++)
            nv->adjacent_to[j] = nd->adjacent_to[j];
        nv->adjacent_count = nd->adjacent_count;

        nv->control_vp = nd->control_vp;
        nv->total_control_vp_per_turn = nd->total_control_vp_per_turn;

        for (int j = 0; j < ns->troop_slot_count && j < MAX_TROOP_SLOTS; j++)
            nv->troop_slots[j] = ns->troop_slots[j];
        nv->troop_slot_count = ns->troop_slot_count;

        for (int j = 0; j < ns->spy_count && j < MAX_SPY_SLOTS; j++)
            nv->spies[j] = ns->spies[j];
        nv->spy_count = ns->spy_count;

        nv->vp_tokens = ns->vp_tokens;
    }

    int controlled_sites = 0;
    int total_control_sites = 0;
    int control_vp_sum = 0;
    int total_control_vp_sum = 0;
    Sym site_sym = intern("site");
    for (int i = 0; i < state->node_count && i < MAX_NODES; i++) {
        const NodeDefinition *nd = &board->nodes[i];
        if (nd->kind != site_sym) continue;
        {
            int owner = site_control_owner(state, nd->node_id);
            if (owner >= 0 && (Sym)owner == state->current_player_id) {
                controlled_sites++;
                control_vp_sum += nd->control_vp;
            }
        }
        if (is_total_control(state, nd->node_id, state->current_player_id)) {
            total_control_sites++;
            total_control_vp_sum += nd->total_control_vp_per_turn;
        }
    }
    out->controlled_sites = controlled_sites;
    out->total_control_sites = total_control_sites;
    out->current_player_control_vp = control_vp_sum;
    out->current_player_total_control_vp = total_control_vp_sum;
}
