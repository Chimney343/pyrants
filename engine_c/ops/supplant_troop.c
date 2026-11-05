#include "op.h"
#include "describe.h"
#include "helpers.h"
#include "intern.h"
#include "selection.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int op_supplant_troop_enumerate(const GameState *state, Sym player_id,
                                       const PendingGenericChoiceState *pending,
                                       const CardDefinition *card, const CardAction *action,
                                       Move *out, int max_out) {
    return legal_assassinate_supplant_moves(state, player_id, pending, card,
                                            action, out, max_out);
}

static int op_supplant_troop_target(const GameState *state, Sym player_id,
                                    const CardAction *action, const Move *move,
                                    OpTarget *out) {
    (void)state; (void)player_id; (void)action;
    Sym node_id = move->data.resolve_generic.action_id;
    Sym tid = move->data.resolve_generic.target_id;
    if (node_id == SYM_NULL || tid == SYM_NULL) return 0;
    const char *ts = intern_str(tid);
    if (!ts) return 0;
    out->kind = OP_TARGET_TROOP_SLOT;
    out->as.troop_slot.node_id = node_id;
    out->as.troop_slot.slot_index = atoi(ts);
    return 1;
}

static GameState *op_supplant_troop_apply(GameState *state, Sym player_id,
                                          const CardDefinition *card,
                                          const CardAction *action,
                                          const OpTarget *target) {
    (void)card;
    if (!target || target->kind != OP_TARGET_TROOP_SLOT) return state;
    Sym node_id = target->as.troop_slot.node_id;
    int slot = target->as.troop_slot.slot_index;
    if (node_id == SYM_NULL || slot < 0) return state;

    NodeState *ns = cow_node(state, node_id);
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

static void op_supplant_troop_describe(const GameState *state, const CardAction *action,
                                       const OpTarget *target,
                                       const char *const *node_ids, const char *const *node_labels,
                                       int node_pair_count, char *buf, size_t cap) {
    (void)action;
    if (!target || target->kind != OP_TARGET_TROOP_SLOT) {
        snprintf(buf, cap, "Supplant troop");
        return;
    }
    const char *owner = troop_owner_label(state, target->as.troop_slot.node_id,
                                          target->as.troop_slot.slot_index);
    const char *label = engine_node_label(intern_str(target->as.troop_slot.node_id),
                                          node_ids, node_labels, node_pair_count);
    snprintf(buf, cap, "Supplant %s troop at %s", owner, label);
}

const CardOp OP_SUPPLANT_TROOP = {
    .name = "supplant_troop",
    .needs_selection = 1,
    .enumerate = op_supplant_troop_enumerate,
    .target_from_move = op_supplant_troop_target,
    .apply = op_supplant_troop_apply,
    .describe = op_supplant_troop_describe,
};
