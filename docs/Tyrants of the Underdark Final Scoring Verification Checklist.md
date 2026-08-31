Tyrants of the Underdark: Final Scoring Verification Checklist
Verified against the active C engine (engine_c/scoring.c, engine_c/phases.c, engine_c/state.h) and the shipped board data (`data/boards/tyrants_of_the_underdark.json`). All items below match the current engine.

1. Game Termination & Final Round

    [x] End-of-Game Trigger — engine_c/phases.c:51-64: at cleanup, when the next player wraps to player_ids[0] (round boundary), sets game-over if market.deck_count == 0 (empty market deck) OR any players[i].barracks == 0 (last troop deployed). set_game_over (phases.c:70-73) flips phase to PHASE_GAME_OVER. Matches the checklist.
    [x] Round Completion — engine_c/phases.c:52-53: the trigger fires only when next == player_ids[0], i.e. after every player has completed the round. Final tallying begins only at that boundary. Matches.

2. Map-Based Scoring

    [x] Site Control VP — engine_c/scoring.c:96-101: compute_final_scores iterates sites and awards nd->control_vp to site_control_owner. site_control_owner (scoring.c:12-44) counts every non-empty occupant toward the majority (white troops DO count toward the majority — scoring.c:21-30; but white cannot own — scoring.c:40), requires a unique leader, and excludes white from owning (scoring.c:40). Award uses the site-specific control_vp value (NodeDefinition.control_vp, state.h:153). Matches the checklist.
    [x] Total Control Bonus — engine_c/scoring.c:102-108: compute_final_scores awards +2 VP per site under total control at final tally (on top of control_vp), locked by tests/c_engine/test_scoring.py::TestTotalControlFinalBonus. This is distinct from award_end_of_turn_site_vp (scoring.c:75-88), which grants the per-site configured total_control_vp_per_turn during end-of-turn scoring. Matches the checklist.
    [x] Trophy Hall Tally — engine_c/scoring.c:112: total += ps->trophy_hall_count (1 VP per trophy). Locked by tests/c_engine/test_scoring.py::test_final_score_includes_both_trophies_and_tokens. Matches.

3. Minion & Card Scoring

    [x] Deck, Hand, and Discard VP — engine_c/scoring.c:115-120: concatenates deck + hand + discard_pile and sums CardDefinition.deck_vp (state.h:122) via cards_vp(..., 1). Matches.
    [x] Inner Circle VP — engine_c/scoring.c:122: sums CardDefinition.inner_circle_vp (state.h:123) for players' inner_circle zones via cards_vp(..., 0). Matches.
    [x] Devoured Cards Exclusion — engine_c/state.h:326: devour_pile is a per-player zone never read by compute_final_scores (scoring.c:90-126 only reads ps->deck, ps->hand, ps->discard_pile, ps->inner_circle, plus ps->score/trophy_hall_count/vp_tokens). Devoured cards are therefore excluded from all players' final scores. Matches.

4. Token & Winner Determination

    [x] VP Token Summation — engine_c/scoring.c:113: total += ps->vp_tokens. Tokens are accumulated face-value into ps->vp_tokens at grant time (engine_c/actions.c:558 and engine_c/rules.c:542 for the as:vp_tokens variants), so the final sum is the cumulative face value of all collected 1 VP / 5 VP tokens. Locked by tests/c_engine/test_scoring.py::test_vp_tokens_included_in_final_score. Note: the engine stores tokens as a running integer rather than tracking denominations separately; the contribution to the final total is equivalent. Matches.
    [x] Winner Identification — engine_c/scoring.c:128-138: find_winner calls compute_final_scores then returns state->players[max_idx].player_id for the highest total. Matches.
    [x] Tie-Handling — engine_c/scoring.c:135-137: any tie among the leaders sets the tie flag, and find_winner returns SYM_NULL (no single winner), which the rest of the engine treats as shared victory. Matches.