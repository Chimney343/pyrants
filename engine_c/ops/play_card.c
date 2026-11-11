#include "op.h"
#include "describe.h"
#include "helpers.h"
#include "intern.h"
#include "rules.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int op_play_card_enumerate(const GameState *state, Sym player_id,
                                  const PendingGenericChoiceState *pending,
                                  const CardDefinition *card, const CardAction *action,
                                  Move *out, int max_out) {
    (void)pending; (void)card;
    int w = 0;
    const char *sf = intern_str(action->source_fragment);
    if (sf && strcmp(sf, "play_from_inner_circle_without_removal") == 0) {
        int pi = -1;
        for (int i = 0; i < state->player_count; i++)
            if (state->players[i].player_id == player_id) { pi = i; break; }
        if (pi < 0) return 0;
        for (int i = 0; i < state->players[pi].inner_circle_count; i++) {
            if (w >= max_out) { w++; if (g_op_enum_probe) return w; continue; }
            out[w].type = MOVE_RESOLVE_GENERIC;
            out[w].data.resolve_generic.action_id = state->players[pi].inner_circle[i];
            out[w].player_index = 0;
            w++;
        }
        return w;
    }
    if (sf && strcmp(sf, "play") == 0) {
        int max_cost = 9999;
        for (int i = 0; i < action->metadata_count; i++) {
            const char *k = intern_str(action->metadata[i].key);
            const char *v = intern_str(action->metadata[i].value);
            if (k && strcmp(k, "max_cost") == 0 && v) max_cost = atoi(v);
        }
        for (int s = 0; s < state->market.row_count; s++) {
            Sym cid = state->market.row[s];
            if (max_cost < 9999) {
                const CardDefinition *cd = NULL;
                for (int ci = 0; ci < state->definition->catalog.card_count; ci++)
                    if (state->definition->catalog.cards[ci].card_id == cid) {
                        cd = &state->definition->catalog.cards[ci];
                        break;
                    }
                if (!cd || cd->cost > max_cost) continue;
            }
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
    return 0;
}

static int op_play_card_target(const GameState *state, Sym player_id,
                               const CardAction *action, const Move *move,
                               OpTarget *out) {
    Sym aid = move->data.resolve_generic.action_id;
    if (aid == SYM_NULL) return 0;
    const char *sf = intern_str(action->source_fragment);
    out->kind = OP_TARGET_PLAY_CARD;
    out->as.play_card.target_card_id = aid;
    out->as.play_card.inner_circle_index = -1;
    out->as.play_card.from_inner_circle = 0;
    if (sf && strcmp(sf, "play_from_inner_circle_without_removal") == 0) {
        int pi = -1;
        for (int i = 0; i < state->player_count; i++)
            if (state->players[i].player_id == player_id) { pi = i; break; }
        if (pi < 0) return 0;
        for (int i = 0; i < state->players[pi].inner_circle_count; i++) {
            if (state->players[pi].inner_circle[i] == aid) {
                out->as.play_card.inner_circle_index = i;
                out->as.play_card.from_inner_circle = 1;
                return 1;
            }
        }
        return 0;
    }
    return 1;
}

static GameState *op_play_card_apply(GameState *state, Sym player_id,
                                     const CardDefinition *card,
                                     const CardAction *action,
                                     const OpTarget *target) {
    (void)card;
    if (!target || target->kind != OP_TARGET_PLAY_CARD) return state;
    Sym nested_id = SYM_NULL;
    if (target->as.play_card.from_inner_circle) {
        PlayerState *ps = cow_player(state, player_id);
        int idx = target->as.play_card.inner_circle_index;
        if (!ps || idx < 0 || idx >= ps->inner_circle_count) return state;
        nested_id = ps->inner_circle[idx];
    } else {
        nested_id = target->as.play_card.target_card_id;
    }
    if (nested_id == SYM_NULL) return state;

    const CardDefinition *nested_cd = NULL;
    for (int i = 0; i < state->definition->catalog.card_count; i++) {
        if (state->definition->catalog.cards[i].card_id == nested_id) {
            nested_cd = &state->definition->catalog.cards[i];
            break;
        }
    }
    if (!nested_cd || !card_effect_is_generic(nested_cd)) return state;
    if (state->pending_generic)
        state->pending_generic->last_played_card_id = nested_id;
    return apply_card_effect(state, player_id, nested_cd);
}

static void op_play_card_describe(const GameState *state, const CardAction *action,
                                  const OpTarget *target,
                                  const char *const *node_ids, const char *const *node_labels,
                                  int node_pair_count, char *buf, size_t cap) {
    (void)action; (void)node_ids; (void)node_labels; (void)node_pair_count;
    if (!target || target->kind != OP_TARGET_PLAY_CARD) {
        snprintf(buf, cap, "Play a card");
        return;
    }
    snprintf(buf, cap, "Play %s",
             engine_card_name(state, target->as.play_card.target_card_id));
}

const CardOp OP_PLAY_CARD = {
    .name = "play_card",
    .needs_selection = 1,
    .enumerate = op_play_card_enumerate,
    .target_from_move = op_play_card_target,
    .apply = op_play_card_apply,
    .describe = op_play_card_describe,
};
