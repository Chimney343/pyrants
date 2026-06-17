#ifndef ENGINE_DESCRIBE_H
#define ENGINE_DESCRIBE_H

#include "state.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Format a human-readable label for a legal move.
 *
 * @param state          Current game state (may be NULL for move types that
 *                       don't need state data).
 * @param move           The move to describe.
 * @param node_ids       Parallel array of internal node IDs (Sym strings).
 *                       May be NULL to trigger humanize fallback.
 * @param node_labels    Parallel array of friendly node labels, one per
 *                       entry in node_ids. May be NULL.
 * @param node_pair_count  Number of entries in node_ids / node_labels.
 * @param out            Output buffer (may be NULL to query size).
 * @param out_cap        Capacity of the output buffer.
 * @return               Bytes needed for the full null-terminated string,
 *                       or 0 on failure. The output is always null-terminated
 *                       when out is non-NULL and out_cap > 0.
 */
int engine_describe_move(const GameState *state, const Move *move,
                         const char *const *node_ids, const char *const *node_labels,
                         int node_pair_count,
                         char *out, int out_cap);

#ifdef __cplusplus
}
#endif

#endif
