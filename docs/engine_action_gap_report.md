# Engine Action Gap Report

Source review log: docs/first_deck_review.md

## Summary

This report maps derived effect families to current engine support in engine/state.py, engine/moves.py, and engine/rules.py.

- Supported: 2
- Partial: 43
- Unsupported: 68

## Family Coverage

| family_id | status | notes |
|---|---|---|
| assassinate_plus_conditional_power_from_trophies | partial | AssassinateMove exists; family-specific filters and free-effect variants missing |
| assassinate_plus_scaled_power_from_trophy_hall | partial | AssassinateMove exists; family-specific filters and free-effect variants missing |
| assassinate_troop_plus_focus_power_bonus | partial | AssassinateMove exists; family-specific filters and free-effect variants missing |
| assassinate_troop_plus_recruit_aspect_filtered_card_by_cost | partial | AssassinateMove exists; family-specific filters and free-effect variants missing |
| assassinate_white_troop_plus_triggered_promote_aspect_filtered | partial | Promotion queues exist, but family-specific promote handlers are not registered; AssassinateMove exists; family-specific filters and free-effect variants missing |
| assassinate_white_troop_with_focus_deploy_troops | partial | DeployMove exists; many families require multi-step or conditional deploy logic; AssassinateMove exists; family-specific filters and free-effect variants missing |
| choose_twice_white_troop_assassinate_or_white_trophy_relocate | partial | AssassinateMove exists; family-specific filters and free-effect variants missing |
| conditional_influence_from_promoted_cards_plus_triggered_promote | partial | Promotion queues exist, but family-specific promote handlers are not registered |
| deploy_troops | partial | DeployMove exists; many families require multi-step or conditional deploy logic |
| deploy_troops_plus_recruit_aspect_filtered_card_by_cost | partial | DeployMove exists; many families require multi-step or conditional deploy logic |
| deploy_troops_with_focus_draw | partial | DeployMove exists; many families require multi-step or conditional deploy logic |
| draw_cards_plus_spy | partial | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing |
| gain_influence_plus_assassinate_white_troop | partial | Resource gain primitives exist, but composed family effect_key is not registered; AssassinateMove exists; family-specific filters and free-effect variants missing |
| gain_influence_plus_promote_top_of_deck | partial | Resource gain primitives exist, but composed family effect_key is not registered; Promotion queues exist, but family-specific promote handlers are not registered |
| gain_influence_plus_return_enemy_unit | partial | Resource gain primitives exist, but composed family effect_key is not registered |
| gain_influence_plus_return_enemy_unit_plus_focus_draw | partial | Resource gain primitives exist, but composed family effect_key is not registered |
| gain_influence_plus_return_other_player_unit | partial | Resource gain primitives exist, but composed family effect_key is not registered |
| gain_influence_plus_triggered_promote | partial | Resource gain primitives exist, but composed family effect_key is not registered; Promotion queues exist, but family-specific promote handlers are not registered |
| gain_influence_plus_triggered_promote_plus_recruit_aspect_filtered_card_by_cost | partial | Resource gain primitives exist, but composed family effect_key is not registered; Promotion queues exist, but family-specific promote handlers are not registered |
| gain_influence_plus_triggered_promote_with_focus_bonus | partial | Resource gain primitives exist, but composed family effect_key is not registered; Promotion queues exist, but family-specific promote handlers are not registered |
| gain_power_and_influence | partial | Resource gain primitives exist, but composed family effect_key is not registered |
| gain_power_plus_assassinate_white_troop | partial | Resource gain primitives exist, but composed family effect_key is not registered; AssassinateMove exists; family-specific filters and free-effect variants missing |
| gain_power_plus_spy_plus_recruit_aspect_filtered_card_by_cost | partial | Resource gain primitives exist, but composed family effect_key is not registered; ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing |
| gain_power_plus_triggered_promote_aspect_filtered | partial | Resource gain primitives exist, but composed family effect_key is not registered; Promotion queues exist, but family-specific promote handlers are not registered |
| gain_power_with_focus_power_bonus | partial | Resource gain primitives exist, but composed family effect_key is not registered |
| multi_assassinate_plus_threshold_self_promote | partial | Promotion queues exist, but family-specific promote handlers are not registered; AssassinateMove exists; family-specific filters and free-effect variants missing |
| multi_assassinate_single_site_plus_scaled_influence | partial | AssassinateMove exists; family-specific filters and free-effect variants missing |
| promote_top_card_plus_play_from_inner_circle_without_removal | partial | Promotion queues exist, but family-specific promote handlers are not registered |
| repeated_assassinate | partial | AssassinateMove exists; family-specific filters and free-effect variants missing |
| repeated_white_troop_assassinate | partial | AssassinateMove exists; family-specific filters and free-effect variants missing |
| repeated_white_troop_assassinate_by_controlled_sites | partial | AssassinateMove exists; family-specific filters and free-effect variants missing |
| return_enemy_unit_plus_triggered_multi_promote_by_tag | partial | Promotion queues exist, but family-specific promote handlers are not registered |
| return_unit_plus_triggered_promote | partial | Promotion queues exist, but family-specific promote handlers are not registered |
| spy | partial | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing |
| spy_plus_conditional_power_if_spy_present | partial | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing |
| spy_plus_conditional_take_from_trophy_hall_and_deploy | partial | DeployMove exists; many families require multi-step or conditional deploy logic; ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing |
| spy_plus_return_spy_for_power | partial | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing |
| spy_plus_site_troop_power_effect | partial | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing |
| spy_plus_triggered_promote_aspect_filtered | partial | Promotion queues exist, but family-specific promote handlers are not registered; ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing |
| spy_then_assassinate_plus_focus_spy | partial | AssassinateMove exists; family-specific filters and free-effect variants missing; ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing |
| spy_then_conditional_influence_if_enemy_troop_present | partial | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing |
| triggered_promote | partial | Promotion queues exist, but family-specific promote handlers are not registered |
| triggered_promote_plus_focus_influence_bonus | partial | Promotion queues exist, but family-specific promote handlers are not registered |
| gain_influence | supported | Registered effect handler exists in engine.rules |
| gain_power | supported | Registered effect handler exists in engine.rules |
| assassinate_plus_conditional_owner_discard | unsupported | AssassinateMove exists; family-specific filters and free-effect variants missing; Requires mechanics not modeled by current move set or effect registry |
| deploy_troops_plus_conditional_give_negative_card | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; Requires mechanics not modeled by current move set or effect registry |
| deploy_troops_plus_end_of_turn_mass_discard | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; Requires mechanics not modeled by current move set or effect registry |
| deploy_troops_plus_on_opponent_discard_draw | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; Requires mechanics not modeled by current move set or effect registry |
| deploy_troops_plus_on_opponent_discard_punish | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; Requires mechanics not modeled by current move set or effect registry |
| deploy_troops_plus_optional_market_devour | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; Requires mechanics not modeled by current move set or effect registry |
| deploy_troops_plus_optional_self_devour_for_extra_deploy | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; Requires mechanics not modeled by current move set or effect registry |
| deploy_troops_plus_scaled_vp_from_controlled_sites | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; Requires mechanics not modeled by current move set or effect registry |
| deploy_troops_plus_targeted_discard | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; Requires mechanics not modeled by current move set or effect registry |
| gain_influence_plus_give_negative_card | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; Requires mechanics not modeled by current move set or effect registry |
| gain_influence_plus_optional_devour_market_card | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; Requires mechanics not modeled by current move set or effect registry |
| gain_power_plus_devour_market_card_and_self_replace | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; Requires mechanics not modeled by current move set or effect registry |
| gain_power_plus_give_negative_card_to_each_opponent | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; Requires mechanics not modeled by current move set or effect registry |
| gain_power_plus_optional_self_devour_to_assassinate | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; AssassinateMove exists; family-specific filters and free-effect variants missing; Requires mechanics not modeled by current move set or effect registry |
| give_negative_card_plus_triggered_promote | unsupported | Promotion queues exist, but family-specific promote handlers are not registered; Requires mechanics not modeled by current move set or effect registry |
| hand_devour_for_modal_influence_or_assassinate | unsupported | AssassinateMove exists; family-specific filters and free-effect variants missing; Requires mechanics not modeled by current move set or effect registry |
| hand_devour_for_power | unsupported | Requires mechanics not modeled by current move set or effect registry |
| hand_devour_for_power_plus_repeated_assassinate_plus_redeploy_captured_units | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; AssassinateMove exists; family-specific filters and free-effect variants missing; Requires mechanics not modeled by current move set or effect registry |
| hand_devour_for_repeated_assassinate | unsupported | AssassinateMove exists; family-specific filters and free-effect variants missing; Requires mechanics not modeled by current move set or effect registry |
| hand_devour_plus_mass_supplant_white_plus_mass_negative_recruit | unsupported | Requires mechanics not modeled by current move set or effect registry |
| hand_devour_to_spy_then_assassinate | unsupported | AssassinateMove exists; family-specific filters and free-effect variants missing; ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| hand_devour_to_supplant_white_anywhere_plus_deploy_troop | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; Requires mechanics not modeled by current move set or effect registry |
| inner_circle_devour_for_influence_plus_triggered_multi_promote | unsupported | Promotion queues exist, but family-specific promote handlers are not registered; Requires mechanics not modeled by current move set or effect registry |
| mill_deck_then_promote_from_discard | unsupported | Promotion queues exist, but family-specific promote handlers are not registered; Requires mechanics not modeled by current move set or effect registry |
| modal_deploy_or_assassinate_white_troop | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; AssassinateMove exists; family-specific filters and free-effect variants missing; Requires mechanics not modeled by current move set or effect registry |
| modal_deploy_or_supplant_white_anywhere | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; Requires mechanics not modeled by current move set or effect registry |
| modal_deploy_troops_or_repeated_white_troop_assassinate | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; AssassinateMove exists; family-specific filters and free-effect variants missing; Requires mechanics not modeled by current move set or effect registry |
| modal_deploy_troops_or_self_devour_multi_white_assassinate_single_site | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; AssassinateMove exists; family-specific filters and free-effect variants missing; Requires mechanics not modeled by current move set or effect registry |
| modal_gain_influence_or_assassinate | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; AssassinateMove exists; family-specific filters and free-effect variants missing; Requires mechanics not modeled by current move set or effect registry |
| modal_gain_influence_or_draw_then_force_discard | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; Requires mechanics not modeled by current move set or effect registry |
| modal_gain_influence_or_return_units | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; Requires mechanics not modeled by current move set or effect registry |
| modal_gain_influence_or_self_devour_for_triggered_multi_promote | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; Promotion queues exist, but family-specific promote handlers are not registered; Requires mechanics not modeled by current move set or effect registry |
| modal_gain_influence_or_single_promote_from_multiple_zones | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; Promotion queues exist, but family-specific promote handlers are not registered; Requires mechanics not modeled by current move set or effect registry |
| modal_gain_power_or_assassinate | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; AssassinateMove exists; family-specific filters and free-effect variants missing; Requires mechanics not modeled by current move set or effect registry |
| modal_gain_power_or_devour_from_hand_to_supplant | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; Requires mechanics not modeled by current move set or effect registry |
| modal_gain_power_or_influence | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; Requires mechanics not modeled by current move set or effect registry |
| modal_gain_power_or_influence_with_focus_draw | unsupported | Resource gain primitives exist, but composed family effect_key is not registered; Requires mechanics not modeled by current move set or effect registry |
| modal_place_two_spies_or_return_spies_then_multi_supplant | unsupported | Requires mechanics not modeled by current move set or effect registry |
| modal_place_two_spies_or_return_spy_for_power | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_spy_or_return_spy_draw_then_mass_discard | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_spy_or_return_spy_for_cards | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_spy_or_return_spy_for_influence | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_spy_or_return_spy_for_influence_with_focus_bonus | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_spy_or_return_spy_for_power_and_influence | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_spy_or_return_spy_then_assassinate | unsupported | AssassinateMove exists; family-specific filters and free-effect variants missing; ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_spy_or_return_spy_then_supplant | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_spy_or_return_spy_then_supplant_plus_scaled_vp | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_spy_or_return_spy_to_deploy_troops_with_focus_draw | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_spy_or_return_spy_to_play_top_devoured_as_market | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_spy_or_return_spy_to_recruit_multiple_low_cost_cards | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_spy_place_or_draw | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| modal_supplant_or_promote_from_discard_plus_scaled_vp | unsupported | Promotion queues exist, but family-specific promote handlers are not registered; Requires mechanics not modeled by current move set or effect registry |
| move_enemy_troop_plus_promote_top_of_deck | unsupported | Promotion queues exist, but family-specific promote handlers are not registered; Requires mechanics not modeled by current move set or effect registry |
| move_enemy_troop_plus_triggered_promote | unsupported | Promotion queues exist, but family-specific promote handlers are not registered; Requires mechanics not modeled by current move set or effect registry |
| move_enemy_troops_plus_triggered_promote | unsupported | Promotion queues exist, but family-specific promote handlers are not registered; Requires mechanics not modeled by current move set or effect registry |
| play_then_devour | unsupported | Requires mechanics not modeled by current move set or effect registry |
| self_purge_to_supply | unsupported | No direct handler or move composition path exists for this family |
| spy_plus_optional_self_devour_to_assassinate_there | unsupported | AssassinateMove exists; family-specific filters and free-effect variants missing; ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| spy_then_local_discard | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| supplant | unsupported | Requires mechanics not modeled by current move set or effect registry |
| supplant_plus_return_enemy_spy_plus_scaled_vp_from_controlled_sites | unsupported | ReturnSpyMove exists; targeted spy-placement and modal wrappers are missing; Requires mechanics not modeled by current move set or effect registry |
| supplant_plus_scaled_vp_from_trophies | unsupported | Requires mechanics not modeled by current move set or effect registry |
| supplant_white_anywhere_plus_recruit_negative_card | unsupported | Requires mechanics not modeled by current move set or effect registry |
| supplant_white_troop | unsupported | Requires mechanics not modeled by current move set or effect registry |
| supplant_white_troop_anywhere | unsupported | Requires mechanics not modeled by current move set or effect registry |
| supplant_white_troop_plus_scaled_vp_from_white_trophies | unsupported | Requires mechanics not modeled by current move set or effect registry |
| triggered_multi_promote_plus_scaled_vp_from_promoted_cards | unsupported | Promotion queues exist, but family-specific promote handlers are not registered; Requires mechanics not modeled by current move set or effect registry |
| unrestricted_supplant_white_troop_with_focus_deploy_troops | unsupported | DeployMove exists; many families require multi-step or conditional deploy logic; Requires mechanics not modeled by current move set or effect registry |

## Flagged Missing Primitives

- devour-pile state representation
- white troop distinction and targeting
- modal choice move and branching
- targeted spy placement move
- supplant move and rules
- move-enemy-troop move and rules
- discard mechanics and cause tracking
- scaling math helpers for VP and resource effects
- general effect composition and sequencing model

## Phased Remediation

1. Add missing state primitives (devour zone, white-troop markers, discard-cause metadata).
2. Add move primitives (modal choice, place spy, supplant, move enemy troop, devour cost action).
3. Add rule handlers for conditional/scaled/discard/devour families.
4. Register effect handlers for highest-frequency families first.
5. Add focused tests per new primitive and per family class.
