# First Deck Review Workflow

Date: 2026-04-27

## Goal

Review all unique cards in the first deck workbook, one by one, then derive the smallest useful set of effect families from reviewed cards.

## Workbook

Use this workbook:

- c:/Users/mkkom/pyrants/data/cards/first_deck_review.xlsx

Current live columns:

- market_count
- starter_count
- name
- cost
- deck_vp
- inner_circle_vp
- deck
- benefit1
- benefit2
- benefit3
- aspect
- aspect_2

The live workbook does not currently carry review-status or review-notes columns. Track review outcomes in this markdown log unless the sheet layout changes.

## Status Values

- raw: not reviewed yet
- reviewed: card text reviewed and effect behavior is clear enough to classify
- blocked: card cannot be classified without a rules clarification
- deferred: card is postponed for ordering reasons, but not blocked by missing rules

## One-By-One Review Loop

For each card row in workbook order:

1. Confirm the printed text fields are copied correctly.
2. Restate the effect in plain English with concrete game outcomes.
3. Tag each statement as one of:
   - [from rules: section]
   - [inferred]
   - [gap]
4. Decide status in this markdown log:
   - reviewed if behavior is clear enough to classify
   - blocked if behavior needs a rules answer
   - deferred only for sequencing, not uncertainty
5. Add a short note in notes.
6. Add one entry to the Card Review Log below.
7. Move to the next raw card.

Do not stop early. Continue until every unique card row is reviewed, blocked, or deferred in this log.

## Effect Family Rules

- Cluster effects continuously during review.
- Reuse a family only when game behavior is genuinely the same.
- Use the rule of three: when three or more cards share the same behavior, promote that behavior to a stable effect family.
- Keep flavor_text out of executable effect logic.
- If behavior is unclear, record a blocker question instead of guessing.

## Completion Criteria

- No row remains in raw.
- Every reviewed card has a provisional effect family or a clear note.
- Every blocked card has an explicit unresolved question.
- Starter and market counts are filled for each card used in the first deck.

## Card Review Log

Use one block per card:

### card_id: ambassador

- text_check: ok
- plain_english_effect: At end of turn, promote another card you played this turn. If this card would be discarded from hand to discard pile, you may choose to promote this card instead.
- tags: [from rules: workbook row 2 benefit1] [from rules: workbook row 2 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: triggered_promote
- status: reviewed
- blocker_question: none
- notes: The self-promotion effect is an optional replacement effect that applies only when this card would move from hand to discard pile.

### card_id: ulitharid

- text_check: ok
- plain_english_effect: Choose a market card that costs 4 or less. Play it immediately by resolving its instructions without recruiting it. After its full effect finishes, devour that card. While it is being played this way, it does not count for aspect checks or end-of-turn effects.
- tags: [from rules: workbook row 3 benefit1] [from rules: user clarification 2026-04-28]
- provisional_family: play_then_devour
- status: reviewed
- blocker_question: none
- notes: This is a temporary market-card play effect with a cost cap and an immediate post-resolution devour.

### card_id: aboleth

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place 2 spies on any nodes, with at most 1 of your spies per node, or draw 1 card for each of your spies on the board. If you have fewer than 2 spies available to place, you may move one of your spies that is already on the board instead.
- tags: [from rules: workbook row 4 benefit1] [from rules: workbook row 4 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: modal_spy_place_or_draw
- status: reviewed
- blocker_question: none
- notes: Spy placement ignores normal presence limits, allows any nodes, caps placement at one of your spies per node, and can reposition an existing spy when supply is short.

### card_id: elder_brain

- text_check: ok
- plain_english_effect: Promote the top card of your draw deck. Then play a card from your inner circle as if it were in your hand; it remains in your inner circle after being played.
- tags: [from rules: workbook row 5 benefit1] [from rules: workbook row 5 benefit2] [inferred]
- provisional_family: promote_top_card_plus_play_from_inner_circle_without_removal
- status: reviewed
- blocker_question: none
- notes: `Top card` is interpreted as the top of your draw deck. The inner-circle play is a temporary permission and does not move that card out of inner circle.

### card_id: brainwashed_slave

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place a spy, or return one of your spies to gain 2 power and 2 influence.
- tags: [from rules: workbook row 6 benefit1] [from rules: workbook row 6 benefit2] [inferred]
- provisional_family: modal_spy_or_return_spy_for_power_and_influence
- status: reviewed
- blocker_question: none
- notes: This card established the default interpretation used later: standalone `spy` means place a spy; `return a spy` defaults to returning your own spy to your barracks.

### card_id: puppeteer

- text_check: ok
- plain_english_effect: Gain 2 influence. At end of turn, promote another card you played this turn.
- tags: [from rules: workbook row 7 benefit1] [from rules: workbook row 7 benefit2]
- provisional_family: gain_influence_plus_triggered_promote
- status: reviewed
- blocker_question: none
- notes: This combines a simple resource gain with the same end-of-turn promote-another-played-card pattern seen on Ambassador.

### card_id: intellect_devourer

- text_check: ok
- plain_english_effect: Choose one mode. Either gain 3 influence, or return up to 2 of your own units to your barracks in any mix of troops and spies.
- tags: [from rules: workbook row 8 benefit1] [from rules: workbook row 8 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: modal_gain_influence_or_return_units
- status: reviewed
- blocker_question: none
- notes: By default, "return" targets your own units and sends them to your own barracks. This card allows any mix of up to 2 returned troops and spies.

### card_id: gauth

- text_check: ok
- plain_english_effect: Choose one mode. Either gain 2 influence, or draw a card and choose an opponent with 3 or more cards to discard a card.
- tags: [from rules: workbook row 9 benefit1] [from rules: workbook row 9 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: modal_gain_influence_or_draw_then_force_discard
- status: reviewed
- blocker_question: none
- notes: Cards written as "or X" and "or Y" choose exactly one mode unless the card says otherwise. The discard threshold is based on cards in hand, and the chosen opponent discards 1 card from hand.

### card_id: nothic

- text_check: ok
- plain_english_effect: Choose one mode. Either place a spy from your units onto the board, or return one of your own spies from the board to your barracks, draw a card, and then each opponent with 3 or more cards in hand discards 1 card from hand.
- tags: [from rules: workbook row 10 benefit1] [from rules: workbook row 10 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: modal_spy_or_return_spy_draw_then_mass_discard
- status: reviewed
- blocker_question: none
- notes: The global modal convention applies here. The return-spy branch uses the default self-return-to-barracks rule, then applies draw plus mass discard against opponents with 3 or more cards in hand.

### card_id: chuul

- text_check: ok
- plain_english_effect: Place a spy from your units onto the board. Then each opponent there who has 3 or more cards in hand discards 1 card from hand.
- tags: [from rules: workbook row 11 benefit1] [from rules: workbook row 11 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: spy_then_local_discard
- status: reviewed
- blocker_question: none
- notes: A normal "spy" may be placed on any site that does not already contain your spy, or moved from another site if none remain in assets. In this card, "there" refers to the site where that spy was placed.

### card_id: neogi

- text_check: ok
- plain_english_effect: Deploy 4 troops. At end of turn, each opponent discards a card.
- tags: [from rules: workbook row 12 benefit1] [from rules: workbook row 12 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: deploy_troops_plus_end_of_turn_mass_discard
- status: reviewed
- blocker_question: none
- notes: Multi-deploy means four free troop placements using normal deploy legality. If the player cannot place all four troops, the action is illegal. The end-of-turn discard makes each opponent discard 1 card from hand.

### card_id: cloaker

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place a spy from your units onto the board, or return one of your own spies from the board to your barracks and assassinate a troop there.
- tags: [from rules: workbook row 13 benefit1] [from rules: workbook row 13 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: modal_spy_or_return_spy_then_assassinate
- status: reviewed
- blocker_question: none
- notes: In the second mode, "there" refers to the former site of the returned spy. The assassinate is a free card effect, but it can target only that former site.

### card_id: umber_hulk

- text_check: ok
- plain_english_effect: Deploy 3 troops. If an opponent causes you to discard this card, that opponent discards a card.
- tags: [from rules: workbook row 14 benefit1] [from rules: workbook row 14 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: deploy_troops_plus_on_opponent_discard_punish
- status: reviewed
- blocker_question: none
- notes: The trigger applies only when an opponent effect makes this card move from hand to discard pile. When that happens, the same opponent discards 1 card from hand.

### card_id: spectator

- text_check: ok
- plain_english_effect: Gain 2 power and 1 influence.
- tags: [from rules: workbook row 15 benefit1]
- provisional_family: gain_power_and_influence
- status: reviewed
- blocker_question: none
- notes: Simple fixed resource card with no timing or targeting questions.

### card_id: beholder

- text_check: ok
- plain_english_effect: Assassinate a troop. Then gain 1 power for every 3 troops in your trophy hall.
- tags: [from rules: workbook row 16 benefit1] [from rules: workbook row 16 benefit2] [from rules: user clarification 2026-04-29]
- provisional_family: assassinate_plus_scaled_power_from_trophy_hall
- status: reviewed
- blocker_question: none
- notes: The assassinate is a free card effect that uses normal assassinate target legality. The power bonus counts current trophy-hall troops in groups of 3 and rounds down.

### card_id: mindwitness

- text_check: ok
- plain_english_effect: Assassinate a troop. Then that player discards 1 card from hand if they have 3 or more cards in hand.
- tags: [from rules: workbook row 17 benefit1] [from rules: workbook row 17 benefit2] [from rules: user clarification 2026-04-29]
- provisional_family: assassinate_plus_conditional_owner_discard
- status: reviewed
- blocker_question: none
- notes: This uses the same free card-effect assassinate semantics as Beholder. The discard rider keys off the owner of the assassinated troop and does not apply when the target is a neutral white troop.

### card_id: quaggoth

- text_check: ok
- plain_english_effect: Assassinate a white troop for each site you control.
- tags: [from rules: workbook row 18 benefit1] [from rules: user clarification 2026-04-29]
- provisional_family: repeated_white_troop_assassinate_by_controlled_sites
- status: reviewed
- blocker_question: none
- notes: The effect counts all sites currently under your control, not only sites with a control marker present. It grants that many free white-troop assassinations and resolves as many as possible if legal white targets run short.

### card_id: cranium_rats

- text_check: ok
- plain_english_effect: Deploy 2 troops. Then choose an opponent with 3 or more cards in hand to discard 1 card from hand.
- tags: [from rules: workbook row 19 benefit1] [from rules: workbook row 19 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: deploy_troops_plus_targeted_discard
- status: reviewed
- blocker_question: none
- notes: The troop deployment follows the established free multi-deploy rule. The discard rider follows the resolved 3-plus-cards-in-hand convention.

### card_id: death_tyrant

- text_check: ok
- plain_english_effect: Assassinate up to 3 troops at a single site. Gain 1 influence for each troop removed by this effect.
- tags: [from rules: workbook row 20 benefit1] [from rules: workbook row 20 benefit2] [from rules: user clarification 2026-04-29]
- provisional_family: multi_assassinate_single_site_plus_scaled_influence
- status: reviewed
- blocker_question: none
- notes: This uses the same free card-effect assassinate semantics as Beholder, repeated up to 3 times at one site. The influence gain equals the actual number of troops removed by the effect.

### card_id: grimlock

- text_check: ok
- plain_english_effect: Deploy 1 troop. If your opponent causes you to discard this card from hand to discard pile, draw 2 cards.
- tags: [from rules: workbook row 21 benefit1] [from rules: workbook row 21 benefit2] [from rules: user clarification 2026-04-28] [from rules: user correction 2026-04-30]
- provisional_family: deploy_troops_plus_on_opponent_discard_draw
- status: reviewed
- blocker_question: none
- notes: This reuses the established opponent-caused-discard trigger pattern from Umber Hulk, but the payoff is drawing 2 cards instead of forcing a discard. The correct troop count is 1.

### card_id: blue_dragon

- text_check: ok
- plain_english_effect: At end of turn, promote 2 other cards you played this turn. Gain 1 VP for every 3 promoted cards.
- tags: [from rules: workbook row 22 benefit1] [from rules: workbook row 22 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: triggered_multi_promote_plus_scaled_vp_from_promoted_cards
- status: reviewed
- blocker_question: none
- notes: The end-of-turn promote works as an up-to effect when fewer than 2 other played cards are available. The VP bonus counts all currently promoted cards and rounds down by groups of 3.

### card_id: green_wyrmling

- text_check: corrected
- plain_english_effect: Place a spy. If there is another player's troop on the site where you placed that spy, gain 2 influence.
- tags: [from rules: workbook row 23 benefit1] [from rules: user clarification 2026-04-30]
- provisional_family: spy_then_conditional_influence_if_enemy_troop_present
- status: reviewed
- blocker_question: none
- notes: The workbook row had a typo in the second clause. The resolved effect checks the site where the spy was placed for another player's troop.

### card_id: cleric_of_laogzed

- text_check: ok
- plain_english_effect: Move an enemy troop. At end of turn, promote a played card.
- tags: [from rules: workbook row 24 benefit1] [from rules: workbook row 24 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: move_enemy_troop_plus_triggered_promote
- status: reviewed
- blocker_question: none
- notes: Any enemy troop within the current player's presence is a legal target and it can be moved anywhere. The end-of-turn promote must target a different played card, not Cleric of Laogzed itself.

### card_id: rather_modar

- text_check: ok
- plain_english_effect: Draw 2 cards. Place a spy.
- tags: [from rules: workbook row 25 benefit1] [from rules: workbook row 25 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: draw_cards_plus_spy
- status: reviewed
- blocker_question: none
- notes: Straight additive effect card. The spy instruction uses the established default spy placement rule.

### card_id: enchanter_of_thay

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place a spy, or return one of your spies and gain 4 power.
- tags: [from rules: workbook row 26 benefit1] [from rules: workbook row 26 benefit2] [from rules: user clarification 2026-04-28] [from rules: user clarification 2026-04-30]
- provisional_family: spy_plus_return_spy_for_power
- status: reviewed
- blocker_question: none
- notes: This is a modal card, not a sequential one. The player chooses either the spy placement clause or the return-spy-for-4-power clause.

### card_id: white_dragon

- text_check: ok
- plain_english_effect: Deploy 3 troops. Gain 1 VP for every 2 sites controlled.
- tags: [from rules: workbook row 27 benefit1] [from rules: workbook row 27 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: deploy_troops_plus_scaled_vp_from_controlled_sites
- status: reviewed
- blocker_question: none
- notes: The VP scaling counts all sites currently under the player's control and rounds down by groups of 2. The troop deployment uses the established free multi-deploy rule.

### card_id: wyrmspeaker

- text_check: ok
- plain_english_effect: Gain 1 influence. At end of turn, promote a played card other than this card.
- tags: [from rules: workbook row 28 benefit1] [from rules: workbook row 28 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: gain_influence_plus_triggered_promote
- status: reviewed
- blocker_question: none
- notes: This uses the same target rule as Cleric of Laogzed: it must promote a different played card. If there is no other played card at end of turn, the effect does nothing.

### card_id: watcher_of_thay

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place a spy, or return one of your spies and gain 3 influence.
- tags: [from rules: workbook row 29 benefit1] [from rules: workbook row 29 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: modal_spy_or_return_spy_for_influence
- status: reviewed
- blocker_question: none
- notes: This reuses the established modal `or` structure, default spy placement rule, and self-return-for-reward shorthand.

### card_id: dragon_cultist

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either gain 2 power, or gain 2 influence.
- tags: [from rules: workbook row 30 benefit1] [from rules: workbook row 30 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: modal_gain_power_or_influence
- status: reviewed
- blocker_question: none
- notes: Simple modal resource card.

### card_id: cult_fanatic

- text_check: ok
- plain_english_effect: Gain 2 influence. You may devour a market card.
- tags: [from rules: workbook row 31 benefit1] [from rules: workbook row 31 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: gain_influence_plus_optional_devour_market_card
- status: reviewed
- blocker_question: none
- notes: `Devour` means to take a card from the named zone, discard it from that place, and move it to the devour pile. A devoured card never returns to the game. Here the player may optionally choose any card currently in the market row and devour it after gaining 2 influence.

### card_id: severin_silrajin

- text_check: ok
- plain_english_effect: Gain 5 power.
- tags: [from rules: workbook row 32 benefit1]
- provisional_family: gain_power
- status: reviewed
- blocker_question: none
- notes: Simple fixed resource card with no timing or targeting questions.

### card_id: green_dragon

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place a spy and supplant a troop there, or return one of your spies, supplant a troop there, and gain 1 VP for each site control marker you have.
- tags: [from rules: workbook row 33 benefit1] [from rules: workbook row 33 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: modal_spy_or_return_spy_then_supplant_plus_scaled_vp
- status: reviewed
- blocker_question: none
- notes: `Supplant` means remove another player's troop, move it to your trophy hall, and place your own troop into that exact slot. If no site is named, supplant can happen anywhere you have presence. On this card, `there` restricts supplant to the site where the spy was placed or returned from. The VP clause counts literal site control markers you own, not all sites you currently control.

### card_id: black_dragon

- text_check: ok
- plain_english_effect: Supplant a white troop anywhere. Gain 1 VP for every 3 white trophies.
- tags: [from rules: workbook row 34 benefit1] [from rules: workbook row 34 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: supplant_white_troop_plus_scaled_vp_from_white_trophies
- status: reviewed
- blocker_question: none
- notes: This card-specific wording ignores normal presence restrictions and can supplant a white troop anywhere on the board. `White trophies` means white troops currently in your trophy hall, counted in groups of 3 and rounded down.

### card_id: red_dragon

- text_check: ok
- plain_english_effect: Supplant a troop. Return an enemy spy. Gain 1 VP for each total controlled site.
- tags: [from rules: workbook row 35 benefit1] [from rules: workbook row 35 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: supplant_plus_return_enemy_spy_plus_scaled_vp_from_controlled_sites
- status: reviewed
- blocker_question: none
- notes: This is sequential, not modal. `Supplant a troop` uses normal supplant legality: any enemy troop at a site where you have presence. `Return enemy spy` uses normal enemy-spy return legality as a free card effect, so the target spy must be within your presence and returns to its owner's barracks. The VP clause counts all sites currently under your control.

### card_id: red_wyrmling

- text_check: ok
- plain_english_effect: Gain 2 power and 2 influence.
- tags: [from rules: workbook row 36 benefit1]
- provisional_family: gain_power_and_influence
- status: reviewed
- blocker_question: none
- notes: Simple fixed resource card with no timing or targeting questions.

### card_id: black_wyrmling

- text_check: ok
- plain_english_effect: Gain 1 influence. Assassinate a white troop.
- tags: [from rules: workbook row 37 benefit1] [from rules: workbook row 37 benefit2] [from rules: user clarification 2026-04-29]
- provisional_family: gain_influence_plus_assassinate_white_troop
- status: reviewed
- blocker_question: none
- notes: Uses established free card-effect assassinate semantics. The target must be a neutral white troop at a site where you have presence.

### card_id: white_wyrmling

- text_check: corrected
- plain_english_effect: Deploy 2 troops. You may devour a card in the market.
- tags: [from rules: workbook row 38 benefit1] [from rules: user clarification 2026-04-30]
- provisional_family: deploy_troops_plus_optional_market_devour
- status: reviewed
- blocker_question: none
- notes: Workbook benefit text was wrong here. This uses usual `devour` keyword and mechanic: choose market-row card, move it to devour pile, and it never returns to game.

### card_id: dragonclaw

- text_check: malformed
- plain_english_effect: Assassinate a troop. Then, if you have 5 or more player trophies in your trophy hall, gain 2 power.
- tags: [from rules: workbook row 39 benefit1] [from rules: user clarification 2026-04-30]
- provisional_family: assassinate_plus_conditional_power_from_trophies
- status: reviewed
- blocker_question: none
- notes: Workbook rider text was malformed. Correct meaning is `if you have 5 or more player trophies in your trophy hall, gain 2 power`. White troops do not count toward this threshold.

### card_id: blue_wyrmling

- text_check: ok
- plain_english_effect: Gain 3 influence. Return another players troop or spy where you have Presence.
- tags: [from rules: workbook row 40 benefit1] [from rules: workbook row 40 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: gain_influence_plus_return_other_player_unit
- status: reviewed
- blocker_question: none
- notes: Uses targeted at another player's unit`return` rule: unless card says otherwise, return targets your own pieces and sends them back to your barracks. This card targets other players troop or spy.

### card_id: soldier

- text_check: ok
- plain_english_effect: Gain 1 power.
- tags: [from rules: workbook row 41 benefit1] [from rules: user clarification 2026-04-30]
- provisional_family: gain_power
- status: reviewed
- blocker_question: none
- notes: Bare `power` on this starter card means gain 1 power.

### card_id: noble

- text_check: ok
- plain_english_effect: Gain 1 influence.
- tags: [from rules: workbook row 42 benefit1] [from rules: user clarification 2026-04-30]
- provisional_family: gain_influence
- status: reviewed
- blocker_question: none
- notes: Bare `influence` on this starter card means gain 1 influence.

### card_id: insane_outcast

- text_check: ok
- plain_english_effect: You may discard a card from your hand to return this card to supply. If this card would be devoured or promoted, return it to supply instead.
- tags: [from rules: workbook row 43 benefit1] [from rules: workbook row 43 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: self_purge_to_supply
- status: reviewed
- blocker_question: none
- notes: This hand ability works only while Insane Outcast is in your hand. You must discard another card from hand to return Insane Outcast to supply; it cannot discard itself as the cost. This is anti-deck-clog text for a negative-VP card opponents can force into your deck.

### card_id: matron_mother

- text_check: ok
- plain_english_effect: Put your draw deck into your discard pile. Then promote a card from your discard pile.
- tags: [from rules: workbook row 44 benefit1] [from rules: workbook row 44 benefit2]
- provisional_family: mill_deck_then_promote_from_discard
- status: reviewed
- blocker_question: none
- notes: This moves your draw deck into discard pile, then promotes one card from that renewed discard pile.

### card_id: weaponmaster

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either deploy 1 troop, or assassinate a white troop.
- tags: [from rules: workbook row 45 benefit1] [from rules: workbook row 45 benefit2] [from rules: user clarification 2026-04-28] [from rules: user clarification 2026-04-29]
- provisional_family: modal_deploy_or_assassinate_white_troop
- status: reviewed
- blocker_question: none
- notes: Uses established modal `or` rule. Assassinate branch uses normal free card-effect assassinate legality, limited to neutral white troops.

### card_id: council_member

- text_check: ok
- plain_english_effect: Move 2 enemy troops. At end of turn, promote another played card.
- tags: [from rules: workbook row 46 benefit1] [from rules: workbook row 46 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: move_enemy_troops_plus_triggered_promote
- status: reviewed
- blocker_question: none
- notes: This repeats the resolved enemy-troop move behavior twice. The end-of-turn promote follows the same target rule as Cleric of Laogzed and Wyrmspeaker: another played card, not this card itself.

### card_id: information_broker

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place a spy, or return one of your spies and draw 3 cards.
- tags: [from rules: workbook row 47 benefit1] [from rules: workbook row 47 benefit2] [from rules: user clarification 2026-04-28]
- provisional_family: modal_spy_or_return_spy_for_cards
- status: reviewed
- blocker_question: none
- notes: Uses same modal `or` structure and default self-return-spy rule as earlier cards. `For 3 cards` is treated as draw 3 cards.

### card_id: spy_master

- text_check: ok
- plain_english_effect: Place a spy.
- tags: [from rules: workbook row 48 benefit1] [from rules: user clarification 2026-04-28]
- provisional_family: spy
- status: reviewed
- blocker_question: none
- notes: Uses established default spy placement rule.

### card_id: infiltrator

- text_check: corrected
- plain_english_effect: Place a spy with normal legality. If there is another player's troop at that site, gain 1 power.
- tags: [from rules: workbook row 49 benefit1] [from rules: user clarification 2026-04-30]
- provisional_family: spy_plus_site_troop_power_effect
- status: reviewed
- blocker_question: none
- notes: Workbook text was compressed. `There` means site where the spy was placed, and the power gain checks for another player's troop at that site.

### card_id: bounty_hunter

- text_check: ok
- plain_english_effect: Gain 3 power.
- tags: [from rules: workbook row 50 benefit1]
- provisional_family: gain_power
- status: reviewed
- blocker_question: none
- notes: Simple fixed resource card.

### card_id: house_guard

- text_check: ok
- plain_english_effect: Gain 2 power.
- tags: [from rules: workbook row 51 benefit1]
- provisional_family: gain_power
- status: reviewed
- blocker_question: none
- notes: Simple fixed resource card.

### card_id: drow_negotiator

- text_check: ok
- plain_english_effect: If there are 4 or more promoted cards, gain 3 influence. At end of turn, promote a card played this turn.
- tags: [from rules: workbook row 52 benefit1] [from rules: workbook row 52 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: conditional_influence_from_promoted_cards_plus_triggered_promote
- status: reviewed
- blocker_question: none
- notes: The first clause counts promoted cards in current player's inner circle, not globally. The end-of-turn promote follows same rule as Council Member and Wyrmspeaker: it must target another played card, and if no other played card exists, the effect does nothing.

### card_id: underdark_ranger

- text_check: ok
- plain_english_effect: Assassinate 2 white troops.
- tags: [from rules: workbook row 53 benefit1] [from rules: user clarification 2026-04-30]
- provisional_family: repeated_white_troop_assassinate
- status: reviewed
- blocker_question: none
- notes: This means two separate free assassinations of neutral white troops using normal legality. If fewer than 2 legal white targets exist, resolve as many as possible, including zero.

### card_id: master_of_melee_magthere

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either deploy 4 troops, or supplant a white troop anywhere.
- tags: [from rules: workbook row 54 benefit1] [from rules: workbook row 54 benefit2] [from rules: user clarification 2026-04-28] [from rules: user clarification 2026-04-30]
- provisional_family: modal_deploy_or_supplant_white_anywhere
- status: reviewed
- blocker_question: none
- notes: Uses established modal `or` rule. Supplant-white-troop-anywhere branch follows same card-specific anywhere rule as Black Dragon.

### card_id: doppelganger

- text_check: ok
- plain_english_effect: Supplant.
- tags: [from rules: workbook row 55 benefit1] [from rules: user clarification 2026-04-30]
- provisional_family: supplant
- status: reviewed
- blocker_question: none
- notes: Bare `supplant` means normal supplant: choose enemy troop at site where you have presence, move it to your trophy hall, and place your own troop in that slot.

### card_id: spellspinner

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place a spy, or return one of your spies to supplant a troop at that site.
- tags: [from rules: workbook row 56 benefit1] [from rules: workbook row 56 benefit2] [from rules: user clarification 2026-04-28] [from rules: user clarification 2026-04-30]
- provisional_family: modal_spy_or_return_spy_then_supplant
- status: reviewed
- blocker_question: none
- notes: Uses established modal `or` rule, default self-return-spy rule, and normal supplant mechanics. `There` means former site of returned spy.

### card_id: inquisitor

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either gain 2 influence, or assassinate.
- tags: [from rules: workbook row 57 benefit1] [from rules: workbook row 57 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: modal_gain_influence_or_assassinate
- status: reviewed
- blocker_question: none
- notes: Bare `assassinate` means one free standard assassinate using normal assassinate legality against any legal troop target.

### card_id: blackguard

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either gain 2 power, or assassinate.
- tags: [from rules: workbook row 58 benefit1] [from rules: workbook row 58 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: modal_gain_power_or_assassinate
- status: reviewed
- blocker_question: none
- notes: Uses established modal `or` rule. Bare `assassinate` means one free standard assassinate using normal assassinate legality.

### card_id: priestess_of_lolth

- text_check: ok
- plain_english_effect: Gain 2 influence.
- tags: [from rules: workbook row 59 benefit1]
- provisional_family: gain_influence
- status: reviewed
- blocker_question: none
- notes: Simple fixed resource card.

### card_id: mercenary_squad

- text_check: ok
- plain_english_effect: Deploy 3 troops.
- tags: [from rules: workbook row 60 benefit1] [from rules: user clarification 2026-04-30]
- provisional_family: deploy_troops
- status: reviewed
- blocker_question: none
- notes: Bare `3 troops` means deploy 3 troops.

### card_id: masters_of_sorcere

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place 2 spies, or return one of your spies and gain 4 power.
- tags: [from rules: workbook row 61 benefit1] [from rules: workbook row 61 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: modal_place_two_spies_or_return_spy_for_power
- status: reviewed
- blocker_question: none
- notes: The `place 2 spies` mode uses normal spy placement legality twice. If fewer than 2 spies are available in barracks, you may move an existing spy already on the board.

### card_id: chosen_of_lolth

- text_check: ok
- plain_english_effect: Return another player's troop or spy where you have presence. At end of turn, promote another played card.
- tags: [from rules: workbook row 62 benefit1] [from rules: workbook row 62 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: return_unit_plus_triggered_promote
- status: reviewed
- blocker_question: none
- notes: `Return troop or spy` uses same rule as Blue Wyrmling: another player's troop or spy at a site where you have presence. The end-of-turn promote uses same target rule as Drow Negotiator and does nothing if no other played card exists.

### card_id: deathblade

- text_check: ok
- plain_english_effect: Assassinate 2 troops.
- tags: [from rules: workbook row 63 benefit1]
- provisional_family: repeated_assassinate
- status: reviewed
- blocker_question: none
- notes: Reuses fixed-count repeated assassinate behavior: two separate free standard assassinations, resolving as many as possible if legal targets run short.

### card_id: advance_scout

- text_check: ok
- plain_english_effect: Supplant a white troop.
- tags: [from rules: workbook row 64 benefit1]
- provisional_family: supplant_white_troop
- status: reviewed
- blocker_question: none
- notes: This is normal presence-limited supplant with target restricted to neutral white troops.

### card_id: advocate

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either gain 2 influence, or at end of turn promote another card played this turn.
- tags: [from rules: workbook row 65 benefit1] [from rules: workbook row 65 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: gain_influence_plus_triggered_promote
- status: reviewed
- blocker_question: none
- notes: This is modal, not additive. Promote branch targets another played card and does nothing if no other played card exists.

### card_id: kobold

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either deploy 1 troop, or assassinate a white troop.
- tags: [from rules: workbook row 66 benefit1] [from rules: workbook row 66 benefit2] [from rules: user clarification 2026-04-28] [from rules: user clarification 2026-04-29]
- provisional_family: modal_deploy_or_assassinate_white_troop
- status: reviewed
- blocker_question: none
- notes: Same functional family as Weaponmaster, at lower cost.

### card_id: air_elemental_myrmidon

- text_check: ok
- plain_english_effect: Place a spy. At end of turn, promote an Obedience card played this turn.
- tags: [from rules: workbook row 67 benefit1] [from rules: workbook row 67 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: spy_plus_triggered_promote_aspect_filtered
- status: reviewed
- blocker_question: none
- notes: The promote target can be any Obedience card you played this turn. If none was played, the end-of-turn clause does nothing.

### card_id: ogremoch

- text_check: ok
- plain_english_effect: Gain 2 influence. At end of turn, promote another played card. Focus: at end of turn, promote another played card.
- tags: [from rules: workbook row 68 benefit1] [from rules: workbook row 68 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: gain_influence_plus_triggered_promote_with_focus_bonus
- status: reviewed
- blocker_question: none
- notes: If the focus condition is met, Ogremoch gains a second separate end-of-turn `promote another played card` trigger on top of the base one.

### card_id: howling_hatred_cultist

- text_check: corrected
- plain_english_effect: Choose exactly one mode. Either place a spy, or return one of your spies and gain 3 influence. Focus: gain 1 power.
- tags: [from rules: workbook row 69 benefit1] [from rules: workbook row 69 benefit2] [from rules: user clarification 2026-05-04]
- provisional_family: modal_spy_or_return_spy_for_influence_with_focus_bonus
- status: reviewed
- blocker_question: none
- notes: The focus clause applies only when you choose the `return a spy and gain 3 influence` mode. If the standard focus condition is met, that mode also gains 1 power.

### card_id: earth_elemental_myrmidon

- text_check: ok
- plain_english_effect: Gain 2 influence. At end of turn, promote another played card.
- tags: [from rules: workbook row 70 benefit1] [from rules: workbook row 70 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: gain_influence_plus_triggered_promote
- status: reviewed
- blocker_question: none
- notes: Same triggered-promote family as Advocate, with the target restriction already explicit. If no other played card exists, the end-of-turn clause does nothing.

### card_id: fire_elemental_myrmidon

- text_check: ok
- plain_english_effect: Gain 2 power. At end of turn, promote an Obedience card played this turn.
- tags: [from rules: workbook row 71 benefit1] [from rules: workbook row 71 benefit2] [from rules: user clarification 2026-04-30]
- provisional_family: gain_power_plus_triggered_promote_aspect_filtered
- status: reviewed
- blocker_question: none
- notes: This uses the same aspect-filtered end-of-turn promote rule as Air Elemental Myrmidon. The target can be any Obedience card you played this turn; if none was played, the clause does nothing.

### card_id: yan_c_bin

- text_check: corrected
- plain_english_effect: Place a spy, then assassinate a troop at that site. If the focus condition is met, place another spy.
- tags: [from rules: workbook row 72 benefit1] [from rules: workbook row 72 benefit2] [from rules: user clarification 2026-05-22] [from rules: engine focus mechanic in current repo]
- provisional_family: spy_then_assassinate_plus_focus_spy
- status: reviewed
- blocker_question: none
- notes: Workbook shorthand was misleading here. Focus on Guile follows the current repo rule: another Guile card in hand or already played. When that condition is met, Yan-C-Bin grants one additional separate spy placement after the base spy-plus-assassinate effect.

### card_id: aerisi_kalinoth

- text_check: corrected
- plain_english_effect: Gain 1 power, place 1 spy, then recruit a Guile card that costs 4 or less.
- tags: [from rules: workbook row 73 benefit1] [from rules: user clarification 2026-05-22]
- provisional_family: gain_power_plus_spy_plus_recruit_aspect_filtered_card_by_cost
- status: reviewed
- blocker_question: none
- notes: Workbook text was incomplete and misspelled. The full effect is sequential: gain power, place a spy, then recruit a Guile card costing 4 or less.

### card_id: marlos_urnrayle

- text_check: corrected
- plain_english_effect: Gain 1 influence. At end of turn, promote another played card. Then recruit an Ambition card that costs 4 or less.
- tags: [from rules: workbook row 74 benefit1] [from rules: workbook row 74 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: gain_influence_plus_triggered_promote_plus_recruit_aspect_filtered_card_by_cost
- status: reviewed
- blocker_question: none
- notes: The row has three functional parts. The promote clause uses the established `another played card` rule and does nothing if no other played card exists.

### card_id: fire_elemental

- text_check: corrected
- plain_english_effect: Choose exactly one mode. Either gain 2 power, or gain 2 influence. If the focus condition is met for Malice, draw a card.
- tags: [from rules: workbook row 75 benefit1] [from rules: workbook row 75 benefit2] [from rules: workbook row 75 benefit3] [from rules: user clarification 2026-05-22]
- provisional_family: modal_gain_power_or_influence_with_focus_draw
- status: reviewed
- blocker_question: none
- notes: The workbook row was incomplete unless all three benefit columns were read together. The draw is a separate focus bonus using the normal Malice focus mechanic, not a mode choice.

### card_id: earth_elemental

- text_check: corrected
- plain_english_effect: Gain 1 influence. Return another player's troop or spy to their garrison. If the focus condition is met for Ambition, draw a card from your draw deck.
- tags: [from rules: workbook row 76 benefit1] [from rules: workbook row 76 benefit2] [from rules: workbook row 76 benefit3] [from rules: user clarification 2026-05-22]
- provisional_family: gain_influence_plus_return_enemy_unit_plus_focus_draw
- status: reviewed
- blocker_question: none
- notes: The workbook row was missing the influence clause in the earlier read path, and the user clarified that the focus aspect here is Ambition even though the sheet currently shows `Guile` in the aspect column.

### card_id: air_elemental

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place a spy, or return one of your spies to deploy 3 troops. If the focus condition is met for Guile, draw a card.
- tags: [from rules: workbook row 77 benefit1] [from rules: workbook row 77 benefit2] [from rules: workbook row 77 benefit3] [from rules: workbook row 77 aspect] [from rules: user clarification 2026-05-22]
- provisional_family: modal_spy_or_return_spy_to_deploy_troops_with_focus_draw
- status: reviewed
- blocker_question: none
- notes: The Guile focus draw applies regardless of which base mode you choose.

### card_id: olhydra

- text_check: ok
- plain_english_effect: Supplant a white troop anywhere on the board. If the focus condition is met for Conquest, deploy 2 troops.
- tags: [from rules: workbook row 78 benefit1] [from rules: workbook row 78 benefit2] [from rules: workbook row 78 aspect]
- provisional_family: unrestricted_supplant_white_troop_with_focus_deploy_troops
- status: reviewed
- blocker_question: none
- notes: `Anywhere on the board` overrides the normal presence-limited supplant restriction. The focus clause is a separate Conquest focus bonus.

### card_id: imix

- text_check: ok
- plain_english_effect: Gain 4 power. If the focus condition is met for Malice, gain 2 power.
- tags: [from rules: workbook row 79 benefit1] [from rules: workbook row 79 benefit2] [from rules: workbook row 79 aspect]
- provisional_family: gain_power_with_focus_power_bonus
- status: reviewed
- blocker_question: none
- notes: Simple fixed resource card plus separate same-resource focus bonus.

### card_id: black_earth_cultist

- text_check: ok
- plain_english_effect: At end of turn, promote another played card. If the focus condition is met for Ambition, gain 2 influence.
- tags: [from rules: workbook row 80 benefit1] [from rules: workbook row 80 benefit2] [from rules: workbook row 80 aspect]
- provisional_family: triggered_promote_plus_focus_influence_bonus
- status: reviewed
- blocker_question: none
- notes: The end-of-turn promote uses the established `another played card` rule and does nothing if no other played card exists. The focus bonus is separate.

### card_id: eternal_flame_cultist

- text_check: ok
- plain_english_effect: Assassinate a troop. If the focus condition is met for Malice, gain 2 power.
- tags: [from rules: workbook row 81 benefit1] [from rules: workbook row 81 benefit2] [from rules: workbook row 81 aspect]
- provisional_family: assassinate_troop_plus_focus_power_bonus
- status: reviewed
- blocker_question: none
- notes: Bare `assassinate a troop` uses the established free standard assassinate rule. The Malice focus clause is a separate resource bonus.

### card_id: water_elemental_myrmidon

- text_check: ok
- plain_english_effect: Assassinate a white troop. At end of turn, promote an Obedience card played this turn.
- tags: [from rules: workbook row 82 benefit1] [from rules: workbook row 82 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: assassinate_white_troop_plus_triggered_promote_aspect_filtered
- status: reviewed
- blocker_question: none
- notes: This uses the established white-troop assassination rule plus the established aspect-filtered end-of-turn promote family. If no Obedience card was played this turn, the promote clause does nothing.

### card_id: gar_shatterkeel

- text_check: ok
- plain_english_effect: Deploy 3 troops. Recruit a Conquest card that costs 4 or less.
- tags: [from rules: workbook row 83 benefit1] [from rules: workbook row 83 benefit2] [from rules: workbook row 83 aspect]
- provisional_family: deploy_troops_plus_recruit_aspect_filtered_card_by_cost
- status: reviewed
- blocker_question: none
- notes: Straight additive effect card. `Deploy 3 troops` uses the established free multi-deploy rule.

### card_id: vanifer

- text_check: ok
- plain_english_effect: Assassinate a troop. Recruit a Malice card that costs 4 or less.
- tags: [from rules: workbook row 84 benefit1] [from rules: workbook row 84 benefit2] [from rules: workbook row 84 aspect]
- provisional_family: assassinate_troop_plus_recruit_aspect_filtered_card_by_cost
- status: reviewed
- blocker_question: none
- notes: Straight additive effect card. Bare `assassinate a troop` uses the established free standard assassinate rule.

### card_id: water_elemental

- text_check: ok
- plain_english_effect: Deploy 2 troops. If the focus condition is met for Conquest, draw a card.
- tags: [from rules: workbook row 85 benefit1] [from rules: workbook row 85 benefit2] [from rules: workbook row 85 aspect]
- provisional_family: deploy_troops_with_focus_draw
- status: reviewed
- blocker_question: none
- notes: Straight additive effect card with a separate Conquest focus draw bonus.

### card_id: crushing_wave_cultist

- text_check: ok
- plain_english_effect: Assassinate a white troop. If the focus condition is met for Conquest, deploy 2 troops.
- tags: [from rules: workbook row 86 benefit1] [from rules: workbook row 86 benefit2] [from rules: workbook row 86 aspect]
- provisional_family: assassinate_white_troop_with_focus_deploy_troops
- status: reviewed
- blocker_question: none
- notes: Uses the established white-troop assassination rule plus a separate Conquest focus deploy bonus.

### card_id: night_hag

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place a spy, or return one of your own spies from the board to your barracks and draw 2 cards from your draw deck.
- tags: [from rules: workbook row 87 benefit1] [from rules: workbook row 87 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: modal_spy_or_return_spy_for_cards
- status: reviewed
- blocker_question: none
- notes: `Remove spy for 2 cards` means return one of your own spies from the board to your barracks, then draw 2 cards. This reuses the established modal spy-or-return-spy-for-cards family.

### card_id: myconid_sovereign

- text_check: ok
- plain_english_effect: Choose another player. That player adds an Insane Outcast from the Insane Outcast deck to their discard pile. At end of turn, promote another played card.
- tags: [from rules: workbook row 88 benefit1] [from rules: workbook row 88 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: give_negative_card_plus_triggered_promote
- status: reviewed
- blocker_question: none
- notes: `Give Insane Outcast` means choose another player and add an Insane Outcast from the Insane Outcast deck to that player's discard pile. The end-of-turn promote follows the established `another played card` rule and cannot target Myconid Sovereign itself.

### card_id: jackalwere

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place a spy, or return one of your own spies from the board to your barracks and gain 2 power and 2 influence.
- tags: [from rules: workbook row 89 benefit1] [from rules: workbook row 89 benefit2] [from rules: workbook row 89 aspect]
- provisional_family: modal_spy_or_return_spy_for_power_and_influence
- status: reviewed
- blocker_question: none
- notes: This matches the established Brainwashed Slave family: modal spy placement or self-spy return for a mixed resource reward.

### card_id: vrock

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place a spy, or return one of your own spies from the board to your barracks and gain 5 power.
- tags: [from rules: workbook row 90 benefit1] [from rules: workbook row 90 benefit2] [from rules: workbook row 90 aspect]
- provisional_family: spy_plus_return_spy_for_power
- status: reviewed
- blocker_question: none
- notes: Reuses the established modal spy-or-return-spy-for-power family.

### card_id: succubus

- text_check: truncated
- plain_english_effect: Devour a card from your hand to place a spy and assassinate a troop there.
- tags: [from rules: workbook row 91 benefit1] [from rules: workbook row 91 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: hand_devour_to_spy_then_assassinate
- status: reviewed
- blocker_question: none
- notes: Devouring a card from hand is a required cost. The devoured card goes to the normal devour pile permanently.

### card_id: mind_flayer

- text_check: truncated
- plain_english_effect: Devour a card from your hand, then choose exactly one mode: either gain 3 influence, or assassinate a troop.
- tags: [from rules: workbook row 92 benefit1] [from rules: workbook row 92 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: hand_devour_for_modal_influence_or_assassinate
- status: reviewed
- blocker_question: none
- notes: Devouring a card from hand is a required cost. After paying that cost, choose either 3 influence or a free standard assassinate. The devoured card goes to the normal devour pile.

### card_id: hezrou

- text_check: ok
- plain_english_effect: Move an enemy troop. Promote the top card of your draw deck directly into your promoted area. If your draw deck is empty, apply normal shuffle-to-refill rules first.
- tags: [from rules: workbook row 93 benefit1] [from rules: workbook row 93 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: move_enemy_troop_plus_promote_top_of_deck
- status: reviewed
- blocker_question: none
- notes: `Deck` here means draw deck. If the draw deck is empty, use normal shuffle-to-refill handling before promoting the top card.

### card_id: zuggtmoy

- text_check: truncated
- plain_english_effect: Devour a card in your inner circle to gain 3 influence and at end of turn promote up to 2 other played cards.
- tags: [from rules: workbook row 94 benefit1] [from rules: workbook row 94 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: inner_circle_devour_for_influence_plus_triggered_multi_promote
- status: reviewed
- blocker_question: none
- notes: Devouring a card in your inner circle means devouring one of your promoted cards from that zone as a required cost, sending it to the normal devour pile permanently. The end-of-turn clause promotes up to 2 other played cards.

### card_id: marilith

- text_check: ok
- plain_english_effect: Devour a card from your hand to gain 5 power.
- tags: [from rules: workbook row 95 benefit1] [from rules: workbook row 95 aspect] [inferred]
- provisional_family: hand_devour_for_power
- status: reviewed
- blocker_question: none
- notes: This uses the established hand-devour cost rule from Succubus and Mind Flayer: the devoured hand card goes to the normal devour pile permanently.

### card_id: grazzt

- text_check: truncated
- plain_english_effect: Choose exactly one mode. Either place 2 spies, or return any spies to supplant a troop at each of those sites.
- tags: [from rules: workbook row 96 benefit1] [from rules: workbook row 96 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: modal_place_two_spies_or_return_spies_then_multi_supplant
- status: reviewed
- blocker_question: none
- notes: `Return any spies` means return any number of your own spies from the board to your barracks, then supplant one troop at each former site of the returned spies. This mode cannot be executed if you have no spies on the board.

### card_id: balor

- text_check: truncated
- plain_english_effect: Devour a card from your hand to supplant a white troop anywhere on the board, then deploy 1 troop.
- tags: [from rules: workbook row 97 benefit1] [from rules: workbook row 97 benefit2] [inferred]
- provisional_family: hand_devour_to_supplant_white_anywhere_plus_deploy_troop
- status: reviewed
- blocker_question: none
- notes: This uses the established hand-devour cost rule and the card-specific `white troop anywhere on the board` supplant rule. After the supplant resolves, deploy 1 troop using normal deploy legality.

### card_id: nalfeshnee

- text_check: ok
- plain_english_effect: Gain 3 influence. Promote the top card of your draw deck directly into your promoted area. If your draw deck is empty, apply normal shuffle-to-refill rules first.
- tags: [from rules: workbook row 98 benefit1] [from rules: workbook row 98 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: gain_influence_plus_promote_top_of_deck
- status: reviewed
- blocker_question: none
- notes: This reuses the resolved `promote top card` rule from Hezrou, with a simple influence gain added.

### card_id: myconid_adult

- text_check: ok
- plain_english_effect: Gain 2 influence. Choose another player. That player adds an Insane Outcast from the Insane Outcast deck to their discard pile.
- tags: [from rules: workbook row 99 benefit1] [from rules: workbook row 99 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: gain_influence_plus_give_negative_card
- status: reviewed
- blocker_question: none
- notes: `Give insane outcast` uses the same resolved rule as Myconid Sovereign.

### card_id: derro

- text_check: ok
- plain_english_effect: Supplant a white troop anywhere. Recruit an Insane Outcast.
- tags: [from rules: workbook row 100 benefit1] [from rules: workbook row 100 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: supplant_white_anywhere_plus_recruit_negative_card
- status: reviewed
- blocker_question: none
- notes: `Recruit an insane outcast` means take an Insane Outcast from the Insane Outcast deck and add it to your own discard pile using normal recruit destination rules.

### card_id: ghoul

- text_check: ok
- plain_english_effect: Gain 2 power. Give an Insane Outcast to each opponent.
- tags: [from rules: workbook row 101 benefit1] [from rules: workbook row 101 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: gain_power_plus_give_negative_card_to_each_opponent
- status: reviewed
- blocker_question: none
- notes: `Give insane outcast to each opponent` uses the same resolved Insane Outcast transfer rule as Myconid Sovereign, repeated for every opponent.

### card_id: glabrezu

- text_check: truncated
- plain_english_effect: Devour a card from your hand to assassinate 2 troops.
- tags: [from rules: workbook row 102 benefit1] [from rules: workbook row 102 benefit2] [inferred]
- provisional_family: hand_devour_for_repeated_assassinate
- status: reviewed
- blocker_question: none
- notes: This uses the established hand-devour cost rule. After paying that cost, perform two free standard assassinations, resolving as many as possible if legal targets run short.

### card_id: ettin

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either deploy 3 troops, or assassinate 2 white troops.
- tags: [from rules: workbook row 103 benefit1] [from rules: workbook row 103 benefit2] [from rules: workbook row 103 aspect]
- provisional_family: modal_deploy_troops_or_repeated_white_troop_assassinate
- status: reviewed
- blocker_question: none
- notes: This combines the established modal `or` rule with free multi-deploy and repeated white-troop assassination behavior.

### card_id: gibbering_mouther

- text_check: malformed
- plain_english_effect: Deploy 2 troops. Choose a player who has Presence in the same site as one of the troops you deployed. That player adds an Insane Outcast to their discard pile.
- tags: [from rules: workbook row 104 benefit1] [from rules: workbook row 104 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: deploy_troops_plus_conditional_give_negative_card
- status: reviewed
- blocker_question: none
- notes: The workbook rider text is malformed. The resolved effect gives the Insane Outcast using the established transfer rule to a player who has presence in the same site as one of the deployed troops.

### card_id: demogorgon

- text_check: malformed
- plain_english_effect: Devour a card from your hand to supplant a white troop anywhere on the board. Then supplant 2 more white troops. Then each opponent recruits 2 Insane Outcasts.
- tags: [from rules: workbook row 105 benefit1] [from rules: workbook row 105 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: hand_devour_plus_mass_supplant_white_plus_mass_negative_recruit
- status: reviewed
- blocker_question: none
- notes: This is one long additive sequence, not modal. It uses the established hand-devour cost rule, then resolves three total white-troop supplants, and finally makes each opponent recruit 2 Insane Outcasts.

### card_id: orcus

- text_check: malformed
- plain_english_effect: Devour a card from your hand for 5 power. Assassinate 2 troops. Take up to 2 troops from any trophy halls and deploy them anywhere on the board.
- tags: [from rules: workbook row 106 benefit1] [from rules: workbook row 106 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: hand_devour_for_power_plus_repeated_assassinate_plus_redeploy_captured_units
- status: reviewed
- blocker_question: none
- notes: The workbook rider text is malformed. The resolved effect takes up to 2 troops from any trophy halls and deploys them anywhere on the board after the hand-devour power gain and the two assassinations.

### card_id: ghost

- text_check: truncated
- plain_english_effect: Choose exactly one mode. Either place a spy, or return one of your spies and take the top card from the devour pile into your discard pile for free.
- tags: [from rules: workbook row 107 benefit1] [from rules: workbook row 107 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: modal_spy_or_return_spy_to_play_top_devoured_as_market
- status: reviewed
- blocker_question: none
- notes: The return-spy branch takes the topmost card from the devour pile and adds it to your discard pile for free. It therefore leaves the devour pile when used.

### card_id: high_priest_of_myrkul

- text_check: ok
- plain_english_effect: Return another player's troop or spy. At end of turn, you may promote any number of Undead cards you played this turn (zero, one, some, or all).
- tags: [from rules: workbook row 108 benefit1] [from rules: workbook row 108 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: return_enemy_unit_plus_triggered_multi_promote_by_tag
- status: reviewed
- blocker_question: none
- notes: The promote clause is optional-flexible: you may promote zero through all qualifying cards. Qualifying cards are cards from the Undead deck.

### card_id: vampire

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either supplant a troop, or promote a card from your discard pile and then gain 1 VP for every 3 promoted cards.
- tags: [from rules: workbook row 109 benefit1] [from rules: workbook row 109 benefit2] [from rules: workbook row 109 aspect]
- provisional_family: modal_supplant_or_promote_from_discard_plus_scaled_vp
- status: reviewed
- blocker_question: none
- notes: Uses the established modal `or` rule. The VP scaling follows the established promoted-card counting rule and rounds down by groups of 3.

### card_id: necromancer

- text_check: truncated
- plain_english_effect: Choose exactly one mode. Either gain 3 influence, or perform exactly one promote action on exactly one card chosen from: this card, a card from hand, or a card from discard.
- tags: [from rules: workbook row 110 benefit1] [from rules: workbook row 110 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: modal_gain_influence_or_single_promote_from_multiple_zones
- status: reviewed
- blocker_question: none
- notes: The promote branch is a single promote action for one target card, with flexible source among the listed options.

### card_id: conjurer

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either place a spy, or return one of your spies to recruit up to 2 cards that cost 3 or less.
- tags: [from rules: workbook row 111 benefit1] [from rules: workbook row 111 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: modal_spy_or_return_spy_to_recruit_multiple_low_cost_cards
- status: reviewed
- blocker_question: none
- notes: Recruit up to 2 market cards costing 3 or less. Each recruited card follows normal recruit destination rules and goes to your discard pile.

### card_id: banshee

- text_check: ok
- plain_english_effect: Place a spy. If there is another spy there, gain 3 power.
- tags: [from rules: workbook row 112 benefit1] [from rules: workbook row 112 benefit2] [inferred]
- provisional_family: spy_plus_conditional_power_if_spy_present
- status: reviewed
- blocker_question: none
- notes: Uses established spy placement rules. The conditional checks whether another spy is present at that site after placement.

### card_id: lich

- text_check: ok
- plain_english_effect: Place a spy. If another player has a troop there, take 2 troops from that same player's trophy hall and deploy them anywhere on the board, regardless of presence.
- tags: [from rules: workbook row 113 benefit1] [from rules: workbook row 113 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: spy_plus_conditional_take_from_trophy_hall_and_deploy
- status: reviewed
- blocker_question: none
- notes: `Their trophy hall` refers to the same player who has a troop at the spy site. The taken troops can be deployed anywhere on the board and ignore normal presence restrictions.

### card_id: wight

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either gain 2 power, or devour a card from your hand to supplant a troop.
- tags: [from rules: workbook row 114 benefit1] [from rules: workbook row 114 benefit2] [inferred]
- provisional_family: modal_gain_power_or_devour_from_hand_to_supplant
- status: reviewed
- blocker_question: none
- notes: Uses the established modal `or` convention. The second mode requires devouring one card from hand as part of the effect, then performing a standard supplant.

### card_id: death_knight

- text_check: ok
- plain_english_effect: Supplant a troop. Then gain 1 VP for every 5 player trophies you have.
- tags: [from rules: workbook row 115 benefit1] [from rules: workbook row 115 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: supplant_plus_scaled_vp_from_trophies
- status: reviewed
- blocker_question: none
- notes: `Player trophies` means player-color trophies only; white troops in your trophy hall do not count. VP scales by groups of 5, rounded down.

### card_id: carrion_crawler

- text_check: ok
- plain_english_effect: Gain 3 power. Devour a card in the market and replace it with this one.
- tags: [from rules: workbook row 116 benefit1] [from rules: workbook row 116 benefit2] [from rules: user clarification 2026-05-22]
- provisional_family: gain_power_plus_devour_market_card_and_self_replace
- status: reviewed
- blocker_question: none
- notes: After devouring a chosen market card, Carrion Crawler itself is moved from your played area into that emptied market slot.

### card_id: wraith

- text_check: ok
- plain_english_effect: Place a spy. You may devour this card to assassinate a troop there.
- tags: [from rules: workbook row 117 benefit1] [from rules: workbook row 117 benefit2] [inferred]
- provisional_family: spy_plus_optional_self_devour_to_assassinate_there
- status: reviewed
- blocker_question: none
- notes: `There` refers to the site where the spy was placed. The assassinate uses standard assassinate legality at that site, and devouring this card is the cost for that rider.

### card_id: flesh_golem

- text_check: ok
- plain_english_effect: Gain 2 power. You may devour this card to assassinate a troop.
- tags: [from rules: workbook row 118 benefit1] [from rules: workbook row 118 benefit2] [inferred]
- provisional_family: gain_power_plus_optional_self_devour_to_assassinate
- status: reviewed
- blocker_question: none
- notes: Devouring this card is the cost to gain the assassination rider. Because no location qualifier is given, assassination follows standard global legality.

### card_id: ogre_zombie

- text_check: ok
- plain_english_effect: Supplant a white troop anywhere.
- tags: [from rules: workbook row 119 benefit1] [inferred]
- provisional_family: supplant_white_troop_anywhere
- status: reviewed
- blocker_question: none
- notes: `Anywhere` overrides normal location restrictions, including presence requirements, for this supplant.

### card_id: mummy_lord

- text_check: truncated
- plain_english_effect: Choose two times from this menu: (a) assassinate a white troop, (b) take a white trophy from another player and place it anywhere.
- tags: [from rules: workbook row 120 benefit1] [from rules: workbook row 120 benefit2] [from rules: workbook row 120 benefit3] [from rules: user clarification 2026-05-22]
- provisional_family: choose_twice_white_troop_assassinate_or_white_trophy_relocate
- status: reviewed
- blocker_question: none
- notes: The same option may be chosen both times. The white-trophy option takes a white troop from another player's trophy hall and deploys it anywhere regardless of presence.

### card_id: cultist_of_myrkul

- text_check: truncated
- plain_english_effect: Choose exactly one mode. Either gain 2 influence, or devour this card so that at end of turn you promote up to 2 other cards you played this turn.
- tags: [from rules: workbook row 121 benefit1] [from rules: workbook row 121 benefit2] [inferred]
- provisional_family: modal_gain_influence_or_self_devour_for_triggered_multi_promote
- status: reviewed
- blocker_question: none
- notes: The workbook clause appears typo-truncated (`to end of turn`). Interpreted as an end-of-turn triggered promote effect, reusing the established promote timing convention.

### card_id: ravenous_zombies

- text_check: ok
- plain_english_effect: Gain 1 power. Assassinate a white troop.
- tags: [from rules: workbook row 122 benefit1] [from rules: workbook row 122 benefit2]
- provisional_family: gain_power_plus_assassinate_white_troop
- status: reviewed
- blocker_question: none
- notes: Uses standard free white-troop assassination legality.

### card_id: skeletal_horde

- text_check: ok
- plain_english_effect: Deploy 2 troops. You can devour this card to deploy 3 more troops.
- tags: [from rules: workbook row 123 benefit1] [from rules: workbook row 123 benefit2] [inferred]
- provisional_family: deploy_troops_plus_optional_self_devour_for_extra_deploy
- status: reviewed
- blocker_question: none
- notes: Interpreted as additive (not modal), because no `or` delimiter is present. The self-devour clause is an optional rider.

### card_id: vampire_spawn

- text_check: typo
- plain_english_effect: Gain 1 influence. Return another player's troop or spy.
- tags: [from rules: workbook row 124 benefit1] [from rules: workbook row 124 benefit2] [inferred]
- provisional_family: gain_influence_plus_return_enemy_unit
- status: reviewed
- blocker_question: none
- notes: Workbook name appears misspelled (`Vampie Spawn`). Return clause reuses established enemy-unit return semantics.

### card_id: revenant

- text_check: punctuation
- plain_english_effect: Assassinate 2 troops. If you have 8 or more trophies, promote this card.
- tags: [from rules: workbook row 125 benefit1] [from rules: workbook row 125 benefit2] [inferred]
- provisional_family: multi_assassinate_plus_threshold_self_promote
- status: reviewed
- blocker_question: none
- notes: The assassinations follow standard free assassinate legality. The threshold uses generic `trophies` wording (not `player trophies`) and therefore counts trophies broadly.

### card_id: minotaur_skeleton

- text_check: ok
- plain_english_effect: Choose exactly one mode. Either deploy 3 troops, or devour this card to assassinate up to 3 white troops at a single site.
- tags: [from rules: workbook row 126 benefit1] [from rules: workbook row 126 benefit2] [inferred]
- provisional_family: modal_deploy_troops_or_self_devour_multi_white_assassinate_single_site
- status: reviewed
- blocker_question: none
- notes: Uses established modal `or` semantics. The second mode mirrors existing single-site repeated white-troop assassination patterns.
