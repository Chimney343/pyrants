#ifndef ENGINE_SCORING_H
#define ENGINE_SCORING_H

#include "state.h"

int  site_control_owner(const GameState *state, Sym node_id);
int  is_total_control(const GameState *state, Sym node_id, Sym player_id);
void award_end_of_turn_site_vp(GameState *state, Sym player_id);
void compute_final_scores(const GameState *state, int *scores_out);
Sym  find_winner(const GameState *state);

#endif
