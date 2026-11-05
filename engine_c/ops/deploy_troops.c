#include "op.h"
#include "describe.h"
#include "helpers.h"

#include <stdio.h>
#include <string.h>

static int op_deploy_troops_enumerate(const GameState *state, Sym player_id,
                                      const PendingGenericChoiceState *pending,
                                      const CardDefinition *card, const CardAction *action,
                                      Move *out, int max_out) {
    (void)pending; (void)card; (void)action;
    int w = 0;
    int pi = player_index_for_id(state, player_id);
    if (pi < 0) return 0;
    if (state->players[pi].barracks <= 0) {
        /* Rulebook 319/589: taking Deploy with an empty barracks grants 1 VP
         * instead. Emit one sentinel move; the node is irrelevant. */
        if (max_out > 0) {
            out[0].type = MOVE_RESOLVE_GENERIC;
            out[0].data.resolve_generic.action_id = SYM_NULL;
            out[0].data.resolve_generic.target_id = SYM_NULL;
            out[0].data.resolve_generic.selection_index = 0;
            out[0].player_index = 0;
            return 1;
        }
        return 0;
    }
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

static int op_deploy_troops_target(const GameState *state, Sym player_id,
                                   const CardAction *action, const Move *move,
                                   OpTarget *out) {
    (void)state; (void)player_id; (void)action;
    out->kind = OP_TARGET_DEPLOY_TROOPS;
    out->as.deploy_troops.node_id = move->data.resolve_generic.action_id;
    return 1;
}

static GameState *op_deploy_troops_apply(GameState *state, Sym player_id,
                                         const CardDefinition *card,
                                         const CardAction *action,
                                         const OpTarget *target) {
    (void)card;
    if (!target || target->kind != OP_TARGET_DEPLOY_TROOPS) return state;
    if (apply_free_deploy(state, player_id, target->as.deploy_troops.node_id) != 0)
        return state;
    if (state->pending_generic)
        increment_pending_counter(state->pending_generic, action);
    return state;
}

static void op_deploy_troops_describe(const GameState *state, const CardAction *action,
                                      const OpTarget *target,
                                      const char *const *node_ids, const char *const *node_labels,
                                      int node_pair_count, char *buf, size_t cap) {
    (void)state; (void)action;
    if (!target || target->kind != OP_TARGET_DEPLOY_TROOPS
        || target->as.deploy_troops.node_id == SYM_NULL) {
        snprintf(buf, cap, "Deploy troops");
        return;
    }
    const char *label = engine_node_label(intern_str(target->as.deploy_troops.node_id),
                                          node_ids, node_labels, node_pair_count);
    snprintf(buf, cap, "Deploy a troop to %s", label);
}

const CardOp OP_DEPLOY_TROOPS = {
    .name = "deploy_troops",
    .needs_selection = 1,
    .enumerate = op_deploy_troops_enumerate,
    .target_from_move = op_deploy_troops_target,
    .apply = op_deploy_troops_apply,
    .describe = op_deploy_troops_describe,
};
