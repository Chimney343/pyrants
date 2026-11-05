#ifndef ENGINE_OPS_OP_H
#define ENGINE_OPS_OP_H

#include "state.h"

#include <stddef.h>

/* Typed internal target for a card op. The frozen Move payload string remains
 * the wire format; this record is built at the apply boundary and never
 * crosses the Python/decisions boundary. */
typedef enum {
    OP_TARGET_NONE = 0,
    OP_TARGET_RETURN_SPY,
    OP_TARGET_PLACE_SPY,
    OP_TARGET_RETURN_UNIT,
    OP_TARGET_DEPLOY_TROOPS,
    OP_TARGET_MOVE_TROOP,
    OP_TARGET_TROOP_SLOT,
    OP_TARGET_FORCE_DISCARD,
    OP_TARGET_RECRUIT_CARD,
    OP_TARGET_DEVOUR,
    OP_TARGET_PLAY_CARD,
} OpTargetKind;

typedef struct {
    OpTargetKind kind;
    union {
        struct {
            Sym node_id;
            Sym spy_owner_id;
            int free_enemy_return;
        } return_spy;
        struct {
            Sym target_node_id;
            Sym source_node_id;
        } place_spy;
        struct {
            Sym node_id;
            Sym unit_type;
            int slot_index;
            Sym spy_owner_id;
        } return_unit;
        struct {
            Sym node_id;
        } deploy_troops;
        struct {
            Sym source_node_id;
            int source_slot_index;
            Sym target_node_id;
            int target_slot_index;
        } move_troop;
        struct {
            Sym node_id;
            int slot_index;
        } troop_slot;
        struct {
            Sym target_player_id;
            Sym target_card_id;
        } force_discard;
        struct {
            Sym target_card_id;
        } recruit_card;
        struct {
            Sym target_card_id;
        } devour;
        struct {
            Sym target_card_id;
            int inner_circle_index;
            int from_inner_circle;
        } play_card;
    } as;
} OpTarget;

typedef int (*OpEnumerateFn)(const GameState *state, Sym player_id,
                             const PendingGenericChoiceState *pending,
                             const CardDefinition *card, const CardAction *action,
                             Move *out, int max_out);
typedef int (*OpTargetFromMoveFn)(const GameState *state, Sym player_id,
                                  const CardAction *action, const Move *move,
                                  OpTarget *out);
typedef GameState *(*OpApplyFn)(GameState *state, Sym player_id,
                                const CardDefinition *card, const CardAction *action,
                                const OpTarget *target);
typedef void (*OpDescribeFn)(const GameState *state, const CardAction *action,
                             const OpTarget *target,
                             const char *const *node_ids, const char *const *node_labels,
                             int node_pair_count, char *buf, size_t cap);

typedef struct {
    const char *name;
    int needs_selection;
    OpEnumerateFn enumerate;
    OpTargetFromMoveFn target_from_move;
    OpApplyFn apply;
    OpDescribeFn describe;
} CardOp;

const CardOp *op_lookup(Sym op);
int op_table_count(void);
const CardOp *op_table_at(int index);

#endif
