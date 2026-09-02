#ifndef ENGINE_STATE_H
#define ENGINE_STATE_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "intern.h"
#include "rng.h"

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_PLAYERS         4
#define MAX_NODES           128
#define MAX_ZONE_SIZE       80
#define MAX_TROOP_SLOTS     8
#define MAX_PENDING_PROMO   16
#define MAX_SPY_SLOTS       4
#define MAX_PENDING_ACTIONS 32
#define MAX_OPTIONS         8
#define MAX_FILTERS         4
#define MAX_METADATA        8
#define MAX_DECK_ENTRIES    32
#define MAX_ABILITY_DISCARD 8
#define MAX_SPECIAL_STACKS  3

typedef enum { NODE_SITE = 0, NODE_ROUTE = 1 } NodeKind;

typedef enum {
    PHASE_SETUP = 0, PHASE_DRAW, PHASE_MAIN,
    PHASE_END_OF_TURN, PHASE_CLEANUP, PHASE_GAME_OVER
} TurnPhase;

typedef enum {
    EXEC_SEQUENCE = 0, EXEC_MODAL = 1, EXEC_REPEAT = 2
} ExecKind;

typedef enum {
    QUANT_FIXED = 0, QUANT_UNSPECIFIED = 1
} QuantityKind;

typedef enum {
    MOVE_PLAY_CARD = 0, MOVE_END_MAIN_PHASE, MOVE_RESOLVE_END_OF_TURN,
    MOVE_RESOLVE_CLEANUP, MOVE_ASSASSINATE, MOVE_DEPLOY, MOVE_RECRUIT,
    MOVE_RETURN_SPY, MOVE_ACTIVATE_ABILITY, MOVE_DECLINE_ABILITY,
    MOVE_PROMOTE_CARD, MOVE_SKIP_PROMOTE, MOVE_RESOLVE_GENERIC,
    MOVE_INITIAL_PLACEMENT, MOVE_COUNT
} MoveType;

/* ---- Immutable Catalog Structures (arena-allocated, loaded once) ---- */

typedef struct {
    Sym   key;
    Sym   value;
} MetaEntry;

typedef struct {
    Sym        action_id;
    Sym        op;
    Sym        target_scope;
    Sym        timing;
    bool       optional;
    int        quantity_kind;
    int        quantity_value;
    Sym        filters[MAX_FILTERS];
    int        filter_count;
    Sym        source_fragment;
    MetaEntry  metadata[MAX_METADATA];
    int        metadata_count;
} CardAction;

typedef struct {
    Sym         option_id;
    CardAction *actions;
    int         action_count;
} CardOption;

typedef struct {
    int          kind;
    CardAction  *actions;
    int          action_count;
    CardOption  *options;
    int          option_count;
    Sym          selection;
    int          repeat_count;
    bool         allow_repeat;
} ExecutionModel;

typedef struct {
    Sym  condition_type;
    Sym  description;
} GlobalCondition;

typedef struct {
    Sym *reads;
    int  read_count;
    Sym *writes;
    int  write_count;
} StateContract;

/* Nested paid-ability definition mirroring Python's
 * effect_payload["paid_ability"] = {ability_key, effect_key, effect_payload, cost}.
 * Resolved at load time: ability_key falls back to effect_key and vice-versa. */
typedef struct {
    bool       present;            /* card defines a paid_ability */
    Sym        ability_key;        /* paid_ability.ability_key or effect_key */
    Sym        effect_key;         /* paid_ability.effect_key or ability_key */
    MetaEntry *effect_payload;
    int        effect_payload_count;
    int        cost_power;
    int        cost_influence;
    int        cost_discard;
} PaidAbility;

typedef struct CardDefinition {
    Sym               card_id;
    Sym               name;
    int               cost;
    Sym               aspect;
    Sym              *secondary_aspects;
    int               secondary_aspect_count;
    int               deck_vp;
    int               inner_circle_vp;
    Sym               rules_text;
    Sym               notes;
    ExecutionModel    execution;
    CardAction       *actions;
    int               action_count;
    GlobalCondition  *global_conditions;
    int               global_condition_count;
    StateContract     state_contract;
    Sym               effect_key;
    MetaEntry        *effect_payload;
    int               effect_payload_count;
    PaidAbility       paid_ability;
} CardDefinition;

typedef struct {
    Sym             catalog_id;
    Sym             version;
    CardDefinition *cards;
    int             card_count;
} CardCatalog;

/* ---- Immutable Board / Deck / Setup Structures ---- */

typedef struct {
    Sym   node_id;
    Sym   kind;
    Sym  *adjacent_to;
    int   adjacent_count;
    int   troop_capacity;
    int   control_vp;
    int   total_control_vp_per_turn;
    int   influence_income;
    Sym  *initial_troop_slots;
    int   initial_troop_slot_count;
    int   initial_vp_tokens;
} NodeDefinition;

typedef struct {
    Sym             board_id;
    NodeDefinition *nodes;
    int             node_count;
} BoardDefinition;

typedef struct {
    Sym card_id;
    int count;
} DeckEntry;

typedef struct {
    Sym        deck_id;
    Sym        name;
    Sym        kind;
    int        total_cards;
    bool       per_player;
    DeckEntry *entries;
    int        entry_count;
} DeckDefinition;

typedef struct {
    Sym card_id;
    int market_slot;
    int stack_total;
} SpecialStackDef;

typedef struct {
    Sym            setup_id;
    DeckDefinition starter_deck;
    DeckDefinition market_deck;
    int            market_row_size;
    SpecialStackDef special_stacks[MAX_SPECIAL_STACKS];
    int             special_stack_count;
} SetupDefinition;

typedef struct {
    Sym             definition_id;
    BoardDefinition board;
    CardCatalog     catalog;
    SetupDefinition setup;
    int             default_player_troops;
    int             default_player_spies;
} GameDefinition;

/* ---- Mutable Runtime State Structures ---- */

typedef struct {
    Sym  node_id;
    Sym  troop_slots[MAX_TROOP_SLOTS];
    int  troop_slot_count;
    Sym  spies[MAX_SPY_SLOTS];
    int  spy_count;
    int  vp_tokens;
    bool cow_dirty;
} NodeState;

typedef struct {
    Sym  player_id;
    Sym  deck[MAX_ZONE_SIZE];
    int  deck_count;
    Sym  hand[MAX_ZONE_SIZE];
    int  hand_count;
    Sym  discard_pile[MAX_ZONE_SIZE];
    int  discard_pile_count;
    Sym  played_cards[MAX_ZONE_SIZE];
    int  played_cards_count;
    Sym  inner_circle[MAX_ZONE_SIZE];
    int  inner_circle_count;
    Sym  trophy_hall[MAX_ZONE_SIZE];
    int  trophy_hall_count;
    int  barracks;
    int  spies_available;
    int  vp_tokens;
    int  score;
    bool cow_dirty;
} PlayerState;

typedef struct {
    int power;
    int influence;
    bool cow_dirty;
} ResourcePool;

typedef struct {
    Sym  deck[MAX_ZONE_SIZE];
    int  deck_count;
    Sym  row[MAX_ZONE_SIZE];
    int  row_count;
    Sym  discard_pile[MAX_ZONE_SIZE];
    int  discard_pile_count;
    bool cow_dirty;
} MarketState;

typedef struct {
    Sym  card_id;
    Sym  ability_key;
    bool resolved;
} PendingAbilityState;

typedef struct {
    Sym  card_id;
    Sym  timing;
    bool optional;
    bool deferred_choice;
    Sym  source_card_id;
    bool requires_another_played_card;
    Sym  required_aspect;
    Sym  required_secondary_aspect;
    Sym  focus_aspect;
    bool repeat_while_targets;
    int  promotions_remaining;
} PendingPromotionState;

typedef struct PendingGenericChoiceState {
    Sym          source_card_id;
    int          exec_kind;
    Sym         *option_ids;
    int          option_count;
    Sym         *selected_option_ids;
    int          selected_count;
    Sym          current_option_id;
    CardAction  *current_actions;
    int          current_action_count;
    int          next_action_index;
    bool         awaiting_option;
    int          remaining_repeats;
    bool         allow_repeat;
    Sym          last_selection_keys[8];
    Sym          last_selection_values[8];
    int          last_selection_count;
    Sym          counter_keys[8];
    int          counter_values[8];
    int          counter_count;
    Sym          limit_keys[8];
    int          limit_values[8];
    int          limit_count;
    int          resolve_depth;
    struct PendingGenericChoiceState *parent;
    Sym          last_played_card_id;
} PendingGenericChoiceState;

typedef struct GameState {
    const GameDefinition *definition;

    NodeState  nodes[MAX_NODES];
    int        node_count;

    PlayerState players[MAX_PLAYERS];
    int         player_count;
    Sym         player_ids[MAX_PLAYERS];
    int         player_id_count;

    Sym       current_player_id;
    TurnPhase phase;
    int       round_number;

    ResourcePool resource_pool;
    MarketState  market;

    int final_score_keys[MAX_PLAYERS];
    int final_score_values[MAX_PLAYERS];
    int final_score_count;

    PendingAbilityState *pending_ability;

    PendingPromotionState pending_immediate[MAX_PENDING_PROMO];
    int                    pending_immediate_count;
    PendingPromotionState pending_eot[MAX_PENDING_PROMO];
    int                    pending_eot_count;

    PendingGenericChoiceState *pending_generic;

    Sym  devour_pile[MAX_ZONE_SIZE];
    int  devour_pile_count;

    Sym  setup_complete[MAX_PLAYERS];
    int  setup_complete_count;

    uint64_t shuffle_seed;
    int      shuffle_counter;

    void    *arena;
} GameState;

/* ---- Move Discriminated Union ---- */

typedef struct {
    MoveType type;
    union {
        struct { Sym card_id; int hand_index; } play_card;
        struct { int _pad; } end_main_phase;
        struct { int _pad; } resolve_end_of_turn;
        struct { int _pad; } resolve_cleanup;
        struct { Sym target_node_id; Sym troop_owner_id; int slot_index; } assassinate;
        struct { Sym node_id; int slot_index; } deploy;
        struct { Sym card_id; } recruit;
        struct { Sym node_id; Sym spy_owner_id; } return_spy;
        struct { Sym card_id; Sym ability_key; int discard_hand_indices[MAX_ABILITY_DISCARD]; int discard_hand_count; } activate_ability;
        struct { Sym card_id; Sym ability_key; } decline_ability;
        struct { Sym card_id; } promote_card;
        struct { Sym source_card_id; } skip_promote;
        struct { Sym action_id; Sym target_id; int selection_index; } resolve_generic;
        struct { Sym node_id; } initial_placement;
    } data;
    int player_index;
} Move;

/* ---- Player View Structures ---- */

typedef struct {
    Sym  node_id;
    int  troop_counts[MAX_PLAYERS];
    int  troop_owner_count;
    Sym  troop_owners[MAX_PLAYERS];
    int  white_troops;
    int  spy_owner_count;
    Sym  spy_owners[MAX_SPY_SLOTS];
    int  vp_tokens;
    bool controlled;
    Sym  controller_id;
} PublicNodeView;

typedef struct {
    Sym  ability_key;
    Sym  source_card_id;
    bool resolved;
} PublicPendingAbilityView;

typedef struct {
    Sym  card_id;
    bool is_optional;
    int  player_index;
} PublicPendingPromotionView;

typedef struct {
    Sym  source_card_id;
    int  player_index;
    bool is_pending;
} PublicPendingGenericChoiceView;

typedef struct {
    int          player_count;
    Sym          player_ids[MAX_PLAYERS];
    int          node_count;
    PublicNodeView nodes[MAX_NODES];
    int          round_number;
    TurnPhase    phase;
    Sym          current_player_id;
    ResourcePool resource_pool;
    MarketState  market;
    PublicPendingAbilityView     pending_ability;
    bool                         has_pending_ability;
    PublicPendingPromotionView   pending_immediate[MAX_PENDING_PROMO];
    int                          pending_immediate_count;
    PublicPendingGenericChoiceView pending_generic;
    bool                            has_pending_generic;
} PublicView;

typedef struct {
    PublicView   public_view;
    PlayerState  player;
    int          player_index;
} PrivateView;

#ifdef __cplusplus
}
#endif

NodeState *cow_node(GameState *state, Sym node_id);
PlayerState *cow_player(GameState *state, Sym player_id);
MarketState *cow_market(GameState *state);
ResourcePool *cow_resource_pool(GameState *state);

void expand_deck(const DeckDefinition *dd, Sym *out, int *out_count);
void shuffle_deck(Sym *deck, int count, uint64_t seed, int counter, RNG *rng);
void draw_cards_state(PlayerState *ps, int count, RNG *rng, uint64_t shuffle_seed, int *shuffle_counter);
void reshuffle_discard_into_deck(GameState *state, Sym player_id);

GameState *engine_clone_cow(const GameState *src);
GameState *engine_determinize(const GameState *src, Sym observing_player_id, uint64_t seed);

#endif
