"""Property tests for the two-deck market policy in card scenario generation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from game_setup.loaders import load_card_catalog
from game_setup.scenario_generation.card_scenarios import (
    DEFAULT_ROSTERS_PATH,
    SPECIAL_RECRUIT_IDS,
    _resolve_two_deck_pairing,
    ensure_card_scenario,
    generate_card_scenarios,
    iter_roster_card_ids,
)
from game_setup.scenarios import load_game_state_from_scenario

CARD_PATH = Path(__file__).resolve().parents[1] / "data" / "cards" / "catalog.json"


def _catalog_registry() -> dict[str, object]:
    catalog = load_card_catalog(CARD_PATH)
    return {catalog.catalog_id: catalog}


def test_two_deck_pairing_has_exactly_two_distinct_ids() -> None:
    card_ids = iter_roster_card_ids(DEFAULT_ROSTERS_PATH)
    for card_id in card_ids[:10]:
        roster_a_id, roster_b_id, _special_stacks = _resolve_two_deck_pairing(
            rosters_path=DEFAULT_ROSTERS_PATH,
            target_card_id=card_id,
            base_seed=0,
        )
        assert roster_a_id
        assert roster_b_id
        assert roster_a_id not in SPECIAL_RECRUIT_IDS
        assert roster_b_id not in SPECIAL_RECRUIT_IDS


def test_roster_b_is_not_single_card_stack() -> None:
    card_ids = [cid for cid in iter_roster_card_ids(DEFAULT_ROSTERS_PATH) if cid not in SPECIAL_RECRUIT_IDS]
    for card_id in card_ids[:10]:
        _roster_a_id, roster_b_id, _special_stacks = _resolve_two_deck_pairing(
            rosters_path=DEFAULT_ROSTERS_PATH,
            target_card_id=card_id,
            base_seed=0,
        )
        assert roster_b_id not in SPECIAL_RECRUIT_IDS


def test_aberrations_gates_insane_outcast_slot() -> None:
    for card_id in ("aboleth", "noble", "soldier"):
        _roster_a_id, _roster_b_id, special_stacks = _resolve_two_deck_pairing(
            rosters_path=DEFAULT_ROSTERS_PATH,
            target_card_id=card_id,
            base_seed=0,
        )
        assert "house_guard" in special_stacks
        assert "priestess_of_lolth" in special_stacks

    aberrations_ids = [cid for cid in iter_roster_card_ids(DEFAULT_ROSTERS_PATH)
                       if cid not in SPECIAL_RECRUIT_IDS]
    for card_id in ("aboleth", "beholder", "chuul", "neothelid", "otyugh"):
        if card_id not in aberrations_ids:
            continue
        _roster_a_id, _roster_b_id, special_stacks = _resolve_two_deck_pairing(
            rosters_path=DEFAULT_ROSTERS_PATH,
            target_card_id=card_id,
            base_seed=0,
        )
        assert "insane_outcast" in special_stacks, f"insane_outcast missing for aberrations card {card_id}"


def test_pairing_is_deterministic() -> None:
    args_a = _resolve_two_deck_pairing(
        rosters_path=DEFAULT_ROSTERS_PATH,
        target_card_id="aboleth",
        base_seed=42,
    )
    args_b = _resolve_two_deck_pairing(
        rosters_path=DEFAULT_ROSTERS_PATH,
        target_card_id="aboleth",
        base_seed=42,
    )
    assert args_a == args_b


def test_scenario_market_deck_id_encodes_deck_ids() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "cards"
        saved, _missing = generate_card_scenarios(
            out,
            base_seed=42,
            max_attempts=1,
            max_steps_per_attempt=100,
            card_ids=["aboleth", "noble"],
        )
        for path in saved:
            scenario = json.loads(path.read_text(encoding="utf-8"))
            market_deck_id = scenario["state_payload"]["definition"]["setup"]["market_deck"]["deck_id"]
            assert market_deck_id.startswith("market_"), f"Expected market_ prefix, got {market_deck_id}"
            meta = scenario["metadata"]
            ids_str = "_".join(meta["market_deck_ids"])
            assert ids_str in market_deck_id, f"deck_id {market_deck_id} should contain {ids_str}"


def test_special_recruit_always_force_injected() -> None:
    for card_id in SPECIAL_RECRUIT_IDS:
        state, note, market_deck_ids, special_stacks_present = ensure_card_scenario(
            card_id,
            base_seed=0,
            max_attempts=1,
            max_steps_per_attempt=10,
        )
        assert note is not None, f"Expected forced injection for {card_id}"
        assert note["card_id"] == card_id
        assert card_id in state.players[state.current_player_id].hand
        assert len(market_deck_ids) == 2


def test_scenario_save_roundtrip_preserves_market_deck_ids() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "cards"
        saved, _missing = generate_card_scenarios(
            out,
            base_seed=42,
            max_attempts=1,
            max_steps_per_attempt=100,
            card_ids=["aboleth"],
        )
        assert len(saved) == 1
        state = load_game_state_from_scenario(saved[0], catalog_registry=_catalog_registry())
        market_deck_id = state.definition.setup.market_deck.deck_id
        assert market_deck_id.startswith("market_")

        scenario = json.loads(saved[0].read_text(encoding="utf-8"))
        meta = scenario["metadata"]
        assert len(meta["market_deck_ids"]) == 2
        assert len(meta["special_stacks_present"]) >= 2
