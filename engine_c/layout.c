#include "layout.h"
#include "state.h"
#include "view.h"

#include <string.h>

/* Each entry is derived from the compiler's own sizeof/offsetof, so the probe
 * cannot drift from the structs it describes. The Python bindings assert every
 * mirrored ctypes field against this table at import time. */
typedef struct {
    const char *type_name;
    const char *field_name;
    size_t      size;
    long long   offset;
} LayoutEntry;

#define SIZE_OF(type)        { #type, NULL, sizeof(type), 0 }
#define SIZE_EXPR(name, expr) { name, NULL, (size_t)(expr), 0 }
#define FIELD(type, field)   { #type, #field, 0, (long long)offsetof(type, field) }
#define UNION_FIELD(type, field) { #type, #field, 0, 0 }

static const LayoutEntry layout_entries[] = {
    /* Catalog / definition structs */
    SIZE_OF(MetaEntry),
    FIELD(MetaEntry, key),
    FIELD(MetaEntry, value),

    SIZE_OF(CardAction),
    FIELD(CardAction, action_id),
    FIELD(CardAction, op),
    FIELD(CardAction, target_scope),
    FIELD(CardAction, timing),
    FIELD(CardAction, optional),
    FIELD(CardAction, quantity_kind),
    FIELD(CardAction, quantity_value),
    FIELD(CardAction, filters),
    FIELD(CardAction, filter_count),
    FIELD(CardAction, source_fragment),
    FIELD(CardAction, metadata),
    FIELD(CardAction, metadata_count),

    SIZE_OF(CardOption),
    FIELD(CardOption, option_id),
    FIELD(CardOption, actions),
    FIELD(CardOption, action_count),

    SIZE_OF(ExecutionModel),
    FIELD(ExecutionModel, kind),
    FIELD(ExecutionModel, actions),
    FIELD(ExecutionModel, action_count),
    FIELD(ExecutionModel, options),
    FIELD(ExecutionModel, option_count),
    FIELD(ExecutionModel, selection),
    FIELD(ExecutionModel, repeat_count),
    FIELD(ExecutionModel, allow_repeat),

    SIZE_OF(GlobalCondition),
    FIELD(GlobalCondition, condition_type),
    FIELD(GlobalCondition, description),

    SIZE_OF(StateContract),
    FIELD(StateContract, reads),
    FIELD(StateContract, read_count),
    FIELD(StateContract, writes),
    FIELD(StateContract, write_count),

    SIZE_OF(PaidAbility),
    FIELD(PaidAbility, present),
    FIELD(PaidAbility, ability_key),
    FIELD(PaidAbility, effect_key),
    FIELD(PaidAbility, effect_payload),
    FIELD(PaidAbility, effect_payload_count),
    FIELD(PaidAbility, cost_power),
    FIELD(PaidAbility, cost_influence),
    FIELD(PaidAbility, cost_discard),

    SIZE_OF(CardDefinition),
    FIELD(CardDefinition, card_id),
    FIELD(CardDefinition, name),
    FIELD(CardDefinition, cost),
    FIELD(CardDefinition, aspect),
    FIELD(CardDefinition, secondary_aspects),
    FIELD(CardDefinition, secondary_aspect_count),
    FIELD(CardDefinition, deck_vp),
    FIELD(CardDefinition, inner_circle_vp),
    FIELD(CardDefinition, rules_text),
    FIELD(CardDefinition, notes),
    FIELD(CardDefinition, execution),
    FIELD(CardDefinition, actions),
    FIELD(CardDefinition, action_count),
    FIELD(CardDefinition, global_conditions),
    FIELD(CardDefinition, global_condition_count),
    FIELD(CardDefinition, state_contract),
    FIELD(CardDefinition, effect_key),
    FIELD(CardDefinition, effect_payload),
    FIELD(CardDefinition, effect_payload_count),
    FIELD(CardDefinition, paid_ability),

    SIZE_OF(CardCatalog),
    FIELD(CardCatalog, catalog_id),
    FIELD(CardCatalog, version),
    FIELD(CardCatalog, cards),
    FIELD(CardCatalog, card_count),

    SIZE_OF(NodeDefinition),
    FIELD(NodeDefinition, node_id),
    FIELD(NodeDefinition, kind),
    FIELD(NodeDefinition, adjacent_to),
    FIELD(NodeDefinition, adjacent_count),
    FIELD(NodeDefinition, troop_capacity),
    FIELD(NodeDefinition, control_vp),
    FIELD(NodeDefinition, total_control_vp_per_turn),
    FIELD(NodeDefinition, influence_income),
    FIELD(NodeDefinition, initial_troop_slots),
    FIELD(NodeDefinition, initial_troop_slot_count),
    FIELD(NodeDefinition, initial_vp_tokens),

    SIZE_OF(BoardDefinition),
    FIELD(BoardDefinition, board_id),
    FIELD(BoardDefinition, nodes),
    FIELD(BoardDefinition, node_count),

    SIZE_OF(DeckEntry),
    FIELD(DeckEntry, card_id),
    FIELD(DeckEntry, count),

    SIZE_OF(DeckDefinition),
    FIELD(DeckDefinition, deck_id),
    FIELD(DeckDefinition, name),
    FIELD(DeckDefinition, kind),
    FIELD(DeckDefinition, total_cards),
    FIELD(DeckDefinition, per_player),
    FIELD(DeckDefinition, entries),
    FIELD(DeckDefinition, entry_count),

    SIZE_OF(SpecialStackDef),
    FIELD(SpecialStackDef, card_id),
    FIELD(SpecialStackDef, market_slot),
    FIELD(SpecialStackDef, stack_total),
    FIELD(SpecialStackDef, recruitable),

    SIZE_OF(SetupDefinition),
    FIELD(SetupDefinition, setup_id),
    FIELD(SetupDefinition, starter_deck),
    FIELD(SetupDefinition, market_deck),
    FIELD(SetupDefinition, market_row_size),
    FIELD(SetupDefinition, special_stacks),
    FIELD(SetupDefinition, special_stack_count),

    SIZE_OF(GameDefinition),
    FIELD(GameDefinition, definition_id),
    FIELD(GameDefinition, board),
    FIELD(GameDefinition, catalog),
    FIELD(GameDefinition, setup),
    FIELD(GameDefinition, default_player_troops),
    FIELD(GameDefinition, default_player_spies),

    /* Mutable runtime state */
    SIZE_OF(NodeState),
    FIELD(NodeState, node_id),
    FIELD(NodeState, troop_slots),
    FIELD(NodeState, troop_slot_count),
    FIELD(NodeState, spies),
    FIELD(NodeState, spy_count),
    FIELD(NodeState, vp_tokens),
    FIELD(NodeState, cow_dirty),

    SIZE_OF(PlayerState),
    FIELD(PlayerState, player_id),
    FIELD(PlayerState, deck),
    FIELD(PlayerState, deck_count),
    FIELD(PlayerState, hand),
    FIELD(PlayerState, hand_count),
    FIELD(PlayerState, discard_pile),
    FIELD(PlayerState, discard_pile_count),
    FIELD(PlayerState, played_cards),
    FIELD(PlayerState, played_cards_count),
    FIELD(PlayerState, inner_circle),
    FIELD(PlayerState, inner_circle_count),
    FIELD(PlayerState, trophy_hall),
    FIELD(PlayerState, trophy_hall_count),
    FIELD(PlayerState, barracks),
    FIELD(PlayerState, spies_available),
    FIELD(PlayerState, vp_tokens),
    FIELD(PlayerState, score),
    FIELD(PlayerState, cow_dirty),

    SIZE_OF(ResourcePool),
    FIELD(ResourcePool, power),
    FIELD(ResourcePool, influence),
    FIELD(ResourcePool, cow_dirty),

    SIZE_OF(MarketState),
    FIELD(MarketState, deck),
    FIELD(MarketState, deck_count),
    FIELD(MarketState, row),
    FIELD(MarketState, row_count),
    FIELD(MarketState, discard_pile),
    FIELD(MarketState, discard_pile_count),
    FIELD(MarketState, cow_dirty),

    SIZE_OF(PendingAbilityState),
    FIELD(PendingAbilityState, card_id),
    FIELD(PendingAbilityState, ability_key),
    FIELD(PendingAbilityState, resolved),

    SIZE_OF(PendingPromotionState),
    FIELD(PendingPromotionState, card_id),
    FIELD(PendingPromotionState, timing),
    FIELD(PendingPromotionState, optional),
    FIELD(PendingPromotionState, deferred_choice),
    FIELD(PendingPromotionState, source_card_id),
    FIELD(PendingPromotionState, requires_another_played_card),
    FIELD(PendingPromotionState, required_aspect),
    FIELD(PendingPromotionState, required_secondary_aspect),
    FIELD(PendingPromotionState, focus_aspect),
    FIELD(PendingPromotionState, repeat_while_targets),
    FIELD(PendingPromotionState, promotions_remaining),

    SIZE_OF(PendingGenericChoiceState),
    FIELD(PendingGenericChoiceState, source_card_id),
    FIELD(PendingGenericChoiceState, exec_kind),
    FIELD(PendingGenericChoiceState, option_ids),
    FIELD(PendingGenericChoiceState, option_count),
    FIELD(PendingGenericChoiceState, selected_option_ids),
    FIELD(PendingGenericChoiceState, selected_count),
    FIELD(PendingGenericChoiceState, current_option_id),
    FIELD(PendingGenericChoiceState, current_actions),
    FIELD(PendingGenericChoiceState, current_action_count),
    FIELD(PendingGenericChoiceState, next_action_index),
    FIELD(PendingGenericChoiceState, awaiting_option),
    FIELD(PendingGenericChoiceState, remaining_repeats),
    FIELD(PendingGenericChoiceState, allow_repeat),
    FIELD(PendingGenericChoiceState, last_selection_keys),
    FIELD(PendingGenericChoiceState, last_selection_values),
    FIELD(PendingGenericChoiceState, last_selection_count),
    FIELD(PendingGenericChoiceState, counter_keys),
    FIELD(PendingGenericChoiceState, counter_values),
    FIELD(PendingGenericChoiceState, counter_count),
    FIELD(PendingGenericChoiceState, limit_keys),
    FIELD(PendingGenericChoiceState, limit_values),
    FIELD(PendingGenericChoiceState, limit_count),
    FIELD(PendingGenericChoiceState, resolve_depth),
    FIELD(PendingGenericChoiceState, parent),
    FIELD(PendingGenericChoiceState, last_played_card_id),

    SIZE_OF(GameState),
    FIELD(GameState, definition),
    FIELD(GameState, nodes),
    FIELD(GameState, node_count),
    FIELD(GameState, players),
    FIELD(GameState, player_count),
    FIELD(GameState, player_ids),
    FIELD(GameState, player_id_count),
    FIELD(GameState, current_player_id),
    FIELD(GameState, phase),
    FIELD(GameState, round_number),
    FIELD(GameState, resource_pool),
    FIELD(GameState, market),
    FIELD(GameState, final_score_keys),
    FIELD(GameState, final_score_values),
    FIELD(GameState, final_score_count),
    FIELD(GameState, pending_ability),
    FIELD(GameState, pending_immediate),
    FIELD(GameState, pending_immediate_count),
    FIELD(GameState, pending_eot),
    FIELD(GameState, pending_eot_count),
    FIELD(GameState, pending_generic),
    FIELD(GameState, devour_pile),
    FIELD(GameState, devour_pile_count),
    FIELD(GameState, setup_complete),
    FIELD(GameState, setup_complete_count),
    FIELD(GameState, shuffle_seed),
    FIELD(GameState, shuffle_counter),
    FIELD(GameState, arena),

    /* Move discriminated union */
    SIZE_OF(Move),
    FIELD(Move, type),
    FIELD(Move, data),
    FIELD(Move, player_index),
    SIZE_EXPR("MoveData", sizeof(((Move *)0)->data)),
    UNION_FIELD(MoveData, play_card),
    UNION_FIELD(MoveData, assassinate),
    UNION_FIELD(MoveData, deploy),
    UNION_FIELD(MoveData, recruit),
    UNION_FIELD(MoveData, return_spy),
    UNION_FIELD(MoveData, activate_ability),
    UNION_FIELD(MoveData, decline_ability),
    UNION_FIELD(MoveData, promote_card),
    UNION_FIELD(MoveData, skip_promote),
    UNION_FIELD(MoveData, resolve_generic),
    UNION_FIELD(MoveData, initial_placement),

    /* View structs */
    SIZE_OF(CPlayerZoneView),
    FIELD(CPlayerZoneView, hand),
    FIELD(CPlayerZoneView, hand_count),
    FIELD(CPlayerZoneView, discard),
    FIELD(CPlayerZoneView, discard_count),
    FIELD(CPlayerZoneView, played),
    FIELD(CPlayerZoneView, played_count),
    FIELD(CPlayerZoneView, inner_circle),
    FIELD(CPlayerZoneView, inner_circle_count),
    FIELD(CPlayerZoneView, trophy_hall),
    FIELD(CPlayerZoneView, trophy_hall_count),
    FIELD(CPlayerZoneView, barracks),
    FIELD(CPlayerZoneView, spies_available),
    FIELD(CPlayerZoneView, vp_tokens),
    FIELD(CPlayerZoneView, score),
    FIELD(CPlayerZoneView, deck_count),

    SIZE_OF(CNodeOccupancyView),
    FIELD(CNodeOccupancyView, node_id),
    FIELD(CNodeOccupancyView, kind),
    FIELD(CNodeOccupancyView, adjacent_to),
    FIELD(CNodeOccupancyView, adjacent_count),
    FIELD(CNodeOccupancyView, control_vp),
    FIELD(CNodeOccupancyView, total_control_vp_per_turn),
    FIELD(CNodeOccupancyView, troop_slots),
    FIELD(CNodeOccupancyView, troop_slot_count),
    FIELD(CNodeOccupancyView, spies),
    FIELD(CNodeOccupancyView, spy_count),
    FIELD(CNodeOccupancyView, vp_tokens),

    SIZE_OF(CGameView),
    FIELD(CGameView, round_number),
    FIELD(CGameView, phase),
    FIELD(CGameView, current_player_id),
    FIELD(CGameView, players),
    FIELD(CGameView, player_count),
    FIELD(CGameView, player_ids),
    FIELD(CGameView, market_row),
    FIELD(CGameView, market_row_count),
    FIELD(CGameView, market_deck_count),
    FIELD(CGameView, market_discard_count),
    FIELD(CGameView, resource_power),
    FIELD(CGameView, resource_influence),
    FIELD(CGameView, devour_pile),
    FIELD(CGameView, devour_pile_count),
    FIELD(CGameView, nodes),
    FIELD(CGameView, node_count),
    FIELD(CGameView, controlled_sites),
    FIELD(CGameView, total_control_sites),
    FIELD(CGameView, current_player_control_vp),
    FIELD(CGameView, current_player_total_control_vp),
    FIELD(CGameView, house_guard_remaining),
    FIELD(CGameView, priestess_remaining),
    FIELD(CGameView, insane_outcast_remaining),
};

size_t engine_layout_size(const char *type_name) {
    if (!type_name) return (size_t)-1;
    for (size_t i = 0; i < sizeof(layout_entries) / sizeof(layout_entries[0]); i++) {
        const LayoutEntry *entry = &layout_entries[i];
        if (entry->field_name == NULL && strcmp(entry->type_name, type_name) == 0)
            return entry->size;
    }
    return (size_t)-1;
}

long long engine_layout_offset(const char *type_name, const char *field_name) {
    if (!type_name || !field_name) return -1;
    for (size_t i = 0; i < sizeof(layout_entries) / sizeof(layout_entries[0]); i++) {
        const LayoutEntry *entry = &layout_entries[i];
        if (entry->field_name != NULL &&
            strcmp(entry->type_name, type_name) == 0 &&
            strcmp(entry->field_name, field_name) == 0) {
            return entry->offset;
        }
    }
    return -1;
}
