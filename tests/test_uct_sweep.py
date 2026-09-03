"""Tests for scripts/_uct_sweep.py (pure UCT-sweep analysis helpers).

No engine and no numpy-at-import required: the helpers under test are pure
stdlib, mirroring the testability of scripts/_sims_vs_wins.py.
"""

from __future__ import annotations

import json
import math
import random

import pytest

from scripts._sims_vs_wins import seat_budgets_for_game
from scripts._uct_sweep import (
    analyze_uct,
    deck_variety_metrics,
    parse_uct_spec,
    required_decided_games,
)


def _summary(
    uct,
    vp,
    winner,
    stopped="terminal",
    deck_metrics=None,
):
    s = {
        "uct_c_per_seat": list(uct),
        "final_vp_per_seat": list(vp),
        "winner": winner,
        "stopped_reason": stopped,
    }
    if deck_metrics is not None:
        s["final_deck_metrics"] = list(deck_metrics)
    return s


def _deck_metrics(normalized_entropy, deck_size=10):
    return {
        "full": {
            "unique_count": 4,
            "deck_size": deck_size,
            "unique_ratio": 0.4,
            "shannon_entropy": 1.5,
            "normalized_entropy": normalized_entropy,
            "simpson": 0.6,
        },
        "recruited": {
            "unique_count": 3,
            "deck_size": deck_size,
            "unique_ratio": 0.3,
            "shannon_entropy": 1.2,
            "normalized_entropy": normalized_entropy,
            "simpson": 0.5,
        },
        "recruited_degraded": False,
    }


# ── parse_uct_spec ──────────────────────────────────────────────────────────


class TestParseUctSpec:
    def test_parses(self):
        assert parse_uct_spec("0.3,0.8,1.4,2.5", 4) == [0.3, 0.8, 1.4, 2.5]

    def test_strips_whitespace(self):
        assert parse_uct_spec(" 0.3, 0.8 ,1.4,2.5 ", 4) == [0.3, 0.8, 1.4, 2.5]

    def test_length_mismatch(self):
        with pytest.raises(ValueError):
            parse_uct_spec("0.3,0.8,1.4", 4)

    def test_non_float(self):
        with pytest.raises(ValueError):
            parse_uct_spec("0.3,abc,1.4,2.5", 4)

    def test_empty_segment(self):
        with pytest.raises(ValueError):
            parse_uct_spec("0.3,,1.4,2.5", 4)

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            parse_uct_spec("0.3,0,1.4,2.5", 4)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            parse_uct_spec("0.3,-0.8,1.4,2.5", 4)


# ── deck_variety_metrics ─────────────────────────────────────────────────────


class TestDeckVarietyMetrics:
    def test_all_unique(self):
        m = deck_variety_metrics(["a", "b", "c", "d"])
        assert m["full"]["unique_ratio"] == pytest.approx(1.0)
        assert m["full"]["normalized_entropy"] == pytest.approx(1.0)
        assert m["full"]["unique_count"] == 4
        assert m["full"]["deck_size"] == 4

    def test_identical_card(self):
        m = deck_variety_metrics(["a", "a", "a", "a"])
        assert m["full"]["unique_ratio"] == pytest.approx(0.25)
        assert m["full"]["shannon_entropy"] == pytest.approx(0.0)
        assert m["full"]["simpson"] == pytest.approx(0.0)

    def test_simpson_two_of_three(self):
        # a,a,b -> p_a=2/3, p_b=1/3 -> simpson = 1 - (4/9 + 1/9) = 4/9.
        m = deck_variety_metrics(["a", "a", "b"])
        assert m["full"]["simpson"] == pytest.approx(4.0 / 9.0)

    def test_single_card_normalized_entropy_zero(self):
        m = deck_variety_metrics(["a"])
        assert m["full"]["normalized_entropy"] == pytest.approx(0.0)

    def test_empty_deck(self):
        m = deck_variety_metrics([])
        assert m["full"]["deck_size"] == 0
        assert m["full"]["unique_ratio"] == 0.0
        assert m["full"]["normalized_entropy"] == 0.0
        assert m["full"]["simpson"] == 0.0

    def test_starter_subtraction(self):
        full = ["noble"] * 7 + ["soldier"] * 3 + ["lolth", "lolth", "spy"]
        starter = {"noble": 7, "soldier": 3}
        m = deck_variety_metrics(full, starter_counts=starter)
        assert m["recruited_degraded"] is False
        assert m["recruited"]["deck_size"] == 3
        assert m["recruited"]["unique_count"] == 2
        assert m["recruited"]["unique_ratio"] == pytest.approx(2.0 / 3.0)

    def test_starter_exceeding_observed_degrades(self):
        full = ["noble"] * 6 + ["soldier"] * 3
        starter = {"noble": 7, "soldier": 3}
        m = deck_variety_metrics(full, starter_counts=starter)
        assert m["recruited_degraded"] is True
        assert m["recruited"] == m["full"]


# ── required_decided_games ───────────────────────────────────────────────────


class TestRequiredDecidedGames:
    # Exact-Wilson minimum n for a given half-width. The plan's ±5pp anchor
    # was quoted as 288 (the rounded half-width at n=288 is ~4.98pp), but the
    # exact-Wilson bisection finds 286 as the smallest n with half-width <= 0.05
    # (n=285 -> 0.050048 > 0.05; n=286 -> 0.049961 <= 0.05).
    @pytest.mark.parametrize(
        "target,expected",
        [(0.10, 70), (0.08, 110), (0.05, 286)],
    )
    def test_reference_values(self, target, expected):
        assert required_decided_games(target) == expected

    def test_288_half_width_under_5pp(self):
        # Sanity: n=288 is comfortably within the ±5pp target.
        assert required_decided_games(0.05) <= 288

    def test_monotonic_in_target_width(self):
        vals = [
            required_decided_games(w)
            for w in (0.10, 0.08, 0.06, 0.05, 0.04)
        ]
        assert vals == sorted(vals)

    def test_rejects_nonpositive_target(self):
        with pytest.raises(ValueError):
            required_decided_games(0.0)


# ── seat_budgets_for_game with float ladder ──────────────────────────────────


class TestSeatBudgetsForGameFloats:
    def test_float_ladder_rotation(self):
        ladder = [0.3, 0.8, 1.4, 2.5]
        assert seat_budgets_for_game(ladder, 0, True) == [0.3, 0.8, 1.4, 2.5]
        assert seat_budgets_for_game(ladder, 1, True) == [0.8, 1.4, 2.5, 0.3]
        assert seat_budgets_for_game(ladder, 2, True) == [1.4, 2.5, 0.3, 0.8]

    def test_float_ladder_fixed(self):
        ladder = [0.3, 0.8, 1.4, 2.5]
        assert seat_budgets_for_game(ladder, 3, False) == ladder

    def test_rotation_balances_seats_over_4k_games(self):
        ladder = [0.3, 0.8, 1.4, 2.5]
        n = len(ladder)
        k = 7
        counts = {seat: {b: 0 for b in ladder} for seat in range(n)}
        for g in range(n * k):
            budgets = seat_budgets_for_game(ladder, g, True)
            for seat, b in enumerate(budgets):
                counts[seat][b] += 1
        for seat in range(n):
            for b in ladder:
                assert counts[seat][b] == k


# ── analyze_uct ──────────────────────────────────────────────────────────────


class TestAnalyzeUct:
    def test_win_attribution_per_arm(self):
        # Arm 2.5 always sits in the winning seat (seat 3); rotation is fixed.
        summaries = [
            _summary([0.3, 0.8, 1.4, 2.5], [10, 20, 30, 40], 3)
            for _ in range(40)
        ]
        result = analyze_uct(summaries, n_players=4, n_permutations=50, seed=0)

        assert result["n_decided"] == 40
        assert result["by_arm"][2.5]["wins"] == 40
        assert result["by_arm"][2.5]["win_rate"] == 1.0
        assert result["by_arm"][0.3]["wins"] == 0

    def test_vp_share_means(self):
        summaries = [
            _summary([0.3, 0.8, 1.4, 2.5], [10, 20, 30, 40], 3),
            _summary([0.3, 0.8, 1.4, 2.5], [40, 30, 20, 10], 0),
        ]
        result = analyze_uct(summaries, n_players=4, n_permutations=10, seed=0)

        # Arm 2.5: share 0.4 (game 1) and 0.1 (game 2) -> mean 0.25.
        assert result["by_arm"][2.5]["mean_vp_share"] == pytest.approx(0.25, abs=1e-3)
        assert result["by_arm"][2.5]["mean_vp"] == pytest.approx(25.0, abs=1e-3)

    def test_zero_total_vp_flagged_and_excluded_from_share(self):
        summaries = [
            _summary([0.3, 0.8, 1.4, 2.5], [10, 20, 30, 40], 3),
            _summary([0.3, 0.8, 1.4, 2.5], [0, 0, 0, 0], None, "terminal"),
        ]
        result = analyze_uct(summaries, n_players=4, n_permutations=10, seed=0)

        assert result["n_zero_vp"] == 1
        assert result["exclusions"]["zero_vp"] == 1
        # Only game 1 contributes to share means.
        assert result["by_arm"][2.5]["vp_share_n"] == 1
        assert result["by_arm"][2.5]["mean_vp_share"] == pytest.approx(0.4, abs=1e-3)

    def test_deck_metric_aggregation(self):
        decks_hi = [_deck_metrics(1.0) for _ in range(4)]
        decks_lo = [_deck_metrics(0.2) for _ in range(4)]
        summaries = [
            _summary([0.3, 0.8, 1.4, 2.5], [10, 20, 30, 40], 3, deck_metrics=decks_hi),
            _summary([0.3, 0.8, 1.4, 2.5], [10, 20, 30, 40], 3, deck_metrics=decks_lo),
        ]
        result = analyze_uct(summaries, n_players=4, n_permutations=10, seed=0)

        arm = result["by_arm"][2.5]
        # Arm 2.5 gets one observation per game -> [1.0, 0.2].
        assert arm["deck_recruited"]["normalized_entropy"]["mean"] == pytest.approx(0.6)
        assert arm["deck_recruited"]["normalized_entropy"]["n"] == 2
        # Sample sd of {1.0, 0.2} = |0.8| / sqrt(2).
        assert arm["deck_recruited"]["normalized_entropy"]["sd"] == pytest.approx(
            0.8 / math.sqrt(2)
        )

    def test_exclusions_counted_not_decided(self):
        summaries = [
            _summary([0.3, 0.8, 1.4, 2.5], [10, 20, 30, 40], 3),
            _summary([0.3, 0.8, 1.4, 2.5], [10, 20, 30, 40], 3),
            _summary([0.3, 0.8, 1.4, 2.5], [20, 20, 20, 20], None),
            _summary([0.3, 0.8, 1.4, 2.5], [10, 20, 30, 40], None, "round_cap"),
            {"uct_c_per_seat": [0.3, 0.8, 1.4, 2.5], "stopped_reason": "error"},
        ]
        result = analyze_uct(summaries, n_players=4, n_permutations=20, seed=0)

        assert result["n_games"] == 5
        assert result["n_decided"] == 2
        assert result["n_ties"] == 1
        assert result["n_round_cap"] == 1
        assert result["n_errors"] == 1
        assert result["low_effective_n"] is True

    def test_monotone_vp_effect_small_p(self):
        summaries = [
            _summary([0.3, 0.8, 1.4, 2.5], [10, 20, 30, 40], 3)
            for _ in range(40)
        ]
        result = analyze_uct(summaries, n_players=4, n_permutations=200, seed=0)

        assert result["trend_vp_share"]["statistic"] > 0.9
        assert result["trend_vp_share"]["p_value"] < 0.05

    def test_null_vp_data_large_p(self):
        rng = random.Random(1)
        summaries = []
        for _ in range(40):
            vp = [10, 20, 30, 40]
            rng.shuffle(vp)
            summaries.append(_summary([0.3, 0.8, 1.4, 2.5], vp, rng.randrange(4)))
        result = analyze_uct(summaries, n_players=4, n_permutations=500, seed=0)

        assert result["trend_vp_share"]["p_value"] > 0.05

    def test_games_needed_block(self):
        summaries = [
            _summary([0.3, 0.8, 1.4, 2.5], [10, 20, 30, 40], 3)
            for _ in range(50)
        ]
        result = analyze_uct(summaries, n_players=4, n_permutations=10, seed=0)

        g = result["games_needed"]
        assert g["achieved_n_decided"] == 50
        assert g["decided_fraction"] == 1.0
        assert g["required_10pp"] == 70
        assert g["projected_total_games_10pp"] == 70


# ── --analyze-only path ─────────────────────────────────────────────────────


class TestAnalyzeOnly:
    def test_analyze_only_merges_dirs(self, tmp_path):
        from scripts.run_ismcts_uct_sweep import _analyze_only

        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"
        for d in (dir1, dir2):
            (d / "game_0000").mkdir(parents=True)

        def synth(winner):
            s = _summary([0.3, 0.8, 1.4, 2.5], [10, 20, 30, 40], winner)
            s["num_players"] = 4
            return s

        (dir1 / "game_0000" / "summary.json").write_text(
            json.dumps(synth(3)), encoding="utf-8"
        )
        (dir2 / "game_0000" / "summary.json").write_text(
            json.dumps(synth(3)), encoding="utf-8"
        )

        _analyze_only([dir1, dir2])

        analysis = json.loads((dir1 / "analysis.json").read_text(encoding="utf-8"))
        assert analysis["n_games"] == 2
        assert analysis["n_decided"] == 2
        assert (dir1 / "analysis.md").exists()
        # The merged analysis is written into the first dir only.
        assert not (dir2 / "analysis.json").exists()
