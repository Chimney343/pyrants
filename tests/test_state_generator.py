"""Constrained random state generator tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from engine.moves import PlayCardMove
from engine.rules import is_terminal, legal_moves
from engine.state import TurnPhase
from game_setup.scenarios import load_game_state_from_scenario
from game_setup.state_generator import (
    FORCED_INJECTIONS_FILENAME,
    ensure_card_scenario,
    find_card_scenario,
    find_state,
    find_state_and_save,
    generate_card_scenarios,
    generate_states,
    has_card_in_hand,
    has_card_in_market,
    has_enemy_troop_at_site,
    iter_roster_card_ids,
)

ROSTERS_PATH = Path(__file__).resolve().parents[1] / "data" / "decks"


def test_find_state_returns_matching_state() -> None:
    state = find_state(has_card_in_hand("noble"), seed=7, max_steps=50)

    assert state is not None
    assert "noble" in state.players["p1"].hand


def test_find_state_is_deterministic_by_seed() -> None:
    state_a = find_state(has_card_in_hand("noble"), seed=13, max_steps=50)
    state_b = find_state(has_card_in_hand("noble"), seed=13, max_steps=50)

    assert state_a is not None
    assert state_b is not None
    assert state_a.model_dump(mode="json") == state_b.model_dump(mode="json")


def test_find_state_bounded_by_max_steps() -> None:
    result = find_state(lambda _: False, seed=0, max_steps=10)

    assert result is None


def test_find_state_with_unsatisfiable_predicate_returns_none() -> None:
    def never(state) -> bool:
        return state.phase == TurnPhase.GAME_OVER and len(state.market.row) == 100

    result = find_state(never, seed=0, max_steps=20)

    assert result is None


def test_generate_states_produces_correct_count() -> None:
    states = generate_states(5, seed=42, max_steps_per_state=10)

    assert len(states) == 5
    for state in states:
        assert state.current_player_id in state.players
        assert len(state.turn_order) == 2


def test_generate_states_is_deterministic_by_seed() -> None:
    states_a = generate_states(3, seed=99, max_steps_per_state=15)
    states_b = generate_states(3, seed=99, max_steps_per_state=15)

    assert len(states_a) == len(states_b)
    for state_a, state_b in zip(states_a, states_b, strict=True):
        assert state_a.model_dump(mode="json") == state_b.model_dump(mode="json")


def test_generate_states_different_seeds_diverge() -> None:
    states_a = generate_states(3, seed=1, max_steps_per_state=20)
    states_b = generate_states(3, seed=2, max_steps_per_state=20)

    payloads_a = [state.model_dump(mode="json") for state in states_a]
    payloads_b = [state.model_dump(mode="json") for state in states_b]
    assert payloads_a != payloads_b


def test_find_state_and_save_persists() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "found_state.json"

        result = find_state_and_save(
            has_card_in_hand("noble"),
            save_path=path,
            seed=3,
            max_steps=30,
            scenario_id="found_test",
            description="Test save",
        )

        assert result is not None
        assert path.exists()
        assert "noble" in result.players["p1"].hand

    assert not path.exists()


def test_has_card_in_hand_predicate() -> None:
    pred = has_card_in_hand("noble")
    state = find_state(pred, seed=7, max_steps=5)

    assert state is not None
    assert "noble" in state.players["p1"].hand


def test_has_card_in_market_predicate() -> None:
    pred = has_card_in_market("bounty_hunter")
    state = find_state(pred, seed=5, max_steps=200)

    if state is not None:
        assert "bounty_hunter" in state.market.row


def test_has_enemy_troop_at_site_predicate() -> None:
    pred = has_enemy_troop_at_site("site_a", "p2", "p1")
    state = find_state(pred, seed=1, max_steps=300)

    if state is not None:
        node = state.board.nodes["site_a"]
        assert "p2" in node.troop_slots
        assert "p1" in node.spies


# ---------------------------------------------------------------------------
# Card scenario generation
# ---------------------------------------------------------------------------


def test_iter_roster_card_ids_returns_125_unique() -> None:
    ids = iter_roster_card_ids(ROSTERS_PATH)
    assert len(ids) == 125
    assert len(set(ids)) == 125
    assert "noble" in ids
    assert "aboleth" in ids


def test_find_card_scenario_starter_card_is_instant() -> None:
    state = find_card_scenario("noble", base_seed=0, max_attempts=1, max_steps_per_attempt=10)
    assert state is not None
    assert state.phase == TurnPhase.MAIN
    assert not is_terminal(state)
    assert state.definition.board.board_id == "Tyrants of the Underdark"
    assert len(state.turn_order) == 4
    assert "noble" in state.players[state.current_player_id].hand

    moves = list(legal_moves(state))
    playable = [move for move in moves if isinstance(move, PlayCardMove) and move.card_id == "noble"]
    assert len(playable) >= 1


def test_find_card_scenario_returns_none_for_impossible() -> None:
    state = find_card_scenario("noble", base_seed=0, max_attempts=1, max_steps_per_attempt=0)
    assert state is None


def test_ensure_card_scenario_force_injects_after_exhausted_search() -> None:
    state, note = ensure_card_scenario(
        "aboleth",
        base_seed=0,
        max_attempts=1,
        max_steps_per_attempt=0,
    )

    assert note is not None
    assert note["card_id"] == "aboleth"
    assert note["replaced_card_id"] != "aboleth"
    assert "aboleth" in state.players[state.current_player_id].hand
    assert state.phase == TurnPhase.MAIN
    assert not is_terminal(state)


def test_generate_card_scenarios_small_subset() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "cards"
        saved, missing = generate_card_scenarios(
            out,
            base_seed=42,
            max_attempts=1,
            max_steps_per_attempt=100,
            card_ids=["noble", "soldier"],
        )
        assert len(saved) == 2
        assert len(missing) == 0
        assert out.exists()

        noble_path = next(path for path in saved if "noble" in path.name)
        soldier_path = next(path for path in saved if "soldier" in path.name)
        assert noble_path.exists()
        assert soldier_path.exists()

        noble_state = load_game_state_from_scenario(noble_path)
        assert "noble" in noble_state.players[noble_state.current_player_id].hand

        soldier_state = load_game_state_from_scenario(soldier_path)
        assert "soldier" in soldier_state.players[soldier_state.current_player_id].hand

        notes = json.loads((out / FORCED_INJECTIONS_FILENAME).read_text(encoding="utf-8"))
        assert notes == []


def test_generate_card_scenarios_writes_forced_injection_notes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "cards"
        saved, missing = generate_card_scenarios(
            out,
            base_seed=0,
            max_attempts=1,
            max_steps_per_attempt=0,
            card_ids=["aboleth"],
        )

        assert len(saved) == 1
        assert missing == []

        scenario_state = load_game_state_from_scenario(saved[0])
        assert "aboleth" in scenario_state.players[scenario_state.current_player_id].hand

        notes = json.loads((out / FORCED_INJECTIONS_FILENAME).read_text(encoding="utf-8"))
        assert len(notes) == 1
        assert notes[0]["card_id"] == "aboleth"
        assert notes[0]["scenario_file"] == saved[0].name