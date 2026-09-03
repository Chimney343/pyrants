"""Tests for scripts/_sims_vs_wins.py (pure sims-vs-wins analysis helpers).

No engine and no numpy-at-import required: the helpers under test are pure
stdlib, mirroring the testability of scripts/_obs.py and
scripts/_replay_payload.py.
"""

from __future__ import annotations

import random

import pytest

from scripts._sims_vs_wins import analyze, parse_sims_spec, seat_budgets_for_game


def _summary(budgets, returns, winner, stopped="terminal"):
    s = {
        "num_sims_per_seat": list(budgets),
        "returns": list(returns),
        "winner": winner,
        "stopped_reason": stopped,
    }
    return s


# ── parse_sims_spec ─────────────────────────────────────────────────────────


class TestParseSimsSpec:
    def test_parses(self):
        assert parse_sims_spec("50,100,200,400", 4) == [50, 100, 200, 400]

    def test_strips_whitespace(self):
        assert parse_sims_spec(" 50, 100 ,200,400 ", 4) == [50, 100, 200, 400]

    def test_length_mismatch(self):
        with pytest.raises(ValueError):
            parse_sims_spec("50,100,200", 4)

    def test_non_integer(self):
        with pytest.raises(ValueError):
            parse_sims_spec("50,abc,200,400", 4)

    def test_empty_segment(self):
        with pytest.raises(ValueError):
            parse_sims_spec("50,,200,400", 4)

    def test_negative_budget(self):
        with pytest.raises(ValueError):
            parse_sims_spec("50,0,200,400", 4)


# ── seat_budgets_for_game ───────────────────────────────────────────────────


class TestSeatBudgetsForGame:
    def test_fixed_returns_base(self):
        base = [50, 100, 200, 400]
        assert seat_budgets_for_game(base, 3, False) == base
        assert seat_budgets_for_game(base, 0, False) == base

    def test_rotation_shifts_correctly(self):
        base = [50, 100, 200, 400]
        assert seat_budgets_for_game(base, 0, True) == [50, 100, 200, 400]
        assert seat_budgets_for_game(base, 1, True) == [100, 200, 400, 50]
        assert seat_budgets_for_game(base, 2, True) == [200, 400, 50, 100]
        assert seat_budgets_for_game(base, 3, True) == [400, 50, 100, 200]
        assert seat_budgets_for_game(base, 4, True) == [50, 100, 200, 400]

    def test_rotation_balanced_over_4k_games(self):
        base = [50, 100, 200, 400]
        n = len(base)
        k = 7
        counts = {seat: {b: 0 for b in base} for seat in range(n)}
        for g in range(n * k):
            budgets = seat_budgets_for_game(base, g, True)
            for seat, b in enumerate(budgets):
                counts[seat][b] += 1
        for seat in range(n):
            for b in base:
                assert counts[seat][b] == k


# ── analyze ─────────────────────────────────────────────────────────────────


class TestAnalyze:
    def test_strong_monotone_effect_small_p(self):
        summaries = [
            _summary([50, 100, 200, 400], [10, 20, 30, 40], 3) for _ in range(40)
        ]
        result = analyze(summaries, n_players=4, n_permutations=200, seed=0)

        assert result["trend"]["statistic"] > 0.9
        assert result["trend"]["p_value"] < 0.05
        assert result["by_budget"][400]["wins"] == 40
        assert result["by_budget"][400]["win_rate"] == 1.0

    def test_null_data_large_p(self):
        rng = random.Random(1)
        summaries = []
        for _ in range(40):
            vp = [10, 20, 30, 40]
            rng.shuffle(vp)
            summaries.append(
                _summary([50, 100, 200, 400], vp, rng.randrange(4))
            )
        result = analyze(summaries, n_players=4, n_permutations=500, seed=0)

        assert result["trend"]["p_value"] > 0.05

    def test_exclusions_counted_not_decided(self):
        summaries = [
            _summary([50, 100, 200, 400], [10, 20, 30, 40], 3),
            _summary([50, 100, 200, 400], [10, 20, 30, 40], 3),
            _summary([50, 100, 200, 400], [10, 20, 30, 40], 3),
            _summary([50, 100, 200, 400], [10, 20, 30, 40], 3),
            _summary([50, 100, 200, 400], [20, 20, 20, 20], None),  # tie
            _summary([50, 100, 200, 400], [10, 20, 30, 40], None, "round_cap"),
            {"num_sims_per_seat": [50, 100, 200, 400], "stopped_reason": "error"},
        ]
        result = analyze(summaries, n_players=4, n_permutations=20, seed=0)

        assert result["n_games"] == 7
        assert result["n_decided"] == 4
        assert result["n_ties"] == 1
        assert result["n_round_cap"] == 1
        assert result["n_errors"] == 1
        assert result["exclusions"]["ties"] == 1
        assert result["exclusions"]["round_cap"] == 1
        assert result["exclusions"]["errors"] == 1
        assert result["by_budget"][400]["wins"] == 4
        assert result["by_budget"][400]["decided"] == 4
        assert result["low_effective_n"] is True

    def test_wilson_ci_sanity(self):
        summaries = [
            _summary([50, 100, 200, 400], [10, 20, 30, 40], 3) for _ in range(20)
        ]
        result = analyze(summaries, n_players=4, n_permutations=10, seed=0)

        d = result["by_budget"][400]
        assert d["win_rate"] == 1.0
        assert 0.0 < d["ci95_low"] < 1.0
        assert d["ci95_high"] == 1.0

    def test_mean_vp_and_rank_per_budget(self):
        summaries = [
            _summary([50, 100, 200, 400], [10, 20, 30, 40], 3),
            _summary([50, 100, 200, 400], [40, 30, 20, 10], 0),
        ]
        result = analyze(summaries, n_players=4, n_permutations=10, seed=0)

        # Budget 400 wins game 1 (VP 40) and loses game 2 (VP 10) -> mean VP 25.
        assert result["by_budget"][400]["mean_vp"] == pytest.approx(25.0, abs=0.001)
        # Budget 50 wins game 2 (VP 40) and loses game 1 (VP 10) -> mean VP 25.
        assert result["by_budget"][50]["mean_vp"] == pytest.approx(25.0, abs=0.001)
        # Rank 1 (best) averaged across the two games: 400 is rank 1 then rank 4.
        assert result["by_budget"][400]["mean_rank"] == pytest.approx(2.5, abs=0.001)
