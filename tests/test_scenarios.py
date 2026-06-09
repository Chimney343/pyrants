"""Scenario save/load tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from engine.moves import PlayCardMove, ResolveGenericChoiceMove
from engine.rules import apply, legal_moves
from game_session import GameSession
from game_setup.loaders import load_card_catalog
from game_setup.scenarios import (
    CatalogVersionMismatchError,
    Scenario,
    ScenarioMetadata,
    load_game_state_from_scenario,
    load_scenario,
    save_game_state,
    save_scenario,
)

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _catalog_registry() -> dict[str, object]:
    catalog = load_card_catalog(CARD_PATH)
    return {catalog.catalog_id: catalog}


def _session(seed: int = 41) -> GameSession:
    return GameSession.from_files(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        player_ids=["p1", "p2"],
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Scenario metadata
# ---------------------------------------------------------------------------


def test_scenario_metadata_round_trip_via_json() -> None:
    meta = ScenarioMetadata(
        scenario_id="test_scenario",
        description="A test scenario",
        tags=["cards", "resume"],
        card_under_test="aboleth",
        source_board_id="Tyrants of the Underdark",
        source_catalog_id="base_catalog",
        source_setup_id="base_setup",
        move_count=5,
        is_terminal=False,
    )
    round_tripped = ScenarioMetadata.model_validate(meta.model_dump(mode="json"))
    assert round_tripped == meta


# ---------------------------------------------------------------------------
# GameState JSON round-trip
# ---------------------------------------------------------------------------


def test_game_state_json_round_trip() -> None:
    session = _session(seed=13)
    original = session.state

    payload = original.model_dump(mode="json")
    reconstructed = original.__class__.model_validate(payload)

    assert reconstructed.current_player_id == original.current_player_id
    assert reconstructed.phase == original.phase
    assert reconstructed.turn_order == original.turn_order
    assert set(reconstructed.players.keys()) == set(original.players.keys())
    assert len(reconstructed.market.row) == len(original.market.row)
    assert reconstructed.market.deck == original.market.deck
    assert reconstructed.round_number == original.round_number
    assert reconstructed.resource_pool.power == original.resource_pool.power
    assert reconstructed.resource_pool.influence == original.resource_pool.influence

    for player_id in original.players:
        orig_player = original.players[player_id]
        recon_player = reconstructed.players[player_id]
        assert recon_player.hand == orig_player.hand
        assert recon_player.deck == orig_player.deck
        assert recon_player.discard_pile == orig_player.discard_pile
        assert recon_player.barracks == orig_player.barracks
        assert recon_player.spies_available == orig_player.spies_available


def test_game_state_round_trip_preserves_spies() -> None:
    session = _session(seed=13)
    original = session.state
    updated = original.model_copy(deep=True)
    updated.board.nodes["site_gauntlgrym"].spies = {"p1", "p2"}

    payload = updated.model_dump(mode="json")
    reconstructed = updated.__class__.model_validate(payload)

    assert reconstructed.board.nodes["site_gauntlgrym"].spies == {"p1", "p2"}


def test_game_state_round_trip_preserves_troop_slots() -> None:
    session = _session(seed=13)
    original = session.state
    updated = original.model_copy(deep=True)
    updated.board.nodes["site_gauntlgrym"].troop_slots = ["p1", None, "p2"]

    payload = updated.model_dump(mode="json")
    reconstructed = updated.__class__.model_validate(payload)

    assert reconstructed.board.nodes["site_gauntlgrym"].troop_slots == ["p1", None, "p2"]


# ---------------------------------------------------------------------------
# Scenario save/load to file
# ---------------------------------------------------------------------------


def test_save_and_load_scenario_file() -> None:
    session = _session(seed=13)
    scenario = Scenario.from_game_state(
        session.state,
        scenario_id="my_scenario",
        description="Test scenario",
        tags=["cards"],
        card_under_test="bounty_hunter",
        move_count=0,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_scenario.json"
        save_scenario(scenario, path)

        loaded = load_scenario(path)

    assert loaded.metadata.scenario_id == "my_scenario"
    assert loaded.metadata.description == "Test scenario"
    assert loaded.metadata.card_under_test == "bounty_hunter"
    assert loaded.metadata.move_count == 0
    assert loaded.metadata.is_terminal is False

    state = loaded.to_game_state(catalog_registry=_catalog_registry())
    assert state.current_player_id == session.state.current_player_id
    assert set(state.players.keys()) == set(session.state.players.keys())


def test_save_game_state_convenience() -> None:
    session = _session(seed=13)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "convenience_scenario.json"
        save_game_state(
            session.state,
            path,
            scenario_id="conv_test",
            description="Convenience test",
        )

        state_from_file = load_game_state_from_scenario(path, catalog_registry=_catalog_registry())

    assert state_from_file.current_player_id == session.state.current_player_id


# ---------------------------------------------------------------------------
# Load-and-continue session
# ---------------------------------------------------------------------------


def test_resume_session_from_saved_state() -> None:
    session = _session(seed=13)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "resume_scenario.json"
        save_game_state(session.state, path, scenario_id="resume_test")

        resumed_session = GameSession.from_scenario_file(path)

    assert resumed_session.state.current_player_id == session.state.current_player_id
    assert resumed_session.move_count == 0
    assert not resumed_session.is_terminal()

    legal = resumed_session.legal_moves()
    assert any(isinstance(move, PlayCardMove) for move in legal)


def test_resume_after_moves_continues_correctly() -> None:
    session = _session(seed=13)

    move = next(move for move in session.legal_moves() if isinstance(move, PlayCardMove))
    session.submit_move(move)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "mid_turn_scenario.json"
        save_game_state(session.state, path, scenario_id="mid_turn", move_count=1)

        resumed = GameSession.from_scenario_file(path)

    assert resumed.move_count == 0
    assert resumed.state.players["p1"].played_cards.count(move.card_id) == 1
    assert len(resumed.state.players["p1"].hand) == 4

    legal_after = resumed.legal_moves()
    assert any(isinstance(m, PlayCardMove) for m in legal_after)


# ---------------------------------------------------------------------------
# Pending choice state reload
# ---------------------------------------------------------------------------


def test_reload_state_with_pending_generic_choice() -> None:
    session = _session(seed=31)
    state = session.state.model_copy(deep=True)
    state.players["p1"].hand = ["enchanter_of_thay"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.board.nodes["site_gauntlgrym"].spies.add("p1")

    played = apply(state, PlayCardMove(player_id="p1", card_id="enchanter_of_thay", hand_index=0))

    assert played.pending_generic_choice is not None

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "pending_choice_scenario.json"
        save_game_state(played, path, scenario_id="pending_choice")

        restored = load_game_state_from_scenario(path, catalog_registry=_catalog_registry())

    assert restored.pending_generic_choice is not None
    assert restored.pending_generic_choice.source_card_id == "enchanter_of_thay"
    assert restored.pending_generic_choice.execution_kind == "repeat_choice"

    option_ids = {m.option_id for m in legal_moves(restored) if isinstance(m, ResolveGenericChoiceMove)}
    assert {"option_1", "option_2"}.issubset(option_ids)


def test_reload_state_preserves_market_deck_and_row() -> None:
    session = _session(seed=13)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "market_scenario.json"
        save_game_state(session.state, path, scenario_id="market_check")

        restored = load_game_state_from_scenario(path, catalog_registry=_catalog_registry())

    assert restored.market.row == session.state.market.row
    assert restored.market.deck == session.state.market.deck
    assert restored.market.discard_pile == session.state.market.discard_pile


def test_reload_preserves_inner_circle_and_trophy_hall() -> None:
    session = _session(seed=13)
    state = session.state.model_copy(deep=True)
    state.players["p1"].inner_circle = ["noble", "soldier"]
    state.players["p1"].trophy_hall = ["enemy_troop"]

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "zones_scenario.json"
        save_game_state(state, path, scenario_id="zones_check")

        restored = load_game_state_from_scenario(path, catalog_registry=_catalog_registry())

    assert restored.players["p1"].inner_circle == ["noble", "soldier"]
    assert restored.players["p1"].trophy_hall == ["enemy_troop"]


def test_reload_preserves_shuffle_metadata() -> None:
    session = _session(seed=42)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "shuffle_scenario.json"
        save_game_state(session.state, path, scenario_id="shuffle_check")

        restored = load_game_state_from_scenario(path, catalog_registry=_catalog_registry())

    assert restored.shuffle_seed == session.state.shuffle_seed
    assert restored.shuffle_count == session.state.shuffle_count


# ---------------------------------------------------------------------------
# Canonical scenario fixtures
# ---------------------------------------------------------------------------

SCENARIOS_DIR = BASE_DIR / "data" / "scenarios"


@pytest.mark.parametrize(
    "filename",
    [
        "initial_two_player.json",
        "mid_turn_two_player.json",
        "pending_modal_choice.json",
        "scoring_test.json",
    ],
)
def test_canonical_scenario_loads(filename: str) -> None:
    path = SCENARIOS_DIR / filename
    scenario = load_scenario(path)

    assert scenario.metadata.scenario_id
    assert scenario.metadata.description

    state = scenario.to_game_state(catalog_registry=_catalog_registry())
    assert state.current_player_id in state.players
    assert len(state.turn_order) >= 2


def test_canonical_initial_scenario_is_fresh() -> None:
    state = load_game_state_from_scenario(SCENARIOS_DIR / "initial_two_player.json", catalog_registry=_catalog_registry())
    assert state.phase.value == "main"
    assert len(state.players["p1"].hand) == 5
    assert len(state.market.row) == 6
    assert state.round_number == 1


def test_canonical_mid_turn_has_played_card() -> None:
    state = load_game_state_from_scenario(SCENARIOS_DIR / "mid_turn_two_player.json", catalog_registry=_catalog_registry())
    assert len(state.players["p1"].played_cards) >= 1
    assert len(state.players["p1"].hand) == 4


def test_canonical_pending_modal_choice_has_both_options() -> None:
    state = load_game_state_from_scenario(SCENARIOS_DIR / "pending_modal_choice.json", catalog_registry=_catalog_registry())
    assert state.pending_generic_choice is not None
    assert state.pending_generic_choice.source_card_id == "enchanter_of_thay"

    option_ids = {
        m.option_id for m in legal_moves(state) if isinstance(m, ResolveGenericChoiceMove)
    }
    assert {"option_1", "option_2"}.issubset(option_ids)


def test_canonical_scoring_state_has_control() -> None:
    state = load_game_state_from_scenario(SCENARIOS_DIR / "scoring_test.json", catalog_registry=_catalog_registry())
    assert len(state.players["p1"].inner_circle) == 3
    assert len(state.players["p1"].trophy_hall) == 3
    assert len(state.players["p2"].inner_circle) == 2
    assert state.board.nodes["site_gauntlgrym"].troop_slots == ["p1", "p1", "p1"]


# ---------------------------------------------------------------------------
# Catalog deduplication tests
# ---------------------------------------------------------------------------


def test_save_strips_catalog_from_payload() -> None:
    session = _session(seed=13)
    scenario = Scenario.from_game_state(session.state, scenario_id="strip_test")
    payload = scenario.state_payload
    assert "catalog" not in payload.get("definition", {})


def test_save_records_catalog_version() -> None:
    session = _session(seed=13)
    scenario = Scenario.from_game_state(session.state, scenario_id="version_test")
    assert scenario.metadata.source_catalog_version == "1.0.0"
    assert scenario.metadata.source_catalog_id == "base_catalog"


def test_load_with_registry_rehydrates_catalog() -> None:
    session = _session(seed=13)
    scenario = Scenario.from_game_state(session.state, scenario_id="rehydrate_test")
    state = scenario.to_game_state(catalog_registry=_catalog_registry())
    assert state.definition.catalog.catalog_id == "base_catalog"
    assert state.definition.catalog.version == "1.0.0"
    assert len(state.definition.catalog.cards) == 125


def test_load_with_matching_version_succeeds() -> None:
    session = _session(seed=13)
    scenario = Scenario.from_game_state(session.state, scenario_id="match_test")
    state = scenario.to_game_state(catalog_registry=_catalog_registry())
    assert state.current_player_id == session.state.current_player_id


def test_load_with_mismatched_version_raises() -> None:
    session = _session(seed=13)
    catalog = load_card_catalog(CARD_PATH)
    catalog_bumped = catalog.model_copy(update={"version": "1.1.0"})
    bumped_registry: dict[str, object] = {catalog_bumped.catalog_id: catalog_bumped}

    scenario = Scenario.from_game_state(session.state, scenario_id="mismatch_test")
    with pytest.raises(CatalogVersionMismatchError, match="1\\.0\\.0.*1\\.1\\.0"):
        scenario.to_game_state(catalog_registry=bumped_registry)


def test_load_with_force_overrides_version_mismatch() -> None:
    session = _session(seed=13)
    catalog = load_card_catalog(CARD_PATH)
    catalog_bumped = catalog.model_copy(update={"version": "1.1.0"})
    bumped_registry: dict[str, object] = {catalog_bumped.catalog_id: catalog_bumped}

    scenario = Scenario.from_game_state(session.state, scenario_id="force_test")
    state = scenario.to_game_state(catalog_registry=bumped_registry, force=True)
    assert state.definition.catalog.version == "1.1.0"


def test_save_file_size_drops_significantly() -> None:
    import json

    session = _session(seed=13)
    legacy_payload = session.state.model_dump(mode="json")
    legacy_size = len(json.dumps(legacy_payload))

    scenario = Scenario.from_game_state(session.state, scenario_id="size_test")
    new_payload = scenario.model_dump(mode="json")
    new_size = len(json.dumps(new_payload))

    reduction = (legacy_size - new_size) / legacy_size
    assert reduction > 0.5, f"Expected >50% reduction, got {reduction:.1%}"


def test_legacy_save_with_embedded_catalog_raises_clear_error() -> None:
    import json

    session = _session(seed=13)
    legacy_payload = session.state.model_dump(mode="json")
    legacy_scenario_payload = {
        "metadata": {
            "scenario_id": "legacy_test",
            "description": "legacy embedded catalog",
            "tags": [],
            "card_under_test": None,
            "source_board_id": "Tyrants of the Underdark",
            "source_catalog_id": "base_catalog",
            "source_catalog_version": "1.0.0",
            "source_setup_id": "base_setup",
            "move_count": 0,
            "is_terminal": False,
        },
        "state_payload": legacy_payload,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "legacy_scenario.json"
        path.write_text(json.dumps(legacy_scenario_payload, indent=2), encoding="utf-8")

        with pytest.raises(ValueError, match="catalog"):
            load_game_state_from_scenario(path, catalog_registry=_catalog_registry())
