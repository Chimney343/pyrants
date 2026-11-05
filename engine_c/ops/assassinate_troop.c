#include "op.h"
#include "describe.h"
#include "helpers.h"
#include "intern.h"
#include "selection.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int op_assassinate_troop_enumerate(const GameState *state, Sym player_id,
                                          const PendingGenericChoiceState *pending,
                                          const CardDefinition *card, const CardAction *action,
                                          Move *out, int max_out) {
    return legal_assassinate_supplant_moves(state, player_id, pending, card,
                                            action, out, max_out);
}

static int op_assassinate_troop_target(const GameState *state, Sym player_id,
                                       const CardAction *action, const Move *move,
                                       OpTarget *out) {
    (void)state; (void)player_id; (void)action;
    Sym node_id = move->data.resolve_generic.action_id;
    Sym tid = move->data.resolve_generic.target_id;
    if (node_id == SYM_NULL || tid == SYM_NULL) return 0;
    const char *ts = intern_str(tid);
    if (!ts) return 0;
    out->kind = OP_TARGET_ASSASSINATE_TROOP;
    out->as.assassinate_troop.node_id = node_id;
    out->as.assassinate_troop.slot_index = atoi(ts);
    return 1;
}

static GameState *op_assassinate_troop_apply(GameState *state, Sym player_id,
                                             const CardDefinition *card,
                                             const CardAction *action,
                                             const OpTarget *target) {
    (void)card;
    if (!target || target->kind != OP_TARGET_ASSASSINATE_TROOP) return state;
    Sym node_id = target->as.assassinate_troop.node_id;
    int slot = target->as.assassinate_troop.slot_index;
    if (node_id == SYM_NULL || slot < 0) return state;

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
            if (required == SYM_NULL || node_id != required) return state;
            break;
        }
    }
    int ignore_presence = 0;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "ignore_presence_requirement") == 0 && v
            && strcmp(v, "true") == 0) {
            ignore_presence = 1;
            break;
        }
    }
    if (apply_free_assassinate(state, player_id, node_id, slot, ignore_presence) != 0)
        return state;
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

static void op_assassinate_troop_describe(const GameState *state, const CardAction *action,
                                          const OpTarget *target,
                                          const char *const *node_ids, const char *const *node_labels,
                                          int node_pair_count, char *buf, size_t cap) {
    (void)action;
    if (!target || target->kind != OP_TARGET_ASSASSINATE_TROOP) {
        snprintf(buf, cap, "Assassinate troop");
        return;
    }
    const char *owner = troop_owner_label(state, target->as.assassinate_troop.node_id,
                                          target->as.assassinate_troop.slot_index);
    const char *label = engine_node_label(intern_str(target->as.assassinate_troop.node_id),
                                          node_ids, node_labels, node_pair_count);
    snprintf(buf, cap, "Assassinate %s troop at %s", owner, label);
}

const CardOp OP_ASSASSINATE_TROOP = {
    .name = "assassinate_troop",
    .needs_selection = 1,
    .enumerate = op_assassinate_troop_enumerate,
    .target_from_move = op_assassinate_troop_target,
    .apply = op_assassinate_troop_apply,
    .describe = op_assassinate_troop_describe,
};
