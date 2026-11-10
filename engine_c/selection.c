#include "generic_runtime.h"
#include "helpers.h"
#include "ops/op.h"
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

/* Every target is counted; only those that fit are written, so a caller can
 * detect truncation. (Unused today, kept consistent with the query contract.) */
static int mk_move(Move *out, int w, int max, Sym pid, const PendingGenericChoiceState *p,
                   Sym k1, Sym v1, Sym k2, Sym v2, Sym k3, Sym v3) {
    (void)pid; (void)p; (void)k1; (void)k2; (void)v2; (void)k3; (void)v3;
    if (w < max) {
        out[w].type = MOVE_RESOLVE_GENERIC;
        out[w].data.resolve_generic.action_id = v1;
        out[w].player_index = 0;
    }
    return w + 1;
}

int legal_assassinate_supplant_moves(const GameState *state, Sym player_id,
                                     const PendingGenericChoiceState *pending,
                                     const CardDefinition *card, const CardAction *action,
                                     Move *out, int max_out) {
    int w = 0;
    int white_only = 0, allow_white = 0;
    int requires_last = 0;
    int ignore_presence = 0;
    Sym last_site = SYM_NULL;
    const char *op_name = intern_str(action->op);
    int is_assassinate = op_name && strcmp(op_name, "assassinate_troop") == 0;
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
    for (int i = 0; i < state->node_count; i++) {
        Sym nid = state->nodes[i].node_id;
        if (requires_last) {
            if (last_site == SYM_NULL || nid != last_site) continue;
        } else if (!ignore_presence) {
            if (!has_presence(state, player_id, nid)) continue;
        }
        for (int s = 0; s < state->nodes[i].troop_slot_count; s++) {
            Sym occ = state->nodes[i].troop_slots[s];
            if (occ == SYM_NULL || occ == player_id) continue;
            if (white_only && strcmp(intern_str(occ) ? intern_str(occ) : "", "white") != 0) continue;
            if (!white_only && !allow_white && !is_assassinate
                && strcmp(intern_str(occ) ? intern_str(occ) : "", "white") == 0) continue;
            char buf[16];
            snprintf(buf, sizeof(buf), "%d", s);
            if (w >= max_out) { w++; continue; }
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
            int site_white_only = 0;
            for (int fi = 0; fi < action->filter_count; fi++) {
                const char *f = intern_str(action->filters[fi]);
                if (f && strcmp(f, "white_troop_only") == 0) site_white_only = 1;
            }
            int ignore_presence = 0;
            for (int mi = 0; mi < action->metadata_count; mi++) {
                const char *mk = intern_str(action->metadata[mi].key);
                const char *mv = intern_str(action->metadata[mi].value);
                if (mk && strcmp(mk, "ignore_presence_requirement") == 0 && mv
                    && strcmp(mv, "true") == 0) {
                    ignore_presence = 1;
                    break;
                }
            }
            for (int ni = 0; ni < state->node_count; ni++) {
                Sym nid = state->nodes[ni].node_id;
                const NodeDefinition *nd = NULL;
                for (int j = 0; j < state->definition->board.node_count; j++)
                    if (state->definition->board.nodes[j].node_id == nid)
                        { nd = &state->definition->board.nodes[j]; break; }
                if (!nd || strcmp(intern_str(nd->kind), "site") != 0) continue;
                if (!ignore_presence && !has_presence(state, player_id, nid)) continue;
                if (site_white_only) {
                    int has_white = 0;
                    for (int s = 0; s < state->nodes[ni].troop_slot_count; s++) {
                        Sym occ = state->nodes[ni].troop_slots[s];
                        if (occ == SYM_NULL) continue;
                        const char *os = intern_str(occ);
                        if (os && strcmp(os, "white") == 0) { has_white = 1; break; }
                    }
                    if (!has_white) continue;
                }
                if (w >= max_out) { w++; continue; }
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
            for (int p = 0; p < state->player_count; p++) {
                if (state->players[p].player_id == player_id) continue;
                if (needs_presence && !has_presence(state, state->players[p].player_id, last_site)) continue;
                if (w >= max_out) { w++; continue; }
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = state->players[p].player_id;
                out[w].data.resolve_generic.target_id = SYM_NULL;
                out[w].data.resolve_generic.selection_index = 0;
                out[w].player_index = 0;
                w++;
            }
        } else if (strcmp(v, "self_purge_to_supply") == 0) {
            int pi = -1;
            for (int i = 0; i < state->player_count; i++)
                if (state->players[i].player_id == player_id) { pi = i; break; }
            if (pi < 0) continue;
            for (int h = 0; h < state->players[pi].hand_count; h++) {
                if (state->players[pi].hand[h] == pending->source_card_id) continue;
                char idx_buf[16];
                snprintf(idx_buf, sizeof(idx_buf), "%d", h);
                if (w >= max_out) { w++; continue; }
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = state->players[pi].hand[h];
                out[w].data.resolve_generic.target_id = intern(idx_buf);
                out[w].data.resolve_generic.selection_index = 0;
                out[w].player_index = 0;
                w++;
            }
        } else if (strcmp(v, "select_trophy_hall") == 0) {
            int white_only = 0;
            int allow_white = 0;
            int exclude_self = 0;
            for (int fi = 0; fi < action->filter_count; fi++) {
                const char *f = intern_str(action->filters[fi]);
                if (f && strcmp(f, "white_troop_only") == 0) white_only = 1;
                if (f && strcmp(f, "allow_white_troop") == 0) allow_white = 1;
                if (f && strcmp(f, "exclude_self") == 0) exclude_self = 1;
            }
            for (int sp = 0; sp < state->player_count; sp++) {
                Sym sp_id = state->players[sp].player_id;
                if (exclude_self && sp_id == player_id) continue;
                for (int ti = 0; ti < state->players[sp].trophy_hall_count; ti++) {
                    Sym occ = state->players[sp].trophy_hall[ti];
                    const char *oc = intern_str(occ);
                    int is_white = oc && strcmp(oc, "white") == 0;
                    if (white_only && !is_white) continue;
                    if (!white_only && !allow_white && is_white) continue;
                    char idx_buf[16];
                    snprintf(idx_buf, sizeof(idx_buf), "%d", ti);
                    if (w >= max_out) { w++; continue; }
                    out[w].type = MOVE_RESOLVE_GENERIC;
                    out[w].data.resolve_generic.action_id = sp_id;
                    out[w].data.resolve_generic.target_id = intern(idx_buf);
                    out[w].data.resolve_generic.selection_index = 0;
                    out[w].player_index = 0;
                    w++;
                }
            }
        } else if (strcmp(v, "steal_from_selected_trophy") == 0) {
            Sym source_player = find_ls_sym(pending, "source_player_id");
            Sym trophy_idx_sym = find_ls_sym(pending, "selected_trophy_index");
            if (source_player == SYM_NULL || trophy_idx_sym == SYM_NULL) continue;
            int spi = -1;
            for (int p = 0; p < state->player_count; p++)
                if (state->players[p].player_id == source_player) { spi = p; break; }
            if (spi < 0) continue;
            const char *idx_str = intern_str(trophy_idx_sym);
            int trophy_idx = idx_str ? atoi(idx_str) : -1;
            if (trophy_idx < 0 || trophy_idx >= state->players[spi].trophy_hall_count) continue;
            for (int ni = 0; ni < state->node_count; ni++) {
                Sym nid = state->nodes[ni].node_id;
                for (int s = 0; s < state->nodes[ni].troop_slot_count; s++) {
                    if (state->nodes[ni].troop_slots[s] != SYM_NULL) continue;
                    char buf[128];
                    const char *sp_str = intern_str(source_player);
                    const char *tn_str = intern_str(trophy_idx_sym);
                    const char *nid_str = intern_str(nid);
                    snprintf(buf, sizeof(buf), "%.24s:%.16s:%.48s:%d",
                             sp_str ? sp_str : "", tn_str ? tn_str : "",
                             nid_str ? nid_str : "", s);
                    if (w >= max_out) { w++; continue; }
                    out[w].type = MOVE_RESOLVE_GENERIC;
                    out[w].data.resolve_generic.action_id = nid;
                    out[w].data.resolve_generic.target_id = intern(buf);
                    out[w].data.resolve_generic.selection_index = 0;
                    out[w].player_index = 0;
                    w++;
                }
            }
        } else if (strcmp(v, "steal_white_trophy_to_board") == 0) {
            Sym source_player = find_ls_sym(pending, "source_player_id");
            Sym trophy_idx_sym = find_ls_sym(pending, "selected_trophy_index");
            if (source_player == SYM_NULL || trophy_idx_sym == SYM_NULL) {
                /* Step 1: choose an enemy player's white trophy. */
                for (int sp = 0; sp < state->player_count; sp++) {
                    Sym sp_id = state->players[sp].player_id;
                    if (sp_id == player_id) continue;
                    for (int ti = 0; ti < state->players[sp].trophy_hall_count; ti++) {
                        Sym occ = state->players[sp].trophy_hall[ti];
                        const char *oc = intern_str(occ);
                        if (!oc || strcmp(oc, "white") != 0) continue;
                        char idx_buf[16];
                        snprintf(idx_buf, sizeof(idx_buf), "%d", ti);
                        if (w >= max_out) { w++; continue; }
                        out[w].type = MOVE_RESOLVE_GENERIC;
                        out[w].data.resolve_generic.action_id = sp_id;
                        out[w].data.resolve_generic.target_id = intern(idx_buf);
                        out[w].data.resolve_generic.selection_index = 0;
                        out[w].player_index = 0;
                        w++;
                    }
                }
            } else {
                /* Step 2: deploy the stolen white trophy anywhere on the board
                 * (no presence requirement). */
                int spi = -1;
                for (int p = 0; p < state->player_count; p++)
                    if (state->players[p].player_id == source_player) { spi = p; break; }
                if (spi < 0) continue;
                const char *idx_str = intern_str(trophy_idx_sym);
                int trophy_idx = idx_str ? atoi(idx_str) : -1;
                if (trophy_idx < 0 || trophy_idx >= state->players[spi].trophy_hall_count) continue;
                for (int ni = 0; ni < state->node_count; ni++) {
                    Sym nid = state->nodes[ni].node_id;
                    for (int s = 0; s < state->nodes[ni].troop_slot_count; s++) {
                        if (state->nodes[ni].troop_slots[s] != SYM_NULL) continue;
                        char buf[128];
                        const char *sp_str = intern_str(source_player);
                        const char *tn_str = intern_str(trophy_idx_sym);
                        const char *nid_str = intern_str(nid);
                        snprintf(buf, sizeof(buf), "%.24s:%.16s:%.48s:%d",
                                 sp_str ? sp_str : "", tn_str ? tn_str : "",
                                 nid_str ? nid_str : "", s);
                        if (w >= max_out) { w++; continue; }
                        out[w].type = MOVE_RESOLVE_GENERIC;
                        out[w].data.resolve_generic.action_id = nid;
                        out[w].data.resolve_generic.target_id = intern(buf);
                        out[w].data.resolve_generic.selection_index = 0;
                        out[w].player_index = 0;
                        w++;
                    }
                }
            }
        } else if (strcmp(v, "lich_select_target_player") == 0) {
            Sym target_node = find_ls_sym(pending, "target_node_id");
            if (target_node == SYM_NULL) continue;
            int ni = -1;
            for (int n = 0; n < state->node_count; n++)
                if (state->nodes[n].node_id == target_node) { ni = n; break; }
            if (ni < 0) continue;
            Sym seen[4];
            int seen_count = 0;
            for (int s = 0; s < state->nodes[ni].troop_slot_count; s++) {
                Sym occ = state->nodes[ni].troop_slots[s];
                if (occ == SYM_NULL || occ == player_id) continue;
                const char *os = intern_str(occ);
                if (os && strcmp(os, "white") == 0) continue;
                int already = 0;
                for (int j = 0; j < seen_count; j++)
                    if (seen[j] == occ) { already = 1; break; }
                if (already) continue;
                if (seen_count < 4) seen[seen_count++] = occ;
                if (w >= max_out) { w++; continue; }
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = occ;
                out[w].data.resolve_generic.target_id = SYM_NULL;
                out[w].data.resolve_generic.selection_index = 0;
                out[w].player_index = 0;
                w++;
            }
        } else if (strcmp(v, "deploy_from_trophy_hall") == 0) {
            Sym source_player = SYM_NULL;
            const char *color_filter = NULL;
            for (int mi = 0; mi < action->metadata_count; mi++) {
                const char *mk = intern_str(action->metadata[mi].key);
                const char *mv = intern_str(action->metadata[mi].value);
                if (mk && strcmp(mk, "trophy_source_player") == 0 && mv) {
                    if (strcmp(mv, "lich_target_player") == 0)
                        source_player = find_ls_sym(pending, "source_player_id");
                }
                if (mk && strcmp(mk, "trophy_color_filter") == 0 && mv)
                    color_filter = mv;
            }
            if (source_player == SYM_NULL) continue;
            int spi = -1;
            for (int p = 0; p < state->player_count; p++)
                if (state->players[p].player_id == source_player) { spi = p; break; }
            if (spi < 0) continue;
            const PlayerState *sps = &state->players[spi];
            for (int ti = 0; ti < sps->trophy_hall_count; ti++) {
                Sym occ = sps->trophy_hall[ti];
                const char *oc = intern_str(occ);
                int is_white = oc && strcmp(oc, "white") == 0;
                if (color_filter && strcmp(color_filter, "white_only") == 0 && !is_white) continue;
                if (color_filter && strcmp(color_filter, "player_only") == 0 && is_white) continue;
                for (int ni2 = 0; ni2 < state->node_count; ni2++) {
                    Sym nid = state->nodes[ni2].node_id;
                    const NodeDefinition *nd = NULL;
                    for (int j = 0; j < state->definition->board.node_count; j++)
                        if (state->definition->board.nodes[j].node_id == nid)
                            { nd = &state->definition->board.nodes[j]; break; }
                    if (!nd || strcmp(intern_str(nd->kind), "site") != 0) continue;
                    for (int s = 0; s < state->nodes[ni2].troop_slot_count; s++) {
                        if (state->nodes[ni2].troop_slots[s] != SYM_NULL) continue;
                        char tbuf[128];
                        const char *sp_str = intern_str(source_player);
                        char idx_buf[16];
                        snprintf(idx_buf, sizeof(idx_buf), "%d", ti);
                        const char *nid_str = intern_str(nid);
                        snprintf(tbuf, sizeof(tbuf), "%.24s:%.16s:%.48s:%d",
                                 sp_str ? sp_str : "", idx_buf,
                                 nid_str ? nid_str : "", s);
                        if (w >= max_out) { w++; continue; }
                        out[w].type = MOVE_RESOLVE_GENERIC;
                        out[w].data.resolve_generic.action_id = nid;
                        out[w].data.resolve_generic.target_id = intern(tbuf);
                        out[w].data.resolve_generic.selection_index = 0;
                        out[w].player_index = 0;
                        w++;
                    }
                }
            }
        }
    }
    return w;
}

int legal_promote_card_moves(const GameState *state, Sym player_id,
                        const PendingGenericChoiceState *pending,
                        const CardDefinition *card, const CardAction *action,
                        Move *out, int max_out) {
    int w = 0;
    int pi = -1;
    for (int i = 0; i < state->player_count; i++)
        if (state->players[i].player_id == player_id) { pi = i; break; }
    if (pi < 0) return 0;
    const char *sf = intern_str(action->source_fragment);
    if (sf && strcmp(sf, "promote_from_discard") == 0) {
        for (int i = 0; i < state->players[pi].discard_pile_count; i++) {
            if (w >= max_out) { w++; continue; }
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = state->players[pi].discard_pile[i];
            out[w].player_index = 0;
            w++;
        }
    } else if (sf && strcmp(sf, "single_promote_from_multiple_zones") == 0) {
        Sym src = pending->source_card_id;
        for (int i = 0; i < state->players[pi].played_cards_count; i++) {
            if (state->players[pi].played_cards[i] == src) {
                if (w >= max_out) { w++; break; }
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = src;
                out[w].data.resolve_generic.target_id = intern("played");
                out[w].player_index = 0;
                w++;
                break;
            }
        }
        for (int i = 0; i < state->players[pi].hand_count; i++) {
            if (w >= max_out) { w++; continue; }
            out[w].type = MOVE_RESOLVE_GENERIC;
            char idx_buf[16];
            snprintf(idx_buf, sizeof(idx_buf), "%d", i);
            out[w].data.resolve_generic.action_id = intern(idx_buf);
            out[w].data.resolve_generic.target_id = intern("hand");
            out[w].player_index = 0;
            w++;
        }
        for (int i = 0; i < state->players[pi].discard_pile_count; i++) {
            if (w >= max_out) { w++; continue; }
            out[w].type = MOVE_RESOLVE_GENERIC;
            char idx_buf[16];
            snprintf(idx_buf, sizeof(idx_buf), "%d", i);
            out[w].data.resolve_generic.action_id = intern(idx_buf);
            out[w].data.resolve_generic.target_id = intern("discard");
            out[w].player_index = 0;
            w++;
        }
    } else {
        for (int i = 0; i < state->players[pi].played_cards_count; i++) {
            if (w >= max_out) { w++; continue; }
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = state->players[pi].played_cards[i];
            out[w].player_index = 0;
            w++;
        }
    }
    return w;
}

int devour_target_count(const GameState *state, Sym player_id,
                        const CardAction *action, int exclude_hand_index) {
    /* Resolve the source zone exactly like sel_devour: metadata.source_zone
     * wins, falling back to target_scope; known zones are market /
     * inner_circle / played_self, default is hand. */
    Sym zone = SYM_NULL;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        if (k && strcmp(k, "source_zone") == 0) { zone = action->metadata[i].value; break; }
    }
    if (zone == SYM_NULL) zone = action->target_scope;
    const char *z = intern_str(zone);

    if (z && strcmp(z, "market") == 0) {
        for (int i = 0; i < action->metadata_count; i++) {
            const char *k = intern_str(action->metadata[i].key);
            const char *v = intern_str(action->metadata[i].value);
            if (k && strcmp(k, "requires_last_selected_market_slot") == 0
                && v && strcmp(v, "true") == 0)
                return -1; /* dependent selection: always satisfiable */
        }
        return state->market.row_count;
    } else if (z && strcmp(z, "played_self") == 0) {
        return -1; /* always satisfiable: the played card itself is the target */
    } else if (z && strcmp(z, "inner_circle") == 0) {
        int pi = player_index_for_id(state, player_id);
        if (pi < 0) return 0;
        return state->players[pi].inner_circle_count;
    } else {
        /* Default: hand. */
        int pi = player_index_for_id(state, player_id);
        if (pi < 0) return 0;
        int count = state->players[pi].hand_count;
        if (exclude_hand_index >= 0 && exclude_hand_index < state->players[pi].hand_count)
            count--;
        return count;
    }
}

int legal_devour_moves(const GameState *state, Sym player_id,
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
            if (prev_card != SYM_NULL) {
                if (w < max_out) {
                    out[w].type = MOVE_RESOLVE_GENERIC;
                    out[w].data.resolve_generic.action_id = prev_card;
                    out[w].player_index = 0;
                }
                w++;
            }
        } else {
            for (int s = 0; s < state->market.row_count; s++) {
                if (w >= max_out) { w++; continue; }
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = state->market.row[s];
                out[w].player_index = 0;
                w++;
            }
        }
    } else if (z && strcmp(z, "inner_circle") == 0) {
        /* Devour from the player's inner circle. */
        for (int ic = 0; ic < state->players[pi].inner_circle_count; ic++) {
            if (w >= max_out) { w++; continue; }
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = state->players[pi].inner_circle[ic];
            out[w].player_index = 0;
            w++;
        }
    } else if (z && strcmp(z, "played_self") == 0) {
        /* Devour the card that was just played (self-devour). */
        if (pending->source_card_id != SYM_NULL) {
            if (w < max_out) {
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = pending->source_card_id;
                out[w].player_index = 0;
            }
            w++;
        }
    } else {
        /* Default: devour from the player's hand. */
        for (int h = 0; h < state->players[pi].hand_count; h++) {
            if (w >= max_out) { w++; continue; }
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = state->players[pi].hand[h];
            out[w].player_index = 0;
            w++;
        }
    }
    return w;
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
    const CardOp *op = card_op_for(action);
    if (op && op->enumerate)
        return op->enumerate(state, player_id, pending, card, action, out, max_out);

    for (int i = 0; i < sel_dispatch_count; i++) {
        if (sel_op_keys[i] == action->op && sel_dispatch[i])
            return sel_dispatch[i](state, player_id, pending, card, action, out, max_out);
    }
    return 0;
}

void register_selection_handlers(void) {
    register_sel(intern("custom_effect"), sel_custom_effect);
}

