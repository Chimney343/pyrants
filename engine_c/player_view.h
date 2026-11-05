#ifndef ENGINE_PLAYER_VIEW_H
#define ENGINE_PLAYER_VIEW_H
#include "state.h"

/* 128-bit fingerprint of exactly the fields
 * ``CEngineAdapter.private_view_json`` serialises for ``player_id`` (the A1
 * IS-MCTS tree key).  Equal keys iff equal observation strings; hidden deck /
 * devour identities and opponents' hands are deliberately excluded, node spies
 * are order-insensitive to match the string's sorted spy list. */
void engine_infostate_hash(const GameState *state, Sym player_id, uint64_t out[2]);
#endif
