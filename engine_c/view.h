#ifndef ENGINE_VIEW_H
#define ENGINE_VIEW_H

#include "state.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    Sym  hand[MAX_ZONE_SIZE];
    int  hand_count;
    Sym  discard[MAX_ZONE_SIZE];
    int  discard_count;
    Sym  played[MAX_ZONE_SIZE];
    int  played_count;
    Sym  inner_circle[MAX_ZONE_SIZE];
    int  inner_circle_count;
    Sym  trophy_hall[MAX_ZONE_SIZE];
    int  trophy_hall_count;
    int  barracks;
    int  spies_available;
    int  vp_tokens;
    int  score;
    int  deck_count;
} CPlayerZoneView;

typedef struct {
    Sym  node_id;
    int  kind;
    Sym  adjacent_to[MAX_NODES];
    int  adjacent_count;
    int  control_vp;
    int  total_control_vp_per_turn;
    Sym  troop_slots[MAX_TROOP_SLOTS];
    int  troop_slot_count;
    Sym  spies[MAX_SPY_SLOTS];
    int  spy_count;
    int  vp_tokens;
} CNodeOccupancyView;

typedef struct {
    int round_number;
    int phase;
    Sym current_player_id;
    CPlayerZoneView players[MAX_PLAYERS];
    int player_count;
    Sym player_ids[MAX_PLAYERS];
    Sym market_row[MAX_ZONE_SIZE];
    int market_row_count;
    int market_deck_count;
    int market_discard_count;
    int resource_power;
    int resource_influence;
    Sym devour_pile[MAX_ZONE_SIZE];
    int devour_pile_count;
    CNodeOccupancyView nodes[MAX_NODES];
    int node_count;
    int controlled_sites;
    int total_control_sites;
    int current_player_control_vp;
    int current_player_total_control_vp;
    int house_guard_remaining;
    int priestess_remaining;
    int insane_outcast_remaining;
} CGameView;

void engine_build_view(const GameState *state, CGameView *out);

#ifdef __cplusplus
}
#endif

#endif
