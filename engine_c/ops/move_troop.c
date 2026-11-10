#include "op.h"
#include "describe.h"
#include "helpers.h"
#include "intern.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int op_move_troop_enumerate(const GameState *state, Sym player_id,
                                   const PendingGenericChoiceState *pending,
                                   const CardDefinition *card, const CardAction *action,
                                   Move *out, int max_out) {
    (void)pending; (void)card;
    int w = 0;
    int requires_presence = 1;
    int allow_white = 0, white_only = 0;
    for (int i = 0; i < action->filter_count; i++) {
        const char *f = intern_str(action->filters[i]);
        if (f && strcmp(f, "allow_white_troop") == 0) allow_white = 1;
        if (f && strcmp(f, "white_troop_only") == 0) white_only = 1;
    }
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "ignore_presence_requirement") == 0 && v
            && strcmp(v, "true") == 0)
            requires_presence = 0;
    }
    for (int si = 0; si < state->node_count; si++) {
        Sym src = state->nodes[si].node_id;
        if (requires_presence && !has_presence(state, player_id, src)) continue;
        for (int ss = 0; ss < state->nodes[si].troop_slot_count; ss++) {
            Sym occ = state->nodes[si].troop_slots[ss];
            if (occ == SYM_NULL || occ == player_id) continue;
            const char *os = intern_str(occ);
            int is_white = (os && strcmp(os, "white") == 0);
            if (white_only && !is_white) continue;
            if (!allow_white && is_white) continue;
            for (int di = 0; di < state->node_count; di++) {
                if (di == si) continue;
                for (int ts = 0; ts < state->nodes[di].troop_slot_count; ts++) {
                    if (state->nodes[di].troop_slots[ts] != SYM_NULL) continue;
                    const char *dst_str = intern_str(state->nodes[di].node_id);
                    char buf[128];
                    snprintf(buf, sizeof(buf), "%d:%s:%d", ss, dst_str ? dst_str : "?", ts);
                    if (w >= max_out) { w++; continue; }
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

static int op_move_troop_target(const GameState *state, Sym player_id,
                                const CardAction *action, const Move *move,
                                OpTarget *out) {
    (void)state; (void)player_id; (void)action;
    Sym source = move->data.resolve_generic.action_id;
    Sym tid = move->data.resolve_generic.target_id;
    if (source == SYM_NULL || tid == SYM_NULL) return 0;
    const char *ts = intern_str(tid);
    if (!ts) return 0;
    const char *c1 = strchr(ts, ':');
    const char *c2 = c1 ? strchr(c1 + 1, ':') : NULL;
    if (!c1 || !c2) return 0;
    int src_len = (int)(c1 - ts);
    int node_len = (int)(c2 - c1 - 1);
    char node_buf[64];
    if (src_len <= 0 || node_len <= 0 || node_len >= (int)sizeof(node_buf)) return 0;
    memcpy(node_buf, c1 + 1, (size_t)node_len);
    node_buf[node_len] = '\0';

    out->kind = OP_TARGET_MOVE_TROOP;
    out->as.move_troop.source_node_id = source;
    out->as.move_troop.source_slot_index = atoi(ts);
    out->as.move_troop.target_node_id = intern(node_buf);
    out->as.move_troop.target_slot_index = atoi(c2 + 1);
    return 1;
}

static GameState *op_move_troop_apply(GameState *state, Sym player_id,
                                      const CardDefinition *card,
                                      const CardAction *action,
                                      const OpTarget *target) {
    (void)card;
    if (!target || target->kind != OP_TARGET_MOVE_TROOP) return state;
    Sym src_node = target->as.move_troop.source_node_id;
    Sym dst_node = target->as.move_troop.target_node_id;
    int src_slot = target->as.move_troop.source_slot_index;
    int dst_slot = target->as.move_troop.target_slot_index;
    if (src_node == SYM_NULL || dst_node == SYM_NULL || src_slot < 0 || dst_slot < 0)
        return state;

    NodeState *nss = cow_node(state, src_node);
    NodeState *nsd = cow_node(state, dst_node);
    if (!nss || !nsd) return state;
    if (src_slot >= nss->troop_slot_count || dst_slot >= nsd->troop_slot_count)
        return state;
    Sym occ = nss->troop_slots[src_slot];
    if (occ == SYM_NULL || occ == player_id) return state;
    if (nsd->troop_slots[dst_slot] != SYM_NULL) return state;

    nss->troop_slots[src_slot] = SYM_NULL;
    nsd->troop_slots[dst_slot] = occ;
    if (state->pending_generic)
        increment_pending_counter(state->pending_generic, action);
    return state;
}

static const char *troop_owner_label(const GameState *state, Sym node_id, int slot_index) {
    if (!state) return "unknown";
    for (int i = 0; i < state->node_count; i++) {
        if (state->nodes[i].node_id != node_id) continue;
        const NodeState *ns = &state->nodes[i];
        if (slot_index < 0 || slot_index >= ns->troop_slot_count) return "unknown";
        Sym owner = ns->troop_slots[slot_index];
        if (owner == SYM_NULL) return "empty";
        return engine_player_label(intern_str(owner));
    }
    return "unknown";
}

static void op_move_troop_describe(const GameState *state, const CardAction *action,
                                   const OpTarget *target,
                                   const char *const *node_ids, const char *const *node_labels,
                                   int node_pair_count, char *buf, size_t cap) {
    (void)action;
    if (!target || target->kind != OP_TARGET_MOVE_TROOP) {
        snprintf(buf, cap, "Move troop");
        return;
    }
    const char *owner = troop_owner_label(
        state, target->as.move_troop.source_node_id, target->as.move_troop.source_slot_index);
    const char *src = engine_node_label(
        intern_str(target->as.move_troop.source_node_id),
        node_ids, node_labels, node_pair_count);
    const char *dst = engine_node_label(
        intern_str(target->as.move_troop.target_node_id),
        node_ids, node_labels, node_pair_count);
    snprintf(buf, cap, "Move %s troop from %s to %s", owner, src, dst);
}

const CardOp OP_MOVE_TROOP = {
    .name = "move_troop",
    .needs_selection = 1,
    .enumerate = op_move_troop_enumerate,
    .target_from_move = op_move_troop_target,
    .apply = op_move_troop_apply,
    .describe = op_move_troop_describe,
};
