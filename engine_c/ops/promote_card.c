#include "op.h"
#include "describe.h"
#include "helpers.h"
#include "intern.h"
#include "selection.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int op_promote_card_enumerate(const GameState *state, Sym player_id,
                                     const PendingGenericChoiceState *pending,
                                     const CardDefinition *card, const CardAction *action,
                                     Move *out, int max_out) {
    return legal_promote_card_moves(state, player_id, pending, card, action,
                                    out, max_out);
}

static int op_promote_card_target(const GameState *state, Sym player_id,
                                  const CardAction *action, const Move *move,
                                  OpTarget *out) {
    (void)state; (void)player_id;
    Sym aid = move->data.resolve_generic.action_id;
    Sym tid = move->data.resolve_generic.target_id;
    if (aid == SYM_NULL) return 0;
    out->kind = OP_TARGET_PROMOTE_CARD;
    out->as.promote_card.target_card_id = SYM_NULL;
    out->as.promote_card.source_zone = SYM_NULL;
    out->as.promote_card.hand_index = -1;
    out->as.promote_card.discard_index = -1;

    const char *sf = intern_str(action->source_fragment);
    if (sf && strcmp(sf, "single_promote_from_multiple_zones") == 0 && tid != SYM_NULL) {
        out->as.promote_card.source_zone = tid;
        const char *sz = intern_str(tid);
        if (sz && strcmp(sz, "played") == 0) {
            out->as.promote_card.target_card_id = aid;
        } else if (sz && strcmp(sz, "hand") == 0) {
            out->as.promote_card.hand_index = atoi(intern_str(aid));
        } else if (sz && strcmp(sz, "discard") == 0) {
            out->as.promote_card.discard_index = atoi(intern_str(aid));
        } else {
            return 0;
        }
        return 1;
    }
    out->as.promote_card.target_card_id = aid;
    return 1;
}

static GameState *op_promote_card_apply(GameState *state, Sym player_id,
                                        const CardDefinition *card,
                                        const CardAction *action,
                                        const OpTarget *target) {
    (void)card;
    if (!target || target->kind != OP_TARGET_PROMOTE_CARD) return state;
    const char *sf = intern_str(action->source_fragment);
    PlayerState *ps = cow_player(state, player_id);
    if (!ps) return state;

    if (sf && strcmp(sf, "promote_from_discard") == 0) {
        Sym target_card = target->as.promote_card.target_card_id;
        if (target_card == SYM_NULL) return state;
        for (int i = 0; i < ps->discard_pile_count; i++) {
            if (ps->discard_pile[i] != target_card) continue;
            for (int j = i; j < ps->discard_pile_count - 1; j++)
                ps->discard_pile[j] = ps->discard_pile[j + 1];
            ps->discard_pile_count--;
            if (ps->inner_circle_count < MAX_ZONE_SIZE)
                ps->inner_circle[ps->inner_circle_count++] = target_card;
            return state;
        }
        return state;
    }

    if (sf && strcmp(sf, "single_promote_from_multiple_zones") == 0) {
        const char *sz = intern_str(target->as.promote_card.source_zone);
        if (sz && strcmp(sz, "played") == 0) {
            if (target->as.promote_card.target_card_id != SYM_NULL)
                promote_card(state, player_id, target->as.promote_card.target_card_id);
        } else if (sz && strcmp(sz, "hand") == 0) {
            int idx = target->as.promote_card.hand_index;
            if (idx >= 0 && idx < ps->hand_count
                && ps->inner_circle_count < MAX_ZONE_SIZE) {
                Sym card_id = ps->hand[idx];
                
                for (int i = idx; i < ps->hand_count - 1; i++)
                    ps->hand[i] = ps->hand[i + 1];
                ps->hand_count--;
                if (!card_is_negative(state, card_id))
                    ps->inner_circle[ps->inner_circle_count++] = card_id;
            }
        } else if (sz && strcmp(sz, "discard") == 0) {
            int idx = target->as.promote_card.discard_index;
            if (idx >= 0 && idx < ps->discard_pile_count
                && ps->inner_circle_count < MAX_ZONE_SIZE) {
                Sym card_id = ps->discard_pile[idx];
                
                for (int i = idx; i < ps->discard_pile_count - 1; i++)
                    ps->discard_pile[i] = ps->discard_pile[i + 1];
                ps->discard_pile_count--;
                if (!card_is_negative(state, card_id))
                    ps->inner_circle[ps->inner_circle_count++] = card_id;
            }
        }
        return state;
    }

    if (target->as.promote_card.target_card_id != SYM_NULL)
        promote_card(state, player_id, target->as.promote_card.target_card_id);
    return state;
}

static void op_promote_card_describe(const GameState *state, const CardAction *action,
                                     const OpTarget *target,
                                     const char *const *node_ids, const char *const *node_labels,
                                     int node_pair_count, char *buf, size_t cap) {
    (void)node_ids; (void)node_labels; (void)node_pair_count;
    if (!target || target->kind != OP_TARGET_PROMOTE_CARD) {
        snprintf(buf, cap, "Promote a card");
        return;
    }
    const char *sf = intern_str(action->source_fragment);
    if (sf && strcmp(sf, "single_promote_from_multiple_zones") == 0) {
        const char *sz = intern_str(target->as.promote_card.source_zone);
        const char *name = "?";
        if (sz && strcmp(sz, "played") == 0) {
            name = engine_card_name(state, target->as.promote_card.target_card_id);
        } else if (sz && strcmp(sz, "hand") == 0) {
            int pi = player_index_for_id(state, state->current_player_id);
            int idx = target->as.promote_card.hand_index;
            if (pi >= 0 && idx >= 0 && idx < state->players[pi].hand_count)
                name = engine_card_name(state, state->players[pi].hand[idx]);
        } else if (sz && strcmp(sz, "discard") == 0) {
            int pi = player_index_for_id(state, state->current_player_id);
            int idx = target->as.promote_card.discard_index;
            if (pi >= 0 && idx >= 0 && idx < state->players[pi].discard_pile_count)
                name = engine_card_name(state, state->players[pi].discard_pile[idx]);
        }
        snprintf(buf, cap, "Promote %s (%s)", name, sz ? sz : "?");
        return;
    }
    snprintf(buf, cap, "Promote %s",
             engine_card_name(state, target->as.promote_card.target_card_id));
}

const CardOp OP_PROMOTE_CARD = {
    .name = "promote_card",
    .needs_selection = 1,
    .enumerate = op_promote_card_enumerate,
    .target_from_move = op_promote_card_target,
    .apply = op_promote_card_apply,
    .describe = op_promote_card_describe,
};

