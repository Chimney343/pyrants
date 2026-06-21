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
            return intern_str(owner);
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
            snprintf(buf, sizeof(buf), "Remove %s troop from %s", owner, label);
            break;
        }
        case MOVE_RECRUIT: {
            const char *name = card_name_for(state, move->data.recruit.card_id);
            snprintf(buf, sizeof(buf), "Recruit %s", name);
            break;
        }
        case MOVE_RETURN_SPY: {
            const char *owner = intern_str(move->data.return_spy.spy_owner_id);
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
        case MOVE_SKIP_PROMOTE:
            snprintf(buf, sizeof(buf), "Skip promotion");
            break;
        case MOVE_RESOLVE_GENERIC: {
            Sym aid = move->data.resolve_generic.action_id;
            if (aid == SYM_NULL) {
                snprintf(buf, sizeof(buf), "Skip (resign)");
            } else if (state && state->pending_generic) {
                const CardAction *act = pending_generic_active_action(state->pending_generic);
                if (act) {
                    const char *op = intern_str(act->op);
                    if (op && (strcmp(op, "devour") == 0 || strcmp(op, "devour_cost") == 0)) {
                        const char *name = card_name_for(state, aid);
                        snprintf(buf, sizeof(buf), "Devour %s", name);
                    } else if (op && strcmp(op, "promote_card") == 0) {
                        const char *name = card_name_for(state, aid);
                        snprintf(buf, sizeof(buf), "Promote %s", name);
                    } else if (op && strcmp(op, "recruit_card") == 0) {
                        const char *name = card_name_for(state, aid);
                        snprintf(buf, sizeof(buf), "Recruit %s", name);
                    } else if (op && strcmp(op, "assassinate_troop") == 0) {
                        Sym tid = move->data.resolve_generic.target_id;
                        int slot_idx = 0;
                        if (tid != SYM_NULL) {
                            const char *ts = intern_str(tid);
                            if (ts) slot_idx = atoi(ts);
                        }
                        const char *owner = troop_owner_label(state, aid, slot_idx);
                        const char *label = node_label(intern_str(aid), node_ids, node_labels, node_pair_count);
                        snprintf(buf, sizeof(buf), "Remove %s troop from %s", owner, label);
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
                        if (ts && strncmp(ts, "troop:", 6) == 0) {
                            snprintf(buf, sizeof(buf), "Return troop from %s", label);
                        } else if (ts && strncmp(ts, "spy:", 4) == 0) {
                            snprintf(buf, sizeof(buf), "Return spy from %s", label);
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
                    } else {
                        const char *name = card_name_for(state, aid);
                        snprintf(buf, sizeof(buf), "Resolve %s", name);
                    }
                } else {
                    const char *name = card_name_for(state, aid);
                    snprintf(buf, sizeof(buf), "Resolve %s", name);
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
