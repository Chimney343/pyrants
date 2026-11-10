#include "op.h"
#include "describe.h"
#include "helpers.h"
#include "intern.h"

#include <stdio.h>
#include <string.h>

static int node_has_own_spy(const GameState *state, Sym player_id, int node_index) {
    const NodeState *ns = &state->nodes[node_index];
    for (int i = 0; i < ns->spy_count; i++)
        if (ns->spies[i] == player_id) return 1;
    return 0;
}

static int op_place_spy_enumerate(const GameState *state, Sym player_id,
                                  const PendingGenericChoiceState *pending,
                                  const CardDefinition *card, const CardAction *action,
                                  Move *out, int max_out) {
    (void)pending; (void)card; (void)action;
    int w = 0;
    int pi = -1;
    for (int i = 0; i < state->player_count; i++)
        if (state->players[i].player_id == player_id) { pi = i; break; }
    if (pi < 0) return 0;

    int has_spies = state->players[pi].spies_available > 0;

    if (!has_spies) {
        if (w < max_out) {
            /* Rulebook 338: all spies placed -> may do nothing. */
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = SYM_NULL;
            out[w].data.resolve_generic.target_id = SYM_NULL;
            out[w].player_index = 0;
        }
        w++;
    }

    for (int i = 0; i < state->node_count; i++) {
        Sym nid = state->nodes[i].node_id;
        const NodeDefinition *nd = NULL;
        for (int j = 0; j < state->definition->board.node_count; j++)
            if (state->definition->board.nodes[j].node_id == nid) {
                nd = &state->definition->board.nodes[j];
                break;
            }
        if (!nd || strcmp(intern_str(nd->kind), "site") != 0) continue;
        if (node_has_own_spy(state, player_id, i)) continue;
        if (has_spies) {
            if (w < max_out) {
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = nid;
                out[w].player_index = 0;
            }
            w++;
        } else {
            /* Rulebook 338: all spies placed -> may return one of your spies
             * and place it. Emit (source, destination) pairs. */
            for (int s = 0; s < state->node_count; s++) {
                if (state->nodes[s].node_id == nid) continue;
                if (!node_has_own_spy(state, player_id, s)) continue;
                if (w >= max_out) { w++; continue; }
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = nid;
                out[w].data.resolve_generic.target_id = state->nodes[s].node_id;
                out[w].player_index = 0;
                w++;
            }
        }
    }
    return w;
}

static int op_place_spy_target(const GameState *state, Sym player_id,
                               const CardAction *action, const Move *move,
                               OpTarget *out) {
    (void)state; (void)player_id; (void)action;
    /* action_id == NULL is the rulebook "may do nothing" decline; it remains
     * a valid no-op target so the pending card advances like the legacy path. */
    out->kind = OP_TARGET_PLACE_SPY;
    out->as.place_spy.target_node_id = move->data.resolve_generic.action_id;
    out->as.place_spy.source_node_id = move->data.resolve_generic.target_id;
    return 1;
}

static GameState *op_place_spy_apply(GameState *state, Sym player_id,
                                     const CardDefinition *card,
                                     const CardAction *action,
                                     const OpTarget *target) {
    (void)card; (void)action;
    if (!target || target->kind != OP_TARGET_PLACE_SPY) return state;
    Sym destination = target->as.place_spy.target_node_id;
    if (destination == SYM_NULL) return state;
    NodeState *ns = cow_node(state, destination);
    if (!ns) return state;
    for (int i = 0; i < ns->spy_count; i++)
        if (ns->spies[i] == player_id) return state;

    PlayerState *ps = cow_player(state, player_id);
    if (!ps) return state;
    if (ps->spies_available > 0) {
        ps->spies_available--;
    } else {
        Sym source = target->as.place_spy.source_node_id;
        if (source == SYM_NULL || source == destination) return state;
        NodeState *sns = cow_node(state, source);
        if (!sns) return state;
        int found = -1;
        for (int i = 0; i < sns->spy_count; i++)
            if (sns->spies[i] == player_id) { found = i; break; }
        if (found < 0) return state;
        for (int i = found; i < sns->spy_count - 1; i++)
            sns->spies[i] = sns->spies[i + 1];
        sns->spy_count--;
    }
    if (ns->spy_count < MAX_SPY_SLOTS)
        ns->spies[ns->spy_count++] = player_id;
    return state;
}

static void op_place_spy_describe(const GameState *state, const CardAction *action,
                                  const OpTarget *target,
                                  const char *const *node_ids, const char *const *node_labels,
                                  int node_pair_count, char *buf, size_t cap) {
    (void)state; (void)action;
    if (!target || target->kind != OP_TARGET_PLACE_SPY) {
        snprintf(buf, cap, "Place a spy");
        return;
    }
    const char *dst = engine_node_label(
        intern_str(target->as.place_spy.target_node_id),
        node_ids, node_labels, node_pair_count);
    if (target->as.place_spy.source_node_id != SYM_NULL) {
        const char *src = engine_node_label(
            intern_str(target->as.place_spy.source_node_id),
            node_ids, node_labels, node_pair_count);
        snprintf(buf, cap, "Move your spy from %s to %s", src, dst);
    } else {
        snprintf(buf, cap, "Place a spy at %s", dst);
    }
}

const CardOp OP_PLACE_SPY = {
    .name = "place_spy",
    .needs_selection = 1,
    .enumerate = op_place_spy_enumerate,
    .target_from_move = op_place_spy_target,
    .apply = op_place_spy_apply,
    .describe = op_place_spy_describe,
};
