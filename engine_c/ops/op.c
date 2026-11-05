#include "op.h"
#include "intern.h"

#include <string.h>

extern const CardOp OP_RETURN_SPY;
extern const CardOp OP_PLACE_SPY;
extern const CardOp OP_RETURN_UNIT;
extern const CardOp OP_DEPLOY_TROOPS;
extern const CardOp OP_MOVE_TROOP;
extern const CardOp OP_ASSASSINATE_TROOP;
extern const CardOp OP_SUPPLANT_TROOP;
extern const CardOp OP_FORCE_DISCARD;
extern const CardOp OP_RECRUIT_CARD;
extern const CardOp OP_DEVOUR;
extern const CardOp OP_DEVOUR_COST;
extern const CardOp OP_PLAY_CARD;
extern const CardOp OP_PROMOTE_CARD;

static const CardOp *const OPS[] = {
    &OP_RETURN_SPY,
    &OP_PLACE_SPY,
    &OP_RETURN_UNIT,
    &OP_DEPLOY_TROOPS,
    &OP_MOVE_TROOP,
    &OP_ASSASSINATE_TROOP,
    &OP_SUPPLANT_TROOP,
    &OP_FORCE_DISCARD,
    &OP_RECRUIT_CARD,
    &OP_DEVOUR,
    &OP_DEVOUR_COST,
    &OP_PLAY_CARD,
    &OP_PROMOTE_CARD,
};

const CardOp *op_lookup(Sym op) {
    const char *name = intern_str(op);
    if (!name) return NULL;
    for (size_t i = 0; i < sizeof(OPS) / sizeof(OPS[0]); i++) {
        if (strcmp(OPS[i]->name, name) == 0) return OPS[i];
    }
    return NULL;
}

int op_table_count(void) {
    return (int)(sizeof(OPS) / sizeof(OPS[0]));
}

const CardOp *op_table_at(int index) {
    if (index < 0 || index >= op_table_count()) return NULL;
    return OPS[index];
}

