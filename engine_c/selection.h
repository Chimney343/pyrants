#ifndef ENGINE_SELECTION_H
#define ENGINE_SELECTION_H
#include "state.h"

/* Count legal devour targets for `action`'s source zone, excluding hand slot
 * `exclude_hand_index` (pass -1 when not excluding). Pure read; mirrors
 * sel_devour's zone semantics. Returns -1 for dependent-selection devours
 * (requires_last_selected_market_slot) and self-devours (played_self) —
 * always satisfiable. */
int devour_target_count(const GameState *state, Sym player_id,
                        const CardAction *action, int exclude_hand_index);

#endif
