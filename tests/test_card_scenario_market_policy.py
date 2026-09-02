"""Property tests for the two-deck market policy in card scenario generation."""

from __future__ import annotations

from game_setup.market_setup import SPECIAL_RECRUIT_IDS, compute_special_stacks
from game_setup.scenario_generation.rosters import (
    DEFAULT_ROSTERS_PATH,
    _resolve_two_deck_pairing,
    iter_roster_card_ids,
)


def _present_cards(special_stacks) -> set[str]:
    return {spec.card_id for spec in special_stacks}


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


def test_demons_gates_insane_outcast_slot() -> None:
    for card_id in ("aboleth", "noble", "soldier"):
        _roster_a_id, _roster_b_id, special_stacks = _resolve_two_deck_pairing(
            rosters_path=DEFAULT_ROSTERS_PATH,
            target_card_id=card_id,
            base_seed=0,
        )
        present = _present_cards(special_stacks)
        assert "house_guard" in present
        assert "priestess_of_lolth" in present

    # Demons in the market ⇒ the insane stack is present.
    demons_present = _present_cards(
        compute_special_stacks("demons", "elementals", decks_dir=DEFAULT_ROSTERS_PATH)
    )
    assert "insane_outcast" in demons_present

    # Aberrations (non-demons) in the market ⇒ the insane stack is absent.
    aberrations_present = _present_cards(
        compute_special_stacks("aberrations", "drow", decks_dir=DEFAULT_ROSTERS_PATH)
    )
    assert "insane_outcast" not in aberrations_present


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
