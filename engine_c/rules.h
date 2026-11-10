#ifndef ENGINE_RULES_H
#define ENGINE_RULES_H

#include "state.h"

/* Both queries return the number of moves that exist, which can exceed
 * max_moves. At most max_moves moves are written; the caller sizes its buffer
 * from engine_move_capacity() and treats a larger count as truncation. */
int        engine_legal_moves(const GameState *state, Move *out, int max_moves);
GameState *engine_apply(const GameState *state, const Move *move);
int        engine_is_terminal(const GameState *state);
Sym        engine_winner(const GameState *state, int *score_out);

void register_default_effects(void);

int card_effect_is_generic(const CardDefinition *card);
GameState *apply_card_effect(GameState *state, Sym player_id, const CardDefinition *card);

#endif
