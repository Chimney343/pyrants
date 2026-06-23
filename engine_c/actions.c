#include "generic_runtime.h"
#include "helpers.h"
#include "phases.h"
#include "moves.h"
#include "rng.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

static const CardDefinition *card_by_id_act(const GameState *state, Sym card_id) {
    for (int i = 0; i < state->definition->catalog.card_count; i++)
        if (state->definition->catalog.cards[i].card_id == card_id)
            return &state->definition->catalog.cards[i];
    return NULL;
}

static Sym find_sel(int *keys, Sym *vals, int count, const char *key) {
    Sym k = intern(key);
    for (int i = 0; i < count; i++) if ((Sym)keys[i] == k) return vals[i];
    return SYM_NULL;
}

static int find_sel_int(int *keys, Sym *vals, int count, const char *key, int def) {
    Sym v = find_sel(keys, vals, count, key);
    if (v == SYM_NULL) return def;
    const char *s = intern_str(v);
    return s ? atoi(s) : def;
}

static int resolve_count(GameState *state, Sym player_id, const CardAction *action) {
    int per = 1;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "per") == 0 && v) per = atoi(v);
    }
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "count_from") == 0 && v) {
            if (per <= 0) per = 1;
            if (strcmp(v, "total_controlled_sites") == 0)
                return count_total_controlled_sites(state, player_id) / per;
            if (strcmp(v, "controlled_sites") == 0)
                return count_controlled_sites(state, player_id) / per;
            if (strcmp(v, "owned_control_markers") == 0)
                return count_owned_control_markers(state, player_id) / per;
            if (strcmp(v, "spies_on_board") == 0) {
                int c = 0;
                for (int ni = 0; ni < state->node_count; ni++)
                    for (int si = 0; si < state->nodes[ni].spy_count; si++)
                        if (state->nodes[ni].spies[si] == player_id) c++;
                return c / per;
            }
            if (strcmp(v, "assassinations_by_source_effect") == 0) {
                PendingGenericChoiceState *p = state->pending_generic;
                if (!p) return 0;
                int total = 0;
                for (int ci = 0; ci < p->counter_count; ci++) {
                    const char *ck = intern_str(p->counter_keys[ci]);
                    if (ck && strncmp(ck, "assassinate_troop:", 17) == 0)
                        total += p->counter_values[ci];
                }
                return total / per;
            }
        }
    }
    if (action->quantity_kind == QUANT_FIXED && action->quantity_value > 0)
        return action->quantity_value;
    return 1;
}

static Sym pending_counter_key(const CardAction *action) {
    char buf[128];
    snprintf(buf, sizeof(buf), "%s:%s", intern_str(action->op), intern_str(action->action_id));
    return intern(buf);
}

static int pending_counter_val(const PendingGenericChoiceState *p, const CardAction *action) {
    Sym key = pending_counter_key(action);
    for (int i = 0; i < p->counter_count; i++)
        if (p->counter_keys[i] == key) return p->counter_values[i];
    return 0;
}

static void increment_pending_counter(PendingGenericChoiceState *p, const CardAction *action) {
    Sym key = pending_counter_key(action);
    for (int i = 0; i < p->counter_count; i++) {
        if (p->counter_keys[i] == key) { p->counter_values[i]++; return; }
    }
    if (p->counter_count < 8) {
        p->counter_keys[p->counter_count] = key;
        p->counter_values[p->counter_count] = 1;
        p->counter_count++;
    }
}

static GameState *apply_gain_resource(GameState *state, Sym player_id, const CardDefinition *card,
                                       Sym source, const CardAction *action,
                                       int *sk, Sym *sv, int sc) {
    (void)player_id; (void)card; (void)source; (void)sk; (void)sv; (void)sc;
    int count = resolve_count(state, player_id, action);
    Sym resource = SYM_NULL;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        if (k && strcmp(k, "resource") == 0)
            resource = action->metadata[i].value;
    }
    if (resource != SYM_NULL) grant_resource(state, resource, count);
    return state;
}

static GameState *apply_draw_cards(GameState *state, Sym player_id, const CardDefinition *card,
                                    Sym source, const CardAction *action,
                                    int *sk, Sym *sv, int sc) {
    (void)card; (void)source; (void)sk; (void)sv; (void)sc;
    int count = resolve_count(state, player_id, action);
    PlayerState *ps = cow_player(state, player_id);
    if (!ps) return state;
    for (int i = 0; i < count; i++) {
        if (ps->deck_count == 0 && ps->discard_pile_count > 0)
            reshuffle_discard_into_deck(state, player_id);
        if (ps->deck_count == 0) break;
        if (ps->hand_count < MAX_ZONE_SIZE)
            ps->hand[ps->hand_count++] = ps->deck[--ps->deck_count];
    }
    return state;
}

static GameState *apply_deploy_troops(GameState *state, Sym player_id, const CardDefinition *card,
                                       Sym source, const CardAction *action,
                                       int *sk, Sym *sv, int sc) {
    (void)card; (void)source;
    Sym target = find_sel(sk, sv, sc, "target_node_id");
    if (target == SYM_NULL) return state;
    if (apply_free_deploy(state, player_id, target) != 0) return state;
    if (state->pending_generic)
        increment_pending_counter(state->pending_generic, action);
    return state;
}

static GameState *apply_assassinate_troop(GameState *state, Sym player_id, const CardDefinition *card,
                                           Sym source, const CardAction *action,
                                           int *sk, Sym *sv, int sc) {
    (void)card; (void)source;
    Sym target = find_sel(sk, sv, sc, "target_node_id");
    int slot = find_sel_int(sk, sv, sc, "target_slot_index", -1);
    if (target == SYM_NULL || slot < 0) return state;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "requires_last_selected_node") == 0 && v) {
            PendingGenericChoiceState *p = state->pending_generic;
            if (!p) return state;
            Sym required = SYM_NULL;
            for (int j = 0; j < p->last_selection_count; j++) {
                const char *lsk = intern_str(p->last_selection_keys[j]);
                if (lsk && strcmp(lsk, "target_node_id") == 0) {
                    required = p->last_selection_values[j];
                    break;
                }
            }
            if (required == SYM_NULL || target != required) return state;
            break;
        }
    }
    if (apply_free_assassinate(state, player_id, target, slot) != 0) return state;
    if (state->pending_generic)
        increment_pending_counter(state->pending_generic, action);
    return state;
}

static GameState *apply_supplant_troop(GameState *state, Sym player_id, const CardDefinition *card,
                                        Sym source, const CardAction *action,
                                        int *sk, Sym *sv, int sc) {
    (void)card; (void)source;
    Sym target = find_sel(sk, sv, sc, "target_node_id");
    int slot = find_sel_int(sk, sv, sc, "target_slot_index", -1);
    if (target == SYM_NULL || slot < 0) return state;

    NodeState *ns = cow_node(state, target);
    if (!ns || slot >= ns->troop_slot_count) return state;
    Sym occ = ns->troop_slots[slot];
    if (occ == SYM_NULL || occ == player_id) return state;
    ns->troop_slots[slot] = SYM_NULL;
    PlayerState *ps = cow_player(state, player_id);
    if (ps && ps->trophy_hall_count < MAX_ZONE_SIZE)
        ps->trophy_hall[ps->trophy_hall_count++] = occ;
    if (ps && ps->barracks > 0) {
        ns->troop_slots[slot] = player_id;
        ps->barracks--;
    } else if (ps) {
        ps->score += 1;
    }
    if (state->pending_generic)
        increment_pending_counter(state->pending_generic, action);
    return state;
}

static GameState *apply_place_spy(GameState *state, Sym player_id, const CardDefinition *card,
                                   Sym source, const CardAction *action,
                                   int *sk, Sym *sv, int sc) {
    (void)card; (void)source; (void)action;
    Sym target = find_sel(sk, sv, sc, "target_node_id");
    if (target == SYM_NULL) return state;
    NodeState *ns = cow_node(state, target);
    if (!ns) return state;
    for (int i = 0; i < ns->spy_count; i++)
        if (ns->spies[i] == player_id) return state;
    PlayerState *ps = cow_player(state, player_id);
    if (!ps) return state;
    if (ps->spies_available > 0) {
        ps->spies_available--;
    } else {
        Sym src_node = find_sel(sk, sv, sc, "source_node_id");
        if (src_node == SYM_NULL || src_node == target) return state;
        NodeState *sns = cow_node(state, src_node);
        if (!sns) return state;
        int found = -1;
        for (int i = 0; i < sns->spy_count; i++)
            if (sns->spies[i] == player_id) { found = i; break; }
        if (found < 0) return state;
        for (int i = found; i < sns->spy_count - 1; i++)
            sns->spies[i] = sns->spies[i + 1];
        sns->spy_count--;
    }
    if (ns->spy_count < MAX_SPY_SLOTS)
        ns->spies[ns->spy_count++] = player_id;
    return state;
}

static GameState *apply_return_spy_gen(GameState *state, Sym player_id, const CardDefinition *card,
                                        Sym source, const CardAction *action,
                                        int *sk, Sym *sv, int sc) {
    (void)card; (void)source;
    Sym node_id = find_sel(sk, sv, sc, "node_id");
    if (node_id == SYM_NULL) return state;
    Sym spy_owner = find_sel(sk, sv, sc, "spy_owner_id");
    if (spy_owner == SYM_NULL) {
        int enemy_only = 0;
        for (int i = 0; i < action->metadata_count; i++) {
            const char *k = intern_str(action->metadata[i].key);
            const char *v = intern_str(action->metadata[i].value);
            if (k && strcmp(k, "spy_owner") == 0) {
                if (v && strcmp(v, "self") == 0) spy_owner = player_id;
                else if (v && strcmp(v, "opponent") == 0) enemy_only = 1;
            }
        }
        if (spy_owner == SYM_NULL && enemy_only) {
            NodeState *ns = cow_node(state, node_id);
            if (ns) {
                for (int si = 0; si < ns->spy_count; si++) {
                    if (ns->spies[si] != SYM_NULL && ns->spies[si] != player_id) {
                        spy_owner = ns->spies[si];
                        break;
                    }
                }
            }
        }
    }
    if (spy_owner == SYM_NULL) spy_owner = player_id;
    int free_enemy_return = 0;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "free_enemy_return") == 0 && v && strcmp(v, "true") == 0)
            free_enemy_return = 1;
    }
    apply_return_spy(state, player_id, node_id, spy_owner, free_enemy_return);
    return state;
}

static GameState *apply_return_unit(GameState *state, Sym player_id, const CardDefinition *card,
                                     Sym source, const CardAction *action,
                                     int *sk, Sym *sv, int sc) {
    (void)card; (void)source; (void)action;
    Sym unit_type = find_sel(sk, sv, sc, "unit_type");
    Sym node_id = find_sel(sk, sv, sc, "node_id");
    if (unit_type == SYM_NULL || node_id == SYM_NULL) return state;

    NodeState *ns = cow_node(state, node_id);
    if (!ns) return state;

    const char *ut = intern_str(unit_type);
    if (ut && strcmp(ut, "troop") == 0) {
        int slot = find_sel_int(sk, sv, sc, "target_slot_index", -1);
        if (slot < 0 || slot >= ns->troop_slot_count) return state;
        Sym owner = ns->troop_slots[slot];
        if (owner == SYM_NULL || owner == intern("white")) return state;
        ns->troop_slots[slot] = SYM_NULL;
        PlayerState *ps = cow_player(state, owner);
        if (ps) ps->barracks++;
    } else if (ut && strcmp(ut, "spy") == 0) {
        Sym spy_owner = find_sel(sk, sv, sc, "spy_owner_id");
        int found = -1;
        for (int i = 0; i < ns->spy_count; i++)
            if (ns->spies[i] == spy_owner) { found = i; break; }
        if (found < 0) return state;
        for (int i = found; i < ns->spy_count - 1; i++)
            ns->spies[i] = ns->spies[i + 1];
        ns->spy_count--;
        PlayerState *ps = cow_player(state, spy_owner);
        if (ps) ps->spies_available++;
    }
    return state;
}

static GameState *apply_move_troop(GameState *state, Sym player_id, const CardDefinition *card,
                                    Sym source, const CardAction *action,
                                    int *sk, Sym *sv, int sc) {
    (void)card; (void)source; (void)action;
    Sym src_node = find_sel(sk, sv, sc, "source_node_id");
    Sym dst_node = find_sel(sk, sv, sc, "target_node_id");
    int src_slot = find_sel_int(sk, sv, sc, "source_slot_index", -1);
    int dst_slot = find_sel_int(sk, sv, sc, "target_slot_index", -1);
    if (src_node == SYM_NULL || dst_node == SYM_NULL || src_slot < 0 || dst_slot < 0) return state;

    NodeState *nss = cow_node(state, src_node);
    NodeState *nsd = cow_node(state, dst_node);
    if (!nss || !nsd) return state;
    if (src_slot >= nss->troop_slot_count || dst_slot >= nsd->troop_slot_count) return state;
    Sym occ = nss->troop_slots[src_slot];
    if (occ == SYM_NULL || occ == player_id) return state;
    if (nsd->troop_slots[dst_slot] != SYM_NULL) return state;

    nss->troop_slots[src_slot] = SYM_NULL;
    nsd->troop_slots[dst_slot] = occ;
    return state;
}

static GameState *apply_force_discard(GameState *state, Sym player_id, const CardDefinition *card,
                                       Sym source, const CardAction *action,
                                       int *sk, Sym *sv, int sc) {
    (void)card; (void)source;
    Sym target = find_sel(sk, sv, sc, "target_player_id");
    int hand_idx = find_sel_int(sk, sv, sc, "hand_index", -1);
    if (target == SYM_NULL || target == player_id) return state;
    PlayerState *ps = cow_player(state, target);
    if (!ps) return state;
    /* targeted_discard: no hand_index → pick a random card (3+ card guard). */
    if (hand_idx < 0) {
        if (ps->hand_count < 3) return state;
        RNG rng;
        rng_seed(&rng, state->shuffle_seed);
        for (int c = 0; c < state->shuffle_counter; c++)
            rng_next(&rng);
        hand_idx = rng_randint(&rng, 0, ps->hand_count - 1);
        state->shuffle_counter++;
    }
    if (hand_idx < 0 || hand_idx >= ps->hand_count) return state;
    if (ps->discard_pile_count < MAX_ZONE_SIZE)
        ps->discard_pile[ps->discard_pile_count++] = ps->hand[hand_idx];
    for (int i = hand_idx; i < ps->hand_count - 1; i++)
        ps->hand[i] = ps->hand[i + 1];
    ps->hand_count--;
    return state;
}

static GameState *apply_promote_card_gen(GameState *state, Sym player_id, const CardDefinition *card,
                                          Sym source, const CardAction *action,
                                          int *sk, Sym *sv, int sc) {
    (void)card;
    const char *sf = intern_str(action->source_fragment);
    if (sf && strcmp(sf, "promote_top_of_deck") == 0) {
        PlayerState *ps = cow_player(state, player_id);
        if (!ps) return state;
        if (ps->deck_count == 0 && ps->discard_pile_count > 0)
            reshuffle_discard_into_deck(state, player_id);
        if (ps->deck_count == 0) return state;
        if (ps->inner_circle_count < MAX_ZONE_SIZE)
            ps->inner_circle[ps->inner_circle_count++] = ps->deck[--ps->deck_count];
        return state;
    }
    if (sf && strcmp(sf, "threshold_self_promote") == 0) {
        promote_card(state, player_id, source);
        return state;
    }

    Sym target_card = find_sel(sk, sv, sc, "target_card_id");
    if (target_card != SYM_NULL) {
        promote_card(state, player_id, target_card);
        return state;
    }

    Sym source_zone = find_sel(sk, sv, sc, "source_zone");
    if (source_zone != SYM_NULL) {
        const char *sz = intern_str(source_zone);
        PlayerState *ps = cow_player(state, player_id);
        if (!ps) return state;
        if (sz && strcmp(sz, "discard") == 0) {
            int idx = find_sel_int(sk, sv, sc, "discard_index", -1);
            if (idx >= 0 && idx < ps->discard_pile_count && ps->inner_circle_count < MAX_ZONE_SIZE) {
                ps->inner_circle[ps->inner_circle_count++] = ps->discard_pile[idx];
                for (int i = idx; i < ps->discard_pile_count - 1; i++)
                    ps->discard_pile[i] = ps->discard_pile[i + 1];
                ps->discard_pile_count--;
            }
        } else if (sz && strcmp(sz, "hand") == 0) {
            int idx = find_sel_int(sk, sv, sc, "hand_index", -1);
            if (idx >= 0 && idx < ps->hand_count && ps->inner_circle_count < MAX_ZONE_SIZE) {
                ps->inner_circle[ps->inner_circle_count++] = ps->hand[idx];
                for (int i = idx; i < ps->hand_count - 1; i++)
                    ps->hand[i] = ps->hand[i + 1];
                ps->hand_count--;
            }
        } else if (sz && strcmp(sz, "played") == 0) {
            Sym tcid = find_sel(sk, sv, sc, "target_card_id");
            if (tcid != SYM_NULL) promote_card(state, player_id, tcid);
        }
    }
    return state;
}

static GameState *apply_recruit_card_gen(GameState *state, Sym player_id, const CardDefinition *card,
                                          Sym source, const CardAction *action,
                                          int *sk, Sym *sv, int sc) {
    (void)card; (void)source;
    int slot = find_sel_int(sk, sv, sc, "market_slot", -1);
    if (slot >= 0) apply_recruit(state, player_id, slot);
    return state;
}

static GameState *apply_grant_vp(GameState *state, Sym player_id, const CardDefinition *card,
                                  Sym source, const CardAction *action,
                                  int *sk, Sym *sv, int sc) {
    (void)card; (void)source; (void)sk; (void)sv; (void)sc;
    int count = resolve_count(state, player_id, action);
    PlayerState *ps = cow_player(state, player_id);
    if (!ps) return state;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "as") == 0 && v && strcmp(v, "vp_tokens") == 0) {
            ps->vp_tokens += count;
            return state;
        }
    }
    ps->score += count;
    return state;
}

static GameState *apply_devour(GameState *state, Sym player_id, const CardDefinition *card,
                                Sym source, const CardAction *action,
                                int *sk, Sym *sv, int sc) {
    (void)card;
    Sym zone = find_sel(sk, sv, sc, "source_zone");
    if (zone == SYM_NULL) {
        for (int i = 0; i < action->metadata_count; i++) {
            const char *k = intern_str(action->metadata[i].key);
            if (k && strcmp(k, "source_zone") == 0) zone = action->metadata[i].value;
        }
    }
    const char *z = intern_str(zone);
    PlayerState *ps = cow_player(state, player_id);
    if (!ps || !z) return state;

    /* Check self_replace metadata (Carrion Crawler). */
    int self_replace = 0;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "self_replace") == 0 && v && strcmp(v, "true") == 0) {
            self_replace = 1;
            break;
        }
    }

    if (strcmp(z, "hand") == 0) {
        int idx = find_sel_int(sk, sv, sc, "hand_index", 0);
        if (idx < ps->hand_count && state->devour_pile_count < MAX_ZONE_SIZE) {
            state->devour_pile[state->devour_pile_count++] = ps->hand[idx];
            for (int i = idx; i < ps->hand_count - 1; i++) ps->hand[i] = ps->hand[i + 1];
            ps->hand_count--;
        }
    } else if (strcmp(z, "played_self") == 0) {
        for (int i = 0; i < ps->played_cards_count; i++) {
            if (ps->played_cards[i] == source) {
                state->devour_pile[state->devour_pile_count++] = source;
                for (int j = i; j < ps->played_cards_count - 1; j++)
                    ps->played_cards[j] = ps->played_cards[j + 1];
                ps->played_cards_count--;
                break;
            }
        }
    } else if (strcmp(z, "market") == 0) {
        Sym target_card_id = find_sel(sk, sv, sc, "target_card_id");
        if (target_card_id == SYM_NULL) return state;
        for (int i = 0; i < state->market.row_count; i++) {
            if (state->market.row[i] == target_card_id) {
                if (state->devour_pile_count < MAX_ZONE_SIZE)
                    state->devour_pile[state->devour_pile_count++] = target_card_id;
                MarketState *ms = cow_market(state);
                if (ms) {
                    if (self_replace && ms->row_count < MAX_ZONE_SIZE) {
                        ms->row[i] = source;
                    } else if (ms->deck_count > 0) {
                        ms->row[i] = ms->deck[--ms->deck_count];
                    } else {
                        for (int j = i; j < ms->row_count - 1; j++)
                            ms->row[j] = ms->row[j + 1];
                        ms->row_count--;
                    }
                }
                break;
            }
        }
    } else if (strcmp(z, "inner_circle") == 0) {
        Sym target_card_id = find_sel(sk, sv, sc, "target_card_id");
        if (target_card_id == SYM_NULL) return state;
        for (int i = 0; i < ps->inner_circle_count; i++) {
            if (ps->inner_circle[i] == target_card_id) {
                if (state->devour_pile_count < MAX_ZONE_SIZE)
                    state->devour_pile[state->devour_pile_count++] = target_card_id;
                for (int j = i; j < ps->inner_circle_count - 1; j++)
                    ps->inner_circle[j] = ps->inner_circle[j + 1];
                ps->inner_circle_count--;
                break;
            }
        }
    }
    return state;
}

static GameState *apply_play_card_nested(GameState *state, Sym player_id, const CardDefinition *card,
                                          Sym source, const CardAction *action,
                                          int *sk, Sym *sv, int sc) {
    (void)card;
    const char *sf = intern_str(action->source_fragment);
    if (!sf) return state;

    Sym nested_id = SYM_NULL;
    if (strcmp(sf, "play_from_inner_circle_without_removal") == 0) {
        int idx = find_sel_int(sk, sv, sc, "inner_circle_index", -1);
        PlayerState *ps = cow_player(state, player_id);
        if (!ps || idx < 0 || idx >= ps->inner_circle_count) return state;
        nested_id = ps->inner_circle[idx];
    } else if (strcmp(sf, "play") == 0) {
        nested_id = find_sel(sk, sv, sc, "target_card_id");
        if (nested_id == SYM_NULL) return state;
    } else {
        return state;
    }

    const CardDefinition *nested_cd = card_by_id_act(state, nested_id);
    if (!nested_cd) return state;

    EffectFn effect = lookup_effect(nested_cd->effect_key);
    if (!effect) return state;

    if (state->pending_generic) state->pending_generic->last_played_card_id = nested_id;
    return effect(state, player_id, nested_cd);
}

static void give_insane_outcast(GameState *state, Sym player_id, Sym target_id, const CardAction *action) {
    int count = resolve_count(state, player_id, action);
    PlayerState *ps = cow_player(state, target_id);
    if (ps) {
        for (int c = 0; c < count && ps->discard_pile_count < MAX_ZONE_SIZE; c++)
            ps->discard_pile[ps->discard_pile_count++] = intern("insane_outcast");
    }
}

static GameState *apply_custom_effect(GameState *state, Sym player_id, const CardDefinition *card,
                                       Sym source, const CardAction *action,
                                       int *sk, Sym *sv, int sc) {
    Sym kind = SYM_NULL;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        if (k && strcmp(k, "effect_kind") == 0) { kind = action->metadata[i].value; break; }
    }
    const char *ek = intern_str(kind);
    if (!ek) return state;

    if (strcmp(ek, "give_insane_outcast_to_each_opponent") == 0) {
        for (int p = 0; p < state->player_count; p++) {
            if (state->players[p].player_id == player_id) continue;
            give_insane_outcast(state, player_id, state->players[p].player_id, action);
        }
    } else if (strcmp(ek, "give_insane_outcast_to_self") == 0) {
        give_insane_outcast(state, player_id, player_id, action);
    } else if (strcmp(ek, "give_insane_outcast_to_selected_player") == 0 ||
               strcmp(ek, "give_insane_outcast_to_player_with_presence_on_last_selected_node") == 0) {
        Sym target = find_sel(sk, sv, sc, "target_node_id");
        if (target == SYM_NULL || target == player_id) return state;
        give_insane_outcast(state, player_id, target, action);
    } else if (strcmp(ek, "mill_deck_to_discard") == 0) {
        PlayerState *ps = cow_player(state, player_id);
        if (ps) {
            for (int i = 0; i < ps->deck_count && ps->discard_pile_count < MAX_ZONE_SIZE; i++)
                ps->discard_pile[ps->discard_pile_count++] = ps->deck[i];
            ps->deck_count = 0;
        }
    } else if (strcmp(ek, "select_trophy_hall") == 0) {
        return state;
    } else if (strcmp(ek, "steal_from_selected_trophy") == 0) {
        Sym source_player = find_sel(sk, sv, sc, "source_player_id");
        Sym trophy_idx_sym = find_sel(sk, sv, sc, "selected_trophy_index");
        Sym target_node = find_sel(sk, sv, sc, "target_node_id");
        int target_slot = find_sel_int(sk, sv, sc, "target_slot_index", -1);
        if (source_player == SYM_NULL || trophy_idx_sym == SYM_NULL
            || target_node == SYM_NULL || target_slot < 0) return state;
        const char *idx_str = intern_str(trophy_idx_sym);
        int trophy_idx = idx_str ? atoi(idx_str) : -1;
        int spi = -1;
        for (int p = 0; p < state->player_count; p++)
            if (state->players[p].player_id == source_player) { spi = p; break; }
        if (spi < 0 || trophy_idx < 0) return state;
        PlayerState *sp = cow_player(state, source_player);
        if (!sp || trophy_idx >= sp->trophy_hall_count) return state;
        Sym trophy_owner = sp->trophy_hall[trophy_idx];
        for (int t = trophy_idx; t < sp->trophy_hall_count - 1; t++)
            sp->trophy_hall[t] = sp->trophy_hall[t + 1];
        sp->trophy_hall_count--;
        NodeState *ns = cow_node(state, target_node);
        if (!ns || target_slot < 0 || target_slot >= ns->troop_slot_count) return state;
        if (ns->troop_slots[target_slot] != SYM_NULL) return state;
        ns->troop_slots[target_slot] = trophy_owner;
    } else if (strcmp(ek, "scaled_resource_from_player_zone") == 0) {
        Sym zone = SYM_NULL, resource_sym = SYM_NULL;
        int per = 1;
        for (int i = 0; i < action->metadata_count; i++) {
            const char *k = intern_str(action->metadata[i].key);
            const char *v = intern_str(action->metadata[i].value);
            if (k && strcmp(k, "source_zone") == 0 && v) zone = intern(v);
            if (k && strcmp(k, "resource") == 0 && v) resource_sym = intern(v);
            if (k && strcmp(k, "per") == 0 && v) per = atoi(v);
        }
        if (zone == SYM_NULL || resource_sym == SYM_NULL) return state;
        if (per <= 0) per = 1;
        int pi = -1;
        for (int i = 0; i < state->player_count; i++)
            if (state->players[i].player_id == player_id) { pi = i; break; }
        if (pi < 0) return state;
        int count = 0;
        const char *zs = intern_str(zone);
        if (zs && strcmp(zs, "trophy_hall") == 0)
            count = state->players[pi].trophy_hall_count;
        int amount = count / per;
        if (amount > 0) grant_resource(state, resource_sym, amount);
    }
    return state;
}

static GameState *apply_conditional_bonus(GameState *state, Sym player_id, const CardDefinition *card,
                                           Sym source, const CardAction *action,
                                           int *sk, Sym *sv, int sc) {
    Sym cond = SYM_NULL, resource = SYM_NULL;
    int amount = 0;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "condition") == 0 && v) cond = intern(v);
        if (k && strcmp(k, "resource") == 0 && v) resource = intern(v);
        if (k && strcmp(k, "amount") == 0 && v) amount = atoi(v);
    }
    if (cond == SYM_NULL) return state;
    if (amount <= 0) amount = 1;

    const char *cs = intern_str(cond);
    if (cs && strcmp(cs, "focus_aspect_present") == 0) {
        if (focus_requirement_met(state, player_id, card, source))
            grant_resource(state, resource != SYM_NULL ? resource : intern("influence"), amount);
    } else if (cs && strcmp(cs, "selected_node_has_other_player_troop") == 0) {
        PendingGenericChoiceState *p = state->pending_generic;
        if (p) {
            Sym node_id = SYM_NULL;
            for (int j = 0; j < p->last_selection_count; j++) {
                const char *lsk = intern_str(p->last_selection_keys[j]);
                if (lsk && strcmp(lsk, "target_node_id") == 0) {
                    node_id = p->last_selection_values[j];
                    break;
                }
            }
            if (node_id != SYM_NULL) {
                NodeState *ns = cow_node(state, node_id);
                if (ns) {
                    int has_other = 0;
                    for (int i = 0; i < ns->troop_slot_count; i++) {
                        if (ns->troop_slots[i] != SYM_NULL && ns->troop_slots[i] != player_id) {
                            has_other = 1;
                            break;
                        }
                    }
                    if (has_other)
                        grant_resource(state, resource != SYM_NULL ? resource : intern("influence"), amount);
                }
            }
        }
    }
    return state;
}

typedef GameState* (*ActionFn)(GameState*, Sym, const CardDefinition*, Sym, const CardAction*,
                                int*, Sym*, int);

static ActionFn action_dispatch[32];
static Sym action_op_keys[32];
static int action_dispatch_count = 0;

static void register_action(Sym op, ActionFn fn) {
    if (action_dispatch_count < 32) {
        action_op_keys[action_dispatch_count] = op;
        action_dispatch[action_dispatch_count] = fn;
        action_dispatch_count++;
    }
}

GameState *apply_generic_action(GameState *state, Sym player_id, const CardDefinition *card,
                                 Sym source_card_id, const CardAction *action,
                                 int *sel_keys, Sym *sel_vals, int sel_count) {
    if (!action_focus_requirement_met(state, player_id, card, source_card_id, action))
        return state;

    for (int i = 0; i < action_dispatch_count; i++) {
        if (action_op_keys[i] == action->op && action_dispatch[i])
            return action_dispatch[i](state, player_id, card, source_card_id, action,
                                       sel_keys, sel_vals, sel_count);
    }
    return state;
}

void register_generic_actions(void) {
    register_action(intern("gain_resource"), apply_gain_resource);
    register_action(intern("draw_cards"), apply_draw_cards);
    register_action(intern("deploy_troops"), apply_deploy_troops);
    register_action(intern("assassinate_troop"), apply_assassinate_troop);
    register_action(intern("supplant_troop"), apply_supplant_troop);
    register_action(intern("place_spy"), apply_place_spy);
    register_action(intern("return_spy"), apply_return_spy_gen);
    register_action(intern("return_unit"), apply_return_unit);
    register_action(intern("move_troop"), apply_move_troop);
    register_action(intern("force_discard"), apply_force_discard);
    register_action(intern("promote_card"), apply_promote_card_gen);
    register_action(intern("recruit_card"), apply_recruit_card_gen);
    register_action(intern("devour"), apply_devour);
    register_action(intern("devour_cost"), apply_devour);
    register_action(intern("grant_vp"), apply_grant_vp);
    register_action(intern("conditional_bonus"), apply_conditional_bonus);
    register_action(intern("custom_effect"), apply_custom_effect);
    register_action(intern("play_card"), apply_play_card_nested);
}
