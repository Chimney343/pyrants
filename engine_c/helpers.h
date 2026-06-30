#ifndef ENGINE_HELPERS_H
#define ENGINE_HELPERS_H

#include "state.h"

#define EFFECT_COUNT 16

typedef GameState* (*EffectFn)(GameState*, Sym player_id, const CardDefinition* card);

extern EffectFn effect_registry[EFFECT_COUNT];
void register_effect(Sym effect_key, EffectFn fn);
EffectFn lookup_effect(Sym effect_key);

int  has_presence(const GameState *state, Sym player_id, Sym node_id);
int  player_has_any_troops_on_board(const GameState *state, Sym player_id);
int  can_deploy_to_node(const GameState *state, Sym player_id, Sym node_id, int has_troops);
int  legal_initial_placement_node_ids(const GameState *state, Sym *out, int max_out);
int  count_controlled_sites(const GameState *state, Sym player_id);
int  count_owned_control_markers(const GameState *state, Sym player_id);
int  count_total_controlled_sites(const GameState *state, Sym player_id);
int  count_runtime_cards_by_aspect(const GameState *state, Sym *card_ids, int count,
                                    Sym required_aspect, Sym required_secondary_aspect);
int  is_aberrations_enabled(const GameState *state);
int  special_stack_config(int market_slot, Sym *card_id_out, int *stack_total);
int  remaining_special_stack_count(const GameState *state, Sym card_id, int stack_total);
int  player_index_for_id(const GameState *state, Sym player_id);
int  count_trophies(const PlayerState *ps, const char *filter);
int  scaled_vp_award_count(const GameState *state, Sym player_id, const CardAction *action);
int  focus_requirement_met(const GameState *state, Sym player_id, const CardDefinition *card, Sym source_card_id, Sym focus_aspect_override);

void promote_card(GameState *state, Sym player_id, Sym card_id);
int  apply_promote_instruction(GameState *state, Sym player_id, Sym card_id, Sym timing, int optional);

void grant_resource(GameState *state, Sym resource, int amount);
int  apply_free_assassinate(GameState *state, Sym player_id, Sym target_node_id, int target_slot_index);
int  apply_free_deploy(GameState *state, Sym player_id, Sym target_node_id);
int  apply_return_spy(GameState *state, Sym player_id, Sym node_id, Sym spy_owner_id, int free_enemy_return);
int  apply_recruit(GameState *state, Sym player_id, int market_slot);
int  apply_recruit_free(GameState *state, Sym player_id, int market_slot);

int  ability_cost_affordable(const GameState *state, Sym player_id, Sym card_id);
int  pay_ability_cost(GameState *state, Sym player_id, Sym card_id, int *discard_indices, int discard_count);
int  can_activate_pending_ability(const GameState *state, Sym player_id, Sym card_id, Sym ability_key);
int  deferred_promotion_target_ids(const GameState *state, Sym player_id,
                                    const PendingPromotionState *pending, Sym *out, int max_out);

#endif
