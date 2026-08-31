> **Archived 2026-08-30** — every item below is now implemented and tested; `docs/openspiel_integration.md` is the live doc.

Tyrants of the Underdark: OpenSpiel Integration Checklist (IS-MCTS Support)
1. Core Forward Model & Actions

    [ ] Action Space ID Mapping: Map every house action (Recruit, Promote, Deploy, Assassinate, etc.) to a unique integer ID within the OpenSpiel action space.
    [ ] Deterministic State Transitions: Ensure that given a specific state and action, the engine reaches a consistent and predictable next state.
    [ ] Presence Logic: Verify that the LegalActions function correctly identifies "Presence" (controlling a troop or spy at or adjacent to a site) before allowing deployments or assassinations.
    [ ] Control & Total Control: Ensure the engine correctly updates Control (most troops at a site) and Total Control (occupying all spaces with no enemy spies) after every move.

2. Information Sets & Observability

    [ ] Information Set Definition: The InformationStateString or Tensor must include only observable data: the player's own hand/discard pile, the visible board, face-up market cards, and public counts of cards in opponent decks.
    [ ] Hidden Information Masking: Ensure that opponent hand contents and the specific order of the market deck are strictly excluded from the current player's observation.
    [ ] Partially Observable Moves: If an action is only partially visible to others, the engine must treat these as indistinguishable moves for the observer.

3. Determinization Support (Required for IS-MCTS)

    [ ] Resampling Logic: The engine must be able to resample a hidden state (determinization) that is consistent with the current information set by randomly assigning cards to opponent hands and the market deck.
    [ ] Consistency: Randomly assigned cards must align with the known recruitment history and total card counts (e.g., if 5 Priestesses of Lolth are visible, only 5 can be assigned to hidden areas).
    [ ] State Cloning: Verify that the Clone() method creates a perfect copy of all internal engine variables, including Influence and Power pools.

4. Action Legalization & Subset-Armed Bandits

    [ ] Availability Logic: Because IS-MCTS handles moves that may only be legal in certain determinizations, verify that LegalActions correctly filters actions based on the specific sampled state ω.
    [ ] Branching Factor Management: For complex card plays involving "kicker" effects, consider splitting the action into consecutive decision nodes to prevent branching factor explosion.

5. Termination & Rewards

    [ ] Termination Conditions: The game must accurately trigger the end-state when a player deploys their last troop or the market deck is empty.
    [ ] Final VP Scoring: Upon termination, the Returns() function must accurately sum Victory Points from site control markers, troops on the board, and the deck/inner-circle values of all cards.

Note on Information Sources: Information regarding specific OpenSpiel API integration points (such as LegalActions, InformationStateString, Action IDs, and Clone()) is not contained within the provided sources and should be independently verified against official framework documentation. Information regarding Information Set Monte Carlo Tree Search (IS-MCTS) and Tyrants of the Underdark game rules is drawn directly from the sources.