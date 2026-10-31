"""Tests for ``scripts.card_playstats.report`` — pandas/plotly aggregation layer."""

from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from scripts.card_playstats.extract import GameExtraction  # noqa: E402
from scripts.card_playstats.metadata import RunMetadata  # noqa: E402
from scripts.card_playstats.report import (  # noqa: E402
    build_card_table,
    build_modal_choice_frames,
    build_overview_frames,
)


class _FakeCatalog:
    def __init__(self, modal: dict[str, dict[str, str]]) -> None:
        self._modal = modal

    def is_modal(self, card_id: str) -> bool:
        return card_id in self._modal

    def option_ids(self, card_id: str) -> frozenset[str]:
        return frozenset(self._modal.get(card_id, {}))

    def label_for(self, card_id: str, option_id: str) -> str:
        return self._modal.get(card_id, {}).get(option_id, option_id)


def _extraction(**overrides) -> GameExtraction:
    base = {
        "game_dir": "game_0000",
        "run_id": "r",
        "recruited": {},
        "played": {},
        "hand_appearances": {},
        "modal_played": {},
        "modal_choices": {},
        "modal_source": "decisions",
        "warnings": [],
        "winner_seat": 0,
        "num_players": 2,
        "outcome": "p1_win",
        "final_scores": {"p1": 1, "p2": 0},
        "step_count": 1,
        "deck_a_id": "a",
        "deck_b_id": "b",
        "decision_count": 1,
        "move_type_counts": {},
        "complete": True,
        "engine_replayed": True,
    }
    base.update(overrides)
    return GameExtraction(**base)


def test_build_card_table_joins_and_sorts() -> None:
    catalog = _FakeCatalog({"advocate": {"gain_influence": "Gain", "promote": "Promote"}})
    extractions = [
        _extraction(
            recruited={"soldier": 3, "advocate": 2, "wight": 1},
            played={"soldier": 1, "advocate": 2},
            hand_appearances={"soldier": 4, "advocate": 3},
            modal_played={"advocate": 2},
            modal_choices={"advocate": {"gain_influence": 1, "promote": 1}},
        )
    ]

    table = build_card_table(extractions, catalog)

    assert list(table.columns[:4]) == ["card_id", "recruited", "appeared_in_hand", "played"]
    assert table.iloc[0]["card_id"] == "soldier"
    soldier = table.set_index("card_id").loc["soldier"]
    assert soldier["recruited"] == 3
    assert soldier["played"] == 1
    assert soldier["appeared_in_hand"] == 4
    advocate = table.set_index("card_id").loc["advocate"]
    assert bool(advocate["is_modal"]) is True
    assert advocate["play_rate_given_recruited"] == pytest.approx(1.0)
    wight = table.set_index("card_id").loc["wight"]
    assert wight["recruited_never_played"] is True or bool(wight["recruited_never_played"]) is True
    assert bool(wight["recruited_never_drawn"]) is True


def test_build_modal_choice_frames_includes_zero_choice_cards() -> None:
    catalog = _FakeCatalog(
        {
            "advocate": {"gain_influence": "Gain influence", "promote": "Promote"},
            "wight": {"option_1": "One", "option_2": "Two"},
        }
    )
    extractions = [
        _extraction(
            modal_played={"advocate": 2},
            modal_choices={"advocate": {"gain_influence": 1, "promote": 1}},
        )
    ]

    frames = build_modal_choice_frames(extractions, catalog, {"advocate", "wight"})

    assert set(frames) == {"advocate", "wight"}
    advocate = frames["advocate"].set_index("option_id")
    assert advocate.loc["gain_influence", "count"] == 1
    assert advocate.loc["gain_influence", "share"] == pytest.approx(0.5)
    assert advocate.loc["promote", "label"] == "Promote"
    wight = frames["wight"].set_index("option_id")
    assert wight["count"].sum() == 0


def test_build_overview_frames_per_run() -> None:
    meta_a = RunMetadata(
        run_dir="runs/a",
        run_id="a",
        config={"num_sims": 16},
        engine_git_sha="a",
        engine_git_dirty=False,
        num_games=2,
        complete_games=1,
        incomplete_games=1,
        winner_counts_by_seat={0: 1},
        win_rate_by_seat={0: 1.0},
        matchup_counts={"x vs y": 1},
        deck_counts={"x": 1, "y": 1},
        move_type_totals={"recruit": 3},
        game_lengths=[10],
        mean_score_by_seat={"p1": 5.0},
        mean_deck_entropy={"full": 3.0, "recruited": 2.0},
    )
    meta_b = RunMetadata(
        run_dir="runs/b",
        run_id="b",
        config={"num_sims": 32},
        engine_git_sha="b",
        engine_git_dirty=True,
        num_games=1,
        complete_games=1,
        incomplete_games=0,
        winner_counts_by_seat={1: 1},
        win_rate_by_seat={1: 1.0},
        matchup_counts={},
        deck_counts={},
        move_type_totals={},
        game_lengths=[20],
        mean_score_by_seat={},
        mean_deck_entropy={},
    )

    frames = build_overview_frames([meta_a, meta_b])

    assert list(frames["config"][frames["config"].columns[0]]) == ["a", "b"]
    assert "win_rate_by_seat" in frames
    assert "matchups" in frames
    assert "deck_diversity" in frames
    assert "game_lengths" in frames
    assert "mean_scores" in frames
    assert frames["game_lengths"]["decision_count"].tolist() == [10, 20]
