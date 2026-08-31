# Catalog Execution Audit

Source catalog: C:/Users/mkkom/pyrants/data/cards
Probe artifact: not provided

## Summary

- Total cards audited: 125
- Clean cards: 120
- Cards with rules-text mismatches: 0
- Cards with runtime gaps: 4
- Cards flagged as heuristic-review only: 1
- Cards blocked, errored, or stuck in the live probe: 0

## Cards With Findings

| card_id | verdict | findings | probe |
|---|---|---:|---|
| derro | runtime_gap | 1 | n/a |
| ghost | runtime_gap | 1 | n/a |
| lich | runtime_gap | 3 | n/a |
| orcus | runtime_gap | 4 | n/a |
| skeletal_horde | heuristic-only | 1 | n/a |

## Card Review

### Aboleth (`aboleth`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `7`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place 2 spies on any nodes, with at most 1 of your spies per node, or draw 1 card for each of your spies on the board. If you have fewer than 2 spies available to place, you may move one of your spies that is already on the board instead.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=fixed:1 source_fragment=spy_place
  - option_1_action_2 -> place_spy [board_site] timing=immediate quantity=fixed:1 source_fragment=spy_place
  - option_2_action_1 -> draw_cards [self] timing=immediate quantity=unspecified source_fragment=draw
- Findings: none

### Advance Scout (`advance_scout`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Supplant a white troop.
- Actions:
  - action_1 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant_white_troop
- Findings: none

### Advocate (`advocate`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `2`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either gain 2 influence, or at end of turn promote another card played this turn.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
- Findings: none

### Aerisi Kalinoth (`aerisi_kalinoth`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Gain 1 power, place 1 spy, then recruit a Guile card that costs 4 or less.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:1 source_fragment=gain_power
  - action_2 -> place_spy [board_site] timing=immediate quantity=fixed:1 source_fragment=spy
  - action_3 -> recruit_card [market] timing=immediate quantity=unspecified source_fragment=recruit_aspect_filtered_card_by_cost
- Findings: none

### Air Elemental (`air_elemental`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy, or return one of your spies to deploy 3 troops. If the focus condition is met for Guile, draw a card.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_own_spy
  - option_2_action_2 -> deploy_troops [board_site] timing=immediate quantity=fixed:1 source_fragment=deploy_troops_step_1
  - option_2_action_3 -> deploy_troops [board_site] timing=immediate quantity=fixed:1 source_fragment=deploy_troops_step_2
  - option_2_action_4 -> deploy_troops [board_site] timing=immediate quantity=fixed:1 source_fragment=deploy_troops_step_3
  - option_2_action_5 -> draw_cards [self] timing=immediate quantity=fixed:1 source_fragment=focus_draw
- Findings: none

### Air Elemental Myrmidon (`air_elemental_myrmidon`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Place a spy. At end of turn, promote an Obedience card played this turn.
- Actions:
  - action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote_aspect_filtered
- Findings: none

### Ambassador (`ambassador`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `3`
- Execution model: `sequence`
- Rules text: At end of turn, promote another card you played this turn. If this card would be discarded from hand to discard pile, you may choose to promote this card instead.
- Actions:
  - action_1 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
- Findings: none

### Balor (`balor`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Devour a card from your hand to supplant a white troop anywhere on the board, then deploy 1 troop.
- Actions:
  - action_1 -> devour_cost [hand] timing=immediate quantity=unspecified source_fragment=hand_devour
  - action_2 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant_white_troop_anywhere
  - action_3 -> deploy_troops [board_site] timing=immediate quantity=fixed:1 source_fragment=deploy_troop
- Findings: none

### Banshee (`banshee`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Place a spy. If there is another spy there, gain 3 power.
- Actions:
  - action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - action_2 -> conditional_bonus [self] timing=immediate quantity=unspecified source_fragment=conditional_power_if_spy_present
- Findings: none

### Beholder (`beholder`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Assassinate a troop. Then gain 1 power for every 3 troops in your trophy hall.
- Actions:
  - action_1 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate
  - action_2 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=scaled_power_from_trophy_hall
- Findings: none

### Black Dragon (`black_dragon`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `8`
- Execution model: `sequence`
- Rules text: Supplant a white troop anywhere. Gain 1 VP for every 3 white trophies.
- Actions:
  - action_1 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant_white_troop_anywhere
  - action_2 -> grant_vp [self] timing=immediate quantity=unspecified source_fragment=scaled_vp_from_white_trophies
- Findings: none

### Black Earth Cultist (`black_earth_cultist`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `2`
- Execution model: `sequence`
- Rules text: At end of turn, promote another played card. If the focus condition is met for Ambition, gain 2 influence.
- Actions:
  - action_1 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
  - action_2 -> conditional_bonus [self] timing=immediate quantity=unspecified source_fragment=focus_influence_bonus
- Findings: none

### Black Wyrmling (`black_wyrmling`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Gain 1 influence. Assassinate a white troop.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:1 source_fragment=gain_influence
  - action_2 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate_white_troop
- Findings: none

### Blackguard (`blackguard`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either gain 2 power, or assassinate.
- Actions:
  - option_1_action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power
  - option_2_action_1 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate
- Findings: none

### Blue Dragon (`blue_dragon`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `8`
- Execution model: `sequence`
- Rules text: At end of turn, promote 2 other cards you played this turn. Gain 1 VP for every 3 promoted cards.
- Actions:
  - action_1 -> promote_card [self] timing=end_of_turn quantity=fixed:2 source_fragment=triggered_multi_promote
  - action_2 -> grant_vp [self] timing=end_of_turn quantity=unspecified source_fragment=scaled_vp_from_promoted_cards
- Findings: none

### Blue Wyrmling (`blue_wyrmling`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Gain 3 influence. Return another players troop or spy where you have Presence.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:3 source_fragment=gain_influence
  - action_2 -> return_unit [opponent_unit] timing=immediate quantity=unspecified source_fragment=return_other_player_unit
- Findings: none

### Bounty Hunter (`bounty_hunter`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Gain 3 power.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:3 source_fragment=gain_power
- Findings: none

### Brainwashed Slave (`brainwashed_slave`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `4`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy, or return one of your spies to gain 2 power and 2 influence.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy_for_power_and_influence
  - option_2_action_2 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power
  - option_2_action_3 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
- Findings: none

### Carrion Crawler (`carrion_crawler`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `2`
- Execution model: `sequence`
- Rules text: Gain 3 power. Devour a card in the market and replace it with this one.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:3 source_fragment=gain_power
  - action_2 -> devour_cost [market] timing=immediate quantity=unspecified source_fragment=devour_market_card_and_self_replace
- Findings: none

### Chosen of Lolth (`chosen_of_lolth`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Return another player's troop or spy where you have presence. At end of turn, promote another played card.
- Actions:
  - action_1 -> return_unit [opponent_unit] timing=immediate quantity=unspecified source_fragment=return_unit
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
- Findings: none

### Chuul (`chuul`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Place a spy from your units onto the board. Then each opponent there who has 3 or more cards in hand discards 1 card from hand.
- Actions:
  - action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - action_2 -> force_discard [opponent] timing=immediate quantity=unspecified source_fragment=local_discard
- Findings: none

### Cleric of Laogzed (`cleric_of_laogzed`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Move an enemy troop. At end of turn, promote another played card.
- Actions:
  - action_1 -> move_troop [board_site] timing=immediate quantity=unspecified source_fragment=move_enemy_troop
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
- Findings: none

### cloaker (`cloaker`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `2`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy from your units onto the board, or return one of your own spies from the board to your barracks and assassinate a troop there.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy
  - option_2_action_2 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate
- Findings: none

### Conjurer (`conjurer`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `5`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy, or return one of your spies to recruit up to 2 cards that cost 3 or less without paying their cost.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_own_spy
  - option_2_action_2 -> recruit_card [market] timing=immediate quantity=unspecified source_fragment=recruit_low_cost_card
  - option_2_action_3 -> recruit_card [market] timing=immediate quantity=unspecified source_fragment=recruit_low_cost_card
- Findings: none

### Council Member (`council_member`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Move 2 enemy troops. At end of turn, promote another played card.
- Actions:
  - action_1 -> move_troop [board_site] timing=immediate quantity=fixed:2 source_fragment=move_enemy_troops
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
- Findings: none

### Cranium Rats (`cranium_rats`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `2`
- Execution model: `sequence`
- Rules text: Deploy 2 troops. Then choose an opponent with 3 or more cards in hand to discard 1 card from hand.
- Actions:
  - action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:2 source_fragment=deploy_troops
  - action_2 -> force_discard [opponent] timing=immediate quantity=unspecified source_fragment=targeted_discard
- Findings: none

### Crushing Wave Cultist (`crushing_wave_cultist`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Assassinate a white troop. If the focus condition is met for Conquest, deploy 2 troops.
- Actions:
  - action_1 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_white_troop
  - action_2 -> deploy_troops [board_site] timing=immediate quantity=fixed:2 source_fragment=focus_deploy_troops
- Findings: none

### Cult Fanatic (`cult_fanatic`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Gain 2 influence. You may devour a market card.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
  - action_2 -> devour_cost [market] timing=immediate quantity=unspecified source_fragment=optional_devour_market_card
- Findings: none

### Cultist of Myrkul (`cultist_of_myrkul`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `2`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either gain 2 influence, or devour this card so that at end of turn you promote up to 2 other cards you played this turn.
- Actions:
  - option_1_action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
  - option_2_action_1 -> devour_cost [played_self] timing=immediate quantity=unspecified source_fragment=self_devour
  - option_2_action_2 -> promote_card [self] timing=end_of_turn quantity=fixed:2 source_fragment=triggered_multi_promote
- Findings: none

### Death Knight (`death_knight`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Supplant a troop. Then gain 1 VP for every 5 player trophies you have.
- Actions:
  - action_1 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant
  - action_2 -> grant_vp [self] timing=immediate quantity=unspecified source_fragment=scaled_vp_from_trophies
- Findings: none

### Death Tyrant (`death_tyrant`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `7`
- Execution model: `sequence`
- Rules text: Assassinate up to 3 troops at a single site. Gain 1 influence for each troop removed by this effect.
- Actions:
  - action_1 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_step_1
  - action_2 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_step_2
  - action_3 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_step_3
  - action_4 -> gain_resource [self] timing=immediate quantity=fixed:1 source_fragment=gain_influence_per_troop_removed_by_effect
- Findings: none

### Deathblade (`deathblade`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Assassinate 2 troops.
- Actions:
  - action_1 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_step_1
  - action_2 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_step_2
- Findings: none

### Demogorgon (`demogorgon`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `8`
- Execution model: `sequence`
- Rules text: Devour a card from your hand to supplant a white troop anywhere on the board. Then supplant 2 more white troops. Then each opponent recruits 2 Insane Outcasts.
- Actions:
  - action_1 -> devour_cost [hand] timing=immediate quantity=unspecified source_fragment=hand_devour
  - action_2 -> supplant_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=supplant_white_troop_anywhere
  - action_3 -> supplant_troop [board_site] timing=immediate quantity=fixed:2 source_fragment=supplant_white_troop
  - action_4 -> custom_effect [opponent_player] timing=immediate quantity=fixed:2 source_fragment=give_negative_card_to_each_opponent
- Findings: none

### Derro (`derro`)

- Verdict: `runtime_gap`
- Aspect: `conquest`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Supplant a white troop anywhere. Recruit an Insane Outcast.
- Actions:
  - action_1 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant_white_troop_anywhere
  - action_2 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=give_negative_card
- Findings:
  - [runtime_gap][high][engine_fix] action_2: custom_effect_unsupported:give_insane_outcast_to_self
    - action_2 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=give_negative_card
    - owning_engine_path=engine/rules.py::_legal_generic_target_selection_moves + _apply_generic_action

### Doppelganger (`doppelganger`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Supplant.
- Actions:
  - action_1 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant
- Findings: none

### Dragon Cultist (`dragon_cultist`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either gain 2 power, or gain 2 influence.
- Actions:
  - option_1_action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power
  - option_2_action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
- Findings: none

### Dragonclaw (`dragonclaw`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Assassinate a troop. Then, if you have 5 or more player trophies in your trophy hall, gain 2 power.
- Actions:
  - action_1 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate
  - action_2 -> conditional_bonus [self] timing=immediate quantity=unspecified source_fragment=conditional_power_from_trophies
- Findings: none

### Drow Negotiator (`drow_negotiator`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `3`
- Execution model: `sequence`
- Rules text: If there are 4 or more promoted cards, gain 3 influence. At end of turn, promote a card played this turn.
- Actions:
  - action_1 -> conditional_bonus [self] timing=immediate quantity=unspecified source_fragment=conditional_influence_from_promoted_cards
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
- Findings: none

### Earth Elemental (`earth_elemental`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Gain 1 influence. Return another player's troop or spy to their garrison. If the focus condition is met for Ambition, draw a card from your draw deck.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:1 source_fragment=gain_influence
  - action_2 -> return_unit [opponent_unit] timing=immediate quantity=unspecified source_fragment=return_enemy_unit
  - action_3 -> draw_cards [self] timing=immediate quantity=fixed:1 source_fragment=focus_draw
- Findings: none

### Earth Elemental Myrmidon (`earth_elemental_myrmidon`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Gain 2 influence. At end of turn, promote another played card.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
- Findings: none

### Elder Brain (`elder_brain`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `7`
- Execution model: `sequence`
- Rules text: Promote the top card of your draw deck. Then play a card from your inner circle as if it were in your hand; it remains in your inner circle after being played.
- Actions:
  - action_1 -> promote_card [self] timing=immediate quantity=unspecified source_fragment=promote_top_of_deck
  - action_2 -> play_card [inner_circle_or_market] timing=immediate quantity=unspecified source_fragment=play_from_inner_circle_without_removal
- Findings: none

### Enchanter of Thay (`enchanter_of_thay`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `4`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy, or return one of your spies and gain 4 power.
- Actions:
  - action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy_for_power
  - action_2 -> gain_resource [self] timing=immediate quantity=fixed:4 source_fragment=gain_4_power
- Findings: none

### Eternal Flame Cultist (`eternal_flame_cultist`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Assassinate a troop. If the focus condition is met for Malice, gain 2 power.
- Actions:
  - action_1 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate_troop
  - action_2 -> conditional_bonus [self] timing=immediate quantity=unspecified source_fragment=focus_power_bonus
- Findings: none

### Ettin (`ettin`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `4`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either deploy 3 troops, or assassinate 2 white troops.
- Actions:
  - option_1_action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:3 source_fragment=deploy_troops
  - option_2_action_1 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=repeated_white_troop_assassinate
  - option_2_action_2 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=repeated_white_troop_assassinate
- Findings: none

### Fire Elemental (`fire_elemental`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either gain 2 power, or gain 2 influence. If the focus condition is met for Malice, draw a card.
- Actions:
  - option_1_action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power
  - option_1_action_2 -> draw_cards [self] timing=immediate quantity=fixed:1 source_fragment=focus_draw
  - option_2_action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
  - option_2_action_2 -> draw_cards [self] timing=immediate quantity=fixed:1 source_fragment=focus_draw
- Findings: none

### Fire Elemental Myrmidon (`fire_elemental_myrmidon`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Gain 2 power. At end of turn, promote an Obedience card played this turn.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote_aspect_filtered
- Findings: none

### Flesh Golem (`flesh_golem`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Gain 2 power. You may devour this card to assassinate a troop.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power
  - action_2 -> devour_cost [played_self] timing=immediate quantity=unspecified source_fragment=optional_self_devour
  - action_3 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate
- Findings: none

### Gar Shatterkeel (`gar_shatterkeel`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Deploy 3 troops. Recruit a Conquest card that costs 4 or less.
- Actions:
  - action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:3 source_fragment=deploy_troops
  - action_2 -> recruit_card [market] timing=immediate quantity=unspecified source_fragment=recruit_aspect_filtered_card_by_cost
- Findings: none

### Gauth (`gauth`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose one mode. Either gain 2 influence, or draw a card and choose an opponent with 3 or more cards to discard a card.
- Actions:
  - option_1_action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
  - option_2_action_1 -> draw_cards [self] timing=immediate quantity=unspecified source_fragment=draw
  - option_2_action_2 -> force_discard [opponent] timing=immediate quantity=unspecified source_fragment=targeted_discard
- Findings: none

### Ghost (`ghost`)

- Verdict: `runtime_gap`
- Aspect: `guile`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy, or return one of your spies and take the top card from the devour pile into your discard pile for free.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy
  - option_2_action_2 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=take_from_devour_pile_to_discard
- Findings:
  - [runtime_gap][high][engine_fix] option_2_action_2: custom_effect_unsupported:take_from_devour_pile_to_discard
    - option_2_action_2 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=take_from_devour_pile_to_discard
    - owning_engine_path=engine/rules.py::_legal_generic_target_selection_moves + _apply_generic_action

### Ghoul (`ghoul`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Gain 2 power. Give an Insane Outcast to each opponent.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power
  - action_2 -> custom_effect [opponent_player] timing=immediate quantity=unspecified source_fragment=give_negative_card_to_each_opponent
- Findings: none

### Gibbering Mouther (`gibbering_mouther`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `2`
- Execution model: `sequence`
- Rules text: Deploy 2 troops. Choose a player who has Presence in the same site as one of the troops you deployed. That player adds an Insane Outcast to their discard pile.
- Actions:
  - action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:2 source_fragment=deploy_troops
  - action_2 -> custom_effect [opponent_player] timing=immediate quantity=unspecified source_fragment=give_insane_outcast_to_player_with_presence_at_deployed_site
- Findings: none

### Glabrezu (`glabrezu`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Devour a card from your hand to assassinate 2 troops.
- Actions:
  - action_1 -> devour_cost [hand] timing=immediate quantity=unspecified source_fragment=hand_devour
  - action_2 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_step_1
  - action_3 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_step_2
- Findings: none

### Graz'zt (`grazzt`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `6`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place 2 spies, or return any spies to supplant a troop at each of those sites.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=fixed:1 source_fragment=place_spy_step_1
  - option_1_action_2 -> place_spy [board_site] timing=immediate quantity=fixed:1 source_fragment=place_spy_step_2
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy_for_site_supplant
  - option_2_action_2 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=multi_supplant
- Findings: none

### Green Dragon (`green_dragon`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `8`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy and supplant a troop there, or return one of your spies, supplant a troop there, and gain 1 VP for each site control marker you have.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_1_action_2 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy
  - option_2_action_2 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant
  - option_2_action_3 -> grant_vp [self] timing=immediate quantity=unspecified source_fragment=scaled_vp
- Findings: none

### Green Wyrmling (`green_wyrmling`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Place a spy. If there is another player's troop on the site where you placed that spy, gain 2 influence.
- Actions:
  - action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - action_2 -> conditional_bonus [self] timing=immediate quantity=unspecified source_fragment=conditional_influence_if_enemy_troop_present
- Findings: none

### Grimlock (`grimlock`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `1`
- Execution model: `sequence`
- Rules text: Deploy 1 troop. If your opponent causes you to discard this card from hand to discard pile, draw 2 cards.
- Actions:
  - action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:1 source_fragment=deploy_troops
  - action_2 -> draw_cards [self] timing=immediate quantity=fixed:2 source_fragment=on_opponent_discard_draw
- Findings: none

### Hezrou (`hezrou`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Move an enemy troop. Promote the top card of your draw deck directly into your promoted area. If your draw deck is empty, apply normal shuffle-to-refill rules first.
- Actions:
  - action_1 -> move_troop [board_site] timing=immediate quantity=unspecified source_fragment=move_enemy_troop
  - action_2 -> promote_card [self] timing=immediate quantity=unspecified source_fragment=promote_top_of_deck
- Findings: none

### High Priest of Myrkul (`high_priest_of_myrkul`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Return another player's troop or spy. At end of turn, you may promote any number of Undead cards you played this turn (zero, one, some, or all).
- Actions:
  - action_1 -> return_unit [opponent_unit] timing=immediate quantity=unspecified source_fragment=return_enemy_unit
  - action_2 -> promote_card [self] timing=end_of_turn quantity=variable_repeat source_fragment=triggered_multi_promote_by_tag
- Findings: none

### House Guard (`house_guard`)

- Verdict: `clean`
- Aspect: `obedience`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Gain 2 power.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power
- Findings: none

### Howling Hatred Cultist (`howling_hatred_cultist`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy, or return one of your spies and gain 3 influence. Focus: gain 1 power.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy_for_influence_with_focus_bonus
  - option_2_action_2 -> gain_resource [self] timing=immediate quantity=fixed:3 source_fragment=gain_influence
  - option_2_action_3 -> conditional_bonus [self] timing=immediate quantity=unspecified source_fragment=focus_gain_power
- Findings: none

### Imix (`imix`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Gain 4 power. If the focus condition is met for Malice, gain 2 power.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:4 source_fragment=gain_power
  - action_2 -> conditional_bonus [self] timing=immediate quantity=unspecified source_fragment=focus_gain_power
- Findings: none

### Infiltrator (`infiltrator`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Place a spy with normal legality. If there is another player's troop at that site, gain 1 power.
- Actions:
  - action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - action_2 -> conditional_bonus [self] timing=immediate quantity=unspecified source_fragment=conditional_power_if_enemy_troop_present
- Findings: none

### Information Broker (`information_broker`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `5`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy, or return one of your spies and draw 3 cards.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy_for_cards
  - option_2_action_2 -> draw_cards [self] timing=immediate quantity=fixed:3 source_fragment=draw_cards
- Findings: none

### Inquisitor (`inquisitor`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either gain 2 influence, or assassinate.
- Actions:
  - option_1_action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
  - option_2_action_1 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate
- Findings: none

### Insane Outcast (`insane_outcast`)

- Verdict: `clean`
- Aspect: `-`
- Cost: `0`
- Execution model: `sequence`
- Rules text: You may discard a card from your hand to return this card to supply. If this card would be devoured or promoted, return it to supply instead.
- Actions:
  - action_1 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=self_purge_to_supply
- Findings: none

### intellect Devourer (`intellect_devourer`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `4`
- Execution model: `modal_choice`
- Rules text: Choose one mode. Either gain 3 influence, or return up to 2 of your own units to your barracks in any mix of troops and spies.
- Actions:
  - option_1_action_1 -> gain_resource [self] timing=immediate quantity=fixed:3 source_fragment=gain_influence
  - option_2_action_1 -> return_unit [self_unit] timing=immediate quantity=unspecified source_fragment=return_units
  - option_2_action_2 -> return_unit [self_unit] timing=immediate quantity=unspecified source_fragment=return_units
- Findings: none

### Jackalwere (`jackalwere`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `4`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy, or return one of your own spies from the board to your barracks and gain 2 power and 2 influence.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy_for_power_and_influence
  - option_2_action_2 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power
  - option_2_action_3 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
- Findings: none

### Kobold (`kobold`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `1`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either deploy 1 troop, or assassinate a white troop.
- Actions:
  - option_1_action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:1 source_fragment=deploy
  - option_2_action_1 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate_white_troop
- Findings: none

### Lich (`lich`)

- Verdict: `runtime_gap`
- Aspect: `guile`
- Cost: `7`
- Execution model: `sequence`
- Rules text: Place a spy. If another player has a troop there, take 2 troops from that same player's trophy hall and deploy them anywhere on the board, regardless of presence.
- Actions:
  - action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - action_2 -> custom_effect [self] timing=immediate quantity=fixed:1 source_fragment=lich_select_target_player
  - action_3 -> custom_effect [self] timing=immediate quantity=fixed:1 source_fragment=lich_take_trophy
  - action_4 -> custom_effect [self] timing=immediate quantity=fixed:1 source_fragment=lich_take_trophy
- Findings:
  - [runtime_gap][high][engine_fix] action_2: custom_effect_unsupported:lich_select_target_player
    - action_2 -> custom_effect [self] timing=immediate quantity=fixed:1 source_fragment=lich_select_target_player
    - owning_engine_path=engine/rules.py::_legal_generic_target_selection_moves + _apply_generic_action
  - [runtime_gap][high][engine_fix] action_3: custom_effect_unsupported:deploy_from_trophy_hall
    - action_3 -> custom_effect [self] timing=immediate quantity=fixed:1 source_fragment=lich_take_trophy
    - owning_engine_path=engine/rules.py::_legal_generic_target_selection_moves + _apply_generic_action
  - [runtime_gap][high][engine_fix] action_4: custom_effect_unsupported:deploy_from_trophy_hall
    - action_4 -> custom_effect [self] timing=immediate quantity=fixed:1 source_fragment=lich_take_trophy
    - owning_engine_path=engine/rules.py::_legal_generic_target_selection_moves + _apply_generic_action

### Marilith (`marilith`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Devour a card from your hand to gain 5 power.
- Actions:
  - action_1 -> devour_cost [hand] timing=immediate quantity=unspecified source_fragment=hand_devour
  - action_2 -> gain_resource [self] timing=immediate quantity=fixed:5 source_fragment=gain_power
- Findings: none

### Marlos Urnrayle (`marlos_urnrayle`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Gain 1 influence. At end of turn, promote another played card. Then recruit an Ambition card that costs 4 or less without paying its cost.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:1 source_fragment=gain_influence
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
  - action_3 -> recruit_card [market] timing=immediate quantity=unspecified source_fragment=recruit_aspect_filtered_card_by_cost
- Findings: none

### Master of Melee-Magthere (`master_of_melee_magthere`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `5`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either deploy 4 troops, or supplant a white troop anywhere.
- Actions:
  - option_1_action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:4 source_fragment=deploy
  - option_2_action_1 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant_white_troop_anywhere
- Findings: none

### Masters of Sorcere (`masters_of_sorcere`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place 2 spies, or return one of your spies and gain 4 power.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=fixed:1 source_fragment=spy
  - option_1_action_2 -> place_spy [board_site] timing=immediate quantity=fixed:1 source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy_for_power
  - option_2_action_2 -> gain_resource [self] timing=immediate quantity=fixed:4 source_fragment=gain_power
- Findings: none

### Matron Mother (`matron_mother`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Put your draw deck into your discard pile. Then promote a card from your discard pile.
- Actions:
  - action_1 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=mill_deck
  - action_2 -> promote_card [self] timing=immediate quantity=unspecified source_fragment=promote_from_discard
- Findings: none

### Mercenary Squad (`mercenary_squad`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Deploy 3 troops.
- Actions:
  - action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:3 source_fragment=deploy_troops
- Findings: none

### Mind Flayer (`mind_flayer`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Devour a card from your hand, then choose exactly one mode: either gain 3 influence, or assassinate a troop.
- Actions:
  - option_1_action_1 -> devour_cost [hand] timing=immediate quantity=unspecified source_fragment=hand_devour
  - option_1_action_2 -> gain_resource [self] timing=immediate quantity=fixed:3 source_fragment=gain_influence
  - option_2_action_1 -> devour_cost [hand] timing=immediate quantity=unspecified source_fragment=hand_devour
  - option_2_action_2 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate
- Findings: none

### Mindwitness (`mindwitness`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Assassinate a troop. Then that player discards 1 card from hand if they have 3 or more cards in hand.
- Actions:
  - action_1 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate
  - action_2 -> force_discard [opponent] timing=immediate quantity=unspecified source_fragment=conditional_owner_discard
- Findings: none

### Minotaur Skeleton (`minotaur_skeleton`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either deploy 3 troops, or devour this card to assassinate up to 3 white troops at a single site.
- Actions:
  - option_1_action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:3 source_fragment=deploy_troops
  - option_2_action_1 -> devour_cost [played_self] timing=immediate quantity=unspecified source_fragment=self_devour
  - option_2_action_2 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=self_devour_multi_white_assassinate_single_site
  - option_2_action_3 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=self_devour_multi_white_assassinate_single_site
  - option_2_action_4 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=self_devour_multi_white_assassinate_single_site
- Findings: none

### Mummy Lord (`mummy_lord`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `6`
- Execution model: `repeat_choice`
- Rules text: Choose two times from this menu: (a) assassinate a white troop, (b) take a white trophy from another player and place it anywhere.
- Actions:
  - option_1_action_1 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=white_troop_assassinate
  - option_2_action_1 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=white_trophy_relocate
- Findings: none

### Myconid Adult (`myconid_adult`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Gain 2 influence. Choose another player. That player adds an Insane Outcast from the Insane Outcast deck to their discard pile.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
  - action_2 -> custom_effect [opponent_player] timing=immediate quantity=unspecified source_fragment=give_negative_card
- Findings: none

### Myconid Sovereign (`myconid_sovereign`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Choose another player. That player adds an Insane Outcast from the Insane Outcast deck to their discard pile. At end of turn, promote another played card.
- Actions:
  - action_1 -> custom_effect [opponent_player] timing=immediate quantity=unspecified source_fragment=give_negative_card
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
- Findings: none

### nalfeshnee (`nalfeshnee`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Gain 3 influence. Promote the top card of your draw deck directly into your promoted area. If your draw deck is empty, apply normal shuffle-to-refill rules first.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:3 source_fragment=gain_influence
  - action_2 -> promote_card [self] timing=immediate quantity=unspecified source_fragment=promote_top_of_deck
- Findings: none

### Necromancer (`necromancer`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `5`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either gain 3 influence, or perform exactly one promote action on exactly one card chosen from: this card, a card from hand, or a card from discard.
- Actions:
  - option_1_action_1 -> gain_resource [self] timing=immediate quantity=fixed:3 source_fragment=gain_influence
  - option_2_action_1 -> promote_card [self] timing=immediate quantity=variable_repeat source_fragment=single_promote_from_multiple_zones
- Findings: none

### Neogi (`neogi`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `7`
- Execution model: `sequence`
- Rules text: Deploy 4 troops. At end of turn, each opponent discards a card.
- Actions:
  - action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:4 source_fragment=deploy_troops
  - action_2 -> force_discard [opponent] timing=end_of_turn quantity=variable_repeat source_fragment=end_of_turn_mass_discard
- Findings: none

### Night Hag (`night_hag`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy, or return one of your own spies from the board to your barracks and draw 2 cards from your draw deck.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy_for_cards
  - option_2_action_2 -> draw_cards [self] timing=immediate quantity=fixed:2 source_fragment=draw_cards
- Findings: none

### Noble (`noble`)

- Verdict: `clean`
- Aspect: `obedience`
- Cost: `0`
- Execution model: `sequence`
- Rules text: Gain 1 influence.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:1 source_fragment=gain_influence
- Findings: none

### Nothic (`nothic`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose one mode. Either place a spy from your units onto the board, or return one of your own spies from the board to your barracks, draw a card, and then each opponent with 3 or more cards in hand discards 1 card from hand.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy_draw
  - option_2_action_2 -> draw_cards [self] timing=immediate quantity=fixed:1 source_fragment=draw_cards
  - option_2_action_3 -> force_discard [opponent] timing=immediate quantity=variable_repeat source_fragment=mass_discard
- Findings: none

### Ogre Zombie (`ogre_zombie`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Supplant a white troop anywhere.
- Actions:
  - action_1 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant_white_troop_anywhere
- Findings: none

### Ogremoch (`ogremoch`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Gain 2 influence. At end of turn, promote another played card. Focus: at end of turn, promote another played card.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
  - action_3 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
- Findings: none

### Olhydra (`olhydra`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Supplant a white troop anywhere on the board. If the focus condition is met for Conquest, deploy 2 troops.
- Actions:
  - action_1 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant_white_troop_anywhere
  - action_2 -> deploy_troops [board_site] timing=immediate quantity=fixed:2 source_fragment=focus_deploy_troops
- Findings: none

### Orcus (`orcus`)

- Verdict: `runtime_gap`
- Aspect: `malice`
- Cost: `8`
- Execution model: `sequence`
- Rules text: Devour a card from your hand for 5 power. Assassinate 2 troops. Take up to 2 troops from any trophy halls and deploy them anywhere on the board.
- Actions:
  - action_1 -> devour_cost [hand] timing=immediate quantity=unspecified source_fragment=hand_devour
  - action_2 -> gain_resource [self] timing=immediate quantity=fixed:5 source_fragment=gain_power_from_devour
  - action_3 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_step_1
  - action_4 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_step_2
  - action_5 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=steal_trophy_1
  - action_6 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=steal_trophy_1_deploy
  - action_7 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=steal_trophy_2
  - action_8 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=steal_trophy_2_deploy
- Findings:
  - [runtime_gap][high][engine_fix] action_5: custom_effect_unsupported:select_trophy_hall
    - action_5 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=steal_trophy_1
    - owning_engine_path=engine/rules.py::_legal_generic_target_selection_moves + _apply_generic_action
  - [runtime_gap][high][engine_fix] action_6: custom_effect_unsupported:steal_from_selected_trophy
    - action_6 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=steal_trophy_1_deploy
    - owning_engine_path=engine/rules.py::_legal_generic_target_selection_moves + _apply_generic_action
  - [runtime_gap][high][engine_fix] action_7: custom_effect_unsupported:select_trophy_hall
    - action_7 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=steal_trophy_2
    - owning_engine_path=engine/rules.py::_legal_generic_target_selection_moves + _apply_generic_action
  - [runtime_gap][high][engine_fix] action_8: custom_effect_unsupported:steal_from_selected_trophy
    - action_8 -> custom_effect [self] timing=immediate quantity=unspecified source_fragment=steal_trophy_2_deploy
    - owning_engine_path=engine/rules.py::_legal_generic_target_selection_moves + _apply_generic_action

### Priestess of Lolth (`priestess_of_lolth`)

- Verdict: `clean`
- Aspect: `obedience`
- Cost: `2`
- Execution model: `sequence`
- Rules text: Gain 2 influence.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
- Findings: none

### Puppeteer (`puppeteer`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Gain 2 influence. At end of turn, promote another card you played this turn.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_influence
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
- Findings: none

### Quaggoth (`quaggoth`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Assassinate a white troop for each site you control.
- Actions:
  - action_1 -> assassinate_troop [board_site] timing=immediate quantity=variable_repeat source_fragment=repeated_white_troop_assassinate_by_controlled_sites
- Findings: none

### Rath Modar (`rath_modar`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Draw 2 cards. Place a spy.
- Actions:
  - action_1 -> draw_cards [self] timing=immediate quantity=fixed:2 source_fragment=draw_cards
  - action_2 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
- Findings: none

### Ravenous Zombies (`ravenous_zombies`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Gain 1 power. Assassinate a white troop.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:1 source_fragment=gain_power
  - action_2 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate_white_troop
- Findings: none

### Red Dragon (`red_dragon`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `8`
- Execution model: `sequence`
- Rules text: Supplant a troop. Return an enemy spy. Gain 1 VP for each total controlled site.
- Actions:
  - action_1 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant
  - action_2 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_enemy_spy
  - action_3 -> grant_vp [self] timing=immediate quantity=unspecified source_fragment=scaled_vp_from_total_controlled_sites
- Findings: none

### Red Wyrmling (`red_wyrmling`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Gain 2 power and 2 influence.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power_and_influence
  - action_2 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power_and_influence
- Findings: none

### Revenant (`revenant`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Assassinate 2 troops. If you have 8 or more trophies, promote this card.
- Actions:
  - action_1 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_step_1
  - action_2 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_step_2
  - action_3 -> promote_card [self] timing=immediate quantity=unspecified source_fragment=threshold_self_promote
- Findings: none

### Severin Silrajin (`severin_silrajin`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `7`
- Execution model: `sequence`
- Rules text: Gain 5 power.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:5 source_fragment=gain_power
- Findings: none

### Skeletal Horde (`skeletal_horde`)

- Verdict: `heuristic-only`
- Aspect: `conquest`
- Cost: `2`
- Execution model: `sequence`
- Rules text: Deploy 2 troops. You can devour this card to deploy 3 more troops.
- Actions:
  - action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:2 source_fragment=deploy_troops
  - action_2 -> devour_cost [played_self] timing=immediate quantity=unspecified source_fragment=optional_self_devour
  - action_3 -> deploy_troops [board_site] timing=immediate quantity=fixed:3 source_fragment=extra_deploy
- Findings:
  - [heuristic_false_positive][low][audit_fix] deploy_troops_expected_2_fixed_sum_5
    - rules_text fixed expectation for deploy_troops=2
    - flattened deploy_troops fixed sum=5
    - matching actions present=True, non_fixed=False

### Soldier (`soldier`)

- Verdict: `clean`
- Aspect: `obedience`
- Cost: `0`
- Execution model: `sequence`
- Rules text: Gain 1 power.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:1 source_fragment=gain_power
- Findings: none

### Spectator (`spectator`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Gain 2 power and 1 influence.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power_and_influence
  - action_2 -> gain_resource [self] timing=immediate quantity=fixed:1 source_fragment=gain_power_and_influence
- Findings: none

### Spellspinner (`spellspinner`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy, or return one of your spies to supplant a troop at that site.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy
  - option_2_action_2 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant
- Findings: none

### Spy Master (`spy_master`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `2`
- Execution model: `sequence`
- Rules text: Place a spy.
- Actions:
  - action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
- Findings: none

### Succubus (`succubus`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Devour a card from your hand to place a spy and assassinate a troop there.
- Actions:
  - action_1 -> devour_cost [hand] timing=immediate quantity=unspecified source_fragment=hand_devour
  - action_2 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - action_3 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate
- Findings: none

### Ulitharid (`ulitharid`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Choose a market card that costs 4 or less. Play it immediately by resolving its instructions without recruiting it. After its full effect finishes, devour that card. While it is being played this way, it does not count for aspect checks or end-of-turn effects.
- Actions:
  - action_1 -> play_card [inner_circle_or_market] timing=immediate quantity=unspecified source_fragment=play
  - action_2 -> devour_cost [unknown] timing=immediate quantity=unspecified source_fragment=devour
- Findings: none

### Umber Hulk (`umber_hulk`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Deploy 3 troops. If an opponent causes you to discard this card, that opponent discards a card.
- Actions:
  - action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:3 source_fragment=deploy_troops
  - action_2 -> force_discard [opponent] timing=immediate quantity=unspecified source_fragment=on_opponent_discard_punish
- Findings: none

### Underdark Ranger (`underdark_ranger`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Assassinate 2 white troops.
- Actions:
  - action_1 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_white_troop_step_1
  - action_2 -> assassinate_troop [board_site] timing=immediate quantity=fixed:1 source_fragment=assassinate_white_troop_step_2
- Findings: none

### Vampire (`vampire`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `7`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either supplant a troop, or promote a card from your discard pile and then gain 1 VP for every 3 promoted cards.
- Actions:
  - option_1_action_1 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant
  - option_2_action_1 -> promote_card [self] timing=immediate quantity=unspecified source_fragment=promote_from_discard
  - option_2_action_2 -> grant_vp [self] timing=immediate quantity=unspecified source_fragment=scaled_vp
- Findings: none

### Vampie Spawn (`vampire_spawn`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `2`
- Execution model: `sequence`
- Rules text: Gain 1 influence. Return another player's troop or spy.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:1 source_fragment=gain_influence
  - action_2 -> return_unit [opponent_unit] timing=immediate quantity=unspecified source_fragment=return_enemy_unit
- Findings: none

### Vanifer (`vanifer`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `5`
- Execution model: `sequence`
- Rules text: Assassinate a troop. You may recruit a Malice card that costs 4 or less without paying its cost.
- Actions:
  - action_1 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate_troop
  - action_2 -> recruit_card [market] timing=immediate quantity=unspecified source_fragment=recruit_aspect_filtered_card_by_cost
- Findings: none

### Vrock (`vrock`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `5`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy, or return one of your own spies from the board to your barracks and gain 5 power.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy_for_power
  - option_2_action_2 -> gain_resource [self] timing=immediate quantity=fixed:5 source_fragment=gain_power
- Findings: none

### Watcher of Thay (`watcher_of_thay`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either place a spy, or return one of your spies and gain 3 influence.
- Actions:
  - option_1_action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - option_2_action_1 -> return_spy [board_site] timing=immediate quantity=unspecified source_fragment=return_spy_for_influence
  - option_2_action_2 -> gain_resource [self] timing=immediate quantity=fixed:3 source_fragment=gain_influence
- Findings: none

### Water Elemental (`water_elemental`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `2`
- Execution model: `sequence`
- Rules text: Deploy 2 troops. If the focus condition is met for Conquest, draw a card.
- Actions:
  - action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:2 source_fragment=deploy_troops_with_focus_draw
  - action_2 -> draw_cards [self] timing=immediate quantity=fixed:1 source_fragment=focus_draw
- Findings: none

### Water Elemental Myrmidon (`water_elemental_myrmidon`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `4`
- Execution model: `sequence`
- Rules text: Assassinate a white troop. At end of turn, promote an Obedience card played this turn.
- Actions:
  - action_1 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate_white_troop
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote_aspect_filtered
- Findings: none

### Weaponmaster (`weaponmaster`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `6`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either deploy 1 troop, or assassinate a white troop.
- Actions:
  - option_1_action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:1 source_fragment=deploy
  - option_2_action_1 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate_white_troop
- Findings: none

### White Dragon (`white_dragon`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `8`
- Execution model: `sequence`
- Rules text: Deploy 3 troops. Gain 1 VP for every 2 sites controlled.
- Actions:
  - action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:3 source_fragment=deploy_troops
  - action_2 -> grant_vp [self] timing=immediate quantity=unspecified source_fragment=scaled_vp_from_controlled_sites
- Findings: none

### White Wyrmling (`white_wyrmling`)

- Verdict: `clean`
- Aspect: `conquest`
- Cost: `2`
- Execution model: `sequence`
- Rules text: Deploy 2 troops. You may devour a card in the market.
- Actions:
  - action_1 -> deploy_troops [board_site] timing=immediate quantity=fixed:2 source_fragment=deploy_troops
  - action_2 -> devour_cost [market] timing=immediate quantity=unspecified source_fragment=optional_market_devour
- Findings: none

### Wight (`wight`)

- Verdict: `clean`
- Aspect: `malice`
- Cost: `3`
- Execution model: `modal_choice`
- Rules text: Choose exactly one mode. Either gain 2 power, or devour a card from your hand to supplant a troop.
- Actions:
  - option_1_action_1 -> gain_resource [self] timing=immediate quantity=fixed:2 source_fragment=gain_power
  - option_2_action_1 -> devour_cost [hand] timing=immediate quantity=unspecified source_fragment=devour_from_hand
  - option_2_action_2 -> supplant_troop [board_site] timing=immediate quantity=unspecified source_fragment=supplant
- Findings: none

### Wraith (`wraith`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `2`
- Execution model: `sequence`
- Rules text: Place a spy. You may devour this card to assassinate a troop there.
- Actions:
  - action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - action_2 -> devour_cost [played_self] timing=immediate quantity=unspecified source_fragment=optional_self_devour
  - action_3 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate_there
- Findings: none

### Wyrmspeaker (`wyrmspeaker`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `3`
- Execution model: `sequence`
- Rules text: Gain 1 influence. At end of turn, promote a played card other than this card.
- Actions:
  - action_1 -> gain_resource [self] timing=immediate quantity=fixed:1 source_fragment=gain_influence
  - action_2 -> promote_card [self] timing=end_of_turn quantity=unspecified source_fragment=triggered_promote
- Findings: none

### Yan-C-Bin (`yan_c_bin`)

- Verdict: `clean`
- Aspect: `guile`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Place a spy, then assassinate a troop at that site. If the focus condition is met, place another spy.
- Actions:
  - action_1 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=spy
  - action_2 -> assassinate_troop [board_site] timing=immediate quantity=unspecified source_fragment=assassinate
  - action_3 -> place_spy [board_site] timing=immediate quantity=unspecified source_fragment=focus_spy
- Findings: none

### Zuggtmoy (`zuggtmoy`)

- Verdict: `clean`
- Aspect: `ambition`
- Cost: `6`
- Execution model: `sequence`
- Rules text: Devour a card in your inner circle to gain 3 influence and at end of turn promote up to 2 other played cards.
- Actions:
  - action_1 -> devour_cost [inner_circle] timing=immediate quantity=unspecified source_fragment=inner_circle_devour
  - action_2 -> gain_resource [self] timing=immediate quantity=fixed:3 source_fragment=gain_influence
  - action_3 -> promote_card [self] timing=end_of_turn quantity=variable_repeat source_fragment=triggered_multi_promote
- Findings: none
