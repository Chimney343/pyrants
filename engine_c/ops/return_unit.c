#include "op.h"
#include "describe.h"
#include "helpers.h"
#include "intern.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int op_return_unit_enumerate(const GameState *state, Sym player_id,
                                    const PendingGenericChoiceState *pending,
                                    const CardDefinition *card, const CardAction *action,
                                    Move *out, int max_out) {
    (void)pending; (void)card;
    int w = 0;
    int include_self = 1;
    int include_opponent = 0;
    int requires_presence = 0;
    const char *scope = intern_str(action->target_scope);
    if (scope) {
        if (strcmp(scope, "opponent_unit") == 0) {
            include_self = 0;
            include_opponent = 1;
        } else if (strcmp(scope, "self_or_opponent_unit") == 0) {
            include_opponent = 1;
        }
    }
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "requires_presence") == 0 && v && strcmp(v, "true") == 0)
            requires_presence = 1;
    }
    for (int i = 0; i < state->node_count; i++) {
        Sym nid = state->nodes[i].node_id;
        if (requires_presence && !has_presence(state, player_id, nid)) continue;
        for (int s = 0; s < state->nodes[i].troop_slot_count; s++) {
            Sym occ = state->nodes[i].troop_slots[s];
            if (occ == SYM_NULL) continue;
            int is_own = (occ == player_id);
            const char *occ_str = intern_str(occ);
            int is_opponent = (!is_own && occ_str && strcmp(occ_str, "white") != 0);
            int include = (include_self && is_own) || (include_opponent && is_opponent);
            if (!include) continue;
            char buf[32];
            snprintf(buf, sizeof(buf), "troop:%d", s);
            if (w >= max_out) { w++; continue; }
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = nid;
            out[w].data.resolve_generic.target_id = intern(buf);
            out[w].data.resolve_generic.selection_index = 0;
            out[w].player_index = 0;
            w++;
        }
        for (int s = 0; s < state->nodes[i].spy_count; s++) {
            Sym spy = state->nodes[i].spies[s];
            int is_own = (spy == player_id);
            int is_opponent = (!is_own);
            int include = (include_self && is_own) || (include_opponent && is_opponent);
            if (!include) continue;
            char buf[32];
            const char *pid_str = intern_str(spy);
            snprintf(buf, sizeof(buf), "spy:%s", pid_str ? pid_str : "?");
            if (w < max_out) {
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = nid;
                out[w].data.resolve_generic.target_id = intern(buf);
                out[w].data.resolve_generic.selection_index = 0;
                out[w].player_index = 0;
            }
            w++;
        }
    }
    return w;
}

static int op_return_unit_target(const GameState *state, Sym player_id,
                                 const CardAction *action, const Move *move,
                                 OpTarget *out) {
    (void)state; (void)player_id; (void)action;
    Sym node_id = move->data.resolve_generic.action_id;
    Sym tid = move->data.resolve_generic.target_id;
    if (node_id == SYM_NULL || tid == SYM_NULL) return 0;
    const char *ts = intern_str(tid);
    if (!ts) return 0;

    out->kind = OP_TARGET_RETURN_UNIT;
    out->as.return_unit.node_id = node_id;
    out->as.return_unit.unit_type = SYM_NULL;
    out->as.return_unit.slot_index = -1;
    out->as.return_unit.spy_owner_id = SYM_NULL;
    if (strncmp(ts, "troop:", 6) == 0) {
        out->as.return_unit.unit_type = intern("troop");
        out->as.return_unit.slot_index = atoi(ts + 6);
        return 1;
    }
    if (strncmp(ts, "spy:", 4) == 0) {
        out->as.return_unit.unit_type = intern("spy");
        out->as.return_unit.spy_owner_id = intern(ts + 4);
        return 1;
    }
    return 0;
}

static GameState *op_return_unit_apply(GameState *state, Sym player_id,
                                       const CardDefinition *card,
                                       const CardAction *action,
                                       const OpTarget *target) {
    (void)card; (void)action;
    if (!target || target->kind != OP_TARGET_RETURN_UNIT) return state;
    Sym node_id = target->as.return_unit.node_id;
    Sym unit_type = target->as.return_unit.unit_type;
    if (node_id == SYM_NULL || unit_type == SYM_NULL) return state;
    NodeState *ns = cow_node(state, node_id);
    if (!ns) return state;

    const char *ut = intern_str(unit_type);
    if (ut && strcmp(ut, "troop") == 0) {
        int slot = target->as.return_unit.slot_index;
        if (slot < 0 || slot >= ns->troop_slot_count) return state;
        Sym owner = ns->troop_slots[slot];
        if (owner == SYM_NULL || owner == intern("white")) return state;
        ns->troop_slots[slot] = SYM_NULL;
        PlayerState *ps = cow_player(state, owner);
        if (ps) ps->barracks++;
    } else if (ut && strcmp(ut, "spy") == 0) {
        Sym spy_owner = target->as.return_unit.spy_owner_id;
        int found = -1;
        for (int i = 0; i < ns->spy_count; i++)
            if (ns->spies[i] == spy_owner) { found = i; break; }
        if (found < 0) return state;
        for (int i = found; i < ns->spy_count - 1; i++)
            ns->spies[i] = ns->spies[i + 1];
        ns->spy_count--;
        PlayerState *ps = cow_player(state, spy_owner);
        if (ps) ps->spies_available++;
    }
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

static void op_return_unit_describe(const GameState *state, const CardAction *action,
                                    const OpTarget *target,
                                    const char *const *node_ids, const char *const *node_labels,
                                    int node_pair_count, char *buf, size_t cap) {
    (void)action;
    if (!target || target->kind != OP_TARGET_RETURN_UNIT) {
        snprintf(buf, cap, "Return unit");
        return;
    }
    Sym node_id = target->as.return_unit.node_id;
    Sym unit_type = target->as.return_unit.unit_type;
    const char *label = engine_node_label(intern_str(node_id), node_ids, node_labels,
                                          node_pair_count);
    const char *ut = intern_str(unit_type);
    if (ut && strcmp(ut, "troop") == 0) {
        const char *owner = troop_owner_label(state, node_id, target->as.return_unit.slot_index);
        snprintf(buf, cap, "Return %s's troop from %s", owner, label);
    } else if (ut && strcmp(ut, "spy") == 0) {
        const char *owner = engine_player_label(intern_str(target->as.return_unit.spy_owner_id));
        snprintf(buf, cap, "Return %s's spy from %s", owner, label);
    } else {
        snprintf(buf, cap, "Return unit from %s", label);
    }
}

const CardOp OP_RETURN_UNIT = {
    .name = "return_unit",
    .needs_selection = 1,
    .enumerate = op_return_unit_enumerate,
    .target_from_move = op_return_unit_target,
    .apply = op_return_unit_apply,
    .describe = op_return_unit_describe,
};
