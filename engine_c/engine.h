#ifndef ENGINE_H
#define ENGINE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#include "state.h"
#include "loader.h"
#include "visibility.h"

GameState *engine_create_game(const char *json_path, const char **player_ids, int player_count, uint64_t seed);
GameState *engine_create_game_definition(const GameDefinition *def, const char **player_ids, int player_count, uint64_t seed);
GameState *engine_clone(const GameState *state);
void       engine_destroy(GameState *state);

int        engine_legal_moves(const GameState *state, Move *out, int max_moves);
int        engine_display_moves(const GameState *state, Move *out, unsigned char *applicable,
                                int max_moves);

/* The frozen legal-move capacity: one source for the buffer size every caller
 * allocates. A move query reports how many moves exist even when max_moves is
 * smaller, so a caller can size its buffer from this value and treat any larger
 * count as the truncation it is. Python reads this at import and
 * openspiel_pyrants derives NUM_DISTINCT_ACTIONS from it, so the action space
 * cannot drift from the buffer. */
int        engine_move_capacity(void);
GameState *engine_apply(const GameState *state, const Move *move);
int        engine_is_terminal(const GameState *state);
Sym        engine_winner(const GameState *state, int *score_out);

#ifdef __cplusplus
}
#endif

#endif
