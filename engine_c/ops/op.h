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
    OP_TARGET_PROMOTE_CARD,
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
        struct {
            Sym target_card_id;
            Sym source_zone;
            int hand_index;
            int discard_index;
        } promote_card;
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

typedef struct CardOp {
    const char *name;
    int needs_selection;
    OpEnumerateFn enumerate;
    OpTargetFromMoveFn target_from_move;
    OpApplyFn apply;
    OpDescribeFn describe;
} CardOp;

/* Set only while an internal existence probe runs (see
 * legal_generic_target_selection_probe). A probe asks "is there any target?",
 * so an enumerator may return as soon as its buffer is full instead of walking
 * the rest of the target space — which for place_spy can be every node pair.
 * Public move queries leave it 0 and report the true count. The engine is
 * single-threaded within a process (IS-MCTS workers are separate processes),
 * so a plain flag is enough. */
extern int g_op_enum_probe;

/* Set while an internal existence probe runs. A probe only asks "is there any
 * target?", so an enumerator may stop at the first one instead of walking the
 * whole target space to report a count nobody reads. Public move queries leave
 * this 0 and report the true count. The engine is single-threaded within a
 * process (IS-MCTS parallelism is separate processes), so a plain flag is
 * enough; probe scope is a matched set/clear in
 * legal_generic_target_selection_probe(). */
extern int g_enum_probe;

const CardOp *op_lookup(Sym op);
const CardOp *card_op_for(const CardAction *action);
int op_table_count(void);
const CardOp *op_table_at(int index);

#endif
