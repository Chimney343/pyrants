"""Core rules behavior tests for known implemented surfaces."""

from __future__ import annotations

from pathlib import Path

from engine.generic_runtime._utils import _action_requires_selection
from engine.moves import (
    EndMainPhaseMove,
    PlayCardMove,
    PromoteCardMove,
    ResolveGenericChoiceMove,
    SkipPromoteMove,
)
from engine.rules import apply, legal_moves
from engine.state import PendingPromotionState, TurnPhase, build_initial_game_state
from game_setup.loaders import build_game_definition_from_dicts, create_game_state_from_files
from tests.scenario_helpers import advance_past_setup

BASE_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = BASE_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _base_state(seed: int = 11):
    return advance_past_setup(
        create_game_state_from_files(BOARD_PATH, CARD_PATH, SETUP_PATH, ["p1", "p2"], seed=seed)
    )


def _ability_state(cards: list[dict[str, object]], starter_entries: list[dict[str, object]]) -> object:
    board_data = {
        "board_id": "ability_test_board",
        "nodes": [
            {
                "node_id": "site_a",
                "kind": "site",
                "adjacent_to": [],
                "troop_capacity": 3,
                "vp_value": 0,
                "initial_vp_tokens": 0,
            }
        ],
    }
    card_data = {"catalog_id": "ability_test_catalog", "version": "1.0.0", "cards": cards}
    setup_data = {
        "setup_id": "ability_test_setup",
        "starter_deck": {"deck_id": "starter", "entries": starter_entries},
        "market_deck": {"deck_id": "market", "entries": []},
        "market_row_size": 1,
    }

    definition = build_game_definition_from_dicts(board_data, card_data, setup_data, definition_id="ability_test")
    return advance_past_setup(build_initial_game_state(definition, ["p1", "p2"], shuffle_seed=0))


def test_immediate_optional_promote_blocks_further_play_until_resolved() -> None:
    cards = [
        {
            "card_id": "optional_promote",
            "name": "Optional Promote",
            "cost": 0,
            "aspect": "none",
            "deck_vp": 0,
            "inner_circle_vp": 1,
            "effect_key": "noop",
            "effect_payload": {"promote": {"timing": "immediate", "optional": True}},
        },
        {
            "card_id": "filler",
            "name": "Filler",
            "cost": 0,
            "aspect": "none",
            "deck_vp": 0,
            "inner_circle_vp": 0,
            "effect_key": "noop",
            "effect_payload": {},
        },
    ]
    state = _ability_state(cards, [{"card_id": "optional_promote", "count": 1}, {"card_id": "filler", "count": 1}])
    state.players["p1"].hand = ["optional_promote", "filler"]
    state.players["p1"].deck = []

    played = apply(
        state,
        PlayCardMove(player_id="p1", card_id="optional_promote", hand_index=0),
    )

    assert len(played.pending_immediate_promotions) == 1
    assert all(not isinstance(move, PlayCardMove) for move in legal_moves(played))

    promoted = apply(
        played,
        PromoteCardMove(player_id="p1", card_id="optional_promote"),
    )

    assert promoted.pending_immediate_promotions == []
    assert promoted.players["p1"].inner_circle == ["optional_promote"]
    assert "optional_promote" not in promoted.players["p1"].played_cards



def test_end_of_turn_mandatory_promote_moves_card_to_inner_circle() -> None:
    cards = [
        {
            "card_id": "end_promote",
            "name": "End Promote",
            "cost": 0,
            "aspect": "none",
            "deck_vp": 0,
            "inner_circle_vp": 1,
            "effect_key": "noop",
            "effect_payload": {"promote": {"timing": "end_of_turn", "optional": False}},
        }
    ]
    state = _ability_state(cards, [{"card_id": "end_promote", "count": 1}])
    state.players["p1"].hand = ["end_promote"]
    state.players["p1"].deck = []

    played = apply(
        state,
        PlayCardMove(player_id="p1", card_id="end_promote", hand_index=0),
    )
    end_of_turn = apply(played, EndMainPhaseMove(player_id="p1"))

    assert end_of_turn.phase == TurnPhase.END_OF_TURN
    assert end_of_turn.players["p1"].inner_circle == ["end_promote"]
    assert "end_promote" not in end_of_turn.players["p1"].played_cards



def test_end_main_phase_skips_stale_mandatory_promotions() -> None:
    state = _base_state(seed=37)
    updated = state.model_copy(deep=True)
    updated.players["p1"].played_cards = []
    updated.pending_end_of_turn_promotions = [
        PendingPromotionState(card_id="noble", timing="end_of_turn", optional=False)
    ]

    end_of_turn = apply(updated, EndMainPhaseMove(player_id="p1"))

    assert end_of_turn.phase == TurnPhase.END_OF_TURN
    assert end_of_turn.pending_end_of_turn_promotions == []



def test_all_end_of_turn_promote_actions_use_deferred_target_selection_policy() -> None:
    state = _base_state(seed=43)
    actions = [
        action
        for card in state.definition.catalog.cards
        for action in card.actions
        if action.op == "promote_card" and action.timing == "end_of_turn"
    ]

    assert actions
    assert all(_action_requires_selection(action) is False for action in actions)



def test_revenant_threshold_self_promote_triggers_at_eight_trophies() -> None:
    state = _base_state(seed=806).model_copy(deep=True)
    state.players["p1"].hand = ["revenant"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].trophy_hall = ["white", "white", "white", "white", "p2", "p2", "p2", "p2"]
    state.players["p1"].barracks = 5
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p1", "p2", "p2"]

    played = apply(state, PlayCardMove(player_id="p1", card_id="revenant", hand_index=0))
    first = apply(
        played,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="revenant",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 1},
        ),
    )
    resolved = apply(
        first,
        ResolveGenericChoiceMove(
            player_id="p1",
            source_card_id="revenant",
            selection={"target_node_id": "site_gauntlgrym", "target_slot_index": 2},
        ),
    )

    assert "revenant" in resolved.players["p1"].inner_circle
    assert "revenant" not in resolved.players["p1"].played_cards



def test_blue_dragon_awards_scaled_vp_after_end_of_turn_promotions() -> None:
    state = _base_state(seed=807).model_copy(deep=True)
    state.players["p1"].hand = ["blue_dragon", "noble", "soldier"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].inner_circle = ["noble", "soldier", "house_guard", "priestess_of_lolth"]
    state.players["p1"].score = 0

    after_dragon = apply(state, PlayCardMove(player_id="p1", card_id="blue_dragon", hand_index=0))
    after_noble = apply(after_dragon, PlayCardMove(player_id="p1", card_id="noble", hand_index=0))
    after_soldier = apply(after_noble, PlayCardMove(player_id="p1", card_id="soldier", hand_index=0))

    end_of_turn = apply(after_soldier, EndMainPhaseMove(player_id="p1"))
    first_promote = apply(end_of_turn, PromoteCardMove(player_id="p1", card_id="noble"))
    second_promote = apply(first_promote, PromoteCardMove(player_id="p1", card_id="soldier"))
    score_before_resolve = second_promote.players["p1"].score
    resolve_move = next(move for move in legal_moves(second_promote) if move.move_type == "resolve_end_of_turn")
    resolved = apply(second_promote, resolve_move)

    assert resolved.players["p1"].score >= score_before_resolve + 2



def test_high_priest_of_myrkul_promotes_any_number_of_undead_played_cards() -> None:
    state = _base_state(seed=808).model_copy(deep=True)
    state.players["p1"].hand = ["high_priest_of_myrkul", "ogre_zombie", "noble"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []
    state.players["p1"].barracks = 5
    state.board.nodes["site_gauntlgrym"].troop_slots = ["p2", None, None]
    state.board.nodes["site_blingdenfire"].troop_slots = ["white", None, None]

    after_priest = apply(state, PlayCardMove(player_id="p1", card_id="high_priest_of_myrkul", hand_index=0))
    return_move = next(
        move
        for move in legal_moves(after_priest)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "high_priest_of_myrkul"
        and move.selection.get("unit_type") == "troop"
    )
    after_return = apply(after_priest, return_move)
    after_ogre = apply(after_return, PlayCardMove(player_id="p1", card_id="ogre_zombie", hand_index=0))
    ogre_supplant = next(
        move
        for move in legal_moves(after_ogre)
        if isinstance(move, ResolveGenericChoiceMove)
        and move.source_card_id == "ogre_zombie"
    )
    after_ogre_resolved = apply(after_ogre, ogre_supplant)
    after_noble = apply(after_ogre_resolved, PlayCardMove(player_id="p1", card_id="noble", hand_index=0))

    end_of_turn = apply(after_noble, EndMainPhaseMove(player_id="p1"))
    promote_moves = [move for move in legal_moves(end_of_turn) if isinstance(move, PromoteCardMove)]
    assert {move.card_id for move in promote_moves} == {"ogre_zombie"}

    promoted = apply(end_of_turn, PromoteCardMove(player_id="p1", card_id="ogre_zombie"))
    assert "ogre_zombie" in promoted.players["p1"].inner_circle
    assert "noble" in promoted.players["p1"].played_cards
    assert promoted.pending_end_of_turn_promotions == []



def test_ogremoch_grants_second_end_of_turn_promote_when_focus_met() -> None:
    state = _base_state(seed=809).model_copy(deep=True)
    state.players["p1"].hand = ["ogremoch", "ambassador", "noble", "soldier"]
    state.players["p1"].deck = []
    state.players["p1"].discard_pile = []
    state.players["p1"].played_cards = []

    after_ogremoch = apply(state, PlayCardMove(player_id="p1", card_id="ogremoch", hand_index=0))
    after_noble = apply(after_ogremoch, PlayCardMove(player_id="p1", card_id="noble", hand_index=1))
    after_soldier = apply(after_noble, PlayCardMove(player_id="p1", card_id="soldier", hand_index=1))

    end_of_turn = apply(after_soldier, EndMainPhaseMove(player_id="p1"))
    first = apply(end_of_turn, PromoteCardMove(player_id="p1", card_id="noble"))
    second = apply(first, PromoteCardMove(player_id="p1", card_id="soldier"))

    assert "noble" in second.players["p1"].inner_circle
    assert "soldier" in second.players["p1"].inner_circle



def test_ambassador_promotion_target_is_chosen_in_end_of_turn_phase() -> None:
    state = _base_state(seed=41)
    updated = state.model_copy(deep=True)
    updated.players["p1"].hand = ["ambassador", "noble"]
    updated.players["p1"].played_cards = []
    updated.players["p1"].deck = []

    after_ambassador = apply(
        updated,
        PlayCardMove(player_id="p1", card_id="ambassador", hand_index=0),
    )

    assert after_ambassador.pending_generic_choice is None
    assert len(after_ambassador.pending_end_of_turn_promotions) == 1
    pending = after_ambassador.pending_end_of_turn_promotions[0]
    assert pending.deferred_choice
    assert pending.requires_another_played_card

    after_second_card = apply(
        after_ambassador,
        PlayCardMove(player_id="p1", card_id="noble", hand_index=0),
    )
    end_of_turn = apply(after_second_card, EndMainPhaseMove(player_id="p1"))

    assert end_of_turn.phase == TurnPhase.END_OF_TURN
    end_moves = legal_moves(end_of_turn)
    promote_targets = [move.card_id for move in end_moves if isinstance(move, PromoteCardMove)]
    assert "noble" in promote_targets
    assert "ambassador" not in promote_targets

    promoted = apply(end_of_turn, PromoteCardMove(player_id="p1", card_id="noble"))

    assert "noble" in promoted.players["p1"].inner_circle
    assert "noble" not in promoted.players["p1"].played_cards
    assert promoted.pending_end_of_turn_promotions == []
    assert any(move.move_type == "resolve_end_of_turn" for move in legal_moves(promoted))



def test_ambassador_with_no_other_played_card_does_not_soft_lock() -> None:
    state = _base_state(seed=31)
    updated = state.model_copy(deep=True)
    updated.players["p1"].hand = ["ambassador"]
    updated.players["p1"].played_cards = []
    updated.players["p1"].deck = []

    played = apply(
        updated,
        PlayCardMove(player_id="p1", card_id="ambassador", hand_index=0),
    )

    assert played.pending_generic_choice is None
    assert len(played.pending_end_of_turn_promotions) == 1
    assert played.pending_end_of_turn_promotions[0].deferred_choice
    assert any(isinstance(move, EndMainPhaseMove) for move in legal_moves(played))

    end_of_turn = apply(played, EndMainPhaseMove(player_id="p1"))
    end_moves = legal_moves(end_of_turn)
    assert any(isinstance(move, SkipPromoteMove) for move in end_moves)


