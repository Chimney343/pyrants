#include "op.h"
#include "describe.h"
#include "helpers.h"
#include "intern.h"
#include "selection.h"

#include <stdio.h>
#include <string.h>

static int op_devour_enumerate(const GameState *state, Sym player_id,
                               const PendingGenericChoiceState *pending,
                               const CardDefinition *card, const CardAction *action,
                               Move *out, int max_out) {
    return legal_devour_moves(state, player_id, pending, card, action, out, max_out);
}

static int op_devour_target(const GameState *state, Sym player_id,
                            const CardAction *action, const Move *move,
                            OpTarget *out) {
    (void)state; (void)player_id; (void)action;
    Sym card_id = move->data.resolve_generic.action_id;
    if (card_id == SYM_NULL) return 0;
    out->kind = OP_TARGET_DEVOUR;
    out->as.devour.target_card_id = card_id;
    return 1;
}

static GameState *op_devour_apply(GameState *state, Sym player_id,
                                  const CardDefinition *card,
                                  const CardAction *action,
                                  const OpTarget *target) {
    (void)card;
    if (!target || target->kind != OP_TARGET_DEVOUR) return state;
    Sym target_card_id = target->as.devour.target_card_id;
    if (target_card_id == SYM_NULL) return state;

    Sym zone = SYM_NULL;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        if (k && strcmp(k, "source_zone") == 0) {
            zone = action->metadata[i].value;
            break;
        }
    }
    if (zone == SYM_NULL) zone = action->target_scope;
    const char *z = intern_str(zone);
    PlayerState *ps = cow_player(state, player_id);
    if (!ps || !z) return state;

    int self_replace = 0;
    for (int i = 0; i < action->metadata_count; i++) {
        const char *k = intern_str(action->metadata[i].key);
        const char *v = intern_str(action->metadata[i].value);
        if (k && strcmp(k, "self_replace") == 0 && v && strcmp(v, "true") == 0) {
            self_replace = 1;
            break;
        }
    }
    Sym source = state->pending_generic
        ? state->pending_generic->source_card_id : SYM_NULL;
    Sym insane = intern("insane_outcast");

    if (strcmp(z, "hand") == 0) {
        int idx = -1;
        for (int i = 0; i < ps->hand_count; i++)
            if (ps->hand[i] == target_card_id) { idx = i; break; }
        if (idx >= 0 && idx < ps->hand_count
            && (ps->hand[idx] == insane || state->devour_pile_count < MAX_ZONE_SIZE)) {
            if (ps->hand[idx] != insane)
                state->devour_pile[state->devour_pile_count++] = ps->hand[idx];
            for (int i = idx; i < ps->hand_count - 1; i++)
                ps->hand[i] = ps->hand[i + 1];
            ps->hand_count--;
        }
    } else if (strcmp(z, "played_self") == 0) {
        for (int i = 0; i < ps->played_cards_count; i++) {
            if (ps->played_cards[i] == source) {
                if (source != insane && state->devour_pile_count < MAX_ZONE_SIZE)
                    state->devour_pile[state->devour_pile_count++] = source;
                for (int j = i; j < ps->played_cards_count - 1; j++)
                    ps->played_cards[j] = ps->played_cards[j + 1];
                ps->played_cards_count--;
                break;
            }
        }
    } else if (strcmp(z, "market") == 0) {
        for (int i = 0; i < state->market.row_count; i++) {
            if (state->market.row[i] != target_card_id) continue;
            if (target_card_id != insane && state->devour_pile_count < MAX_ZONE_SIZE)
                state->devour_pile[state->devour_pile_count++] = target_card_id;
            MarketState *ms = cow_market(state);
            if (ms) {
                if (self_replace && ms->row_count < MAX_ZONE_SIZE) {
                    ms->row[i] = source;
                    for (int pci = 0; pci < ps->played_cards_count; pci++) {
                        if (ps->played_cards[pci] == source) {
                            for (int pcj = pci; pcj < ps->played_cards_count - 1; pcj++)
                                ps->played_cards[pcj] = ps->played_cards[pcj + 1];
                            ps->played_cards_count--;
                            break;
                        }
                    }
                } else if (ms->deck_count > 0) {
                    ms->row[i] = ms->deck[--ms->deck_count];
                } else {
                    for (int j = i; j < ms->row_count - 1; j++)
                        ms->row[j] = ms->row[j + 1];
                    ms->row_count--;
                }
            }
            break;
        }
    } else if (strcmp(z, "inner_circle") == 0) {
        for (int i = 0; i < ps->inner_circle_count; i++) {
            if (ps->inner_circle[i] != target_card_id) continue;
            if (target_card_id != insane && state->devour_pile_count < MAX_ZONE_SIZE)
                state->devour_pile[state->devour_pile_count++] = target_card_id;
            for (int j = i; j < ps->inner_circle_count - 1; j++)
                ps->inner_circle[j] = ps->inner_circle[j + 1];
            ps->inner_circle_count--;
            break;
        }
    }
    return state;
}

static void op_devour_describe(const GameState *state, const CardAction *action,
                               const OpTarget *target,
                               const char *const *node_ids, const char *const *node_labels,
                               int node_pair_count, char *buf, size_t cap) {
    (void)action; (void)node_ids; (void)node_labels; (void)node_pair_count;
    if (!target || target->kind != OP_TARGET_DEVOUR) {
        snprintf(buf, cap, "Devour a card");
        return;
    }
    snprintf(buf, cap, "Devour %s",
             engine_card_name(state, target->as.devour.target_card_id));
}

const CardOp OP_DEVOUR = {
    .name = "devour",
    .needs_selection = 1,
    .enumerate = op_devour_enumerate,
    .target_from_move = op_devour_target,
    .apply = op_devour_apply,
    .describe = op_devour_describe,
};

const CardOp OP_DEVOUR_COST = {
    .name = "devour_cost",
    .needs_selection = 1,
    .enumerate = op_devour_enumerate,
    .target_from_move = op_devour_target,
    .apply = op_devour_apply,
    .describe = op_devour_describe,
};
