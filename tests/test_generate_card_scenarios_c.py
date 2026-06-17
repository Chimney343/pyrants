"""C-engine card scenario generation tests."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine_c.bindings.scenario_search import (
    FORCED_INJECTIONS_FILENAME,
    ensure_card_scenario_c,
    generate_card_scenarios_c,
)
from engine_c.bindings.session import CSession

ROSTERS_PATH = Path(__file__).resolve().parents[1] / "data" / "decks"
CARD_PATH = Path(__file__).resolve().parents[1] / "data" / "cards" / "catalog.json"
BOARD_PATH = Path(__file__).resolve().parents[1] / "data" / "boards" / "tyrants_of_the_underdark.json"
SETUP_PATH = Path(__file__).resolve().parents[1] / "data" / "decks" / "base_setup.json"


def test_ensure_card_scenario_c_starter_card_is_instant() -> None:
    state, note, market_deck_ids, special_stacks_present = ensure_card_scenario_c(
        "noble",
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        rosters_path=ROSTERS_PATH,
        player_ids=["p1", "p2", "p3", "p4"],
        base_seed=0,
        max_attempts=1,
        max_steps_per_attempt=10,
    )
    assert note is None
    assert state.phase == "main"
    assert state.current_player_id in state.player_ids
    current_idx = state.player_ids.index(state.current_player_id)
    assert "noble" in state.player_hand(current_idx)
    state.destroy()


def test_ensure_card_scenario_c_force_injects_after_exhausted_search() -> None:
    state, note, market_deck_ids, special_stacks_present = ensure_card_scenario_c(
        "aboleth",
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        rosters_path=ROSTERS_PATH,
        player_ids=["p1", "p2", "p3", "p4"],
        base_seed=0,
        max_attempts=1,
        max_steps_per_attempt=0,
    )
    assert note is not None
    assert note["card_id"] == "aboleth"
    assert note["replaced_card_id"] != "aboleth"
    current_idx = state.player_ids.index(state.current_player_id)
    assert "aboleth" in state.player_hand(current_idx)
    assert state.phase == "main"
    assert len(market_deck_ids) == 2
    assert "aberrations" in market_deck_ids
    assert "house_guard" in special_stacks_present
    assert "priestess_of_lolth" in special_stacks_present
    state.destroy()


def test_generate_card_scenarios_c_small_subset() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "cards"
        saved, missing = generate_card_scenarios_c(
            out,
            board_path=BOARD_PATH,
            card_path=CARD_PATH,
            setup_path=SETUP_PATH,
            rosters_path=ROSTERS_PATH,
            player_ids=["p1", "p2", "p3", "p4"],
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

        noble_session = CSession.load(str(noble_path))
        noble_state = noble_session.state
        current_idx = noble_state.player_ids.index(noble_state.current_player_id)
        assert "noble" in noble_state.player_hand(current_idx)
        noble_session.destroy()

        soldier_session = CSession.load(str(soldier_path))
        soldier_state = soldier_session.state
        current_idx = soldier_state.player_ids.index(soldier_state.current_player_id)
        assert "soldier" in soldier_state.player_hand(current_idx)
        soldier_session.destroy()

        for path in (noble_path, soldier_path):
            scenario = json.loads(path.read_text(encoding="utf-8"))
            meta = scenario["metadata"]
            assert len(meta["market_deck_ids"]) == 2
            assert meta["market_deck_ids"][0] != meta["market_deck_ids"][1]
            assert "house_guard" in meta["special_stacks_present"]
            assert "priestess_of_lolth" in meta["special_stacks_present"]

        notes_path = out / FORCED_INJECTIONS_FILENAME
        notes = json.loads(notes_path.read_text(encoding="utf-8")) if notes_path.exists() else []
        assert notes == []


def test_generate_card_scenarios_c_writes_forced_injection_notes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "cards"
        saved, missing = generate_card_scenarios_c(
            out,
            board_path=BOARD_PATH,
            card_path=CARD_PATH,
            setup_path=SETUP_PATH,
            rosters_path=ROSTERS_PATH,
            player_ids=["p1", "p2", "p3", "p4"],
            base_seed=0,
            max_attempts=1,
            max_steps_per_attempt=0,
            card_ids=["aboleth"],
        )
        assert len(saved) == 1
        assert missing == []

        ab_session = CSession.load(str(saved[0]))
        ab_state = ab_session.state
        current_idx = ab_state.player_ids.index(ab_state.current_player_id)
        assert "aboleth" in ab_state.player_hand(current_idx)
        ab_session.destroy()

        scenario = json.loads(saved[0].read_text(encoding="utf-8"))
        meta = scenario["metadata"]
        assert len(meta["market_deck_ids"]) == 2
        assert "aberrations" in meta["market_deck_ids"]

        notes_path = out / FORCED_INJECTIONS_FILENAME
        notes = json.loads(notes_path.read_text(encoding="utf-8"))
        assert len(notes) == 1
        assert notes[0]["card_id"] == "aboleth"
        assert notes[0]["scenario_file"] == saved[0].name
