#include "generic_runtime.h"
#include "helpers.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

static Sym find_ls_sym(const PendingGenericChoiceState *p, const char *key) {
    Sym k = intern(key);
    for (int i = 0; i < p->last_selection_count; i++)
        if (p->last_selection_keys[i] == k) return p->last_selection_values[i];
    return SYM_NULL;
}

static int find_ls_int(const PendingGenericChoiceState *p, const char *key, int def) {
    Sym v = find_ls_sym(p, key);
    if (v == SYM_NULL) return def;
    const char *s = intern_str(v);
    return s ? (int)strtol(s, NULL, 10) : def;
}

static int mk_move(Move *out, int w, int max, Sym pid, const PendingGenericChoiceState *p,
                   Sym k1, Sym v1, Sym k2, Sym v2, Sym k3, Sym v3) {
    if (w >= max) return w;
    out[w].type = MOVE_RESOLVE_GENERIC;
    out[w].data.resolve_generic.action_id = v1;
    out[w].player_index = 0;
    return w + 1;
}

static int sel_deploy(const GameState *state, Sym player_id,
                      const PendingGenericChoiceState *pending,
                      const CardDefinition *card, const CardAction *action,
                      Move *out, int max_out) {
    int w = 0;
    int ht = player_has_any_troops_on_board(state, player_id);
    for (int i = 0; i < state->node_count && w < max_out; i++) {
        Sym nid = state->nodes[i].node_id;
        if (can_deploy_to_node(state, player_id, nid, ht)) {
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = nid;
            out[w].player_index = 0;
            w++;
        }
    }
    return w;
}

static int sel_assassinate_supplant(const GameState *state, Sym player_id,
                                     const PendingGenericChoiceState *pending,
                                     const CardDefinition *card, const CardAction *action,
                                     Move *out, int max_out) {
    int w = 0;
    int white_only = 0, allow_white = 0;
    int requires_last = 0;
    int ignore_presence = 0;
    Sym last_site = SYM_NULL;
    for (int i = 0; i < action->filter_count; i++) {
        const char *f = intern_str(action->filters[i]);
        if (f && strcmp(f, "white_troop_only") == 0) white_only = 1;
        if (f && strcmp(f, "allow_white_troop") == 0) allow_white = 1;
    }
    int requires_returned_spy = 0;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "requires_last_selected_node") == 0 && v) {
            requires_last = 1;
        }
        if (k && strcmp(k, "ignore_presence_requirement") == 0 && v
            && strcmp(v, "true") == 0) {
            ignore_presence = 1;
        }
        if (k && strcmp(k, "requires_returned_spy_site") == 0 && v
            && strcmp(v, "true") == 0) {
            requires_returned_spy = 1;
        }
    }
    if (requires_last) last_site = find_ls_sym(pending, "target_node_id");
    if (requires_returned_spy && last_site == SYM_NULL) {
        requires_last = 1;
        last_site = find_ls_sym(pending, "node_id");
    }
    for (int i = 0; i < state->node_count && w < max_out; i++) {
        Sym nid = state->nodes[i].node_id;
        if (requires_last) {
            if (last_site == SYM_NULL || nid != last_site) continue;
        } else if (!ignore_presence) {
            if (!has_presence(state, player_id, nid)) continue;
        }
        for (int s = 0; s < state->nodes[i].troop_slot_count && w < max_out; s++) {
            Sym occ = state->nodes[i].troop_slots[s];
            if (occ == SYM_NULL || occ == player_id) continue;
            if (white_only && strcmp(intern_str(occ) ? intern_str(occ) : "", "white") != 0) continue;
            if (!white_only && !allow_white && strcmp(intern_str(occ) ? intern_str(occ) : "", "white") == 0) continue;
            char buf[16];
            snprintf(buf, sizeof(buf), "%d", s);
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = nid;
            out[w].data.resolve_generic.target_id = intern(buf);
            out[w].data.resolve_generic.selection_index = 0;
            out[w].player_index = 0;
            w++;
        }
    }
    return w;
}

static int sel_custom_effect(const GameState *state, Sym player_id,
                             const PendingGenericChoiceState *pending,
                             const CardDefinition *card, const CardAction *action,
                             Move *out, int max_out) {
    int w = 0;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (!k || strcmp(k, "effect_kind") != 0 || !v) continue;
        if (strcmp(v, "select_site") == 0) {
            for (int ni = 0; ni < state->node_count && w < max_out; ni++) {
                Sym nid = state->nodes[ni].node_id;
                const NodeDefinition *nd = NULL;
                for (int j = 0; j < state->definition->board.node_count; j++)
                    if (state->definition->board.nodes[j].node_id == nid)
                        { nd = &state->definition->board.nodes[j]; break; }
                if (!nd || strcmp(intern_str(nd->kind), "site") != 0) continue;
                if (!has_presence(state, player_id, nid)) continue;
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = nid;
                out[w].data.resolve_generic.target_id = SYM_NULL;
                out[w].data.resolve_generic.selection_index = 0;
                out[w].player_index = 0;
                w++;
            }
        } else if (strstr(v, "selected_player") || strstr(v, "presence_on_last_selected")) {
            Sym last_site = SYM_NULL;
            int needs_presence = 0;
            if (strstr(v, "presence_on_last_selected")) {
                needs_presence = 1;
                last_site = find_ls_sym(pending, "target_node_id");
                if (last_site == SYM_NULL) continue;
            }
            for (int p = 0; p < state->player_count && w < max_out; p++) {
                if (state->players[p].player_id == player_id) continue;
                if (needs_presence && !has_presence(state, state->players[p].player_id, last_site)) continue;
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = state->players[p].player_id;
                out[w].data.resolve_generic.target_id = SYM_NULL;
                out[w].data.resolve_generic.selection_index = 0;
                out[w].player_index = 0;
                w++;
            }
        }
    }
    return w;
}

static int sel_place_spy(const GameState *state, Sym player_id,
                          const PendingGenericChoiceState *pending,
                          const CardDefinition *card, const CardAction *action,
                          Move *out, int max_out) {
    int w = 0;
    int pi = -1;
    for (int i = 0; i < state->player_count; i++)
        if (state->players[i].player_id == player_id) { pi = i; break; }
    if (pi < 0) return 0;

    int has_spies = state->players[pi].spies_available > 0;
    for (int i = 0; i < state->node_count && w < max_out; i++) {
        Sym nid = state->nodes[i].node_id;
        const NodeDefinition *nd = NULL;
        for (int j = 0; j < state->definition->board.node_count; j++)
            if (state->definition->board.nodes[j].node_id == nid) { nd = &state->definition->board.nodes[j]; break; }
        if (!nd || strcmp(intern_str(nd->kind), "site") != 0) continue;
        int has_spy = 0;
        for (int s = 0; s < state->nodes[i].spy_count; s++)
            if (state->nodes[i].spies[s] == player_id) { has_spy = 1; break; }
        if (has_spy) continue;
        if (has_spies) {
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = nid;
            out[w].player_index = 0;
            w++;
        }
    }
    return w;
}

static int sel_return_spy(const GameState *state, Sym player_id,
                           const PendingGenericChoiceState *pending,
                           const CardDefinition *card, const CardAction *action,
                           Move *out, int max_out) {
    int w = 0;
    const char *spy_owner = NULL;
    for (int mi = 0; mi < action->metadata_count; mi++) {
        const char *mk = intern_str(action->metadata[mi].key);
        if (mk && strcmp(mk, "spy_owner") == 0)
            spy_owner = intern_str(action->metadata[mi].value);
    }
    bool only_self = spy_owner && strcmp(spy_owner, "self") == 0;
    for (int i = 0; i < state->node_count && w < max_out; i++) {
        Sym nid = state->nodes[i].node_id;
        for (int s = 0; s < state->nodes[i].spy_count && w < max_out; s++) {
            Sym spy = state->nodes[i].spies[s];
            if (spy == player_id) {
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = nid;
                out[w].player_index = 0;
                w++;
            } else if (!only_self && has_presence(state, player_id, nid)) {
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = nid;
                out[w].player_index = 0;
                w++;
            }
        }
    }
    return w;
}

static int sel_return_unit(const GameState *state, Sym player_id,
                            const PendingGenericChoiceState *pending,
                            const CardDefinition *card, const CardAction *action,
                            Move *out, int max_out) {
    int w = 0;
    for (int i = 0; i < state->node_count && w < max_out; i++) {
        Sym nid = state->nodes[i].node_id;
        for (int s = 0; s < state->nodes[i].troop_slot_count && w < max_out; s++) {
            Sym occ = state->nodes[i].troop_slots[s];
            if (occ != player_id) continue;
            char buf[32];
            snprintf(buf, sizeof(buf), "troop:%d", s);
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = nid;
            out[w].data.resolve_generic.target_id = intern(buf);
            out[w].data.resolve_generic.selection_index = 0;
            out[w].player_index = 0;
            w++;
        }
        for (int s = 0; s < state->nodes[i].spy_count && w < max_out; s++) {
            if (state->nodes[i].spies[s] != player_id) continue;
            char buf[32];
            const char *pid_str = intern_str(player_id);
            snprintf(buf, sizeof(buf), "spy:%s", pid_str ? pid_str : "?");
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = nid;
            out[w].data.resolve_generic.target_id = intern(buf);
            out[w].data.resolve_generic.selection_index = 0;
            out[w].player_index = 0;
            w++;
        }
    }
    return w;
}

static int sel_move_troop(const GameState *state, Sym player_id,
                           const PendingGenericChoiceState *pending,
                           const CardDefinition *card, const CardAction *action,
                           Move *out, int max_out) {
    int w = 0;
    int requires_presence = 1;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "ignore_presence_requirement") == 0 && v
            && strcmp(v, "true") == 0)
            requires_presence = 0;
    }
    for (int si = 0; si < state->node_count && w < max_out; si++) {
        Sym src = state->nodes[si].node_id;
        if (requires_presence && !has_presence(state, player_id, src)) continue;
        for (int ss = 0; ss < state->nodes[si].troop_slot_count; ss++) {
            Sym occ = state->nodes[si].troop_slots[ss];
            if (occ == SYM_NULL || occ == player_id) continue;
            for (int di = 0; di < state->node_count && w < max_out; di++) {
                if (di == si) continue;
                for (int ts = 0; ts < state->nodes[di].troop_slot_count && w < max_out; ts++) {
                    if (state->nodes[di].troop_slots[ts] != SYM_NULL) continue;
                    const char *dst_str = intern_str(state->nodes[di].node_id);
                    char buf[128];
                    snprintf(buf, sizeof(buf), "%d:%s:%d", ss, dst_str ? dst_str : "?", ts);
                    out[w].type = MOVE_RESOLVE_GENERIC;
                    out[w].data.resolve_generic.action_id = src;
                    out[w].data.resolve_generic.target_id = intern(buf);
                    out[w].player_index = 0;
                    w++;
                }
            }
        }
    }
    return w;
}

static int sel_force_discard(const GameState *state, Sym player_id,
                              const PendingGenericChoiceState *pending,
                              const CardDefinition *card, const CardAction *action,
                              Move *out, int max_out) {
    const char *sf = intern_str(action->source_fragment);
    /* targeted_discard: player picks an opponent (with 3+ cards),
     * then that opponent discards one random card. */
    if (sf && strcmp(sf, "targeted_discard") == 0) {
        int w = 0;
        for (int p = 0; p < state->player_count && w < max_out; p++) {
            if (state->players[p].player_id == player_id) continue;
            if (state->players[p].hand_count >= 3) {
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = state->players[p].player_id;
                out[w].player_index = 0;
                w++;
            }
        }
        return w;
    }
    /* Default: one move per card in each opponent's hand (original behaviour). */
    int w = 0;
    for (int p = 0; p < state->player_count && w < max_out; p++) {
        if (state->players[p].player_id == player_id) continue;
        for (int h = 0; h < state->players[p].hand_count && w < max_out; h++) {
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = state->players[p].hand[h];
            out[w].player_index = 0;
            w++;
        }
    }
    return w;
}

static int sel_promote(const GameState *state, Sym player_id,
                        const PendingGenericChoiceState *pending,
                        const CardDefinition *card, const CardAction *action,
                        Move *out, int max_out) {
    int w = 0;
    int pi = -1;
    for (int i = 0; i < state->player_count; i++)
        if (state->players[i].player_id == player_id) { pi = i; break; }
    if (pi < 0) return 0;
    for (int i = 0; i < state->players[pi].played_cards_count && w < max_out; i++) {
        out[w].type = MOVE_RESOLVE_GENERIC;
        out[w].data.resolve_generic.action_id = state->players[pi].played_cards[i];
        out[w].player_index = 0;
        w++;
    }
    return w;
}

static int sel_recruit(const GameState *state, Sym player_id,
                        const PendingGenericChoiceState *pending,
                        const CardDefinition *card, const CardAction *action,
                        Move *out, int max_out) {
    int w = 0;
    for (int s = 0; s < state->market.row_count && w < max_out; s++) {
        Sym cid = state->market.row[s];
        const CardDefinition *cd = NULL;
        for (int i = 0; i < state->definition->catalog.card_count; i++)
            if (state->definition->catalog.cards[i].card_id == cid) { cd = &state->definition->catalog.cards[i]; break; }
        if (cd && state->resource_pool.influence >= cd->cost) {
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = cid;
            out[w].player_index = 0;
            w++;
        }
    }
    return w;
}

static int sel_devour(const GameState *state, Sym player_id,
                       const PendingGenericChoiceState *pending,
                       const CardDefinition *card, const CardAction *action,
                       Move *out, int max_out) {
    int w = 0;
    int pi = -1;
    for (int i = 0; i < state->player_count; i++)
        if (state->players[i].player_id == player_id) { pi = i; break; }
    if (pi < 0) return 0;

    /* Determine the source zone: read from metadata or fall back to target_scope. */
    Sym zone = SYM_NULL;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        if (k && strcmp(k, "source_zone") == 0) { zone = action->metadata[i].value; break; }
    }
    if (zone == SYM_NULL) zone = action->target_scope;
    const char *z = intern_str(zone);

    if (z && strcmp(z, "market") == 0) {
        int slot_locked = 0;
        for (int i = 0; i < action->metadata_count; i++) {
            const char *k = intern_str(action->metadata[i].key);
            const char *v = intern_str(action->metadata[i].value);
            if (k && strcmp(k, "requires_last_selected_market_slot") == 0 && v
                && strcmp(v, "true") == 0) {
                slot_locked = 1;
                break;
            }
        }
        if (slot_locked) {
            Sym prev_card = pending->last_played_card_id;
            if (prev_card != SYM_NULL && w < max_out) {
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = prev_card;
                out[w].player_index = 0;
                w++;
            }
        } else {
            for (int s = 0; s < state->market.row_count && w < max_out; s++) {
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = state->market.row[s];
                out[w].player_index = 0;
                w++;
            }
        }
    } else if (z && strcmp(z, "played_self") == 0) {
        /* Devour the card that was just played (self-devour). */
        if (pending->source_card_id != SYM_NULL && w < max_out) {
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = pending->source_card_id;
            out[w].player_index = 0;
            w++;
        }
    } else {
        /* Default: devour from the player's hand. */
        for (int h = 0; h < state->players[pi].hand_count && w < max_out; h++) {
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = state->players[pi].hand[h];
            out[w].player_index = 0;
            w++;
        }
    }
    return w;
}

static int sel_play_card(const GameState *state, Sym player_id,
                          const PendingGenericChoiceState *pending,
                          const CardDefinition *card, const CardAction *action,
                          Move *out, int max_out) {
    int w = 0;
    const char *sf = intern_str(action->source_fragment);
    if (sf && strcmp(sf, "play_from_inner_circle_without_removal") == 0) {
        int pi = -1;
        for (int i = 0; i < state->player_count; i++)
            if (state->players[i].player_id == player_id) { pi = i; break; }
        if (pi < 0) return 0;
        for (int i = 0; i < state->players[pi].inner_circle_count && w < max_out; i++) {
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = state->players[pi].inner_circle[i];
            out[w].player_index = 0;
            w++;
        }
        return w;
    }
    if (sf && strcmp(sf, "play") == 0) {
        int max_cost = 9999;
        for (int i = 0; i < action->metadata_count; i++) {
            const char *k = intern_str(action->metadata[i].key);
            const char *v = intern_str(action->metadata[i].value);
            if (k && strcmp(k, "max_cost") == 0 && v) max_cost = atoi(v);
        }
        for (int s = 0; s < state->market.row_count && w < max_out; s++) {
            Sym cid = state->market.row[s];
            if (max_cost < 9999) {
                const CardDefinition *cd = NULL;
                for (int ci = 0; ci < state->definition->catalog.card_count; ci++)
                    if (state->definition->catalog.cards[ci].card_id == cid)
                        { cd = &state->definition->catalog.cards[ci]; break; }
                if (!cd || cd->cost > max_cost) continue;
            }
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = cid;
            out[w].player_index = 0;
            w++;
        }
        return w;
    }
    return 0;
}

typedef int (*SelFn)(const GameState*, Sym, const PendingGenericChoiceState*,
                      const CardDefinition*, const CardAction*, Move*, int);

static SelFn sel_dispatch[32];
static Sym sel_op_keys[32];
static int sel_dispatch_count = 0;

static void register_sel(Sym op, SelFn fn) {
    if (sel_dispatch_count < 32) {
        sel_op_keys[sel_dispatch_count] = op;
        sel_dispatch[sel_dispatch_count] = fn;
        sel_dispatch_count++;
    }
}

int legal_generic_target_selection_moves(const GameState *state, Sym player_id,
                                          const PendingGenericChoiceState *pending,
                                          const CardDefinition *card,
                                          const CardAction *action, Move *out, int max_out) {
    for (int i = 0; i < sel_dispatch_count; i++) {
        if (sel_op_keys[i] == action->op && sel_dispatch[i])
            return sel_dispatch[i](state, player_id, pending, card, action, out, max_out);
    }
    return 0;
}

void register_selection_handlers(void) {
    register_sel(intern("deploy_troops"), sel_deploy);
    register_sel(intern("assassinate_troop"), sel_assassinate_supplant);
    register_sel(intern("supplant_troop"), sel_assassinate_supplant);
    register_sel(intern("place_spy"), sel_place_spy);
    register_sel(intern("return_spy"), sel_return_spy);
    register_sel(intern("return_unit"), sel_return_unit);
    register_sel(intern("move_troop"), sel_move_troop);
    register_sel(intern("force_discard"), sel_force_discard);
    register_sel(intern("promote_card"), sel_promote);
    register_sel(intern("recruit_card"), sel_recruit);
    register_sel(intern("devour"), sel_devour);
    register_sel(intern("devour_cost"), sel_devour);
    register_sel(intern("play_card"), sel_play_card);
    register_sel(intern("custom_effect"), sel_custom_effect);
}
