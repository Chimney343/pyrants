#ifndef ENGINE_PHASES_H
#define ENGINE_PHASES_H

#include "state.h"

Sym next_player_id(const GameState *state);
int  advance_phase(GameState *state);
void set_game_over(GameState *state);

#endif
