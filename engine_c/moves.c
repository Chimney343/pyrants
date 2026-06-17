#include "moves.h"
#include <string.h>

Move make_play_card_move(Sym card_id, int player_index) {
    Move m; memset(&m, 0, sizeof(m));
    m.type = MOVE_PLAY_CARD;
    m.data.play_card.card_id = card_id;
    m.player_index = player_index;
    return m;
}

Move make_end_main_phase_move(int player_index) {
    Move m; memset(&m, 0, sizeof(m));
    m.type = MOVE_END_MAIN_PHASE;
    m.player_index = player_index;
    return m;
}

Move make_assassinate_move(Sym target_node_id, Sym troop_owner_id, int slot_index, int player_index) {
    Move m; memset(&m, 0, sizeof(m));
    m.type = MOVE_ASSASSINATE;
    m.data.assassinate.target_node_id = target_node_id;
    m.data.assassinate.troop_owner_id = troop_owner_id;
    m.data.assassinate.slot_index = slot_index;
    m.player_index = player_index;
    return m;
}

Move make_deploy_move(Sym node_id, int slot_index, int player_index) {
    Move m; memset(&m, 0, sizeof(m));
    m.type = MOVE_DEPLOY;
    m.data.deploy.node_id = node_id;
    m.data.deploy.slot_index = slot_index;
    m.player_index = player_index;
    return m;
}

Move make_recruit_move(Sym card_id, int player_index) {
    Move m; memset(&m, 0, sizeof(m));
    m.type = MOVE_RECRUIT;
    m.data.recruit.card_id = card_id;
    m.player_index = player_index;
    return m;
}

Move make_return_spy_move(Sym node_id, Sym spy_owner_id, int player_index) {
    Move m; memset(&m, 0, sizeof(m));
    m.type = MOVE_RETURN_SPY;
    m.data.return_spy.node_id = node_id;
    m.data.return_spy.spy_owner_id = spy_owner_id;
    m.player_index = player_index;
    return m;
}

Move make_activate_ability_move(Sym card_id, Sym ability_key, const int *discard_indices, int discard_count, int player_index) {
    Move m; memset(&m, 0, sizeof(m));
    m.type = MOVE_ACTIVATE_ABILITY;
    m.data.activate_ability.card_id = card_id;
    m.data.activate_ability.ability_key = ability_key;
    int n = discard_count;
    if (n > MAX_ABILITY_DISCARD) n = MAX_ABILITY_DISCARD;
    if (n < 0) n = 0;
    for (int i = 0; i < n; i++)
        m.data.activate_ability.discard_hand_indices[i] = discard_indices ? discard_indices[i] : 0;
    m.data.activate_ability.discard_hand_count = n;
    m.player_index = player_index;
    return m;
}

Move make_decline_ability_move(Sym card_id, Sym ability_key, int player_index) {
    Move m; memset(&m, 0, sizeof(m));
    m.type = MOVE_DECLINE_ABILITY;
    m.data.decline_ability.card_id = card_id;
    m.data.decline_ability.ability_key = ability_key;
    m.player_index = player_index;
    return m;
}

Move make_promote_card_move(Sym card_id, int player_index) {
    Move m; memset(&m, 0, sizeof(m));
    m.type = MOVE_PROMOTE_CARD;
    m.data.promote_card.card_id = card_id;
    m.player_index = player_index;
    return m;
}

Move make_skip_promote_move(int player_index) {
    Move m; memset(&m, 0, sizeof(m));
    m.type = MOVE_SKIP_PROMOTE;
    m.player_index = player_index;
    return m;
}

Move make_initial_placement_move(Sym node_id, int player_index) {
    Move m; memset(&m, 0, sizeof(m));
    m.type = MOVE_INITIAL_PLACEMENT;
    m.data.initial_placement.node_id = node_id;
    m.player_index = player_index;
    return m;
}

Move make_resolve_generic_move(Sym action_id, Sym target_id, int selection_index, int player_index) {
    Move m; memset(&m, 0, sizeof(m));
    m.type = MOVE_RESOLVE_GENERIC;
    m.data.resolve_generic.action_id = action_id;
    m.data.resolve_generic.target_id = target_id;
    m.data.resolve_generic.selection_index = selection_index;
    m.player_index = player_index;
    return m;
}
