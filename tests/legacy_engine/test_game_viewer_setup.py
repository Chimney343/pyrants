"""Tests for hotseat setup selection helpers in game_viewer."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from engine.moves import (
    HOUSE_GUARD_RECRUIT_SLOT,
    INSANE_OUTCAST_RECRUIT_SLOT,
    PRIESTESS_RECRUIT_SLOT,
    InitialPlacementMove,
    RecruitMove,
)
from engine.rules import legal_moves
from engine.state import TurnPhase
from interface.game_viewer import (
    ABERRATIONS_DECK_ID,
    build_setup_from_market_selection,
    create_hotseat_session,
    discover_map_profiles,
    format_discard_pile_options,
    format_ordered_card_options,
    format_trophy_hall_options,
    load_market_deck_profiles,
)

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
BOARD_PATH = DATA_DIR / "boards" / "tyrants_of_the_underdark.json"
LAYOUT_PATH = DATA_DIR / "layouts" / "tyrants_of_the_underdark_layout.json"
CARD_PATH = DATA_DIR / "cards" / "catalog.json"
SETUP_PATH = DATA_DIR / "decks" / "base_setup.json"
DECKS_DIR = DATA_DIR / "decks"


def _resolve_session_setup(session) -> None:
    from engine.helpers import _legal_initial_placement_node_ids

    while session.state.phase == TurnPhase.SETUP:
        node_ids = _legal_initial_placement_node_ids(session.state)
        move = InitialPlacementMove(
            player_id=session.state.current_player_id,
            target_node_id=node_ids[0],
        )
        session.submit_move(move)


def test_discover_map_profiles_includes_default_pair() -> None:
    profiles = discover_map_profiles(
        DATA_DIR,
        default_board_path=BOARD_PATH,
        default_layout_path=LAYOUT_PATH,
    )

    assert profiles
    assert any(profile.board_path == BOARD_PATH and profile.layout_path == LAYOUT_PATH for profile in profiles)


def test_load_market_deck_profiles_reads_full_40_card_decks() -> None:
    profiles = load_market_deck_profiles(DECKS_DIR)

    assert len(profiles) >= 2
    assert all(profile.total_cards == 40 for profile in profiles)


def test_build_setup_from_market_selection_combines_two_decks() -> None:
    deck_profiles = load_market_deck_profiles(DECKS_DIR)
    setup = build_setup_from_market_selection(
        SETUP_PATH,
        deck_a=deck_profiles[0],
        deck_b=deck_profiles[1],
    )

    market_deck = setup["market_deck"]
    assert isinstance(market_deck, dict)
    entries = market_deck["entries"]
    assert isinstance(entries, list)

    total_count = sum(entry["count"] for entry in entries)
    assert total_count == 80
    assert all(entry["card_id"] != "placeholder_assassinate" for entry in entries)


def test_create_hotseat_session_uses_selected_market_decks() -> None:
    deck_profiles = load_market_deck_profiles(DECKS_DIR)
    session = create_hotseat_session(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        deck_a=deck_profiles[0],
        deck_b=deck_profiles[1],
        player_count=3,
        seed=9,
    )

    state = session.state
    assert len(state.turn_order) == 3
    assert len(state.market.row) == state.definition.setup.market_row_size
    assert len(state.market.row) + len(state.market.deck) == 80


def test_special_recruit_slots_include_house_guard_and_priestess() -> None:
    deck_profiles = load_market_deck_profiles(DECKS_DIR)
    deck_a = next(profile for profile in deck_profiles if profile.deck_id != ABERRATIONS_DECK_ID)
    deck_b = next(
        profile
        for profile in deck_profiles
        if profile.deck_id not in {ABERRATIONS_DECK_ID, deck_a.deck_id}
    )
    session = create_hotseat_session(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        deck_a=deck_a,
        deck_b=deck_b,
        player_count=2,
        seed=11,
    )

    _resolve_session_setup(session)
    session.state.resource_pool.influence = 3
    recruit_slots = {
        move.market_slot
        for move in legal_moves(session.state)
        if isinstance(move, RecruitMove)
    }

    assert HOUSE_GUARD_RECRUIT_SLOT in recruit_slots
    assert PRIESTESS_RECRUIT_SLOT in recruit_slots
    assert INSANE_OUTCAST_RECRUIT_SLOT not in recruit_slots


def test_special_recruit_slots_include_outcasts_with_aberrations_market() -> None:
    deck_profiles = load_market_deck_profiles(DECKS_DIR)
    deck_a = next(profile for profile in deck_profiles if profile.deck_id == ABERRATIONS_DECK_ID)
    deck_b = next(profile for profile in deck_profiles if profile.deck_id != ABERRATIONS_DECK_ID)
    session = create_hotseat_session(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        deck_a=deck_a,
        deck_b=deck_b,
        player_count=2,
        seed=11,
    )

    _resolve_session_setup(session)
    session.state.resource_pool.influence = 3
    recruit_slots = {
        move.market_slot
        for move in legal_moves(session.state)
        if isinstance(move, RecruitMove)
    }

    assert INSANE_OUTCAST_RECRUIT_SLOT in recruit_slots


def test_format_discard_pile_options_includes_names_and_quantities() -> None:
    cards_by_id = {
        "noble": SimpleNamespace(name="Noble"),
        "soldier": SimpleNamespace(name="Soldier"),
    }

    options = format_discard_pile_options(["soldier", "noble", "soldier"], cards_by_id)

    assert options == ["Noble x1", "Soldier x2"]


def test_format_discard_pile_options_empty_returns_placeholder() -> None:
    options = format_discard_pile_options([], {})

    assert options == ["(empty)"]


def test_format_ordered_card_options_keeps_zone_order_with_indices() -> None:
    cards_by_id = {
        "noble": SimpleNamespace(name="Noble"),
        "soldier": SimpleNamespace(name="Soldier"),
    }

    options = format_ordered_card_options(["soldier", "noble", "soldier"], cards_by_id)

    assert options == [
        "1. Soldier",
        "2. Noble",
        "3. Soldier",
    ]


def test_format_ordered_card_options_falls_back_to_unknown_card_when_missing_definition() -> None:
    options = format_ordered_card_options(["unknown_card"], {})

    assert options == ["1. Unknown Card"]


def test_format_ordered_card_options_empty_returns_placeholder() -> None:
    options = format_ordered_card_options([], {})

    assert options == ["(empty)"]


def test_format_ordered_card_options_reverse_shows_newest_first() -> None:
    cards_by_id = {
        "noble": SimpleNamespace(name="Noble"),
        "soldier": SimpleNamespace(name="Soldier"),
        "priestess_of_lolth": SimpleNamespace(name="Priestess of Lolth"),
    }

    options = format_ordered_card_options(
        ["soldier", "noble", "priestess_of_lolth"],
        cards_by_id,
        reverse=True,
    )

    assert options == [
        "1. Priestess of Lolth",
        "2. Noble",
        "3. Soldier",
    ]


def test_format_ordered_card_options_top_label_applied_to_first_entry() -> None:
    cards_by_id = {
        "soldier": SimpleNamespace(name="Soldier"),
        "noble": SimpleNamespace(name="Noble"),
    }

    options = format_ordered_card_options(
        ["noble", "soldier"],
        cards_by_id,
        reverse=True,
        top_label="(top)",
    )

    assert options == [
        "1. Soldier (top)",
        "2. Noble",
    ]


def test_format_ordered_card_options_reverse_and_top_label_on_single_card() -> None:
    cards_by_id = {
        "soldier": SimpleNamespace(name="Soldier"),
    }

    options = format_ordered_card_options(
        ["soldier"],
        cards_by_id,
        reverse=True,
        top_label="(top)",
    )

    assert options == ["1. Soldier (top)"]


def test_format_trophy_hall_options_labels_white_and_player_trophies() -> None:
    options = format_trophy_hall_options(["p2", "white", "p3"])

    assert options == [
        "1. Player p2 troop (p2)",
        "2. White troop (white)",
        "3. Player p3 troop (p3)",
    ]


def test_format_trophy_hall_options_empty_returns_placeholder() -> None:
    assert format_trophy_hall_options([]) == ["(empty)"]
