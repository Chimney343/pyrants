#include "generic_runtime.h"
#include "helpers.h"
#include "arena.h"
#include "engine.h"
#include "rng.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

static const CardDefinition *card_by_id_gr(const GameState *state, Sym card_id) {
    for (int i = 0; i < state->definition->catalog.card_count; i++)
        if (state->definition->catalog.cards[i].card_id == card_id)
            return &state->definition->catalog.cards[i];
    return NULL;
}

static Sym find_selection(int *keys, Sym *vals, int count, const char *key_name) {
    Sym key = intern(key_name);
    for (int i = 0; i < count; i++)
        if ((Sym)keys[i] == key) return vals[i];
    return SYM_NULL;
}

static int find_selection_int(int *keys, Sym *vals, int count, const char *key_name, int def) {
    Sym v = find_selection(keys, vals, count, key_name);
    if (v == SYM_NULL) return def;
    const char *s = intern_str(v);
    return s ? atoi(s) : def;
}

static Sym resolve_action_count_str(GameState *state, Sym player_id, const CardAction *action) {
    if (action->quantity_kind == QUANT_FIXED && action->quantity_value > 0) {
        char buf[16];
        snprintf(buf, sizeof(buf), "%d", action->quantity_value);
        return intern(buf);
    }
    return intern("1");
}

static int resolve_action_count(GameState *state, Sym player_id, const CardAction *action) {
    if (action->quantity_kind == QUANT_FIXED && action->quantity_value > 0)
        return action->quantity_value;
    return 1;
}

static int resolve_runtime_action_count(GameState *state, Sym player_id, const CardAction *action) {
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "count_from") == 0 && v && strcmp(v, "controlled_sites") == 0)
            return count_controlled_sites(state, player_id);
        if (k && strcmp(k, "count_from") == 0 && v && strcmp(v, "spies_on_board") == 0) {
            int count = 0;
            for (int ni = 0; ni < state->node_count; ni++)
                for (int si = 0; si < state->nodes[ni].spy_count; si++)
                    if (state->nodes[ni].spies[si] == player_id) count++;
            return count;
        }
        if (k && strcmp(k, "count_from") == 0 && v && strcmp(v, "assassinations_by_source_effect") == 0) {
            PendingGenericChoiceState *p = state->pending_generic;
            if (!p) return 0;
            int total = 0;
            for (int ci = 0; ci < p->counter_count; ci++) {
                const char *ck = intern_str(p->counter_keys[ci]);
                if (ck && strncmp(ck, "assassinate_troop:", 17) == 0)
                    total += p->counter_values[ci];
            }
            return total;
        }
    }
    const char *sf = intern_str(action->source_fragment);
    if (sf && strstr(sf, "controlled_sites")) return count_controlled_sites(state, player_id);
    return resolve_action_count(state, player_id, action);
}

static Sym pending_action_counter_key(const CardAction *action) {
    char buf[128];
    snprintf(buf, sizeof(buf), "%s:%s",
             intern_str(action->op), intern_str(action->action_id));
    return intern(buf);
}

static int pending_action_counter_value(const PendingGenericChoiceState *p, const CardAction *action) {
    Sym key = pending_action_counter_key(action);
    for (int i = 0; i < p->counter_count; i++)
        if (p->counter_keys[i] == key) return p->counter_values[i];
    return 0;
}

int action_focus_requirement_met(GameState *state, Sym player_id,
                                         const CardDefinition *card, Sym source_card_id,
                                         const CardAction *action) {
    int requires_focus = 0;
    Sym focus_aspect = SYM_NULL;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "requires_focus") == 0 && v && strcmp(v, "true") == 0)
            requires_focus = 1;
        if (k && strcmp(k, "focus_aspect") == 0 && v)
            focus_aspect = intern(v);
    }
    if (!requires_focus) return 1;
    return focus_requirement_met(state, player_id, card, source_card_id);
}

const CardAction *pending_generic_active_action(const PendingGenericChoiceState *p) {
    if (p->next_action_index < 0 || p->next_action_index >= p->current_action_count)
        return NULL;
    return &p->current_actions[p->next_action_index];
}

int action_requires_selection(const CardAction *action) {
    static const char *selection_ops[] = {
        "deploy_troops", "assassinate_troop", "supplant_troop", "place_spy",
        "return_spy", "return_unit", "move_troop", "force_discard",
        "recruit_card", "devour", "devour_cost", "play_card", NULL
    };
    const char *op = intern_str(action->op);
    if (!op) return 0;
    /* force_discard with target_scope "opponent" auto-applies to all
     * opponents at the last-selected site (Chuul's local_discard).
     * conditional_owner_discard auto-applies to the last-assassinated
     * troop's owner (Mindwitness).
     * Other source_fragments (e.g. targeted_discard) require selection. */
    if (strcmp(op, "force_discard") == 0) {
        const char *ts = intern_str(action->target_scope);
        if (ts && strcmp(ts, "opponent") == 0) {
            const char *sf = intern_str(action->source_fragment);
            if (sf && strcmp(sf, "local_discard") == 0) return 0;
            if (sf && strcmp(sf, "conditional_owner_discard") == 0) return 0;
        }
    }
    for (int i = 0; selection_ops[i]; i++)
        if (strcmp(op, selection_ops[i]) == 0) return 1;
    if (op && strcmp(op, "promote_card") == 0) {
        const char *sf = intern_str(action->source_fragment);
        if (sf && strcmp(sf, "promote_top_of_deck") == 0) return 0;
        if (sf && strcmp(sf, "threshold_self_promote") == 0) return 0;
        const char *timing = intern_str(action->timing);
        if (timing && strcmp(timing, "end_of_turn") == 0) return 0;
        return 1;
    }
    if (op && strcmp(op, "custom_effect") == 0) {
        for (int i = 0; i < action->metadata_count; i++) {
            const char *k = intern_str(action->metadata[i].key);
            const char *v = intern_str(action->metadata[i].value);
            if (k && strcmp(k, "effect_kind") == 0 && v) {
                if (strstr(v, "presence_on_last_selected") ||
                    strstr(v, "selected_player") ||
                    strstr(v, "steal_white") ||
                    strstr(v, "discard_selected_hand") ||
                    strcmp(v, "select_site") == 0)
                    return 1;
            }
        }
    }
    return 0;
}

static int action_requires_additional_choice(GameState *state, Sym player_id, const CardAction *action) {
    PendingGenericChoiceState *p = state->pending_generic;
    if (!p) return 0;
    int count = resolve_runtime_action_count(state, player_id, action);
    if (count <= 1) return 0;
    return pending_action_counter_value(p, action) < count;
}

static int resolve_card_option_actions(const PendingGenericChoiceState *pending,
                                        const CardDefinition *card, Sym option_id,
                                        const CardAction **out_actions) {
    for (int i = 0; i < card->execution.option_count; i++) {
        if (card->execution.options[i].option_id == option_id) {
            *out_actions = card->execution.options[i].actions;
            return card->execution.options[i].action_count;
        }
    }
    return 0;
}

static int pending_generic_card_definition(const GameState *state,
                                            const PendingGenericChoiceState *p,
                                            const CardDefinition **out) {
    *out = card_by_id_gr(state, p->source_card_id);
    return *out != NULL;
}

GameState *resolve_generic_execution(GameState *state, Sym player_id,
                                      const CardDefinition *card, Sym source_card_id) {
    GameState *updated = engine_clone_cow(state);
    if (!updated) return NULL;

    Arena *arena = (Arena *)updated->arena;
    PendingGenericChoiceState *pending = arena_calloc(arena, 1, sizeof(PendingGenericChoiceState));
    pending->source_card_id = source_card_id;

    int kind = card->execution.kind;
    if (kind == EXEC_SEQUENCE) {
        pending->exec_kind = EXEC_SEQUENCE;
        pending->current_actions = card->execution.actions;
        pending->current_action_count = card->execution.action_count;
        pending->next_action_index = 0;
        pending->awaiting_option = 0;
    } else if (kind == EXEC_MODAL || kind == EXEC_REPEAT) {
        pending->exec_kind = kind == EXEC_MODAL ? EXEC_MODAL : EXEC_REPEAT;
        int oc = card->execution.option_count;
        pending->option_ids = arena_alloc(arena, (size_t)oc * sizeof(Sym));
        pending->option_count = oc;
        for (int i = 0; i < oc; i++)
            pending->option_ids[i] = card->execution.options[i].option_id;
        pending->awaiting_option = 1;
        pending->remaining_repeats = (kind == EXEC_REPEAT) ? card->execution.repeat_count : 1;
        pending->allow_repeat = (kind == EXEC_REPEAT) ? card->execution.allow_repeat : 0;
    } else {
        engine_destroy(updated);
        return NULL;
    }
    updated->pending_generic = pending;
    return auto_resolve_pending_generic(updated, player_id);
}

GameState *auto_resolve_pending_generic(GameState *state, Sym player_id) {
    int local_iter = 0;
    while (state->pending_generic) {
        PendingGenericChoiceState *p = state->pending_generic;

        p->resolve_depth++;
        if (p->resolve_depth > 300) {
            state->pending_generic = NULL;
            return state;
        }

        local_iter++;
        if (local_iter > 500) {
            state->pending_generic = NULL;
            return state;
        }

        const CardDefinition *card;
        if (!pending_generic_card_definition(state, p, &card)) break;

        if (p->awaiting_option) {
            if (p->option_count == 0) {
                state->pending_generic = NULL;
                return state;
            }
            return state;
        }

        const CardAction *action = pending_generic_active_action(p);
        if (!action) {
            if (p->exec_kind == EXEC_REPEAT && p->remaining_repeats > 0) {
                p->awaiting_option = 1;
                p->current_actions = NULL;
                p->current_action_count = 0;
                p->next_action_index = 0;
                continue;
            }
            state->pending_generic = NULL;
            return state;
        }

        if (!action_focus_requirement_met(state, player_id, card, p->source_card_id, action)) {
            p->next_action_index++;
            continue;
        }

        if (action_requires_selection(action)) {
            Move sel[64];
            int nc = legal_generic_target_selection_moves(state, player_id, p, card, action, sel, 64);
            if (nc == 0) { p->next_action_index++; continue; }
            return state;
        }

        /* Intercept end-of-turn promote_card actions: register as deferred
         * EOT pending promotions instead of silently auto-applying with
         * empty selection data (which would do nothing). */
        {
            const char *op_str = intern_str(action->op);
            if (op_str && strcmp(op_str, "promote_card") == 0) {
                const char *timing_str = intern_str(action->timing);
                if (timing_str && strcmp(timing_str, "end_of_turn") == 0) {
                    if (state->pending_eot_count < MAX_PENDING_PROMO) {
                        PendingPromotionState *pp = &state->pending_eot[state->pending_eot_count];
                        memset(pp, 0, sizeof(*pp));
                        pp->source_card_id = p->source_card_id;
                        pp->timing = intern("end_of_turn");
                        pp->deferred_choice = 1;
                        pp->optional = 0;
                        for (int j = 0; j < action->metadata_count; j++) {
                            const char *mk = intern_str(action->metadata[j].key);
                            const char *mv = intern_str(action->metadata[j].value);
                            if (mk && strcmp(mk, "requires_another_played_card") == 0
                                && mv && strcmp(mv, "true") == 0)
                                pp->requires_another_played_card = 1;
                        }
                        state->pending_eot_count++;
                    }
                    p->next_action_index++;
                    continue;
                }
            }
        }

        /* Intercept conditional_owner_discard opponent-scoped force_discard:
         * the owner of the last-assassinated troop discards a random card
         * if they have 3+ cards in hand (Mindwitness). The owner is
         * captured as target_owner_id during the assassinate resolve step,
         * before the troop is removed from the board. */
        {
            const char *op_str = intern_str(action->op);
            if (op_str && strcmp(op_str, "force_discard") == 0) {
                const char *ts = intern_str(action->target_scope);
                const char *sf_str = intern_str(action->source_fragment);
                if (ts && strcmp(ts, "opponent") == 0
                    && sf_str && strcmp(sf_str, "conditional_owner_discard") == 0) {
                    Sym target_owner = SYM_NULL;
                    for (int i = 0; i < p->last_selection_count; i++) {
                        const char *k = intern_str(p->last_selection_keys[i]);
                        if (k && strcmp(k, "target_owner_id") == 0) {
                            target_owner = p->last_selection_values[i];
                            break;
                        }
                    }
                    if (target_owner != SYM_NULL && target_owner != player_id) {
                        const char *os = intern_str(target_owner);
                        if (os && strcmp(os, "white") != 0) {
                            PlayerState *ps = cow_player(state, target_owner);
                            if (ps && ps->hand_count >= 3) {
                                RNG rng;
                                rng_seed(&rng, state->shuffle_seed);
                                for (int c = 0; c < state->shuffle_counter; c++)
                                    rng_next(&rng);
                                int idx = rng_randint(&rng, 0, ps->hand_count - 1);
                                if (ps->discard_pile_count < MAX_ZONE_SIZE)
                                    ps->discard_pile[ps->discard_pile_count++] = ps->hand[idx];
                                for (int h = idx; h < ps->hand_count - 1; h++)
                                    ps->hand[h] = ps->hand[h + 1];
                                ps->hand_count--;
                                state->shuffle_counter++;
                            }
                        }
                    }
                    p->next_action_index++;
                    continue;
                }
            }
        }

        /* Intercept local_discard opponent-scoped force_discard: each
         * opponent with presence on the last-selected node and 3+ cards
         * discards a random card (Chuul's local_discard). */
        {
            const char *op_str = intern_str(action->op);
            if (op_str && strcmp(op_str, "force_discard") == 0) {
                const char *ts = intern_str(action->target_scope);
                const char *sf_str = intern_str(action->source_fragment);
                if (ts && strcmp(ts, "opponent") == 0
                    && sf_str && strcmp(sf_str, "local_discard") == 0) {
                    Sym site_id = SYM_NULL;
                    for (int i = 0; i < p->last_selection_count; i++) {
                        const char *k = intern_str(p->last_selection_keys[i]);
                        if (k && strcmp(k, "target_node_id") == 0) {
                            site_id = p->last_selection_values[i];
                            break;
                        }
                    }
                    for (int o = 0; o < state->player_count; o++) {
                        if (state->players[o].player_id == player_id) continue;
                        if (state->players[o].hand_count >= 3
                            && (site_id == SYM_NULL || has_presence(state, state->players[o].player_id, site_id))) {
                            RNG rng;
                            rng_seed(&rng, state->shuffle_seed);
                            for (int c = 0; c < state->shuffle_counter; c++)
                                rng_next(&rng);
                            int idx = rng_randint(&rng, 0, state->players[o].hand_count - 1);
                            PlayerState *ps = cow_player(state, state->players[o].player_id);
                            if (ps && idx >= 0 && idx < ps->hand_count) {
                                if (ps->discard_pile_count < MAX_ZONE_SIZE)
                                    ps->discard_pile[ps->discard_pile_count++] = ps->hand[idx];
                                for (int h = idx; h < ps->hand_count - 1; h++)
                                    ps->hand[h] = ps->hand[h + 1];
                                ps->hand_count--;
                                state->shuffle_counter++;
                            }
                        }
                    }
                    p->next_action_index++;
                    continue;
                }
            }
        }

        int ci = p->next_action_index;
        int sel_keys[8] = {0}; Sym sel_vals[8] = {0};
        GameState *prev = state;
        state = apply_generic_action(state, player_id, card, p->source_card_id, action,
                                      sel_keys, sel_vals, 0);
        if (state != prev) engine_destroy(prev);
        if (!state) break;
        p = state->pending_generic;
        if (!p) break;
        p->next_action_index = ci + 1;
    }
    return state;
}

GameState *apply_resolve_generic_choice(GameState *src, const Move *move) {
    GameState *state = engine_clone_cow(src);
    if (!state) return NULL;
    PendingGenericChoiceState *p = state->pending_generic;
    if (!p) { engine_destroy(state); return NULL; }

    Sym pid = state->current_player_id;
    const CardDefinition *card;
    if (!pending_generic_card_definition(state, p, &card)) { engine_destroy(state); return NULL; }

    /* Reject moves tagged as unavailable (generated for UI greying-out). */
    if (move->data.resolve_generic.target_id != SYM_NULL) {
        const char *tid = intern_str(move->data.resolve_generic.target_id);
        if (tid && strcmp(tid, "unavailable") == 0) {
            engine_destroy(state);
            return NULL;
        }
    }

    if (p->awaiting_option) {
        Sym option_id = move->data.resolve_generic.action_id;
        p->current_option_id = option_id;
        const CardAction *acts;
        int ac = resolve_card_option_actions(p, card, option_id, &acts);
        p->current_actions = (CardAction *)acts;
        p->current_action_count = ac;
        p->next_action_index = 0;
        p->awaiting_option = 0;
        if (p->exec_kind == EXEC_REPEAT) p->remaining_repeats--;
    } else {
        const CardAction *action = pending_generic_active_action(p);
        if (!action) { engine_destroy(state); return NULL; }
        if (!action_focus_requirement_met(state, pid, card, p->source_card_id, action)) {
            p->next_action_index++;
            return auto_resolve_pending_generic(state, pid);
        }
        if (action_requires_selection(action)) {
            /* Optional action with NULL action_id = player chose to skip. */
            if (action->optional && move->data.resolve_generic.action_id == SYM_NULL) {
                int skip_to = -1;
                for (int mi = 0; mi < action->metadata_count; mi++) {
                    const char *mk = intern_str(action->metadata[mi].key);
                    const char *mv = intern_str(action->metadata[mi].value);
                    if (mk && strcmp(mk, "skip_advance_to_index") == 0 && mv) {
                        skip_to = atoi(mv);
                        break;
                    }
                }
                if (skip_to >= 0) p->next_action_index = skip_to;
                else p->next_action_index++;
                return auto_resolve_pending_generic(state, pid);
            }
            int sk[4] = {0};
            Sym sv[4] = {0};
            int sc = 0;
            Sym aid = move->data.resolve_generic.action_id;
            Sym tid = move->data.resolve_generic.target_id;
            const char *op = intern_str(action->op);
            if (op) {
                if (strcmp(op, "deploy_troops") == 0 || strcmp(op, "place_spy") == 0) {
                    if (aid != SYM_NULL) { sk[sc] = intern("target_node_id"); sv[sc] = aid; sc++; }
                } else if (strcmp(op, "assassinate_troop") == 0 ||
                           strcmp(op, "supplant_troop") == 0) {
                    if (aid != SYM_NULL) { sk[sc] = intern("target_node_id"); sv[sc] = aid; sc++; }
                    if (tid != SYM_NULL) { sk[sc] = intern("target_slot_index"); sv[sc] = tid; sc++; }
                    if (aid != SYM_NULL && tid != SYM_NULL && sc < 4) {
                        const char *tid_str = intern_str(tid);
                        int si = tid_str ? atoi(tid_str) : 0;
                        for (int ni = 0; ni < state->node_count; ni++) {
                            if (state->nodes[ni].node_id == aid) {
                                if (si >= 0 && si < state->nodes[ni].troop_slot_count) {
                                    Sym occ = state->nodes[ni].troop_slots[si];
                                    if (occ != SYM_NULL) {
                                        sk[sc] = intern("target_owner_id"); sv[sc] = occ; sc++;
                                    }
                                }
                                break;
                            }
                        }
                    }
                } else if (strcmp(op, "return_spy") == 0) {
                    if (aid != SYM_NULL) { sk[sc] = intern("node_id"); sv[sc] = aid; sc++; }
                } else if (strcmp(op, "promote_card") == 0) {
                    if (aid != SYM_NULL) { sk[sc] = intern("target_card_id"); sv[sc] = aid; sc++; }
                } else if (strcmp(op, "recruit_card") == 0) {
                    if (aid != SYM_NULL) { sk[sc] = intern("target_card_id"); sv[sc] = aid; sc++; }
                } else if (strcmp(op, "devour") == 0 || strcmp(op, "devour_cost") == 0) {
                    if (aid != SYM_NULL) { sk[sc] = intern("target_card_id"); sv[sc] = aid; sc++; }
                } else if (strcmp(op, "force_discard") == 0) {
                    if (aid != SYM_NULL) {
                        const char *sf2 = intern_str(action->source_fragment);
                        if (sf2 && (strcmp(sf2, "targeted_discard") == 0 || strcmp(sf2, "conditional_owner_discard") == 0)) {
                            sk[sc] = intern("target_player_id"); sv[sc] = aid; sc++;
                        } else {
                            sk[sc] = intern("target_card_id"); sv[sc] = aid; sc++;
                        }
                    }
                } else if (strcmp(op, "return_unit") == 0 || strcmp(op, "move_troop") == 0) {
                    if (aid != SYM_NULL) { sk[sc] = intern("node_id"); sv[sc] = aid; sc++; }
                } else if (strcmp(op, "play_card") == 0) {
                    if (aid != SYM_NULL) { sk[sc] = intern("target_card_id"); sv[sc] = aid; sc++; }
                } else if (aid != SYM_NULL) {
                    sk[sc] = intern("target_node_id"); sv[sc] = aid; sc++;
                }
            } else if (aid != SYM_NULL) {
                sk[sc] = intern("target_node_id"); sv[sc] = aid; sc++;
            }
            GameState *prev_sel = state;
            /* Store the last selection so subsequent actions in a sequence
             * (e.g. force_discard after place_spy on Chuul) can read it. */
            p->last_selection_count = sc < 8 ? sc : 8;
            for (int si = 0; si < p->last_selection_count; si++) {
                p->last_selection_keys[si] = sk[si];
                p->last_selection_values[si] = sv[si];
            }
            state = apply_generic_action(state, pid, card, p->source_card_id, action,
                                          sk, sv, sc);
            if (state != prev_sel) engine_destroy(prev_sel);
            if (!state) return NULL;
            p = state->pending_generic;
        }
        if (p && action_requires_additional_choice(state, pid, action))
            return auto_resolve_pending_generic(state, pid);
        if (p) p->next_action_index++;
    }
    return auto_resolve_pending_generic(state, pid);
}

int legal_pending_generic_choice_moves(GameState *state, Sym player_id, Move *out, int max_out) {
    PendingGenericChoiceState *p = state->pending_generic;
    if (!p || max_out <= 0) return 0;

    if (p->awaiting_option) {
        int w = 0;
        int pi = -1;
        for (int p = 0; p < state->player_count; p++)
            if (state->players[p].player_id == player_id) { pi = p; break; }
        for (int i = 0; i < p->option_count && w < max_out; i++) {
            Sym oid = p->option_ids[i];
            /* --- Option viability checks for conditional modal choices --- */
            if (p->source_card_id != SYM_NULL && oid != SYM_NULL) {
                const char *cid = intern_str(p->source_card_id);
                const char *oid_str = intern_str(oid);
                /* Cloaker option_2: requires a site where the current player
                 * has a spy deployed AND another (player or white) troop.
                 * When not viable, mark it unavailable instead of omitting it
                 * so the UI can grey it out. */
                if (cid && strcmp(cid, "cloaker") == 0
                    && oid_str && strcmp(oid_str, "option_2") == 0 && pi >= 0) {
                    int viable = 0;
                    for (int n = 0; n < state->node_count && !viable; n++) {
                        const NodeState *ns = &state->nodes[n];
                        int has_spy = 0;
                        for (int s = 0; s < ns->spy_count; s++)
                            if (ns->spies[s] == player_id) { has_spy = 1; break; }
                        if (!has_spy) continue;
                        int has_troop = 0;
                        for (int t = 0; t < ns->troop_slot_count; t++) {
                            Sym occ = ns->troop_slots[t];
                            if (occ == SYM_NULL) continue;
                            if (occ == player_id) { has_troop = 1; break; }
                            const char *os = intern_str(occ);
                            if (os && strcmp(os, "white") == 0) { has_troop = 1; break; }
                        }
                        if (has_troop) viable = 1;
                    }
                    if (!viable) {
                        /* Still emit the move so the UI can grey it out, but
                         * tag it with target_id "unavailable" so it cannot be
                         * applied. */
                        out[w].type = MOVE_RESOLVE_GENERIC;
                        out[w].data.resolve_generic.action_id = oid;
                        out[w].data.resolve_generic.target_id = intern("unavailable");
                        out[w].player_index = 0;
                        w++;
                        continue;
                    }
                }
            }
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = oid;
            out[w].player_index = 0;
            w++;
        }
        return w;
    }

    const CardDefinition *card;
    if (!pending_generic_card_definition(state, p, &card)) return 0;
    const CardAction *action = pending_generic_active_action(p);
    if (!action) {
        if (max_out > 0) { out[0].type = MOVE_RESOLVE_GENERIC; out[0].player_index = 0; return 1; }
        return 0;
    }
    if (!action_focus_requirement_met(state, player_id, card, p->source_card_id, action)) {
        if (max_out > 0) { out[0].type = MOVE_RESOLVE_GENERIC; out[0].player_index = 0; return 1; }
        return 0;
    }
    if (!action_requires_selection(action)) {
        if (max_out > 0) { out[0].type = MOVE_RESOLVE_GENERIC; out[0].player_index = 0; return 1; }
        return 0;
    }

    int nc = legal_generic_target_selection_moves(state, player_id, p, card, action, out, max_out);

    /* Optional actions: prepend a skip (resign) move so the player can decline. */
    if (action->optional) {
        if (nc > 0 && nc < max_out) {
            for (int i = nc - 1; i >= 0; i--)
                out[i + 1] = out[i];
        }
        out[0].type = MOVE_RESOLVE_GENERIC;
        out[0].data.resolve_generic.action_id = SYM_NULL;  /* SYM_NULL = skip marker */
        out[0].data.resolve_generic.target_id = SYM_NULL;
        out[0].data.resolve_generic.selection_index = 0;
        out[0].player_index = 0;
        return (nc < max_out) ? nc + 1 : max_out;
    }

    return nc;
}
