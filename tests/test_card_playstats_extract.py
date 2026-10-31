"""Tests for ``scripts.card_playstats.extract`` — per-game extraction.

Covers the cheap log pass, the expensive engine-replay hand tracking, both
modal-resolution paths (``decisions.jsonl`` and the replay-log fallback), the
sanity checks from plan §7, and the disk cache.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.card_playstats.catalog import load_catalog
from scripts.card_playstats.extract import (
    ExtractionSanityError,
    GameExtraction,
    count_hand_appearances,
    count_move_events,
    extract_game,
    market_card_ids_from_setup,
    resolve_modal_choices,
)

ROOT = Path(__file__).resolve().parents[1]
CARD_DIR = ROOT / "data" / "cards"
GAME_DIR = ROOT / "artifacts" / "ismcts" / "runs" / "20260911T193759Z_58e54c44a5f5" / "game_0000"


def _entry(
    step: int,
    player: str,
    move_type: str,
    payload: dict | None = None,
    *,
    phase: str = "main",
    round_number: int = 1,
) -> dict:
    payload_type = "resolve_generic_choice" if move_type == "resolve_generic" else move_type
    return {
        "step_index": step,
        "player_id": player,
        "round_number": round_number,
        "phase": phase,
        "move_type": move_type,
        "label": "",
        "payload": {"move_type": payload_type, **(payload or {})},
    }


def test_count_move_events_groups_by_card_id() -> None:
    log = [
        _entry(0, "p1", "recruit", {"card_id": "soldier"}),
        _entry(1, "p2", "recruit", {"card_id": "soldier"}),
        _entry(2, "p1", "recruit", {"card_id": "wight"}),
        _entry(3, "p1", "play_card", {"card_id": "noble", "hand_index": 0}),
        _entry(4, "p1", "play_card", {"card_id": "noble", "hand_index": 0}),
    ]

    recruited, played = count_move_events(log)

    assert recruited == Counter({"soldier": 2, "wight": 1})
    assert played == Counter({"noble": 2})


def test_resolve_modal_choices_prefers_decisions() -> None:
    log = [_entry(0, "p1", "play_card", {"card_id": "cultist_of_myrkul", "hand_index": 0})]
    decisions = [
        {"node": 0, "chosen_move": "play_card(card_id='cultist_of_myrkul', hand_index=0)"},
        {
            "chosen_move": "resolve_generic(action_id='option_2', target_id=None, selection_index=0)",
            "pending_context": {"source_card_id": "cultist_of_myrkul", "awaiting_option": True},
            "generic": {"move_action_id": "option_2", "awaiting_option": True},
        },
    ]

    catalog = _fake_catalog({"cultist_of_myrkul": {"option_1", "option_2"}})
    choices, source, warnings = resolve_modal_choices(log, decisions, catalog)

    assert choices == {"cultist_of_myrkul": Counter({"option_2": 1})}
    assert source == "decisions"
    assert warnings == []


def test_resolve_modal_choices_falls_back_to_log() -> None:
    log = [
        _entry(0, "p1", "play_card", {"card_id": "cultist_of_myrkul", "hand_index": 0}),
        # Mandatory downstream sub-choice (site id) must be ignored, not counted.
        _entry(1, "p1", "resolve_generic", {"action_id": "site_kanaglym", "target_id": None, "selection_index": 0}),
        _entry(2, "p1", "resolve_generic", {"action_id": "option_1", "target_id": None, "selection_index": 0}),
    ]

    catalog = _fake_catalog({"cultist_of_myrkul": {"option_1", "option_2"}})
    choices, source, warnings = resolve_modal_choices(log, [], catalog)

    assert choices == {"cultist_of_myrkul": Counter({"option_1": 1})}
    assert source == "fallback"
    assert warnings == []


def test_fallback_stops_at_next_play_or_recruit() -> None:
    log = [
        _entry(0, "p1", "play_card", {"card_id": "cultist_of_myrkul", "hand_index": 0}),
        _entry(1, "p1", "play_card", {"card_id": "noble", "hand_index": 0}),
        _entry(2, "p1", "resolve_generic", {"action_id": "option_1", "target_id": None, "selection_index": 0}),
    ]

    catalog = _fake_catalog({"cultist_of_myrkul": {"option_1", "option_2"}})
    choices, source, warnings = resolve_modal_choices(log, [], catalog)

    assert choices == {"cultist_of_myrkul": Counter()}
    assert source == "fallback"
    assert any("cultist_of_myrkul" in w for w in warnings)


def test_modal_sanity_warning_on_mismatch() -> None:
    warnings = GameExtraction.modal_warnings(
        modal_played=Counter({"cultist_of_myrkul": 2}),
        modal_choices={"cultist_of_myrkul": Counter({"option_1": 1})},
    )
    assert any("cultist_of_myrkul" in w for w in warnings)


def test_modal_sanity_warns_on_choice_without_play() -> None:
    warnings = GameExtraction.modal_warnings(
        modal_played=Counter(),
        modal_choices={"minotaur_skeleton": Counter({"option_2": 1})},
    )
    assert any("minotaur_skeleton" in w for w in warnings)


def test_decisions_path_ignores_undeclared_option_ids() -> None:
    decisions = [
        {
            "chosen_move": "resolve_generic(action_id='site_kanaglym', target_id=None, selection_index=0)",
            "pending_context": {"source_card_id": "cultist_of_myrkul", "awaiting_option": True},
            "generic": {"move_action_id": "site_kanaglym", "awaiting_option": True},
        },
        {
            "chosen_move": "resolve_generic(action_id='option_1', target_id=None, selection_index=0)",
            "pending_context": {"source_card_id": "cultist_of_myrkul", "awaiting_option": True},
            "generic": {"move_action_id": "option_1", "awaiting_option": True},
        },
    ]

    catalog = _fake_catalog({"cultist_of_myrkul": {"option_1", "option_2"}})
    choices, source, warnings = resolve_modal_choices([], decisions, catalog)

    assert choices == {"cultist_of_myrkul": Counter({"option_1": 1})}
    assert source == "decisions"
    assert warnings == []


def test_move_event_total_sanity_raises_on_mismatch() -> None:
    summary = {"move_type_counts": {"recruit": 3, "play_card": 2}}
    with pytest.raises(ExtractionSanityError):
        GameExtraction.check_move_event_totals(
            recruited=Counter({"soldier": 1}),
            played=Counter({"noble": 2}),
            move_type_counts=summary["move_type_counts"],
        )


def test_market_card_ids_from_setup_includes_deck_and_stacks() -> None:
    setup = json.dumps(
        {
            "market_deck": {"entries": [{"card_id": "advocate", "count": 2}, {"card_id": "soldier", "count": 1}]},
            "special_stacks": [{"card_id": "house_guard", "stack_total": 15}],
        }
    )

    assert market_card_ids_from_setup(setup) == ["advocate", "house_guard", "soldier"]
    assert market_card_ids_from_setup("not json") == []


def test_extraction_round_trips_through_dict() -> None:
    extraction = GameExtraction(
        game_dir="game_0000",
        run_id="abc",
        recruited={"soldier": 2},
        played={"noble": 1},
        hand_appearances={"soldier": 3},
        modal_played={"advocate": 2},
        modal_choices={"advocate": {"gain_influence": 1, "promote_end_of_turn": 1}},
    modal_source="decisions",
    warnings=[],
    market_card_ids=["advocate", "soldier"],
    winner_seat=1,
        num_players=4,
        outcome="p2_win",
        final_scores={"p1": 10, "p2": 20},
        step_count=100,
        deck_a_id="undead",
        deck_b_id="aberrations",
        decision_count=99,
        move_type_counts={"recruit": 2},
        complete=True,
        engine_replayed=True,
    )

    restored = GameExtraction.from_dict(extraction.to_dict())

    assert restored == extraction


def _fake_catalog(modal_options: dict[str, set[str]]):
    class _Catalog:
        def is_modal(self, card_id: str) -> bool:
            return card_id in modal_options

        def option_ids(self, card_id: str) -> frozenset[str]:
            return frozenset(modal_options.get(card_id, set()))

    return _Catalog()


def _write_synthetic_game(run_dir: Path, name: str, replay: dict, summary: dict | None = None) -> Path:
    game_dir = run_dir / name
    game_dir.mkdir(parents=True)
    (game_dir / "replay.json").write_text(json.dumps(replay), encoding="utf-8")
    if summary is not None:
        (game_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return game_dir


_ENGINE_READY = GAME_DIR.exists() and (ROOT / "engine_c" / "engine_c.dll").exists()


@pytest.mark.skipif(not _ENGINE_READY, reason="C engine replay artifacts not present")
def test_extract_real_game_counts_and_hand_tracking() -> None:
    catalog = load_catalog(CARD_DIR)

    extraction = extract_game(GAME_DIR, catalog)

    assert extraction.engine_replayed is True
    assert sum(extraction.recruited.values()) == 81
    assert sum(extraction.played.values()) == 480
    assert sum(extraction.hand_appearances.values()) > 0
    assert extraction.complete is True
    assert extraction.num_players == 4
    assert extraction.modal_source == "decisions"
    assert extraction.warnings == []
    assert "priestess_of_lolth" in extraction.market_card_ids


@pytest.mark.skipif(not _ENGINE_READY, reason="C engine replay artifacts not present")
def test_cache_skips_engine_on_second_call(tmp_path: Path) -> None:
    catalog = load_catalog(CARD_DIR)
    calls = {"n": 0}

    def _counting_counter(bundle):
        calls["n"] += 1
        return count_hand_appearances(bundle)

    first = extract_game(GAME_DIR, catalog, cache_dir=tmp_path, hand_counter=_counting_counter)
    assert calls["n"] == 1

    def _explode(bundle):  # pragma: no cover - must never run on a cache hit
        raise AssertionError("engine replay re-ran despite warm cache")

    second = extract_game(GAME_DIR, catalog, cache_dir=tmp_path, hand_counter=_explode)

    assert second == first
