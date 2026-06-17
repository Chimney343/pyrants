#ifndef ENGINE_PLAYER_VIEW_H
#define ENGINE_PLAYER_VIEW_H
#include "state.h"
void engine_public_view(const GameState *state, PublicView *out);
void engine_private_view(const GameState *state, Sym player_id, PrivateView *out);
#endif
