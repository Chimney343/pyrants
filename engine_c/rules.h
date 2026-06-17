#ifndef ENGINE_RULES_H
#define ENGINE_RULES_H

#include "state.h"

int        engine_legal_moves(const GameState *state, Move *out, int max_moves);
GameState *engine_apply(const GameState *state, const Move *move);
int        engine_is_terminal(const GameState *state);
Sym        engine_winner(const GameState *state, int *score_out);

void register_default_effects(void);

#endif
