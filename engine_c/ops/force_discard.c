#include "op.h"
#include "describe.h"
#include "helpers.h"
#include "intern.h"
#include "rng.h"

#include <stdio.h>
#include <string.h>

static int op_force_discard_enumerate(const GameState *state, Sym player_id,
                                      const PendingGenericChoiceState *pending,
                                      const CardDefinition *card, const CardAction *action,
                                      Move *out, int max_out) {
    (void)pending; (void)card;
    const char *sf = intern_str(action->source_fragment);
    if (sf && strcmp(sf, "targeted_discard") == 0) {
        int w = 0;
        for (int p = 0; p < state->player_count && w < max_out; p++) {
            if (state->players[p].player_id == player_id) continue;
            if (state->players[p].hand_count >= 3) {
                out[w].type = MOVE_RESOLVE_GENERIC;
                out[w].data.resolve_generic.action_id = state->players[p].player_id;
                out[w].player_index = 0;
                w++;
            }
        }
        return w;
    }
    int w = 0;
    for (int p = 0; p < state->player_count && w < max_out; p++) {
        if (state->players[p].player_id == player_id) continue;
        for (int h = 0; h < state->players[p].hand_count && w < max_out; h++) {
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = state->players[p].hand[h];
            out[w].player_index = 0;
            w++;
        }
    }
    return w;
}

static int op_force_discard_target(const GameState *state, Sym player_id,
                                   const CardAction *action, const Move *move,
                                   OpTarget *out) {
    (void)state; (void)player_id;
    Sym aid = move->data.resolve_generic.action_id;
    if (aid == SYM_NULL) return 0;
    const char *sf = intern_str(action->source_fragment);
    out->kind = OP_TARGET_FORCE_DISCARD;
    out->as.force_discard.target_player_id = SYM_NULL;
    out->as.force_discard.target_card_id = SYM_NULL;
    if (sf && (strcmp(sf, "targeted_discard") == 0
               || strcmp(sf, "conditional_owner_discard") == 0)) {
        out->as.force_discard.target_player_id = aid;
    } else {
        out->as.force_discard.target_card_id = aid;
    }
    return 1;
}

static GameState *op_force_discard_apply(GameState *state, Sym player_id,
                                         const CardDefinition *card,
                                         const CardAction *action,
                                         const OpTarget *target) {
    (void)card; (void)action;
    if (!target || target->kind != OP_TARGET_FORCE_DISCARD) return state;
    Sym target_player = target->as.force_discard.target_player_id;
    if (target_player == SYM_NULL || target_player == player_id) return state;
    PlayerState *ps = cow_player(state, target_player);
    if (!ps) return state;

    int hand_idx = -1;
    if (ps->hand_count < 3) return state;
    RNG rng;
    rng_seed(&rng, state->shuffle_seed);
    for (int c = 0; c < state->shuffle_counter; c++)
        rng_next(&rng);
    hand_idx = rng_randint(&rng, 0, ps->hand_count - 1);
    state->shuffle_counter++;
    if (hand_idx < 0 || hand_idx >= ps->hand_count) return state;
    Sym discarded_card = ps->hand[hand_idx];
    discard_hand_card(state, target_player, hand_idx);
    trigger_opponent_discard_reactive(state, player_id, target_player, discarded_card);
    return state;
}

static void op_force_discard_describe(const GameState *state, const CardAction *action,
                                      const OpTarget *target,
                                      const char *const *node_ids, const char *const *node_labels,
                                      int node_pair_count, char *buf, size_t cap) {
    (void)action; (void)node_ids; (void)node_labels; (void)node_pair_count;
    if (!target || target->kind != OP_TARGET_FORCE_DISCARD) {
        snprintf(buf, cap, "Force discard");
        return;
    }
    if (target->as.force_discard.target_player_id != SYM_NULL) {
        const char *who = engine_player_label(
            intern_str(target->as.force_discard.target_player_id));
        snprintf(buf, cap, "Force %s to discard", who);
    } else {
        snprintf(buf, cap, "Discard a card");
    }
}

const CardOp OP_FORCE_DISCARD = {
    .name = "force_discard",
    .needs_selection = 1,
    .enumerate = op_force_discard_enumerate,
    .target_from_move = op_force_discard_target,
    .apply = op_force_discard_apply,
    .describe = op_force_discard_describe,
};
