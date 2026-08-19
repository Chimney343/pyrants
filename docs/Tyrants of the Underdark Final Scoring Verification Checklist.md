Tyrants of the Underdark: Final Scoring Verification Checklist
Verified against the active C engine (engine_c/scoring.c, engine_c/phases.c, engine_c/state.h) and docs/game_manual.md. Two engine-vs-checklist divergences are noted inline.

1. Game Termination & Final Round

    [x] End-of-Game Trigger — engine_c/phases.c:51-64: at cleanup, when the next player wraps to player_ids[0] (round boundary), sets game-over if market.deck_count == 0 (empty market deck) OR any players[i].barracks == 0 (last troop deployed). set_game_over (phases.c:70-73) flips phase to PHASE_GAME_OVER. Matches the checklist.
    [x] Round Completion — engine_c/phases.c:52-53: the trigger fires only when next == player_ids[0], i.e. after every player has completed the round. Final tallying begins only at that boundary. Matches.

2. Map-Based Scoring

    [x] Site Control VP — engine_c/scoring.c:90-103: compute_final_scores iterates sites and awards nd->control_vp to site_control_owner. site_control_owner (scoring.c:12-44) counts every non-empty occupant toward the majority (white troops DO count; see game_manual.md:152), requires a unique leader, and excludes white from owning (scoring.c:40). Award uses the site-specific control_vp value (NodeDefinition.control_vp, state.h:153). Matches the checklist.
    [ ] Total Control Bonus — DIVERGENCE: the checklist awards a flat +2 VP per total-control site at end of game; the engine does NOT. engine_c/scoring.c:75-88 (award_end_of_turn_site_vp) uses is_total_control only to grant the per-site configured total_control_vp_per_turn during end-of-turn scoring, not a flat +2 at final tally. compute_final_scores (scoring.c:90-118) does not call is_total_control at all. Affirmed as an intentional design variant per game_manual.md:182-193 and the plan .kilo/plans/1780386979046-nimble-nebula.md:61 ("final score should no longer add a flat +2 per total-control site unless that value is encoded in data"). To match the printed rulebook this would need to change.
    [x] Trophy Hall Tally — engine_c/scoring.c:105: total += ps->trophy_hall_count (1 VP per trophy). Locked by tests/c_engine/test_scoring.py::test_final_score_includes_both_trophies_and_tokens. Matches.

3. Minion & Card Scoring

    [x] Deck, Hand, and Discard VP — engine_c/scoring.c:108-113: concatenates deck + hand + discard_pile and sums CardDefinition.deck_vp (state.h:122) via cards_vp(..., 1). Matches.
    [x] Inner Circle VP — engine_c/scoring.c:115: sums CardDefinition.inner_circle_vp (state.h:123) for players' inner_circle zones via cards_vp(..., 0). Matches.
    [x] Devoured Cards Exclusion — engine_c/state.h:326: devour_pile is a per-player zone never read by compute_final_scores (scoring.c:90-118 only reads ps->deck, ps->hand, ps->discard_pile, ps->inner_circle, plus ps->score/trophy_hall_count/vp_tokens). Devoured cards are therefore excluded from all players' final scores. Matches.

4. Token & Winner Determination

    [x] VP Token Summation — engine_c/scoring.c:106: total += ps->vp_tokens. Tokens are accumulated face-value into ps->vp_tokens at grant time (engine_c/actions.c:558 and engine_c/rules.c:542 for the as:vp_tokens variants), so the final sum is the cumulative face value of all collected 1 VP / 5 VP tokens. Locked by tests/c_engine/test_scoring.py::test_vp_tokens_included_in_final_score. Note: the engine stores tokens as a running integer rather than tracking denominations separately; the contribution to the final total is equivalent. Matches.
    [x] Winner Identification — engine_c/scoring.c:121-131: find_winner calls compute_final_scores then returns state->players[max_idx].player_id for the highest total. Matches.
    [x] Tie-Handling — engine_c/scoring.c:128-130: any tie among the leaders sets the tie flag, and find_winner returns SYM_NULL (no single winner), which the rest of the engine treats as shared victory. Matches.