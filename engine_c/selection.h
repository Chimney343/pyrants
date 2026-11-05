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

/* Shared target enumeration for assassinate_troop and supplant_troop. The
 * action's op selects the white-troop inclusion rule. */
int legal_assassinate_supplant_moves(const GameState *state, Sym player_id,
                                     const PendingGenericChoiceState *pending,
                                     const CardDefinition *card, const CardAction *action,
                                     Move *out, int max_out);

/* Shared target enumeration for devour and devour_cost. */
int legal_devour_moves(const GameState *state, Sym player_id,
                       const PendingGenericChoiceState *pending,
                       const CardDefinition *card, const CardAction *action,
                       Move *out, int max_out);

#endif
