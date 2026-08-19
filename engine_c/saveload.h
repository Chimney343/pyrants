#ifndef ENGINE_SAVELOAD_H
#define ENGINE_SAVELOAD_H

#include "state.h"
#include "arena.h"

#ifdef __cplusplus
extern "C" {
#endif

int engine_serialize_state(const GameState *state,
                           const char *catalog_path,
                           const char *board_path,
                           const char *setup_path,
                           int move_count, int is_terminal,
                           char *out_json, int out_cap);

GameState *engine_deserialize_state(const char *json,
                                    const char *catalog_json,
                                    Arena *arena,
                                    int *out_move_count);

#ifdef __cplusplus
}
#endif

#endif
