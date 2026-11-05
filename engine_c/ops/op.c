#include "op.h"
#include "intern.h"

#include <string.h>

extern const CardOp OP_RETURN_SPY;

static const CardOp *const OPS[] = {
    &OP_RETURN_SPY,
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

