#include "helpers.h"
#include "generic_runtime.h"
#include "scoring.h"
#include <string.h>
#include <stdlib.h>

static int str_sym_compare(const void *a, const void *b) {
    const char *sa = intern_str(*(const Sym *)a);
    const char *sb = intern_str(*(const Sym *)b);
    return strcmp(sa ? sa : "", sb ? sb : "");
}

EffectFn effect_registry[EFFECT_COUNT];
static Sym effect_keys[EFFECT_COUNT];
static int effect_count = 0;

void register_effect(Sym effect_key, EffectFn fn) {
    if (effect_count < EFFECT_COUNT) {
        effect_keys[effect_count] = effect_key;
        effect_registry[effect_count] = fn;
        effect_count++;
    }
}

EffectFn lookup_effect(Sym effect_key) {
    for (int i = 0; i < effect_count; i++) {
        if (effect_keys[i] == effect_key) return effect_registry[i];
    }
    return NULL;
}

static const CardDefinition *card_by_id(const GameState *state, Sym card_id) {
    for (int i = 0; i < state->definition->catalog.card_count; i++) {
        if (state->definition->catalog.cards[i].card_id == card_id)
            return &state->definition->catalog.cards[i];
    }
    return NULL;
}

void trigger_opponent_discard_reactive(GameState *state, Sym actor_id, Sym victim_id, Sym discarded_card_id) {
    if (actor_id == victim_id || discarded_card_id == SYM_NULL) return;

    const CardDefinition *card = card_by_id(state, discarded_card_id);
    if (!card) return;

    for (int i = 0; i < card->global_condition_count; i++) {
        const char *gct = intern_str(card->global_conditions[i].condition_type);
        if (!gct || strcmp(gct, "conditional_gate") != 0) continue;

        for (int ai = 0; ai < card->action_count; ai++) {
            const CardAction *action = &card->actions[ai];
            const char *sf = intern_str(action->source_fragment);
            if (!sf || strncmp(sf, "on_", 3) != 0) continue;

            const char *ts = intern_str(action->target_scope);
            Sym beneficiary = victim_id;
            if (ts && strcmp(ts, "opponent") == 0) beneficiary = actor_id;

            int dummy_keys[8] = {0};
            Sym dummy_vals[8] = {0};
            apply_generic_action(state, beneficiary, card, discarded_card_id, action,
                                 dummy_keys, dummy_vals, 0);
        }
        return;
    }
}

static const NodeDefinition *node_def_by_id(const GameState *state, Sym node_id) {
    for (int i = 0; i < state->definition->board.node_count; i++) {
        if (state->definition->board.nodes[i].node_id == node_id)
            return &state->definition->board.nodes[i];
    }
    return NULL;
}

int player_index_for_id(const GameState *state, Sym player_id) {
    for (int i = 0; i < state->player_count; i++) {
        if (state->players[i].player_id == player_id) return i;
    }
    return -1;
}

int count_trophies(const PlayerState *ps, const char *filter) {
    if (!ps || !filter) return 0;
    if (strcmp(filter, "all") == 0) return ps->trophy_hall_count;
    if (strcmp(filter, "non_white") == 0 || strcmp(filter, "white") == 0) {
        int c = 0;
        for (int i = 0; i < ps->trophy_hall_count; i++) {
            const char *t = intern_str(ps->trophy_hall[i]);
            if (!t) continue;
            if (strcmp(filter, "non_white") == 0 && strcmp(t, "white") != 0) c++;
            if (strcmp(filter, "white") == 0 && strcmp(t, "white") == 0) c++;
        }
        return c;
    }
    return 0;
}

int has_presence(const GameState *state, Sym player_id, Sym node_id) {
    for (int ni = 0; ni < state->node_count; ni++) {
        if (state->nodes[ni].node_id != node_id) continue;
        const NodeState *ns = &state->nodes[ni];
        for (int s = 0; s < ns->spy_count; s++) {
            if (ns->spies[s] == player_id) return 1;
        }
        for (int t = 0; t < ns->troop_slot_count; t++) {
            if (ns->troop_slots[t] == player_id) return 1;
        }
        const NodeDefinition *nd = node_def_by_id(state, node_id);
        if (!nd) return 0;
        for (int a = 0; a < nd->adjacent_count; a++) {
            Sym adj_id = nd->adjacent_to[a];
            for (int ni2 = 0; ni2 < state->node_count; ni2++) {
                if (state->nodes[ni2].node_id != adj_id) continue;
                for (int t = 0; t < state->nodes[ni2].troop_slot_count; t++) {
                    if (state->nodes[ni2].troop_slots[t] == player_id) return 1;
                }
                break;
            }
        }
        return 0;
    }
    return 0;
}

int player_has_any_troops_on_board(const GameState *state, Sym player_id) {
    for (int i = 0; i < state->node_count; i++) {
        for (int j = 0; j < state->nodes[i].troop_slot_count; j++) {
            if (state->nodes[i].troop_slots[j] == player_id) return 1;
        }
    }
    return 0;
}

int can_deploy_to_node(const GameState *state, Sym player_id, Sym node_id, int has_troops) {
    int ni = -1;
    for (int i = 0; i < state->node_count; i++) {
        if (state->nodes[i].node_id == node_id) { ni = i; break; }
    }
    if (ni < 0) return 0;
    const NodeState *ns = &state->nodes[ni];
    int has_empty = 0;
    for (int j = 0; j < ns->troop_slot_count; j++) {
        if (ns->troop_slots[j] == SYM_NULL) { has_empty = 1; break; }
    }
    if (!has_empty) return 0;
    if (!has_troops) return 1;
    return has_presence(state, player_id, node_id);
}

int legal_initial_placement_node_ids(const GameState *state, Sym *out, int max_out) {
    int count = 0;
    for (int i = 0; i < state->definition->board.node_count; i++) {
        const NodeDefinition *nd = &state->definition->board.nodes[i];
        if (strcmp(intern_str(nd->kind), "site") != 0) continue;
        for (int j = 0; j < state->node_count; j++) {
            if (state->nodes[j].node_id != nd->node_id) continue;
            for (int k = 0; k < state->nodes[j].troop_slot_count; k++) {
                if (state->nodes[j].troop_slots[k] == SYM_NULL) {
                    if (count < max_out) out[count++] = nd->node_id;
                    break;
                }
            }
            break;
        }
    }
    qsort(out, count, sizeof(Sym), str_sym_compare);
    return count;
}

static Sym site_majority_owner(const GameState *state, const NodeState *ns) {
    int counts[MAX_PLAYERS + 1] = {0};
    Sym owners[MAX_PLAYERS + 1];
    int oc = 0;
    for (int t = 0; t < ns->troop_slot_count; t++) {
        Sym occ = ns->troop_slots[t];
        if (occ == SYM_NULL) continue;
        int f = -1;
        for (int k = 0; k < oc; k++) { if (owners[k] == occ) { f = k; break; } }
        if (f >= 0) counts[f]++;
        else { owners[oc] = occ; counts[oc++] = 1; }
    }
    if (oc == 0) return SYM_NULL;
    int maxc = 0, maxi = -1, tie = 0;
    for (int k = 0; k < oc; k++) {
        if (counts[k] > maxc) { maxc = counts[k]; maxi = k; tie = 0; }
        else if (counts[k] == maxc) { tie = 1; }
    }
    if (tie || maxi < 0) return SYM_NULL;
    const char *os = intern_str(owners[maxi]);
    if (os && strcmp(os, "white") == 0) return SYM_NULL;
    return owners[maxi];
}

static int node_index(const GameState *state, Sym node_id) {
    for (int j = 0; j < state->node_count; j++)
        if (state->nodes[j].node_id == node_id) return j;
    return -1;
}

int count_controlled_sites(const GameState *state, Sym player_id) {
    int total = 0;
    for (int i = 0; i < state->definition->board.node_count; i++) {
        const NodeDefinition *nd = &state->definition->board.nodes[i];
        if (strcmp(intern_str(nd->kind), "site") != 0) continue;
        int ni = node_index(state, nd->node_id);
        if (ni < 0) continue;
        Sym owner = site_majority_owner(state, &state->nodes[ni]);
        if (owner == player_id) total++;
    }
    return total;
}

int count_owned_control_markers(const GameState *state, Sym player_id) {
    int total = 0;
    for (int i = 0; i < state->definition->board.node_count; i++) {
        const NodeDefinition *nd = &state->definition->board.nodes[i];
        if (strcmp(intern_str(nd->kind), "site") != 0) continue;
        if (nd->total_control_vp_per_turn <= 0) continue;
        int ni = node_index(state, nd->node_id);
        if (ni < 0) continue;
        Sym owner = site_majority_owner(state, &state->nodes[ni]);
        if (owner == player_id) total++;
    }
    return total;
}

int count_total_controlled_sites(const GameState *state, Sym player_id) {
    int total = 0;
    for (int i = 0; i < state->definition->board.node_count; i++) {
        const NodeDefinition *nd = &state->definition->board.nodes[i];
        if (strcmp(intern_str(nd->kind), "site") != 0) continue;
        if (is_total_control(state, nd->node_id, player_id)) total++;
    }
    return total;
}

int count_runtime_cards_by_aspect(const GameState *state, Sym *card_ids, int count,
                                   Sym required_aspect, Sym required_secondary_aspect) {
    int total = 0;
    for (int i = 0; i < count; i++) {
        const CardDefinition *cd = card_by_id(state, card_ids[i]);
        if (!cd) continue;
        if (required_aspect != SYM_NULL && cd->aspect != required_aspect) continue;
        if (required_secondary_aspect != SYM_NULL) {
            int found = 0;
            for (int j = 0; j < cd->secondary_aspect_count; j++) {
                if (cd->secondary_aspects[j] == required_secondary_aspect) { found = 1; break; }
            }
            if (!found) continue;
        }
        total++;
    }
    return total;
}

int is_aberrations_enabled(const GameState *state) {
    Sym ab = intern("aberrations");
    return (state->definition->setup.setup_id == ab ||
            state->definition->setup.market_deck.deck_id == ab);
}

int special_stack_config(int market_slot, Sym *card_id_out, int *stack_total) {
    if (market_slot == 100) { *card_id_out = intern("house_guard"); *stack_total = 15; return 1; }
    if (market_slot == 101) { *card_id_out = intern("priestess_of_lolth"); *stack_total = 15; return 1; }
    if (market_slot == 102) { *card_id_out = intern("insane_outcast"); *stack_total = 30; return 1; }
    return 0;
}

int remaining_special_stack_count(const GameState *state, Sym card_id, int stack_total) {
    int available = 0;
    for (int i = 0; i < state->market.deck_count; i++)
        if (state->market.deck[i] == card_id) available++;
    for (int i = 0; i < state->market.row_count; i++)
        if (state->market.row[i] == card_id) available++;
    if (available > 0) return available;

    int owned = 0;
    for (int p = 0; p < state->player_count; p++) {
        const PlayerState *ps = &state->players[p];
        for (int i = 0; i < ps->deck_count; i++) if (ps->deck[i] == card_id) owned++;
        for (int i = 0; i < ps->hand_count; i++) if (ps->hand[i] == card_id) owned++;
        for (int i = 0; i < ps->discard_pile_count; i++) if (ps->discard_pile[i] == card_id) owned++;
        for (int i = 0; i < ps->played_cards_count; i++) if (ps->played_cards[i] == card_id) owned++;
        for (int i = 0; i < ps->inner_circle_count; i++) if (ps->inner_circle[i] == card_id) owned++;
        for (int i = 0; i < ps->trophy_hall_count; i++) if (ps->trophy_hall[i] == card_id) owned++;
    }
    return stack_total - owned > 0 ? stack_total - owned : 0;
}

int scaled_vp_award_count(const GameState *state, Sym player_id, const CardAction *action) {
    const char *sf = intern_str(action->source_fragment);
    const char *cf = NULL;
    int per = 1;

    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "count_from") == 0) cf = v;
        if (k && strcmp(k, "per") == 0 && v) per = atoi(v);
    }

    if (!cf) {
        if (sf && strcmp(sf, "scaled_vp_from_white_trophies") == 0) { cf = "trophy_hall_white"; per = (per == 1) ? 3 : per; }
        else if (sf && strcmp(sf, "scaled_vp_from_trophies") == 0) { cf = "trophy_hall_non_white"; per = (per == 1) ? 5 : per; }
        else if (sf && strcmp(sf, "scaled_vp_from_controlled_sites") == 0) { cf = "controlled_sites"; per = (per == 1) ? 2 : per; }
        else if (sf && (strcmp(sf, "scaled_vp") == 0 || strcmp(sf, "scaled_vp_from_promoted_cards") == 0))
            { cf = "inner_circle_cards"; per = (per == 1) ? 3 : per; }
    }
    if (!cf || per <= 0) return 0;

    int pi = player_index_for_id(state, player_id);
    if (pi < 0) return 0;
    const PlayerState *ps = &state->players[pi];

    int base = 0;
    if (strcmp(cf, "trophy_hall_white") == 0) {
        base = count_trophies(ps, "white");
    } else if (strcmp(cf, "trophy_hall_non_white") == 0) {
        base = count_trophies(ps, "non_white");
    } else if (strcmp(cf, "trophy_hall_all") == 0) {
        base = count_trophies(ps, "all");
    } else if (strcmp(cf, "inner_circle_cards") == 0) {
        Sym required_aspect = SYM_NULL;
        Sym required_secondary_aspect = SYM_NULL;
        for (int i = 0; i < action->metadata_count; i++) {
            const char *k = intern_str(action->metadata[i].key);
            if (k && strcmp(k, "required_aspect") == 0)
                required_aspect = action->metadata[i].value;
            if (k && strcmp(k, "required_secondary_aspect") == 0)
                required_secondary_aspect = action->metadata[i].value;
        }
        base = count_runtime_cards_by_aspect(state, ps->inner_circle, ps->inner_circle_count,
                                              required_aspect, required_secondary_aspect);
    } else if (strcmp(cf, "controlled_sites") == 0) {
        base = count_controlled_sites(state, player_id);
    } else if (strcmp(cf, "owned_control_markers") == 0) {
        base = count_owned_control_markers(state, player_id);
    }
    return base / per;
}

int focus_requirement_met(const GameState *state, Sym player_id, const CardDefinition *card, Sym source_card_id, Sym focus_aspect_override) {
    Sym required;
    if (focus_aspect_override != SYM_NULL) {
        required = focus_aspect_override;
    } else {
        const char *aspect_str = card->aspect != SYM_NULL ? intern_str(card->aspect) : NULL;
        if (!aspect_str) return 1;
        required = intern(aspect_str);
    }
    int pi = player_index_for_id(state, player_id);
    if (pi < 0) return 0;
    const PlayerState *ps = &state->players[pi];

    for (int i = 0; i < ps->hand_count; i++) {
        const CardDefinition *cd = card_by_id(state, ps->hand[i]);
        if (cd && cd->aspect == required) return 1;
    }
    int skipped = 0;
    for (int i = 0; i < ps->played_cards_count; i++) {
        if (!skipped && ps->played_cards[i] == source_card_id) {
            skipped = 1;
            continue;
        }
        const CardDefinition *cd = card_by_id(state, ps->played_cards[i]);
        if (cd && cd->aspect == required) return 1;
    }
    return 0;
}

void promote_card(GameState *state, Sym player_id, Sym card_id) {
    PlayerState *ps = cow_player(state, player_id);
    if (!ps) return;
    Sym insane = intern("insane_outcast");
    for (int i = 0; i < ps->played_cards_count; i++) {
        if (ps->played_cards[i] == card_id) {
            for (int j = i; j < ps->played_cards_count - 1; j++)
                ps->played_cards[j] = ps->played_cards[j + 1];
            ps->played_cards_count--;
            if (card_id == insane)
                return;
            if (ps->inner_circle_count < MAX_ZONE_SIZE)
                ps->inner_circle[ps->inner_circle_count++] = card_id;
            return;
        }
    }
}

int apply_promote_instruction(GameState *state, Sym player_id, Sym card_id, Sym timing, int optional) {
    const char *ts = intern_str(timing);
    if (!ts) return -1;

    if (strcmp(ts, "immediate") == 0) {
        if (optional) {
            if (state->pending_immediate_count < MAX_PENDING_PROMO) {
                PendingPromotionState *pp = &state->pending_immediate[state->pending_immediate_count++];
                memset(pp, 0, sizeof(*pp));
                pp->card_id = card_id;
                pp->timing = timing;
                pp->optional = 1;
                pp->source_card_id = card_id;
            }
            return 0;
        }
        promote_card(state, player_id, card_id);
        return 0;
    }

    if (strcmp(ts, "end_of_turn") == 0) {
        if (state->pending_eot_count < MAX_PENDING_PROMO) {
            PendingPromotionState *pp = &state->pending_eot[state->pending_eot_count++];
            memset(pp, 0, sizeof(*pp));
            pp->card_id = card_id;
            pp->timing = timing;
            pp->optional = optional;
            pp->source_card_id = card_id;
        }
    }
    return 0;
}

void grant_resource(GameState *state, Sym resource, int amount) {
    ResourcePool *pool = cow_resource_pool(state);
    if (!pool) return;
    const char *rs = intern_str(resource);
    if (rs && strcmp(rs, "power") == 0) pool->power += amount;
    else if (rs && strcmp(rs, "influence") == 0) pool->influence += amount;
}

int apply_free_assassinate(GameState *state, Sym player_id, Sym target_node_id, int target_slot_index, int ignore_presence) {
    if (!ignore_presence && !has_presence(state, player_id, target_node_id)) return -1;
    NodeState *ns = cow_node(state, target_node_id);
    if (!ns) return -1;
    if (target_slot_index < 0 || target_slot_index >= ns->troop_slot_count) return -1;
    Sym occupant = ns->troop_slots[target_slot_index];
    if (occupant == SYM_NULL || occupant == player_id) return -1;

    ns->troop_slots[target_slot_index] = SYM_NULL;
    PlayerState *ps = cow_player(state, player_id);
    if (ps && ps->trophy_hall_count < MAX_ZONE_SIZE)
        ps->trophy_hall[ps->trophy_hall_count++] = occupant;
    return 0;
}

int apply_free_deploy(GameState *state, Sym player_id, Sym target_node_id) {
    int ht = player_has_any_troops_on_board(state, player_id);
    if (!can_deploy_to_node(state, player_id, target_node_id, ht)) return -1;
    PlayerState *ps = cow_player(state, player_id);
    if (!ps) return -1;
    if (ps->barracks == 0) return -1;
    NodeState *ns = cow_node(state, target_node_id);
    if (!ns) return -1;
    for (int i = 0; i < ns->troop_slot_count; i++) {
        if (ns->troop_slots[i] == SYM_NULL) {
            ns->troop_slots[i] = player_id;
            ps->barracks--;
            return 0;
        }
    }
    return -1;
}

int apply_return_spy(GameState *state, Sym player_id, Sym node_id, Sym spy_owner_id, int free_enemy_return) {
    const NodeDefinition *nd = node_def_by_id(state, node_id);
    if (!nd) return -1;
    if (strcmp(intern_str(nd->kind), "route") == 0) return -1;

    NodeState *ns = cow_node(state, node_id);
    if (!ns) return -1;
    int spy_idx = -1;
    for (int i = 0; i < ns->spy_count; i++) {
        if (ns->spies[i] == spy_owner_id) { spy_idx = i; break; }
    }
    if (spy_idx < 0) return -1;

    if (spy_owner_id != player_id) {
        if (!free_enemy_return) {
            ResourcePool *pool = cow_resource_pool(state);
            if (!pool || pool->power < 3) return -1;
            pool->power -= 3;
        }
        if (!has_presence(state, player_id, node_id)) return -1;
    }

    for (int i = spy_idx; i < ns->spy_count - 1; i++)
        ns->spies[i] = ns->spies[i + 1];
    ns->spy_count--;

    PlayerState *ps = cow_player(state, spy_owner_id);
    if (ps) ps->spies_available++;
    return 0;
}

int apply_recruit(GameState *state, Sym player_id, int market_slot) {
    Sym special_id;
    int stack_total;
    if (special_stack_config(market_slot, &special_id, &stack_total)) {
        if (market_slot == 102 && !is_aberrations_enabled(state)) return -1;
        if (remaining_special_stack_count(state, special_id, stack_total) <= 0) return -1;
        const CardDefinition *cd = card_by_id(state, special_id);
        if (!cd) return -1;
        ResourcePool *pool = cow_resource_pool(state);
        if (!pool || pool->influence < cd->cost) return -1;
        pool->influence -= cd->cost;
        PlayerState *ps = cow_player(state, player_id);
        if (ps && ps->discard_pile_count < MAX_ZONE_SIZE)
            ps->discard_pile[ps->discard_pile_count++] = special_id;
        return 0;
    }

    if (market_slot >= state->market.row_count) return -1;
    Sym card_id = state->market.row[market_slot];
    const CardDefinition *cd = card_by_id(state, card_id);
    if (!cd) return -1;
    ResourcePool *pool = cow_resource_pool(state);
    if (!pool || pool->influence < cd->cost) return -1;
    pool->influence -= cd->cost;

    PlayerState *ps = cow_player(state, player_id);
    if (ps && ps->discard_pile_count < MAX_ZONE_SIZE)
        ps->discard_pile[ps->discard_pile_count++] = card_id;

    MarketState *ms = cow_market(state);
    if (ms) {
        if (ms->deck_count > 0) {
            ms->row[market_slot] = ms->deck[--ms->deck_count];
        } else {
            for (int i = market_slot; i < ms->row_count - 1; i++)
                ms->row[i] = ms->row[i + 1];
            ms->row_count--;
        }
    }
    return 0;
}

int apply_recruit_free(GameState *state, Sym player_id, int market_slot) {
    Sym special_id;
    int stack_total;
    if (special_stack_config(market_slot, &special_id, &stack_total)) {
        if (market_slot == 102 && !is_aberrations_enabled(state)) return -1;
        if (remaining_special_stack_count(state, special_id, stack_total) <= 0) return -1;
        PlayerState *ps = cow_player(state, player_id);
        if (ps && ps->discard_pile_count < MAX_ZONE_SIZE)
            ps->discard_pile[ps->discard_pile_count++] = special_id;
        return 0;
    }

    if (market_slot >= state->market.row_count) return -1;
    Sym card_id = state->market.row[market_slot];

    PlayerState *ps = cow_player(state, player_id);
    if (ps && ps->discard_pile_count < MAX_ZONE_SIZE)
        ps->discard_pile[ps->discard_pile_count++] = card_id;

    MarketState *ms = cow_market(state);
    if (ms) {
        if (ms->deck_count > 0) {
            ms->row[market_slot] = ms->deck[--ms->deck_count];
        } else {
            for (int i = market_slot; i < ms->row_count - 1; i++)
                ms->row[i] = ms->row[i + 1];
            ms->row_count--;
        }
    }
    return 0;
}

int ability_cost_affordable(const GameState *state, Sym player_id, Sym card_id) {
    const CardDefinition *cd = card_by_id(state, card_id);
    if (!cd) return 0;
    if (!cd->paid_ability.present) return 0;
    int pi = player_index_for_id(state, player_id);
    if (pi < 0) return 0;
    const PlayerState *ps = &state->players[pi];

    const PaidAbility *pa = &cd->paid_ability;
    if (state->resource_pool.power < pa->cost_power) return 0;
    if (state->resource_pool.influence < pa->cost_influence) return 0;
    if (ps->hand_count < pa->cost_discard) return 0;
    return 1;
}

int pay_ability_cost(GameState *state, Sym player_id, Sym card_id, int *discard_indices, int discard_count) {
    if (!ability_cost_affordable(state, player_id, card_id)) return -1;
    const CardDefinition *cd = card_by_id(state, card_id);
    if (!cd || !cd->paid_ability.present) return -1;
    const PaidAbility *pa = &cd->paid_ability;

    int required_discard = pa->cost_discard;
    if (discard_count != required_discard) return -1;

    ResourcePool *pool = cow_resource_pool(state);
    PlayerState *ps = cow_player(state, player_id);
    if (!pool || !ps) return -1;

    /* Validate indices: unique and in range, mirroring Python's
     * sorted(set(discard_hand_indices), reverse=True) checks. */
    for (int d = 0; d < discard_count; d++) {
        int idx = discard_indices[d];
        if (idx < 0 || idx >= ps->hand_count) return -1;
        for (int e = d + 1; e < discard_count; e++)
            if (discard_indices[e] == idx) return -1;
    }

    pool->power -= pa->cost_power;
    pool->influence -= pa->cost_influence;

    /* Discard in descending index order so earlier pops don't shift
     * the remaining target indices (matches Python reverse-sorted pop). */
    int sorted[MAX_ABILITY_DISCARD];
    for (int d = 0; d < discard_count; d++) sorted[d] = discard_indices[d];
    for (int d = 0; d < discard_count; d++) {
        int max_i = d;
        for (int e = d + 1; e < discard_count; e++)
            if (sorted[e] > sorted[max_i]) max_i = e;
        int tmp = sorted[d]; sorted[d] = sorted[max_i]; sorted[max_i] = tmp;
    }
    for (int d = 0; d < discard_count; d++) {
        int idx = sorted[d];
        discard_hand_card(state, player_id, idx);
    }
    return 0;
}

int discard_hand_card(GameState *state, Sym player_id, int hand_idx) {
    PlayerState *ps = cow_player(state, player_id);
    if (!ps) return -1;
    if (hand_idx < 0 || hand_idx >= ps->hand_count) return -1;

    Sym card_id = ps->hand[hand_idx];
    Sym ambassador_sym = intern("ambassador");

    if (card_id == ambassador_sym) {
        if (ps->inner_circle_count < MAX_ZONE_SIZE)
            ps->inner_circle[ps->inner_circle_count++] = card_id;
    } else {
        if (ps->discard_pile_count < MAX_ZONE_SIZE)
            ps->discard_pile[ps->discard_pile_count++] = card_id;
    }

    for (int i = hand_idx; i < ps->hand_count - 1; i++)
        ps->hand[i] = ps->hand[i + 1];
    ps->hand_count--;
    return 0;
}

int can_activate_pending_ability(const GameState *state, Sym player_id, Sym card_id, Sym ability_key) {
    if (!state->pending_ability) return 0;
    if (state->pending_ability->card_id != card_id) return 0;
    if (state->pending_ability->ability_key != ability_key) return 0;
    const CardDefinition *cd = card_by_id(state, card_id);
    if (!cd || !cd->paid_ability.present) return 0;
    int pi = player_index_for_id(state, player_id);
    if (pi < 0) return 0;
    for (int i = 0; i < state->players[pi].played_cards_count; i++) {
        if (state->players[pi].played_cards[i] == card_id)
            return ability_cost_affordable(state, player_id, card_id);
    }
    return 0;
}

int deferred_promotion_target_ids(const GameState *state, Sym player_id,
                                   const PendingPromotionState *pending, Sym *out, int max_out) {
    int count = 0;
    int pi = player_index_for_id(state, player_id);
    if (pi < 0) return 0;
    const PlayerState *ps = &state->players[pi];

    for (int i = 0; i < ps->played_cards_count && count < max_out; i++) {
        Sym candidate = ps->played_cards[i];
        if (pending->requires_another_played_card &&
            pending->source_card_id != SYM_NULL &&
            candidate == pending->source_card_id) continue;

        if (pending->required_aspect != SYM_NULL) {
            const CardDefinition *cd = card_by_id(state, candidate);
            if (!cd || cd->aspect != pending->required_aspect) continue;
        }
        if (pending->required_secondary_aspect != SYM_NULL) {
            const CardDefinition *cd = card_by_id(state, candidate);
            if (!cd) continue;
            int found = 0;
            for (int j = 0; j < cd->secondary_aspect_count; j++) {
                if (cd->secondary_aspects[j] == pending->required_secondary_aspect) { found = 1; break; }
            }
            if (!found) continue;
        }
        out[count++] = candidate;
    }
    return count;
}
