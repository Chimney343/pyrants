#ifndef ENGINE_LOADER_H
#define ENGINE_LOADER_H

#include "state.h"
#include "arena.h"

GameDefinition *engine_load_definition(const char *catalog_path, const char *board_path,
                                        const char *setup_path, Arena *arena);
int engine_apply_setup_json(GameDefinition *def, const char *setup_json, Arena *arena);
GameState *engine_create_game_definition(const GameDefinition *def, const char **player_ids,
                                          int player_count, uint64_t seed);

#endif
