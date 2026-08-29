"""Pure helpers for per-step game-state snapshots recorded by IS-MCTS runs.

Phase 2 of the IS-MCTS observability work.  Kept import-light (no ``pyspiel``,
no engine bindings at module import time) so these functions stay testable in
isolation: the Tier-2 helpers only need ``NodeOccupancyView``-shaped objects
(``troop_slots`` / ``spies`` attributes).

``_derive_total_control`` locks in the "Total Control" reading from
``docs/tyrants-rulebook.md`` ("all the site's troop spaces are *filled* only
with your troops and no enemy spies are present") which matches the C engine's
``is_total_control`` (``engine_c/scoring.c``): an **empty** troop slot
disqualifies total control because that slot is not filled with your troops.
"""

from __future__ import annotations

_BOARD_MUTATING_MOVE_TYPES = frozenset({"assassinate", "deploy", "return_spy"})

# Op vocabulary (``CardAction.op`` — see ``engine_c/selection.c``'s
# ``register_selection_handlers()``) for the pending generic action that
# board-mutating ``resolve_generic_choice`` moves answer.  Confirmed against
# the card table in ``docs/ismcts-generic-resolution-bugs.md``.
#
# This is NOT the same field as the move's own ``action_id`` (in its
# ``to_payload()``/JSON form): for a target-selection move, ``action_id``
# holds the *selected target* (a site/route/troop/player id, e.g.
# ``"site_chaulssin"``), never the action verb — the verb only exists on the
# engine's pending-generic-choice state, read via
# ``CEngineAdapter.pending_generic_op()`` *before* the move is applied.
_BOARD_MUTATING_GENERIC_ACTIONS = frozenset({
    "deploy_troops",
    "assassinate_troop",
    "supplant_troop",
    "place_spy",
    "move_troop",
    "return_unit",
})

_TIER1_PER_PLAYER_KEYS = frozenset({
    "hand_size",
    "deck_size",
    "discard_size",
    "played_size",
    "inner_circle_size",
    "trophy_hall_size",
    "barracks",
    "spies_available",
    "vp_tokens",
    "score",
})


def _derive_site_controller(node) -> str | None:
    """Return the player with a strict plurality of troops, or None if tied/empty.

    Mirrors the rulebook's "Control" rule and the C engine's
    ``site_control_owner`` (``engine_c/scoring.c``): count ``troop_slots`` by
    non-None owner and return the owner whose count strictly exceeds every
    other owner's.  Ties and fully-empty sites yield ``None``.
    """
    counts: dict[str, int] = {}
    for owner in node.troop_slots:
        if owner is None:
            continue
        counts[owner] = counts.get(owner, 0) + 1
    if not counts:
        return None
    max_count = max(counts.values())
    leaders = [owner for owner, count in counts.items() if count == max_count]
    if len(leaders) != 1:
        return None
    return leaders[0]


def _derive_total_control(node, controller: str | None) -> bool:
    """Return whether *controller* has total control of *node*.

    Total control requires: a definite controller, every troop slot filled
    with that controller's troops (an empty slot disqualifies — per the
    locked-in interpretation documented in the module docstring), and no
    enemy spies present.
    """
    if controller is None:
        return False
    for owner in node.troop_slots:
        if owner != controller:
            return False
    return all(spy_owner == controller for spy_owner in node.spies)


def _tier1_snapshot(adapter) -> dict:
    """Cheap per-player public snapshot, called on every successful step.

    Reuses ``CEngineAdapter._build_public_dict()``'s existing key names
    verbatim (``resource_power``, ``resource_influence``, ``market_row``,
    ``public_player_summaries`` with per-player ``hand_size``/``deck_size``/
    ... keys) to avoid inventing a parallel vocabulary.
    """
    return adapter._build_public_dict()


def _tier2_snapshot(adapter) -> dict:
    """Board snapshot derived from ``build_c_board_view``.

    Pricier than ``_tier1_snapshot`` (iterates every board node) — callers
    should only invoke it on round boundaries and board-mutating moves.
    """
    from engine_c.bindings.view import build_c_board_view

    view = build_c_board_view(adapter)

    board_nodes = []
    for node in view.board_nodes:
        controller = _derive_site_controller(node)
        board_nodes.append({
            "node_id": node.node_id,
            "controller": controller,
            "total_control": _derive_total_control(node, controller),
            "troop_slots": list(node.troop_slots),
            "spies": list(node.spies),
            "control_vp": node.control_vp,
            "total_control_vp_per_turn": node.total_control_vp_per_turn,
            "vp_tokens": node.vp_tokens,
        })

    return {
        "board_nodes": board_nodes,
        "current_player_controlled_sites": view.current_player_controlled_sites,
        "current_player_total_control_sites": view.current_player_total_control_sites,
        "current_player_control_vp": view.current_player_control_vp,
        "current_player_total_control_vp": view.current_player_total_control_vp,
    }


def _is_board_mutating(move_type: str, pending_op: str | None) -> bool:
    """Return whether applying this move can change the board state.

    *pending_op* is the pending generic action's op (from
    ``CEngineAdapter.pending_generic_op()``, read *before* applying the
    move) — only meaningful, and only consulted, when ``move_type ==
    "resolve_generic_choice"``.
    """
    if move_type in _BOARD_MUTATING_MOVE_TYPES:
        return True
    if move_type == "resolve_generic_choice":
        return pending_op in _BOARD_MUTATING_GENERIC_ACTIONS
    return False
