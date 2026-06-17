#ifndef ENGINE_MOVES_H
#define ENGINE_MOVES_H

#include "state.h"

Move make_play_card_move(Sym card_id, int player_index);
Move make_end_main_phase_move(int player_index);
Move make_assassinate_move(Sym target_node_id, Sym troop_owner_id, int slot_index, int player_index);
Move make_deploy_move(Sym node_id, int slot_index, int player_index);
Move make_recruit_move(Sym card_id, int player_index);
Move make_return_spy_move(Sym node_id, Sym spy_owner_id, int player_index);
Move make_activate_ability_move(Sym card_id, Sym ability_key, const int *discard_indices, int discard_count, int player_index);
Move make_decline_ability_move(Sym card_id, Sym ability_key, int player_index);
Move make_promote_card_move(Sym card_id, int player_index);
Move make_skip_promote_move(int player_index);
Move make_initial_placement_move(Sym node_id, int player_index);
Move make_resolve_generic_move(Sym action_id, Sym target_id, int selection_index, int player_index);

#endif
