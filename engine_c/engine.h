#ifndef ENGINE_H
#define ENGINE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#include "state.h"
#include "loader.h"

GameState *engine_create_game(const char *json_path, const char **player_ids, int player_count, uint64_t seed);
GameState *engine_create_game_definition(const GameDefinition *def, const char **player_ids, int player_count, uint64_t seed);
GameState *engine_clone(const GameState *state);
void       engine_destroy(GameState *state);

int        engine_legal_moves(const GameState *state, Move *out, int max_moves);
GameState *engine_apply(const GameState *state, const Move *move);
int        engine_is_terminal(const GameState *state);
Sym        engine_winner(const GameState *state, int *score_out);

void       engine_public_view(const GameState *state, PublicView *out);
void       engine_private_view(const GameState *state, Sym player_id, PrivateView *out);

#ifdef __cplusplus
}
#endif

#endif
