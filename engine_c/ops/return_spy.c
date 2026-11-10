#include "op.h"
#include "helpers.h"
#include "intern.h"

#include <stdio.h>
#include <string.h>

static int node_has_supplantable_troop(const GameState *state, Sym player_id, Sym nid) {
    for (int i = 0; i < state->node_count; i++) {
        if (state->nodes[i].node_id != nid) continue;
        for (int s = 0; s < state->nodes[i].troop_slot_count; s++) {
            Sym occ = state->nodes[i].troop_slots[s];
            if (occ != SYM_NULL && occ != player_id) return 1;
        }
        return 0;
    }
    return 0;
}

static int op_return_spy_enumerate(const GameState *state, Sym player_id,
                                   const PendingGenericChoiceState *pending,
                                   const CardDefinition *card, const CardAction *action,
                                   Move *out, int max_out) {
    (void)pending; (void)card;
    int w = 0;
    const char *spy_owner = NULL;
    int requires_supplant_target = 0;
    for (int mi = 0; mi < action->metadata_count; mi++) {
        const char *mk = intern_str(action->metadata[mi].key);
        const char *mv = intern_str(action->metadata[mi].value);
        if (mk && strcmp(mk, "spy_owner") == 0)
            spy_owner = mv;
        if (mk && strcmp(mk, "requires_supplant_target") == 0
            && mv && strcmp(mv, "true") == 0)
            requires_supplant_target = 1;
    }
    bool only_self = spy_owner && strcmp(spy_owner, "self") == 0;
    bool only_enemy = spy_owner && strcmp(spy_owner, "opponent") == 0;

    for (int i = 0; i < state->node_count; i++) {
        Sym nid = state->nodes[i].node_id;
        if (requires_supplant_target && !node_has_supplantable_troop(state, player_id, nid))
            continue;
        for (int s = 0; s < state->nodes[i].spy_count; s++) {
            Sym spy = state->nodes[i].spies[s];
            if (spy == player_id && !only_enemy) {
                if (w >= max_out) { w++; continue; }
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = nid;
                out[w].player_index = 0;
                w++;
            } else if (spy != player_id && !only_self
                       && has_presence(state, player_id, nid)) {
                if (w < max_out) {
                    out[w].type = MOVE_RESOLVE_GENERIC;
                    out[w].data.resolve_generic.action_id = nid;
                    out[w].player_index = 0;
                }
                w++;
            }
        }
    }
    return w;
}

static int op_return_spy_target(const GameState *state, Sym player_id,
                                const CardAction *action, const Move *move,
                                OpTarget *out) {
    Sym node_id = move->data.resolve_generic.action_id;
    if (node_id == SYM_NULL) return 0;

    Sym spy_owner = SYM_NULL;
    int enemy_only = 0;
    int free_enemy_return = 0;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "spy_owner") == 0) {
            if (v && strcmp(v, "self") == 0) spy_owner = player_id;
            else if (v && strcmp(v, "opponent") == 0) enemy_only = 1;
        }
        if (k && strcmp(k, "free_enemy_return") == 0
            && v && strcmp(v, "true") == 0)
            free_enemy_return = 1;
    }
    if (spy_owner == SYM_NULL && enemy_only) {
        for (int i = 0; i < state->node_count; i++) {
            if (state->nodes[i].node_id != node_id) continue;
            for (int si = 0; si < state->nodes[i].spy_count; si++) {
                Sym spy = state->nodes[i].spies[si];
                if (spy != SYM_NULL && spy != player_id) {
                    spy_owner = spy;
                    break;
                }
            }
            break;
        }
    }
    if (spy_owner == SYM_NULL) spy_owner = player_id;

    out->kind = OP_TARGET_RETURN_SPY;
    out->as.return_spy.node_id = node_id;
    out->as.return_spy.spy_owner_id = spy_owner;
    out->as.return_spy.free_enemy_return = free_enemy_return;
    return 1;
}

static GameState *op_return_spy_apply(GameState *state, Sym player_id,
                                      const CardDefinition *card,
                                      const CardAction *action,
                                      const OpTarget *target) {
    (void)card; (void)action;
    if (!target || target->kind != OP_TARGET_RETURN_SPY) return state;
    apply_return_spy(state, player_id,
                     target->as.return_spy.node_id,
                     target->as.return_spy.spy_owner_id,
                     target->as.return_spy.free_enemy_return);
    return state;
}

static void op_return_spy_describe(const GameState *state, const CardAction *action,
                                   const OpTarget *target,
                                   const char *const *node_ids, const char *const *node_labels,
                                   int node_pair_count, char *buf, size_t cap) {
    (void)state; (void)action; (void)target;
    (void)node_ids; (void)node_labels; (void)node_pair_count;
    snprintf(buf, cap, "Return a spy");
}

const CardOp OP_RETURN_SPY = {
    .name = "return_spy",
    .needs_selection = 1,
    .enumerate = op_return_spy_enumerate,
    .target_from_move = op_return_spy_target,
    .apply = op_return_spy_apply,
    .describe = op_return_spy_describe,
};

