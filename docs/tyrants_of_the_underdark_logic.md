This technical report outlines the architectural requirements for implementing a **Tyrants of the Underdark** engine in Python. As previously noted, this report focuses on the functional logic, while board topography and card data should be maintained in separate configuration files (JSON or YAML).

### 1. Board Encoding: The Underdark Graph
The game board is best represented as a **graph-based adjacency list**, where nodes are either **Sites** or **Route Spaces**.

*   **Node Representation:**
    *   **Sites:** Encoded as complex nodes with a fixed number of `troop_spaces` (List), `spies` (Set of player IDs), and a `VP_value` attribute. Sites also require a `control_state` property to track which player holds the **Site Control Marker**.
    *   **Route Spaces:** Encoded as single-troop-space nodes.
*   **Presence Logic (Graph Traversal):**
    *   Implement a boolean function `has_presence(player_id, node_id)`.
    *   According to the sources, a player has presence if they have a troop or spy at the node, or a troop at an *adjacent* node. In Python, this is a simple check of `node.occupants` and `[neighbor.occupants for neighbor in G.neighbors(node)]`.
*   **Site Control Auditor:**
    *   **Control:** Run a majority check: `player_troops > max(other_players_troops)`.
    *   **Total Control:** A stricter check: `all(space == player_id for space in site.troop_spaces) AND len(site.enemy_spies) == 0`.

### 2. Card Encoding: Functional Objects
Cards should be implemented as objects with immutable metadata and a **functional callback** for rules text.

*   **Card Schema:**
    *   `metadata`: `name`, `cost`, `aspect`, `deck_vp`, `inner_circle_vp`.
    *   `effect_hook`: A function or command object that modifies the `GameState`.
*   **Special Ability Logic:**
    *   **Focus:** Before executing a Focus ability, the engine must scan the `player.played_cards` and `player.hand` for a matching `aspect` symbol.
    *   **Abilities with Costs (▶):** Implement these as **conditional wrappers**. The engine prompts the user to pay the left-side cost (e.g., "Discard a card") to unlock the right-side effect.
    *   **Promote:** Cards moved to the `inner_circle` list are flagged as "out of play" and never returned to the discard pile.

### 3. Player State and Zone Management
Each player requires a class to manage five distinct card zones and physical supply counts.

*   **Card Zones:** Use `collections.deque` or `list` for `deck`, `hand`, `discard_pile`, `played_cards`, and `inner_circle`.
*   **The Draw/Shuffle Routine:** Implement a `draw_card()` method that automatically triggers a `shuffle(discard_pile)` move to the `deck` whenever the `deck` is empty and a draw is required.
*   **Physical Supply:** Maintain integers for `barracks` (40 troops) and `spies_available` (5 spies). Logic must check if `barracks == 0` during a **Deploy** action to instead award 1 VP.

### 4. Turn Sequence (The Game Loop)
The engine should operate as a **Finite State Machine (FSM)** following the three-step sequence:

1.  **Main Phase State:**
    *   Accepts input for **Playing Cards** or **Basic Actions** (Assassinate, Deploy, Recruit, Return Spy).
    *   Maintains a transient `resource_pool` for Power ( ) and Influence ( ) that clears upon state transition.
    *   **Basic action semantics (resolved from user clarification 2026-04-27):**
        *   **Assassinate:** Spend 3 Power. Target one enemy troop (including neutral white troops) at a node where you have presence. You cannot target your own troops. Remove the troop and record one captured marker in your trophy hall.
        *   **Deploy:** Spend 1 Power to place one troop into an empty troop slot at a node where you have presence. If you have no troops on the board, you may deploy to any empty slot. If barracks is empty, gain 1 VP instead of placing.
        *   **Recruit:** Spend Influence equal to the selected market card's printed cost. Put the card into your discard pile, then refill the emptied market-row slot immediately from the market deck when possible.
        *   **Return Spy:** Returning an enemy spy requires presence at that node and costs 3 Power as a basic action. Returning your own spy is legal from any node and has no Power cost. Move the spy back to its owner's barracks. No default reward is granted.
2.  **End of Turn State:**
    *   Triggers "At end of turn" promotes.
    *   **VP Tally:** Queries all `SiteControlMarkers` held by the player and adds the corresponding VP to their total.
3.  **Cleanup State:**
    *   Mass move: `played_cards + hand` $\rightarrow$ `discard_pile`.
    *   Draw 5 new cards.

### 5. Final Scoring Logic
At the game's end (triggered by an empty market deck or a player's last troop), the engine must run a multi-source VP tally:
*   **Map VP:** Sites controlled + Total Control bonuses (+2 VP).
*   **Trophy VP:** `len(player.trophy_hall)`.
*   **Deck VP:** Sum of `deck_vp` for all cards in `deck`, `hand`, and `discard`.
*   **Inner Circle VP:** Sum of `inner_circle_vp` for all promoted cards.
*   **Token VP:** Sum of collected VP markers.