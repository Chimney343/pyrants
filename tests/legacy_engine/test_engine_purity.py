"""Purity guardrails for engine modules."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from engine.moves import PlayCardMove, ResolveGenericChoiceMove
from engine.rules import apply, legal_moves
from engine.state import (
    GameState,
    build_initial_game_state,
)
from game_setup.loaders import build_game_definition_from_files

ENGINE_DIR = Path(__file__).resolve().parents[2] / "engine"
FORBIDDEN_CALLS = {"print", "input", "open"}
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def test_engine_has_no_interface_imports_or_direct_io() -> None:
    violations: list[str] = []

    for file_path in ENGINE_DIR.glob("*.py"):
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for imported in node.names:
                    if imported.name == "interface" or imported.name.startswith("interface."):
                        violations.append(f"{file_path.name}: imports interface module")

            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "interface" or module.startswith("interface."):
                    violations.append(f"{file_path.name}: imports from interface module")

            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_CALLS:
                    violations.append(f"{file_path.name}: forbidden call '{node.func.id}'")

    assert not violations, "\n".join(violations)


def _make_initial_state() -> GameState:
    definition = build_game_definition_from_files(
        _DATA_DIR / "boards" / "tyrants_of_the_underdark.json",
        _DATA_DIR / "cards" / "catalog.json",
        _DATA_DIR / "decks" / "base_setup.json",
    )
    return build_initial_game_state(
        definition, ["p0", "p1"], shuffle_seed=42,
    )


def _snapshot_state(state: GameState) -> dict[str, Any]:
    """Capture identity and value of mutable containers for later comparison."""
    nodes: dict[str, dict[str, Any]] = {}
    for node_id, ns in state.board.nodes.items():
        nodes[node_id] = {
            "id": id(ns),
            "troop_slots": list(ns.troop_slots),
            "spies": set(ns.spies),
            "vp_tokens": ns.vp_tokens,
        }
    players: dict[str, dict[str, Any]] = {}
    for pid, ps in state.players.items():
        players[pid] = {
            "id": id(ps),
            "hand": list(ps.hand),
            "deck": list(ps.deck),
            "discard_pile": list(ps.discard_pile),
            "played_cards": list(ps.played_cards),
            "inner_circle": list(ps.inner_circle),
            "trophy_hall": list(ps.trophy_hall),
            "barracks": ps.barracks,
            "spies_available": ps.spies_available,
            "score": ps.score,
        }
    return {
        "nodes": nodes,
        "players": players,
        "resource_power": state.resource_pool.power,
        "resource_influence": state.resource_pool.influence,
    }


def test_cow_apply_does_not_mutate_source_state() -> None:
    """After applying a move, the source state's node and player objects
    must be unchanged (both identity and value)."""
    state = _make_initial_state()
    before = _snapshot_state(state)

    moves = [
        m for m in apply.__globals__["legal_moves"](state)
        if m.move_type != "initial_placement"
    ]
    if not moves:
        return

    move = moves[0]
    updated = apply(state, move)
    assert updated is not state

    after = _snapshot_state(state)

    for node_id, snap in before["nodes"].items():
        ns = state.board.nodes[node_id]
        assert id(ns) == snap["id"], f"NodeState identity changed for {node_id}"
        assert list(ns.troop_slots) == snap["troop_slots"], f"troop_slots mutated for {node_id}"
        assert set(ns.spies) == snap["spies"], f"spies mutated for {node_id}"
        assert ns.vp_tokens == snap["vp_tokens"], f"vp_tokens mutated for {node_id}"

    for pid, snap in before["players"].items():
        ps = state.players[pid]
        assert id(ps) == snap["id"], f"PlayerState identity changed for {pid}"
        assert list(ps.hand) == snap["hand"], f"hand mutated for {pid}"
        assert list(ps.deck) == snap["deck"], f"deck mutated for {pid}"
        assert list(ps.discard_pile) == snap["discard_pile"], f"discard_pile mutated for {pid}"
        assert list(ps.played_cards) == snap["played_cards"], f"played_cards mutated for {pid}"
        assert list(ps.inner_circle) == snap["inner_circle"], f"inner_circle mutated for {pid}"
        assert list(ps.trophy_hall) == snap["trophy_hall"], f"trophy_hall mutated for {pid}"
        assert ps.barracks == snap["barracks"], f"barracks mutated for {pid}"
        assert ps.spies_available == snap["spies_available"], f"spies_available mutated for {pid}"
        assert ps.score == snap["score"], f"score mutated for {pid}"

    assert state.resource_pool.power == before["resource_power"], "resource power mutated"
    assert state.resource_pool.influence == before["resource_influence"], "resource influence mutated"


def test_cow_does_not_mutate_pending_generic_choice() -> None:
    """After applying a ResolveGenericChoiceMove, the source state's
    pending_generic_choice must be unchanged (both identity and value)."""
    from engine.helpers import _legal_initial_placement_node_ids
    from engine.moves import InitialPlacementMove
    from engine.state import TurnPhase

    state = _make_initial_state()
    # Advance through setup phase so card play becomes legal.
    while state.phase == TurnPhase.SETUP:
        node_ids = _legal_initial_placement_node_ids(state)
        move = InitialPlacementMove(
            player_id=state.current_player_id,
            target_node_id=node_ids[0],
        )
        state = apply(state, move)

    # Now deep-copy and set up Enchanter of Thay scenario (recipe from
    # tests/test_scenarios.py::test_reload_state_with_pending_generic_choice).
    state = state.model_copy(deep=True)
    player_id = state.current_player_id
    state.players[player_id].hand = ["enchanter_of_thay"]
    state.players[player_id].deck = []
    state.players[player_id].discard_pile = []
    state.players[player_id].played_cards = []
    state.board.nodes["site_gauntlgrym"].spies.add(player_id)

    played = apply(state, PlayCardMove(player_id=player_id, card_id="enchanter_of_thay", hand_index=0))
    assert played.pending_generic_choice is not None, "Failed to set up pending_generic_choice"

    pgc = played.pending_generic_choice
    pgc_id = id(pgc)
    pgc_snapshot = pgc.model_copy(deep=True)

    choice_moves = [m for m in legal_moves(played) if isinstance(m, ResolveGenericChoiceMove)]
    assert choice_moves, "No ResolveGenericChoiceMove available after playing Enchanter of Thay"
    choice_move = choice_moves[0]

    updated = apply(played, choice_move)
    assert updated is not played

    src_pgc = played.pending_generic_choice
    assert id(src_pgc) == pgc_id, f"pending_generic_choice identity changed (was {pgc_id}, now {id(src_pgc)})"
    assert src_pgc.selected_option_ids == pgc_snapshot.selected_option_ids, "selected_option_ids mutated"
    assert src_pgc.action_counters == pgc_snapshot.action_counters, "action_counters mutated"
    assert src_pgc.last_selection == pgc_snapshot.last_selection, "last_selection mutated"
    assert src_pgc.option_ids == pgc_snapshot.option_ids, "option_ids mutated"
    assert src_pgc.current_actions == pgc_snapshot.current_actions, "current_actions mutated"
    assert src_pgc.next_action_index == pgc_snapshot.next_action_index, "next_action_index mutated"
    assert src_pgc.remaining_repeats == pgc_snapshot.remaining_repeats, "remaining_repeats mutated"
    assert src_pgc.awaiting_option == pgc_snapshot.awaiting_option, "awaiting_option mutated"
    assert src_pgc == pgc_snapshot, "pending_generic_choice full equality violated"
