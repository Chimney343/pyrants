#include "describe.h"
#include "generic_runtime.h"
#include "intern.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *card_name_for(const GameState *state, Sym card_id) {
    if (!state || !state->definition) return "Unknown Card";
    const CardCatalog *cat = &state->definition->catalog;
    for (int i = 0; i < cat->card_count; i++) {
        if (cat->cards[i].card_id == card_id) {
            return intern_str(cat->cards[i].name);
        }
    }
    return "Unknown Card";
}

static const char *_humanize_id(const char *id_str) {
    static char buf[128];
    if (!id_str || !*id_str) {
        buf[0] = '\0';
        return buf;
    }
    int di = 0;
    int cap = (int)sizeof(buf) - 1;
    for (const char *s = id_str; *s && di < cap; s++) {
        if (*s == '_') {
            buf[di++] = ' ';
        } else if (s == id_str) {
            buf[di++] = (char)toupper((unsigned char)*s);
        } else {
            buf[di++] = *s;
        }
    }
    buf[di] = '\0';
    return buf;
}

static const char *_player_label(const char *id_str) {
    if (id_str && (id_str[0]=='p'||id_str[0]=='P') && id_str[1]>='0' && id_str[1]<='9') {
        static char buf[32];
        snprintf(buf, sizeof(buf), "Player %s", id_str+1);
        return buf;
    }
    return id_str ? id_str : "unknown";
}

static const char *node_label(const char *node_id_str,
                              const char *const *node_ids,
                              const char *const *node_labels,
                              int node_pair_count) {
    if (node_ids && node_labels && node_pair_count > 0) {
        for (int i = 0; i < node_pair_count; i++) {
            if (!node_ids[i] || !node_labels[i]) continue;
            if (strcmp(node_ids[i], node_id_str) == 0) return node_labels[i];
        }
    }
    return _humanize_id(node_id_str);
}

static const char *troop_owner_label(const GameState *state, Sym node_id, int slot_index) {
    if (!state) return "unknown";
    for (int i = 0; i < state->node_count; i++) {
        if (state->nodes[i].node_id == node_id) {
            const NodeState *ns = &state->nodes[i];
            if (slot_index < 0 || slot_index >= ns->troop_slot_count) return "unknown";
            Sym owner = ns->troop_slots[slot_index];
            if (owner == SYM_NULL) return "empty";
            return _player_label(intern_str(owner));
        }
    }
    return "unknown";
}

int engine_describe_move(const GameState *state, const Move *move,
                         const char *const *node_ids, const char *const *node_labels,
                         int node_pair_count,
                         char *out, int out_cap) {
    if (!move) return 0;

    char buf[256];
    buf[0] = '\0';

    switch (move->type) {
        case MOVE_PLAY_CARD: {
            const char *name = card_name_for(state, move->data.play_card.card_id);
            snprintf(buf, sizeof(buf), "Play %s", name);
            break;
        }
        case MOVE_END_MAIN_PHASE:
            snprintf(buf, sizeof(buf), "End main phase");
            break;
        case MOVE_RESOLVE_END_OF_TURN:
            snprintf(buf, sizeof(buf), "Proceed to end of turn");
            break;
        case MOVE_RESOLVE_CLEANUP:
            snprintf(buf, sizeof(buf), "Proceed to cleanup");
            break;
        case MOVE_DEPLOY: {
            if (move->data.deploy.node_id == SYM_NULL) {
                snprintf(buf, sizeof(buf),
                         "Barracks empty; gain 1 VP token instead of deploying a troop");
                break;
            }
            const char *nid = intern_str(move->data.deploy.node_id);
            const char *label = node_label(nid, node_ids, node_labels, node_pair_count);
            snprintf(buf, sizeof(buf), "Deploy a troop to %s", label);
            break;
        }
        case MOVE_INITIAL_PLACEMENT: {
            const char *nid = intern_str(move->data.initial_placement.node_id);
            const char *label = node_label(nid, node_ids, node_labels, node_pair_count);
            snprintf(buf, sizeof(buf), "Place starting troop at %s", label);
            break;
        }
        case MOVE_ASSASSINATE: {
            const char *owner = troop_owner_label(state, move->data.assassinate.target_node_id,
                                                   move->data.assassinate.slot_index);
            const char *nid = intern_str(move->data.assassinate.target_node_id);
            const char *label = node_label(nid, node_ids, node_labels, node_pair_count);
            snprintf(buf, sizeof(buf), "Assassinate %s troop at %s", owner, label);
            break;
        }
        case MOVE_RECRUIT: {
            const char *name = card_name_for(state, move->data.recruit.card_id);
            snprintf(buf, sizeof(buf), "Recruit %s", name);
            break;
        }
        case MOVE_RETURN_SPY: {
            const char *owner = _player_label(intern_str(move->data.return_spy.spy_owner_id));
            const char *nid = intern_str(move->data.return_spy.node_id);
            const char *label = node_label(nid, node_ids, node_labels, node_pair_count);
            snprintf(buf, sizeof(buf), "Return %s's spy from %s", owner, label);
            break;
        }
        case MOVE_ACTIVATE_ABILITY: {
            const char *key = intern_str(move->data.activate_ability.ability_key);
            snprintf(buf, sizeof(buf), "Activate %s", key);
            break;
        }
        case MOVE_DECLINE_ABILITY: {
            const char *key = intern_str(move->data.decline_ability.ability_key);
            snprintf(buf, sizeof(buf), "Decline %s", key);
            break;
        }
        case MOVE_PROMOTE_CARD: {
            const char *name = card_name_for(state, move->data.promote_card.card_id);
            snprintf(buf, sizeof(buf), "Promote %s", name);
            break;
        }
        case MOVE_SKIP_PROMOTE: {
            const char *name = card_name_for(state, move->data.skip_promote.source_card_id);
            snprintf(buf, sizeof(buf), "Skip promotion (%s)", name);
            break;
        }
        case MOVE_RESOLVE_GENERIC: {
            Sym aid = move->data.resolve_generic.action_id;
            if (aid == SYM_NULL) {
                const CardAction *act = (state && state->pending_generic)
                    ? pending_generic_active_action(state->pending_generic) : NULL;
                const char *op = act ? intern_str(act->op) : NULL;
                if (op && strcmp(op, "deploy_troops") == 0) {
                    snprintf(buf, sizeof(buf),
                             "Barracks empty; gain 1 VP token instead of deploying a troop");
                } else {
                    snprintf(buf, sizeof(buf), "Skip");
                }
            } else if (state && state->pending_generic) {
                const CardAction *act = pending_generic_active_action(state->pending_generic);
                if (act) {
                    const char *op = intern_str(act->op);
                    if (op && (strcmp(op, "devour") == 0 || strcmp(op, "devour_cost") == 0)) {
                        const char *name = card_name_for(state, aid);
                        snprintf(buf, sizeof(buf), "Devour %s", name);
                    } else if (op && strcmp(op, "promote_card") == 0) {
                        const char *sf = intern_str(act->source_fragment);
                        Sym tid = move->data.resolve_generic.target_id;
                        if (sf && strcmp(sf, "single_promote_from_multiple_zones") == 0 && tid != SYM_NULL) {
                            const char *sz = intern_str(tid);
                            const char *name = "?";
                            int pi = -1;
                            for (int i = 0; i < state->player_count; i++)
                                if (state->players[i].player_id == state->current_player_id) { pi = i; break; }
                            const char *zone_label = "?";
                            if (sz && pi >= 0) {
                                if (strcmp(sz, "played") == 0) {
                                    name = card_name_for(state, aid);
                                    zone_label = "played";
                                } else if (strcmp(sz, "hand") == 0) {
                                    const char *ais = intern_str(aid);
                                    int idx = ais ? atoi(ais) : -1;
                                    if (idx >= 0 && idx < state->players[pi].hand_count)
                                        name = card_name_for(state, state->players[pi].hand[idx]);
                                    zone_label = "hand";
                                } else if (strcmp(sz, "discard") == 0) {
                                    const char *ais = intern_str(aid);
                                    int idx = ais ? atoi(ais) : -1;
                                    if (idx >= 0 && idx < state->players[pi].discard_pile_count)
                                        name = card_name_for(state, state->players[pi].discard_pile[idx]);
                                    zone_label = "discard";
                                }
                            }
                            snprintf(buf, sizeof(buf), "Promote %s (%s)", name, zone_label);
                        } else {
                            const char *name = card_name_for(state, aid);
                            snprintf(buf, sizeof(buf), "Promote %s", name);
                        }
                    } else if (op && strcmp(op, "recruit_card") == 0) {
                        const char *name = card_name_for(state, aid);
                        snprintf(buf, sizeof(buf), "Recruit %s", name);
                    } else if (op && strcmp(op, "place_spy") == 0) {
                        Sym tid = move->data.resolve_generic.target_id;
                        const char *dst_label = node_label(intern_str(aid), node_ids, node_labels, node_pair_count);
                        if (tid != SYM_NULL) {
                            const char *src_label = node_label(intern_str(tid), node_ids, node_labels, node_pair_count);
                            snprintf(buf, sizeof(buf), "Move your spy from %s to %s", src_label, dst_label);
                        } else {
                            snprintf(buf, sizeof(buf), "Place a spy at %s", dst_label);
                        }
                    } else if (op && strcmp(op, "assassinate_troop") == 0) {
                        Sym tid = move->data.resolve_generic.target_id;
                        int slot_idx = 0;
                        if (tid != SYM_NULL) {
                            const char *ts = intern_str(tid);
                            if (ts) slot_idx = atoi(ts);
                        }
                        const char *owner = troop_owner_label(state, aid, slot_idx);
                        const char *label = node_label(intern_str(aid), node_ids, node_labels, node_pair_count);
                        snprintf(buf, sizeof(buf), "Assassinate %s troop at %s", owner, label);
                    } else if (op && strcmp(op, "supplant_troop") == 0) {
                        Sym tid = move->data.resolve_generic.target_id;
                        int slot_idx = 0;
                        if (tid != SYM_NULL) {
                            const char *ts = intern_str(tid);
                            if (ts) slot_idx = atoi(ts);
                        }
                        const char *owner = troop_owner_label(state, aid, slot_idx);
                        const char *label = node_label(intern_str(aid), node_ids, node_labels, node_pair_count);
                        snprintf(buf, sizeof(buf), "Supplant %s troop at %s", owner, label);
                    } else if (op && strcmp(op, "return_unit") == 0) {
                        Sym tid = move->data.resolve_generic.target_id;
                        const char *label = node_label(intern_str(aid), node_ids, node_labels, node_pair_count);
                        const char *ts = tid != SYM_NULL ? intern_str(tid) : NULL;
                        if (ts) {
                            int ts_len = (int)strlen(ts);
                            if (ts_len > 6 && (ts[0] == 't' || ts[0] == 'T')
                                && (ts[1] == 'r' || ts[1] == 'R')
                                && (ts[2] == 'o' || ts[2] == 'O')
                                && (ts[3] == 'o' || ts[3] == 'O')
                                && (ts[4] == 'p' || ts[4] == 'P')
                                && ts[5] == ':') {
                                int slot_idx = atoi(ts + 6);
                                const char *owner = troop_owner_label(state, aid, slot_idx);
                                snprintf(buf, sizeof(buf), "Return %s's troop from %s", owner, label);
                            } else if (ts_len > 4 && (ts[0] == 's' || ts[0] == 'S')
                                && (ts[1] == 'p' || ts[1] == 'P')
                                && (ts[2] == 'y' || ts[2] == 'Y')
                                && ts[3] == ':') {
                                const char *spy_owner = _player_label(ts + 4);
                                snprintf(buf, sizeof(buf), "Return %s's spy from %s", spy_owner, label);
                            } else {
                                snprintf(buf, sizeof(buf), "Return unit from %s", label);
                            }
                        } else {
                            snprintf(buf, sizeof(buf), "Return unit from %s", label);
                        }
                    } else if (op && strcmp(op, "move_troop") == 0) {
                        Sym tid = move->data.resolve_generic.target_id;
                        const char *owner = troop_owner_label(state, aid, 0);
                        const char *src_label = node_label(intern_str(aid), node_ids, node_labels, node_pair_count);
                        if (tid != SYM_NULL) {
                            const char *ts = intern_str(tid);
                            if (ts) {
                                int src_si = atoi(ts);
                                const char *colon1 = strchr(ts, ':');
                                char dst_buf[64] = "";
                                if (colon1) {
                                    const char *dst_str = colon1 + 1;
                                    const char *colon2 = strchr(dst_str, ':');
                                    if (colon2) {
                                        int dst_len = (int)(colon2 - dst_str);
                                        if (dst_len > 0 && dst_len < (int)sizeof(dst_buf)) {
                                            memcpy(dst_buf, dst_str, (size_t)dst_len);
                                            dst_buf[dst_len] = '\0';
                                        }
                                    }
                                }
                                const char *dst_label = node_label(dst_buf, node_ids, node_labels, node_pair_count);
                                const char *real_owner = troop_owner_label(state, aid, src_si);
                                snprintf(buf, sizeof(buf), "Move %s troop from %s to %s", real_owner, src_label, dst_label);
                            } else {
                                snprintf(buf, sizeof(buf), "Move %s troop from %s", owner, src_label);
                            }
                        } else {
                            snprintf(buf, sizeof(buf), "Move %s troop from %s", owner, src_label);
                        }
                    } else if (op && strcmp(op, "custom_effect") == 0) {
                        const char *effect_kind = NULL;
                        for (int mi = 0; mi < act->metadata_count; mi++) {
                            const char *mk = intern_str(act->metadata[mi].key);
                            const char *mv = intern_str(act->metadata[mi].value);
                            if (mk && strcmp(mk, "effect_kind") == 0 && mv) {
                                effect_kind = mv;
                                break;
                            }
                        }
                        if (effect_kind && strcmp(effect_kind, "select_trophy_hall") == 0) {
                            Sym tid = move->data.resolve_generic.target_id;
                            int trophy_idx = 0;
                            if (tid != SYM_NULL) {
                                const char *ts = intern_str(tid);
                                if (ts) trophy_idx = atoi(ts);
                            }
                            char sp_label_buf[32];
                            snprintf(sp_label_buf, sizeof(sp_label_buf), "%s", _player_label(intern_str(aid)));
                            const char *trophy_type = "troop";
                            for (int p = 0; p < state->player_count; p++) {
                                if (state->players[p].player_id == aid) {
                                    if (trophy_idx >= 0 && trophy_idx < state->players[p].trophy_hall_count) {
                                        Sym occ = state->players[p].trophy_hall[trophy_idx];
                                        const char *oc = intern_str(occ);
                                        if (oc && strcmp(oc, "white") == 0) trophy_type = "white";
                                        else if (oc) {
                                            char tt_buf[32];
                                            snprintf(tt_buf, sizeof(tt_buf), "%s", _player_label(oc));
                                            trophy_type = tt_buf;
                                        }
                                    }
                                    break;
                                }
                            }
                            snprintf(buf, sizeof(buf), "Take %s trophy from %s trophy hall",
                                     trophy_type, sp_label_buf);
                        } else if (effect_kind && strcmp(effect_kind, "steal_from_selected_trophy") == 0) {
                            Sym tid = move->data.resolve_generic.target_id;
                            const char *nid_str = intern_str(aid);
                            char nl_buf[64];
                            snprintf(nl_buf, sizeof(nl_buf), "%s", node_label(nid_str, node_ids, node_labels, node_pair_count));
                            char trophy_type_buf[32] = "troop";
                            if (tid != SYM_NULL) {
                                const char *ts = intern_str(tid);
                                if (ts) {
                                    const char *c1 = strchr(ts, ':');
                                    const char *c2 = c1 ? strchr(c1 + 1, ':') : NULL;
                                    if (c1 && c2) {
                                        int sp_len = (int)(c1 - ts);
                                        char sp_buf[32];
                                        if (sp_len > 0 && sp_len < (int)sizeof(sp_buf)) {
                                            memcpy(sp_buf, ts, (size_t)sp_len);
                                            sp_buf[sp_len] = '\0';
                                            Sym sp_sym = intern(sp_buf);
                                            for (int p = 0; p < state->player_count; p++) {
                                                if (state->players[p].player_id == sp_sym) {
                                                    int c1_plus_nul = (int)(c2 - c1 - 1);
                                                    char idx_buf[16];
                                                    if (c1_plus_nul > 0 && c1_plus_nul < (int)sizeof(idx_buf)) {
                                                        memcpy(idx_buf, c1 + 1, (size_t)c1_plus_nul);
                                                        idx_buf[c1_plus_nul] = '\0';
                                                        int ti = atoi(idx_buf);
                                                        if (ti >= 0 && ti < state->players[p].trophy_hall_count) {
                                                            Sym occ = state->players[p].trophy_hall[ti];
                                                            const char *oc = intern_str(occ);
                                                            if (oc && strcmp(oc, "white") == 0)
                                                                snprintf(trophy_type_buf, sizeof(trophy_type_buf), "white");
                                                            else if (oc)
                                                                snprintf(trophy_type_buf, sizeof(trophy_type_buf), "%s", _player_label(oc));
                                                        }
                                                    }
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            snprintf(buf, sizeof(buf), "Place %s trophy at %s", trophy_type_buf, nl_buf);
                        } else if (effect_kind && strcmp(effect_kind, "steal_white_trophy_to_board") == 0) {
                            Sym tid = move->data.resolve_generic.target_id;
                            const char *ts = tid != SYM_NULL ? intern_str(tid) : NULL;
                            if (ts && strchr(ts, ':')) {
                                const char *nid_str = intern_str(aid);
                                char nl_buf[64];
                                snprintf(nl_buf, sizeof(nl_buf), "%s",
                                         node_label(nid_str, node_ids, node_labels, node_pair_count));
                                snprintf(buf, sizeof(buf), "Place white trophy at %s", nl_buf);
                            } else {
                                char sp_label_buf[32];
                                snprintf(sp_label_buf, sizeof(sp_label_buf), "%s",
                                         _player_label(intern_str(aid)));
                                snprintf(buf, sizeof(buf), "Take white trophy from %s trophy hall",
                                         sp_label_buf);
                            }
                        } else if (effect_kind && strcmp(effect_kind, "lich_select_target_player") == 0) {
                            char tgt_buf[32];
                            snprintf(tgt_buf, sizeof(tgt_buf), "%s", _player_label(intern_str(aid)));
                            snprintf(buf, sizeof(buf), "Choose %s as trophy source", tgt_buf);
                        } else if (effect_kind && strcmp(effect_kind, "select_site") == 0) {
                            const char *nid_str = intern_str(aid);
                            char nl_buf[64];
                            snprintf(nl_buf, sizeof(nl_buf), "%s", node_label(nid_str, node_ids, node_labels, node_pair_count));
                            snprintf(buf, sizeof(buf), "Choose %s", nl_buf);
                        } else if (effect_kind && (strcmp(effect_kind, "deploy_from_trophy_hall") == 0 ||
                                                    strcmp(effect_kind, "deploy_white_from_trophy_hall_with_presence") == 0)) {
                            Sym tid = move->data.resolve_generic.target_id;
                            const char *nid_str = intern_str(aid);
                            char nl_buf[64];
                            snprintf(nl_buf, sizeof(nl_buf), "%s", node_label(nid_str, node_ids, node_labels, node_pair_count));
                            char trophy_type_buf[32] = "troop";
                            char src_buf[32] = "";
                            if (tid != SYM_NULL) {
                                const char *ts = intern_str(tid);
                                if (ts) {
                                    const char *c1 = strchr(ts, ':');
                                    const char *c2 = c1 ? strchr(c1 + 1, ':') : NULL;
                                    if (c1 && c2) {
                                        int sp_len = (int)(c1 - ts);
                                        if (sp_len > 0 && sp_len < (int)sizeof(src_buf)) {
                                            memcpy(src_buf, ts, (size_t)sp_len);
                                            src_buf[sp_len] = '\0';
                                            char src_label_buf[32];
                                            snprintf(src_label_buf, sizeof(src_label_buf), "%s", _player_label(src_buf));
                                            snprintf(src_buf, sizeof(src_buf), "%s", src_label_buf);
                                        }
                                        int c1_plus_nul = (int)(c2 - c1 - 1);
                                        char idx_buf[16];
                                        if (c1_plus_nul > 0 && c1_plus_nul < (int)sizeof(idx_buf)) {
                                            memcpy(idx_buf, c1 + 1, (size_t)c1_plus_nul);
                                            idx_buf[c1_plus_nul] = '\0';
                                            int ti = atoi(idx_buf);
                                            char sp_buf2[32];
                                            if (sp_len > 0 && sp_len < (int)sizeof(sp_buf2)) {
                                                memcpy(sp_buf2, ts, (size_t)sp_len);
                                                sp_buf2[sp_len] = '\0';
                                                Sym sp_sym = intern(sp_buf2);
                                                for (int p = 0; p < state->player_count; p++) {
                                                    if (state->players[p].player_id == sp_sym
                                                        && ti >= 0 && ti < state->players[p].trophy_hall_count) {
                                                        Sym occ = state->players[p].trophy_hall[ti];
                                                        const char *oc = intern_str(occ);
                                                        if (oc && strcmp(oc, "white") == 0)
                                                            snprintf(trophy_type_buf, sizeof(trophy_type_buf), "white");
                                                        else if (oc)
                                                            snprintf(trophy_type_buf, sizeof(trophy_type_buf), "%s", _player_label(oc));
                                                        break;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            snprintf(buf, sizeof(buf), "Deploy %s from %s to %s", trophy_type_buf, src_buf[0] ? src_buf : "trophy hall", nl_buf);
                        } else if (effect_kind && strcmp(effect_kind, "self_purge_to_supply") == 0) {
                            const char *card_name = card_name_for(state, aid);
                            const char *source_name = card_name_for(state, state->pending_generic->source_card_id);
                            snprintf(buf, sizeof(buf), "Discard %s to return %s to supply", card_name, source_name);
                        } else {
                            const char *name = card_name_for(state, aid);
                            snprintf(buf, sizeof(buf), "Resolve %s", name);
                        }
                    } else {
                        const char *name = card_name_for(state, aid);
                        snprintf(buf, sizeof(buf), "Resolve %s", name);
                    }
                } else {
                    if (state->pending_generic->awaiting_option) {
                        PendingGenericChoiceState *pg = state->pending_generic;
                        const CardCatalog *cat = &state->definition->catalog;
                        for (int i = 0; i < cat->card_count; i++) {
                            if (cat->cards[i].card_id == pg->source_card_id) {
                                const CardDefinition *card = &cat->cards[i];
                                if (card->execution.kind == EXEC_MODAL || card->execution.kind == EXEC_REPEAT) {
                                    for (int oi = 0; oi < card->execution.option_count; oi++) {
                                        const CardOption *opt = &card->execution.options[oi];
                                        if (opt->option_id == aid) {
                                            if (opt->action_count == 1) {
                                                const CardAction *a = &opt->actions[0];
                                                const char *op = intern_str(a->op);
                                                if (op && strcmp(op, "gain_resource") == 0) {
                                                    int count = a->quantity_kind == QUANT_FIXED ? a->quantity_value : 1;
                                                    const char *res = "resource";
                                                    for (int mi = 0; mi < a->metadata_count; mi++) {
                                                        const char *mk = intern_str(a->metadata[mi].key);
                                                        if (mk && strcmp(mk, "resource") == 0) {
                                                            const char *mv = intern_str(a->metadata[mi].value);
                                                            if (mv) res = mv;
                                                        }
                                                    }
                                                    snprintf(buf, sizeof(buf), "Gain %d %s", count, res);
                                                } else if (op && strcmp(op, "draw_cards") == 0) {
                                                    int count = a->quantity_kind == QUANT_FIXED ? a->quantity_value : 1;
                                                    snprintf(buf, sizeof(buf), "Draw %d card%s", count, count == 1 ? "" : "s");
                                                } else if (op && strcmp(op, "place_spy") == 0) {
                                                    snprintf(buf, sizeof(buf), "Place a spy");
                                                } else {
                                                    snprintf(buf, sizeof(buf), "%s", _humanize_id(intern_str(opt->option_id)));
                                                }
                                            } else {
                                                char part_buf[128];
                                                buf[0] = '\0';
                                                for (int ai = 0; ai < opt->action_count && ai < 4; ai++) {
                                                    const CardAction *a = &opt->actions[ai];
                                                    const char *op = intern_str(a->op);
                                                    if (!op) continue;
                                                    if (strcmp(op, "return_spy") == 0) {
                                                        snprintf(part_buf, sizeof(part_buf), "Return a spy");
                                                    } else if (strcmp(op, "custom_effect") == 0) {
                                                        const char *ek = NULL;
                                                        for (int mi = 0; mi < a->metadata_count; mi++) {
                                                            const char *mk = intern_str(a->metadata[mi].key);
                                                            const char *mv = intern_str(a->metadata[mi].value);
                                                            if (mk && strcmp(mk, "effect_kind") == 0 && mv) { ek = mv; break; }
                                                        }
                                                        if (ek && strcmp(ek, "take_from_devour_pile_to_discard") == 0)
                                                            snprintf(part_buf, sizeof(part_buf), "take from devour pile");
                                                        else if (ek && strcmp(ek, "steal_white_trophy_to_board") == 0)
                                                            snprintf(part_buf, sizeof(part_buf), "take a white trophy and deploy it");
                                                        else if (ek && strcmp(ek, "select_site") == 0) {
                                                            int white_only = 0;
                                                            for (int fi = 0; fi < a->filter_count; fi++) {
                                                                const char *fl = intern_str(a->filters[fi]);
                                                                if (fl && strcmp(fl, "white_troop_only") == 0) { white_only = 1; break; }
                                                            }
                                                            snprintf(part_buf, sizeof(part_buf),
                                                                     white_only ? "Choose a site with a white troop"
                                                                                : "Choose a site");
                                                        } else
                                                            snprintf(part_buf, sizeof(part_buf), "%s", _humanize_id(op));
                                                    } else {
                                                        snprintf(part_buf, sizeof(part_buf), "%s", _humanize_id(op));
                                                    }
                                                    if (buf[0] != '\0') {
                                                        size_t cur = strlen(buf);
                                                        snprintf(buf + cur, sizeof(buf) - cur, " & %s", part_buf);
                                                    } else {
                                                        snprintf(buf, sizeof(buf), "%s", part_buf);
                                                    }
                                                }
                                                if (buf[0] == '\0')
                                                    snprintf(buf, sizeof(buf), "%s", _humanize_id(intern_str(opt->option_id)));
                                            }
                                            break;
                                        }
                                    }
                                }
                                break;
                            }
                        }
                        if (buf[0] == '\0') {
                            snprintf(buf, sizeof(buf), "Resolve %s", _humanize_id(intern_str(aid)));
                        }
                    } else {
                        const char *name = card_name_for(state, aid);
                        snprintf(buf, sizeof(buf), "Resolve %s", name);
                    }
                }
            } else {
                const char *aid_str = intern_str(aid);
                snprintf(buf, sizeof(buf), "Resolve %s", aid_str ? aid_str : "?");
            }
            break;
        }
        default:
            snprintf(buf, sizeof(buf), "Unknown move (type %d)", (int)move->type);
            break;
    }

    int needed = (int)strlen(buf) + 1;
    if (out && out_cap > 0) {
        int copy = needed < out_cap ? needed : out_cap;
        memcpy(out, buf, (size_t)copy);
        out[out_cap - 1] = '\0';
    }
    return needed;
}
