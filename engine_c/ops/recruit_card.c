#include "op.h"
#include "describe.h"
#include "helpers.h"
#include "intern.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int op_recruit_card_enumerate(const GameState *state, Sym player_id,
                                     const PendingGenericChoiceState *pending,
                                     const CardDefinition *card, const CardAction *action,
                                     Move *out, int max_out) {
    (void)pending; (void)card;
    int w = 0;
    Sym required_aspect = SYM_NULL;
    int max_cost = -1;
    int free_recruit = 0;
    for (int mi = 0; mi < action->metadata_count; mi++) {
        const char *mk = intern_str(action->metadata[mi].key);
        const char *mv = intern_str(action->metadata[mi].value);
        if (mk && strcmp(mk, "required_aspect") == 0 && mv) required_aspect = intern(mv);
        if (mk && strcmp(mk, "max_cost") == 0 && mv) max_cost = atoi(mv);
        if (mk && strcmp(mk, "free_recruit") == 0) free_recruit = 1;
    }
    for (int s = 0; s < state->market.row_count; s++) {
        Sym cid = state->market.row[s];
        const CardDefinition *cd = NULL;
        for (int i = 0; i < state->definition->catalog.card_count; i++)
            if (state->definition->catalog.cards[i].card_id == cid) {
                cd = &state->definition->catalog.cards[i];
                break;
            }
        if (!cd) continue;
        if (required_aspect != SYM_NULL && cd->aspect != required_aspect) continue;
        if (max_cost >= 0 && cd->cost > max_cost) continue;
        if (!free_recruit && state->resource_pool.influence < cd->cost) continue;
        if (w >= max_out && g_op_enum_probe) { w++; return w; }
        if (w < max_out) {
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = cid;
            out[w].player_index = 0;
        }
        w++;
    }
    return w;
}

static int op_recruit_card_target(const GameState *state, Sym player_id,
                                  const CardAction *action, const Move *move,
                                  OpTarget *out) {
    (void)state; (void)player_id; (void)action;
    Sym card_id = move->data.resolve_generic.action_id;
    if (card_id == SYM_NULL) return 0;
    out->kind = OP_TARGET_RECRUIT_CARD;
    out->as.recruit_card.target_card_id = card_id;
    return 1;
}

static GameState *op_recruit_card_apply(GameState *state, Sym player_id,
                                        const CardDefinition *card,
                                        const CardAction *action,
                                        const OpTarget *target) {
    (void)card;
    if (!target || target->kind != OP_TARGET_RECRUIT_CARD) return state;
    Sym target_card_id = target->as.recruit_card.target_card_id;
    if (target_card_id == SYM_NULL) return state;
    int slot = -1;
    for (int i = 0; i < state->market.row_count; i++)
        if (state->market.row[i] == target_card_id) { slot = i; break; }
    if (slot < 0) {
        for (int s = 0; s < state->definition->setup.special_stack_count; s++) {
            if (state->definition->setup.special_stacks[s].card_id == target_card_id) {
                slot = state->definition->setup.special_stacks[s].market_slot;
                break;
            }
        }
    }
    if (slot < 0) return state;
    int free_recruit = 0;
    for (int mi = 0; mi < action->metadata_count; mi++) {
        const char *mk = intern_str(action->metadata[mi].key);
        if (mk && strcmp(mk, "free_recruit") == 0) { free_recruit = 1; break; }
    }
    if (free_recruit) apply_recruit_free(state, player_id, slot);
    else apply_recruit(state, player_id, slot);
    return state;
}

static void op_recruit_card_describe(const GameState *state, const CardAction *action,
                                     const OpTarget *target,
                                     const char *const *node_ids, const char *const *node_labels,
                                     int node_pair_count, char *buf, size_t cap) {
    (void)action; (void)node_ids; (void)node_labels; (void)node_pair_count;
    if (!target || target->kind != OP_TARGET_RECRUIT_CARD) {
        snprintf(buf, cap, "Recruit a card");
        return;
    }
    snprintf(buf, cap, "Recruit %s",
             engine_card_name(state, target->as.recruit_card.target_card_id));
}

const CardOp OP_RECRUIT_CARD = {
    .name = "recruit_card",
    .needs_selection = 1,
    .enumerate = op_recruit_card_enumerate,
    .target_from_move = op_recruit_card_target,
    .apply = op_recruit_card_apply,
    .describe = op_recruit_card_describe,
};
