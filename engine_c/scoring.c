#include "scoring.h"
#include <string.h>

static int count_troops(const NodeState *ns, Sym player_id) {
    int count = 0;
    for (int i = 0; i < ns->troop_slot_count; i++) {
        if (ns->troop_slots[i] == player_id) count++;
    }
    return count;
}

int site_control_owner(const GameState *state, Sym node_id) {
    for (int i = 0; i < state->node_count; i++) {
        if (state->nodes[i].node_id != node_id) continue;
        const NodeState *ns = &state->nodes[i];

        int counts[MAX_PLAYERS + 1] = {0};
        Sym owners[MAX_PLAYERS + 1];
        int owner_count = 0;

        for (int j = 0; j < ns->troop_slot_count; j++) {
            Sym occ = ns->troop_slots[j];
            if (occ == SYM_NULL) continue;
            int found = -1;
            for (int k = 0; k < owner_count; k++) {
                if (owners[k] == occ) { found = k; break; }
            }
            if (found >= 0) counts[found]++;
            else { owners[owner_count] = occ; counts[owner_count] = 1; owner_count++; }
        }
        if (owner_count == 0) return -1;

        int max_count = 0, max_idx = -1, tie = 0;
        for (int k = 0; k < owner_count; k++) {
            if (counts[k] > max_count) { max_count = counts[k]; max_idx = k; tie = 0; }
            else if (counts[k] == max_count) { tie = 1; }
        }
        if (tie || max_idx < 0) return -1;
        Sym leader = owners[max_idx];
        if (intern_str(leader) && strcmp(intern_str(leader), "white") == 0) return -1;
        return max_idx >= 0 ? (int)leader : -1;
    }
    return -1;
}

int is_total_control(const GameState *state, Sym node_id, Sym player_id) {
    for (int i = 0; i < state->node_count; i++) {
        if (state->nodes[i].node_id != node_id) continue;
        const NodeState *ns = &state->nodes[i];
        for (int j = 0; j < ns->troop_slot_count; j++) {
            if (ns->troop_slots[j] != player_id) return 0;
        }
        for (int j = 0; j < ns->spy_count; j++) {
            if (ns->spies[j] != player_id) return 0;
        }
        return 1;
    }
    return 0;
}

static int cards_vp(const GameState *state, Sym *cards, int count, int field_is_deck_vp) {
    int total = 0;
    for (int i = 0; i < count; i++) {
        for (int j = 0; j < state->definition->catalog.card_count; j++) {
            const CardDefinition *cd = &state->definition->catalog.cards[j];
            if (cd->card_id == cards[i]) {
                total += field_is_deck_vp ? cd->deck_vp : cd->inner_circle_vp;
                break;
            }
        }
    }
    return total;
}

void award_end_of_turn_site_vp(GameState *state, Sym player_id) {
    int site_vp = 0;
    for (int i = 0; i < state->definition->board.node_count; i++) {
        const NodeDefinition *nd = &state->definition->board.nodes[i];
        if (strcmp(intern_str(nd->kind), "site") != 0) continue;
        if (is_total_control(state, nd->node_id, player_id)) {
            site_vp += nd->total_control_vp_per_turn;
        }
    }
    if (site_vp > 0) {
        PlayerState *ps = cow_player(state, player_id);
        if (ps) ps->score += site_vp;
    }
}

void compute_final_scores(const GameState *state, int *scores_out) {
    for (int p = 0; p < state->player_count; p++) {
        Sym pid = state->players[p].player_id;
        const PlayerState *ps = &state->players[p];
        int total = ps->score;

        for (int i = 0; i < state->definition->board.node_count; i++) {
            const NodeDefinition *nd = &state->definition->board.nodes[i];
            if (strcmp(intern_str(nd->kind), "site") != 0) continue;
            int owner = site_control_owner(state, nd->node_id);
            if (owner >= 0 && (Sym)owner == pid) {
                total += nd->control_vp;
            }
        }

        total += ps->trophy_hall_count;
        total += ps->vp_tokens;

        int all_cards[MAX_ZONE_SIZE * 3];
        int all_count = 0;
        for (int j = 0; j < ps->deck_count; j++) all_cards[all_count++] = ps->deck[j];
        for (int j = 0; j < ps->hand_count; j++) all_cards[all_count++] = ps->hand[j];
        for (int j = 0; j < ps->discard_pile_count; j++) all_cards[all_count++] = ps->discard_pile[j];
        total += cards_vp(state, all_cards, all_count, 1);

        total += cards_vp(state, ps->inner_circle, ps->inner_circle_count, 0);

        scores_out[p] = total;
    }
}

Sym find_winner(const GameState *state) {
    int scores[MAX_PLAYERS];
    compute_final_scores(state, scores);

    int max_score = -1, max_idx = -1, tie = 0;
    for (int i = 0; i < state->player_count; i++) {
        if (scores[i] > max_score) { max_score = scores[i]; max_idx = i; tie = 0; }
        else if (scores[i] == max_score) { tie = 1; }
    }
    if (tie || max_idx < 0) return SYM_NULL;
    return state->players[max_idx].player_id;
}
