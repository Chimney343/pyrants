#include "rules.h"
#include "helpers.h"
#include "phases.h"
#include "scoring.h"
#include "arena.h"
#include "engine.h"
#include "generic_runtime.h"
#include <string.h>
#include <stdlib.h>
#include <assert.h>

static int player_index_for_id_state(const GameState *state, Sym player_id) {
    for (int i = 0; i < state->player_count; i++)
        if (state->players[i].player_id == player_id) return i;
    return -1;
}

static const CardDefinition *card_by_id_state(const GameState *state, Sym card_id) {
    for (int i = 0; i < state->definition->catalog.card_count; i++)
        if (state->definition->catalog.cards[i].card_id == card_id)
            return &state->definition->catalog.cards[i];
    return NULL;
}

static int node_index_for_id(const GameState *state, Sym node_id) {
    for (int i = 0; i < state->node_count; i++)
        if (state->nodes[i].node_id == node_id) return i;
    return -1;
}

static GameState *apply_effect_with_wrappers(GameState *state, Sym player_id,
                                              const CardDefinition *card, Sym source_card_id) {
    int focus_needed = 0;
    for (int i = 0; i < card->effect_payload_count; i++) {
        const char *k = intern_str(card->effect_payload[i].key);
        const char *v = intern_str(card->effect_payload[i].value);
        if (k && strcmp(k, "focus_required") == 0 && v && strcmp(v, "true") == 0)
            focus_needed = 1;
    }
    if (focus_needed && !focus_requirement_met(state, player_id, card, source_card_id))
        return state;

    EffectFn effect = lookup_effect(card->effect_key);
    if (!effect) return state;

    GameState *result = effect(state, player_id, card);
    if (!result) return state;
    if (result != state) engine_destroy(state);

    if (result->pending_generic) return result;

    Sym promote_timing = SYM_NULL;
    int promote_optional = 0;
    for (int i = 0; i < card->effect_payload_count; i++) {
        const char *k = intern_str(card->effect_payload[i].key);
        if (k && strcmp(k, "promote") == 0) {
            promote_timing = intern("immediate");
            break;
        }
    }
    if (promote_timing != SYM_NULL) {
        apply_promote_instruction(result, player_id, source_card_id, promote_timing, promote_optional);
    }
    return result;
}

static int legal_optional_promotion_moves(const PendingPromotionState *pending,
                                           Sym player_id, Move *out, int max_out) {
    if (max_out < 2) return 0;
    out[0].type = MOVE_PROMOTE_CARD;
    out[0].data.promote_card.card_id = pending->card_id;
    out[0].player_index = 0;
    out[1].type = MOVE_SKIP_PROMOTE;
    out[1].player_index = 0;
    return 2;
}

static int legal_deferred_eot_promotion_moves(const GameState *state, Sym player_id,
                                               const PendingPromotionState *pending,
                                               Move *out, int max_out) {
    Sym targets[MAX_ZONE_SIZE];
    int tc = deferred_promotion_target_ids(state, player_id, pending, targets, MAX_ZONE_SIZE);
    int written = 0;
    for (int i = 0; i < tc && written < max_out; i++) {
        out[written].type = MOVE_PROMOTE_CARD;
        out[written].data.promote_card.card_id = targets[i];
        out[written].player_index = 0;
        written++;
    }
    if (pending->optional && written < max_out) {
        out[written].type = MOVE_SKIP_PROMOTE;
        out[written].player_index = 0;
        written++;
    } else if (tc == 0 && written < max_out) {
        out[written].type = MOVE_SKIP_PROMOTE;
        out[written].player_index = 0;
        written++;
    }
    return written;
}

static int legal_pending_ability_moves(const GameState *state, Sym player_id,
                                        Move *out, int max_out) {
    if (!state->pending_ability) return 0;
    int w = 0;
    if (w < max_out) {
        out[w].type = MOVE_DECLINE_ABILITY;
        out[w].data.decline_ability.card_id = state->pending_ability->card_id;
        out[w].data.decline_ability.ability_key = state->pending_ability->ability_key;
        out[w].player_index = 0;
        w++;
    }
    if (can_activate_pending_ability(state, player_id,
            state->pending_ability->card_id, state->pending_ability->ability_key)) {
        if (w < max_out) {
            out[w].type = MOVE_ACTIVATE_ABILITY;
            out[w].data.activate_ability.card_id = state->pending_ability->card_id;
            out[w].data.activate_ability.ability_key = state->pending_ability->ability_key;
            out[w].data.activate_ability.discard_hand_count = 0;
            out[w].player_index = 0;
            w++;
        }
    }
    return w;
}

static int legal_main_phase_actions(const GameState *state, Sym player_id,
                                     Move *out, int max_out) {
    int w = 0;
    if (state->resource_pool.power >= 1) {
        int ht = player_has_any_troops_on_board(state, player_id);
        for (int i = 0; i < state->node_count && w < max_out; i++) {
            Sym nid = state->nodes[i].node_id;
            if (can_deploy_to_node(state, player_id, nid, ht)) {
                out[w].type = MOVE_DEPLOY;
                out[w].data.deploy.node_id = nid;
                out[w].data.deploy.slot_index = 0;
                w++;
            }
        }
    }
    if (state->resource_pool.power >= 3) {
        for (int i = 0; i < state->node_count && w < max_out; i++) {
            Sym nid = state->nodes[i].node_id;
            if (!has_presence(state, player_id, nid)) continue;
            for (int s = 0; s < state->nodes[i].troop_slot_count && w < max_out; s++) {
                Sym occ = state->nodes[i].troop_slots[s];
                if (occ == SYM_NULL || occ == player_id) continue;
                out[w].type = MOVE_ASSASSINATE;
                out[w].data.assassinate.target_node_id = nid;
                out[w].data.assassinate.troop_owner_id = occ;
                out[w].data.assassinate.slot_index = s;
                w++;
            }
            for (int s = 0; s < state->nodes[i].spy_count && w < max_out; s++) {
                Sym spy = state->nodes[i].spies[s];
                if (spy == player_id) continue;
                out[w].type = MOVE_RETURN_SPY;
                out[w].data.return_spy.node_id = nid;
                out[w].data.return_spy.spy_owner_id = spy;
                w++;
            }
        }
    }
    for (int slot = 0; slot < state->market.row_count && w < max_out; slot++) {
        Sym cid = state->market.row[slot];
        const CardDefinition *cd = card_by_id_state(state, cid);
        if (cd && state->resource_pool.influence >= cd->cost) {
            out[w].type = MOVE_RECRUIT;
            out[w].data.recruit.card_id = cid;
            w++;
        }
    }
    int special_slots[] = {100, 101, 102};
    for (int si = 0; si < 3 && w < max_out; si++) {
        int slot = special_slots[si];
        Sym cid;
        int st;
        if (!special_stack_config(slot, &cid, &st)) continue;
        if (slot == 102 && !is_aberrations_enabled(state)) continue;
        if (remaining_special_stack_count(state, cid, st) <= 0) continue;
        const CardDefinition *cd = card_by_id_state(state, cid);
        if (!cd || state->resource_pool.influence < cd->cost) continue;
        out[w].type = MOVE_RECRUIT;
        out[w].data.recruit.card_id = cid;
        w++;
    }
    return w;
}

int engine_legal_moves(const GameState *state, Move *out, int max_moves) {
    if (state->phase == PHASE_GAME_OVER || max_moves <= 0) return 0;

    Sym player_id = state->current_player_id;

    if (state->phase == PHASE_SETUP) {
        int found = 0;
        for (int i = 0; i < state->setup_complete_count; i++)
            if (state->setup_complete[i] == player_id) { found = 1; break; }
        if (found) return 0;
        Sym nodes[MAX_NODES];
        int nc = legal_initial_placement_node_ids(state, nodes, MAX_NODES);
        int w = 0;
        for (int i = 0; i < nc && w < max_moves; i++) {
            out[w].type = MOVE_INITIAL_PLACEMENT;
            out[w].data.initial_placement.node_id = nodes[i];
            out[w].player_index = 0;
            w++;
        }
        return w;
    }

    if (state->phase == PHASE_DRAW) return 0;

    if (state->phase == PHASE_MAIN) {
        if (state->pending_immediate_count > 0) {
            return legal_optional_promotion_moves(
                &state->pending_immediate[0], player_id, out, max_moves);
        }
        if (state->pending_generic)
            return legal_pending_generic_choice_moves((GameState *)state, player_id, out, max_moves);

        int w = legal_pending_ability_moves(state, player_id, out, max_moves);
        if (state->pending_ability == NULL) {
            int pi = player_index_for_id_state(state, player_id);
            if (pi >= 0) {
                for (int i = 0; i < state->players[pi].hand_count && w < max_moves; i++) {
                    out[w].type = MOVE_PLAY_CARD;
                    out[w].data.play_card.card_id = state->players[pi].hand[i];
                    out[w].data.play_card.hand_index = i;
                    out[w].player_index = 0;
                    w++;
                }
            }
        }
        w += legal_main_phase_actions(state, player_id, out + w, max_moves - w);
        if (w < max_moves) {
            out[w].type = MOVE_END_MAIN_PHASE;
            out[w].player_index = 0;
            w++;
        }
        return w;
    }

    if (state->phase == PHASE_END_OF_TURN) {
        if (state->pending_eot_count > 0) {
            const PendingPromotionState *p = &state->pending_eot[0];
            if (p->deferred_choice)
                return legal_deferred_eot_promotion_moves(state, player_id, p, out, max_moves);
            if (p->optional)
                return legal_optional_promotion_moves(p, player_id, out, max_moves);
        }
        if (max_moves > 0) {
            out[0].type = MOVE_RESOLVE_END_OF_TURN;
            out[0].player_index = 0;
            return 1;
        }
        return 0;
    }

    if (state->phase == PHASE_CLEANUP) {
        if (max_moves > 0) {
            out[0].type = MOVE_RESOLVE_CLEANUP;
            out[0].player_index = 0;
            return 1;
        }
        return 0;
    }
    return 0;
}

static GameState *apply_play_card(GameState *state, Sym card_id, int hand_index, Sym player_id) {
    int pi = player_index_for_id_state(state, player_id);
    if (pi < 0) return NULL;
    PlayerState *ps = cow_player(state, player_id);
    if (!ps) return NULL;

    if (hand_index >= ps->hand_count) return NULL;
    Sym played = ps->hand[hand_index];
    if (played != card_id) return NULL;

    for (int i = hand_index; i < ps->hand_count - 1; i++)
        ps->hand[i] = ps->hand[i + 1];
    ps->hand_count--;

    if (ps->played_cards_count < MAX_ZONE_SIZE)
        ps->played_cards[ps->played_cards_count++] = played;

    const CardDefinition *cd = card_by_id_state(state, played);
    if (!cd) return NULL;

    GameState *result = apply_effect_with_wrappers(state, player_id, cd, played);
    if (!result) return NULL;

    if (cd->paid_ability.present) {
        if (cd->paid_ability.ability_key == SYM_NULL) return NULL;
        int still_played = 0;
        int rpi = player_index_for_id_state(result, player_id);
        if (rpi >= 0) {
            for (int i = 0; i < result->players[rpi].played_cards_count; i++)
                if (result->players[rpi].played_cards[i] == played) { still_played = 1; break; }
        }
        if (!still_played) return NULL;
        Arena *arena = (Arena *)result->arena;
        result->pending_ability = arena_calloc(arena, 1, sizeof(PendingAbilityState));
        result->pending_ability->card_id = played;
        result->pending_ability->ability_key = cd->paid_ability.ability_key;
        result->pending_ability->resolved = 0;
    }
    return result;
}

static GameState *apply_assassinate(GameState *state, Sym player_id, Sym target_node_id, int slot_index) {
    if (state->resource_pool.power < 3) return NULL;
    if (!has_presence(state, player_id, target_node_id)) return NULL;

    NodeState *ns = cow_node(state, target_node_id);
    if (!ns || slot_index >= ns->troop_slot_count) return NULL;
    Sym occ = ns->troop_slots[slot_index];
    if (occ == SYM_NULL || occ == player_id) return NULL;

    cow_resource_pool(state)->power -= 3;
    ns->troop_slots[slot_index] = SYM_NULL;
    PlayerState *ps = cow_player(state, player_id);
    if (ps && ps->trophy_hall_count < MAX_ZONE_SIZE)
        ps->trophy_hall[ps->trophy_hall_count++] = occ;
    return state;
}

static GameState *apply_deploy(GameState *state, Sym player_id, Sym target_node_id) {
    if (state->resource_pool.power < 1) return NULL;
    int ht = player_has_any_troops_on_board(state, player_id);
    if (!can_deploy_to_node(state, player_id, target_node_id, ht)) return NULL;

    cow_resource_pool(state)->power -= 1;
    PlayerState *ps = cow_player(state, player_id);
    if (!ps) return NULL;
    if (ps->barracks == 0) { ps->score += 1; return state; }

    NodeState *ns = cow_node(state, target_node_id);
    if (!ns) return NULL;
    for (int i = 0; i < ns->troop_slot_count; i++) {
        if (ns->troop_slots[i] == SYM_NULL) {
            ns->troop_slots[i] = player_id;
            ps->barracks--;
            return state;
        }
    }
    return NULL;
}

static GameState *apply_initial_placement(GameState *state, Sym player_id, Sym target_node_id) {
    for (int i = 0; i < state->setup_complete_count; i++)
        if (state->setup_complete[i] == player_id) return NULL;

    int ni = node_index_for_id(state, target_node_id);
    if (ni < 0) return NULL;
    NodeState *ns = cow_node(state, target_node_id);
    if (!ns) return NULL;
    int empty = -1;
    for (int i = 0; i < ns->troop_slot_count; i++) {
        if (ns->troop_slots[i] == SYM_NULL) { empty = i; break; }
    }
    if (empty < 0) return NULL;

    PlayerState *ps = cow_player(state, player_id);
    if (!ps || ps->barracks <= 0) return NULL;

    ns->troop_slots[empty] = player_id;
    ps->barracks--;
    if (state->setup_complete_count < MAX_PLAYERS)
        state->setup_complete[state->setup_complete_count++] = player_id;

    advance_phase(state);
    return state;
}

static GameState *apply_activate_card_ability(GameState *state, Sym player_id, const Move *move) {
    Sym card_id = move->data.activate_ability.card_id;
    Sym ability_key = move->data.activate_ability.ability_key;
    if (!state->pending_ability) return NULL;
    if (state->pending_ability->card_id != card_id) return NULL;
    if (state->pending_ability->ability_key != ability_key) return NULL;

    int pi = player_index_for_id_state(state, player_id);
    if (pi < 0) return NULL;
    int found = 0;
    for (int i = 0; i < state->players[pi].played_cards_count; i++)
        if (state->players[pi].played_cards[i] == card_id) { found = 1; break; }
    if (!found) return NULL;

    const CardDefinition *cd = card_by_id_state(state, card_id);
    if (!cd || !cd->paid_ability.present) return NULL;
    if (cd->paid_ability.ability_key != ability_key) return NULL;

    int discard_count = move->data.activate_ability.discard_hand_count;
    int *discard_indices = (discard_count > 0) ? move->data.activate_ability.discard_hand_indices : NULL;
    if (pay_ability_cost(state, player_id, card_id, discard_indices, discard_count) != 0)
        return NULL;

    state->pending_ability = NULL;

    /* D12: build a transient CardDefinition override carrying the paid-ability's
     * effect_key/effect_payload, mirroring Python's definition.model_copy(update=...).
     * Stack-allocated; only used for the duration of the effect call. */
    CardDefinition override = *cd;
    override.effect_key = cd->paid_ability.effect_key;
    override.effect_payload = cd->paid_ability.effect_payload;
    override.effect_payload_count = cd->paid_ability.effect_payload_count;
    memset(&override.paid_ability, 0, sizeof(PaidAbility));

    return apply_effect_with_wrappers(state, player_id, &override, card_id);
}

static GameState *apply_decline_card_ability(GameState *state, Sym player_id, Sym card_id, Sym ability_key) {
    if (!state->pending_ability) return NULL;
    if (state->pending_ability->card_id != card_id) return NULL;
    if (state->pending_ability->ability_key != ability_key) return NULL;
    state->pending_ability = NULL;
    return state;
}

static GameState *apply_promote_card_impl(GameState *state, Sym player_id, Sym card_id) {
    if (state->pending_immediate_count > 0) {
        const PendingPromotionState *p = &state->pending_immediate[0];
        if (p->card_id != card_id) return NULL;
        promote_card(state, player_id, card_id);
        for (int i = 0; i < state->pending_immediate_count - 1; i++)
            state->pending_immediate[i] = state->pending_immediate[i + 1];
        state->pending_immediate_count--;
        return state;
    }
    if (state->pending_eot_count > 0) {
        PendingPromotionState *p = &state->pending_eot[0];
        if (p->deferred_choice) {
            Sym targets[MAX_ZONE_SIZE];
            int tc = deferred_promotion_target_ids(state, player_id, p, targets, MAX_ZONE_SIZE);
            int found = 0;
            for (int i = 0; i < tc; i++) if (targets[i] == card_id) { found = 1; break; }
            if (!found) return NULL;
            promote_card(state, player_id, card_id);
            if (p->promotions_remaining > 0)
                p->promotions_remaining--;
            if (!p->repeat_while_targets || p->promotions_remaining <= 0) {
                for (int i = 0; i < state->pending_eot_count - 1; i++)
                    state->pending_eot[i] = state->pending_eot[i + 1];
                state->pending_eot_count--;
            }
            return state;
        }
        if (p->card_id != card_id || !p->optional) return NULL;
        promote_card(state, player_id, card_id);
        for (int i = 0; i < state->pending_eot_count - 1; i++)
            state->pending_eot[i] = state->pending_eot[i + 1];
        state->pending_eot_count--;
        return state;
    }
    return NULL;
}

static GameState *apply_skip_promote_impl(GameState *state) {
    if (state->pending_immediate_count > 0) {
        for (int i = 0; i < state->pending_immediate_count - 1; i++)
            state->pending_immediate[i] = state->pending_immediate[i + 1];
        state->pending_immediate_count--;
        return state;
    }
    if (state->pending_eot_count > 0) {
        for (int i = 0; i < state->pending_eot_count - 1; i++)
            state->pending_eot[i] = state->pending_eot[i + 1];
        state->pending_eot_count--;
        return state;
    }
    return NULL;
}

static void apply_end_of_turn_effects(GameState *state, int include_force_discard, int include_scaled_vp) {
    Sym pid = state->current_player_id;
    Sym generic_key = intern("generic_card");

    int pi = player_index_for_id_state(state, pid);
    if (pi < 0) return;
    PlayerState *ps = &state->players[pi];

    for (int ci = 0; ci < ps->played_cards_count; ci++) {
        const CardDefinition *cd = card_by_id_state(state, ps->played_cards[ci]);
        if (!cd || cd->effect_key != generic_key) continue;

        for (int ai = 0; ai < cd->action_count; ai++) {
            const CardAction *action = &cd->actions[ai];
            const char *timing = intern_str(action->timing);
            if (!timing || strcmp(timing, "end_of_turn") != 0) continue;

            const char *op = intern_str(action->op);
            const char *sf = intern_str(action->source_fragment);

            if (include_force_discard && op && strcmp(op, "force_discard") == 0
                && sf && strcmp(sf, "end_of_turn_mass_discard") == 0) {
                for (int tp = 0; tp < state->player_count; tp++) {
                    Sym tpid = state->players[tp].player_id;
                    if (tpid == pid) continue;
                    PlayerState *tps = cow_player(state, tpid);
                    if (!tps || tps->hand_count == 0) continue;
                    RNG rng;
                    rng_seed(&rng, state->shuffle_seed);
                    for (int c = 0; c < state->shuffle_counter; c++)
                        rng_next(&rng);
                    int idx = rng_randint(&rng, 0, tps->hand_count - 1);
                    if (tps->discard_pile_count < MAX_ZONE_SIZE)
                        tps->discard_pile[tps->discard_pile_count++] = tps->hand[idx];
                    for (int h = idx; h < tps->hand_count - 1; h++)
                        tps->hand[h] = tps->hand[h + 1];
                    tps->hand_count--;
                    state->shuffle_counter++;
                }
            }

            if (include_scaled_vp && op && strcmp(op, "grant_vp") == 0
                && sf && strncmp(sf, "scaled_vp", 9) == 0) {
                PlayerState *cps = cow_player(state, pid);
                if (cps) {
                    int vp = scaled_vp_award_count(state, pid, action);
                    int as_tokens = 0;
                    for (int mi = 0; mi < action->metadata_count; mi++) {
                        const char *mk = intern_str(action->metadata[mi].key);
                        const char *mv = intern_str(action->metadata[mi].value);
                        if (mk && strcmp(mk, "as") == 0 && mv && strcmp(mv, "vp_tokens") == 0)
                            as_tokens = 1;
                    }
                    if (as_tokens)
                        cps->vp_tokens += vp;
                    else
                        cps->score += vp;
                }
            }
        }
    }
}

static GameState *enter_end_of_turn(GameState *state) {
    if (state->pending_immediate_count > 0) return NULL;

    state->pending_ability = NULL;

    int kept_count = 0;
    int pi = player_index_for_id_state(state, state->current_player_id);
    for (int i = 0; i < state->pending_eot_count; i++) {
        PendingPromotionState *p = &state->pending_eot[i];
        if (p->optional || p->deferred_choice) {
            if (i != kept_count) state->pending_eot[kept_count] = *p;
            kept_count++;
        } else {
            /* D14b: only promote mandatory cards still in played_cards
             * (a prior effect may have removed the card). Mirrors Python's
             * `if pending.card_id not in played_cards: continue` guard.
             * promote_card is also a no-op on absent cards, but the guard
             * makes the parity explicit. */
            int in_played = 0;
            if (pi >= 0) {
                for (int j = 0; j < state->players[pi].played_cards_count; j++)
                    if (state->players[pi].played_cards[j] == p->card_id) { in_played = 1; break; }
            }
            if (in_played)
                promote_card(state, state->current_player_id, p->card_id);
        }
    }
    state->pending_eot_count = kept_count;

    apply_end_of_turn_effects(state, 1, 0);
    advance_phase(state);
    return state;
}

static GameState *apply_resolve_end_of_turn(GameState *state, Sym player_id) {
    if (state->pending_eot_count > 0) return NULL;
    apply_end_of_turn_effects(state, 0, 1);
    award_end_of_turn_site_vp(state, player_id);
    advance_phase(state);
    return state;
}

static GameState *apply_cleanup(GameState *state) {
    Sym pid = state->current_player_id;
    PlayerState *ps = cow_player(state, pid);
    if (!ps) return NULL;

    for (int i = 0; i < ps->hand_count; i++)
        if (ps->discard_pile_count < MAX_ZONE_SIZE)
            ps->discard_pile[ps->discard_pile_count++] = ps->hand[i];
    ps->hand_count = 0;

    for (int i = 0; i < ps->played_cards_count; i++)
        if (ps->discard_pile_count < MAX_ZONE_SIZE)
            ps->discard_pile[ps->discard_pile_count++] = ps->played_cards[i];
    ps->played_cards_count = 0;

    for (int i = 0; i < 5; i++) {
        if (ps->deck_count == 0 && ps->discard_pile_count > 0)
            reshuffle_discard_into_deck(state, pid);
        if (ps->deck_count == 0) break;
        ps->hand[ps->hand_count++] = ps->deck[--ps->deck_count];
    }
    advance_phase(state);
    return state;
}

GameState *engine_apply(const GameState *src, const Move *move) {
    GameState *state = engine_clone_cow(src);
    if (!state) return NULL;

    Sym pid = state->current_player_id;

    switch (move->type) {
    case MOVE_PLAY_CARD: {
        GameState *r = apply_play_card(state, move->data.play_card.card_id, move->data.play_card.hand_index, pid);
        if (!r) { engine_destroy(state); return NULL; }
        return r;
    }
    case MOVE_END_MAIN_PHASE:
        if (state->phase != PHASE_MAIN) { engine_destroy(state); return NULL; }
        { GameState *r = enter_end_of_turn(state);
          if (!r) { engine_destroy(state); return NULL; }
          return r; }

    case MOVE_RESOLVE_END_OF_TURN:
        if (state->phase != PHASE_END_OF_TURN) { engine_destroy(state); return NULL; }
        { GameState *r = apply_resolve_end_of_turn(state, pid);
          if (!r) { engine_destroy(state); return NULL; }
          return r; }

    case MOVE_RESOLVE_CLEANUP:
        if (state->phase != PHASE_CLEANUP) { engine_destroy(state); return NULL; }
        { GameState *r = apply_cleanup(state);
          if (!r) { engine_destroy(state); return NULL; }
          return r; }

    case MOVE_ASSASSINATE: {
        GameState *r = apply_assassinate(state, pid,
            move->data.assassinate.target_node_id,
            move->data.assassinate.slot_index);
        if (!r) { engine_destroy(state); return NULL; }
        return r;
    }
    case MOVE_DEPLOY: {
        GameState *r = apply_deploy(state, pid,
            move->data.deploy.node_id);
        if (!r) { engine_destroy(state); return NULL; }
        return r;
    }
    case MOVE_RECRUIT: {
        int slot = -1;
        for (int i = 0; i < state->market.row_count; i++)
            if (state->market.row[i] == move->data.recruit.card_id) { slot = i; break; }
        if (slot < 0) {
            Sym card_id = move->data.recruit.card_id;
            for (int s = 100; s <= 102; s++) {
                Sym scid; int st;
                if (special_stack_config(s, &scid, &st) && scid == card_id) { slot = s; break; }
            }
            if (slot < 0) { engine_destroy(state); return NULL; }
        }
        if (apply_recruit(state, pid, slot) != 0) { engine_destroy(state); return NULL; }
        return state;
    }
    case MOVE_RETURN_SPY:
        if (move->data.return_spy.spy_owner_id == pid) { engine_destroy(state); return NULL; }
        if (apply_return_spy(state, pid, move->data.return_spy.node_id,
                             move->data.return_spy.spy_owner_id) != 0)
            { engine_destroy(state); return NULL; }
        return state;

    case MOVE_ACTIVATE_ABILITY: {
        GameState *r = apply_activate_card_ability(state, pid, move);
        if (!r) { engine_destroy(state); return NULL; }
        return r;
    }
    case MOVE_DECLINE_ABILITY: {
        GameState *r = apply_decline_card_ability(state, pid,
            move->data.decline_ability.card_id,
            move->data.decline_ability.ability_key);
        if (!r) { engine_destroy(state); return NULL; }
        return r;
    }
    case MOVE_PROMOTE_CARD: {
        GameState *r = apply_promote_card_impl(state, pid, move->data.promote_card.card_id);
        if (!r) { engine_destroy(state); return NULL; }
        return r;
    }
    case MOVE_SKIP_PROMOTE: {
        GameState *r = apply_skip_promote_impl(state);
        if (!r) { engine_destroy(state); return NULL; }
        return r;
    }
    case MOVE_INITIAL_PLACEMENT: {
        GameState *r = apply_initial_placement(state, pid,
            move->data.initial_placement.node_id);
        if (!r) { engine_destroy(state); return NULL; }
        return r;
    }
    case MOVE_RESOLVE_GENERIC: {
        GameState *r = apply_resolve_generic_choice(state, move);
        if (!r) { engine_destroy(state); return NULL; }
        assert(r != state);
        engine_destroy(state);
        return r;
    }

    default:
        engine_destroy(state);
        return NULL;
    }
}

int engine_is_terminal(const GameState *state) {
    if (state->phase == PHASE_GAME_OVER) return 1;
    if (state->market.deck_count == 0) return 1;
    for (int i = 0; i < state->player_count; i++)
        if (state->players[i].barracks == 0) return 1;
    return 0;
}

Sym engine_winner(const GameState *state, int *score_out) {
    if (!engine_is_terminal(state)) return SYM_NULL;
    int scores[MAX_PLAYERS];
    compute_final_scores(state, scores);
    int max_score = -1, max_idx = -1, tie = 0;
    for (int i = 0; i < state->player_count; i++) {
        if (scores[i] > max_score) { max_score = scores[i]; max_idx = i; tie = 0; }
        else if (scores[i] == max_score) tie = 1;
    }
    if (tie || max_idx < 0) {
        if (score_out) *score_out = 0;
        return SYM_NULL;
    }
    if (score_out) *score_out = max_score;
    return state->players[max_idx].player_id;
}

static GameState *effect_gain_power(GameState *state, Sym player_id, const CardDefinition *card) {
    (void)player_id;
    int amount = 0;
    for (int i = 0; i < card->effect_payload_count; i++) {
        const char *k = intern_str(card->effect_payload[i].key);
        const char *v = intern_str(card->effect_payload[i].value);
        if (k && strcmp(k, "power") == 0 && v) amount = atoi(v);
    }
    cow_resource_pool(state)->power += amount;
    return state;
}

static GameState *effect_gain_influence(GameState *state, Sym player_id, const CardDefinition *card) {
    (void)player_id;
    int amount = 0;
    for (int i = 0; i < card->effect_payload_count; i++) {
        const char *k = intern_str(card->effect_payload[i].key);
        const char *v = intern_str(card->effect_payload[i].value);
        if (k && strcmp(k, "influence") == 0 && v) amount = atoi(v);
    }
    cow_resource_pool(state)->influence += amount;
    return state;
}

static GameState *effect_noop(GameState *state, Sym player_id, const CardDefinition *card) {
    (void)player_id; (void)card;
    return state;
}

static GameState *effect_generic_card(GameState *state, Sym player_id, const CardDefinition *card) {
    Sym source = card->card_id;
    for (int i = 0; i < card->effect_payload_count; i++) {
        const char *k = intern_str(card->effect_payload[i].key);
        if (k && strcmp(k, "source_card_id") == 0 && card->effect_payload[i].value != SYM_NULL)
            source = card->effect_payload[i].value;
    }
    return resolve_generic_execution(state, player_id, card, source);
}

void register_default_effects(void) {
    register_effect(intern("gain_power"), effect_gain_power);
    register_effect(intern("gain_influence"), effect_gain_influence);
    register_effect(intern("noop"), effect_noop);
    register_effect(intern("generic_card"), effect_generic_card);
    register_generic_actions();
    register_selection_handlers();
}
