"""Integration-style tests for roster card stuck probe script."""

from __future__ import annotations

from pathlib import Path

from scripts.check_roster_card_stuck_states import (
    ProbeResult,
    ProbeSummary,
    evaluate_ci_gate,
    iter_roster_card_ids,
    run_probe,
    summary_to_json_payload,
)

BASE_DIR = Path(__file__).resolve().parents[1]
ROSTERS_PATH = BASE_DIR / "data" / "decks"
BOARD_PATH = BASE_DIR / "data" / "boards" / "base_game.json"
CARD_PATH = BASE_DIR / "data" / "cards" / "catalog.json"
SETUP_PATH = BASE_DIR / "data" / "decks" / "base_setup.json"


def _probe_result(card_id: str, status: str) -> ProbeResult:
    return ProbeResult(
        card_id=card_id,
        seed=1,
        status=status,
        stopped_reason="test",
        step_count=0,
        phase="main",
        current_player_id="p1",
        prompts=(),
        trace=(),
    )


def test_iter_roster_card_ids_returns_125_unique_ids() -> None:
    card_ids = iter_roster_card_ids(ROSTERS_PATH)

    assert len(card_ids) == 125
    assert len(set(card_ids)) == 125
    assert "ambassador" in card_ids
    assert "noble" in card_ids


def test_summary_to_json_payload_preserves_counts() -> None:
    summary = ProbeSummary(
        total_runs=3,
        status_counts={"ok": 1, "stuck": 1, "blocked": 1, "error": 0, "max_steps": 0},
        results=(
            ProbeResult(
                card_id="ambassador",
                seed=1,
                status="ok",
                stopped_reason="turn_completed",
                step_count=4,
                phase="main",
                current_player_id="p2",
                prompts=("prompt",),
                trace=("play_card:ambassador",),
            ),
            ProbeResult(
                card_id="noble",
                seed=2,
                status="stuck",
                stopped_reason="non_terminal_no_legal_moves",
                step_count=3,
                phase="end_of_turn",
                current_player_id="p1",
                prompts=("stuck",),
                trace=("play_card:noble",),
            ),
            ProbeResult(
                card_id="ulitharid",
                seed=3,
                status="blocked",
                stopped_reason="engine_not_implemented",
                step_count=1,
                phase="main",
                current_player_id="p1",
                prompts=(),
                trace=("play_card:ulitharid",),
                error="not implemented",
            ),
        ),
    )

    payload = summary_to_json_payload(summary)

    assert payload["total_runs"] == 3
    assert payload["status_counts"]["stuck"] == 1
    assert len(payload["results"]) == 3
    assert payload["results"][2]["status"] == "blocked"


def test_run_probe_single_card_smoke_returns_result() -> None:
    summary = run_probe(
        board_path=BOARD_PATH,
        card_path=CARD_PATH,
        setup_path=SETUP_PATH,
        rosters_path=ROSTERS_PATH,
        seed=7,
        seed_count=1,
        max_steps=60,
        include_duplicates=False,
        card_id="ambassador",
    )

    assert summary.total_runs == 1
    assert len(summary.results) == 1
    assert summary.results[0].card_id == "ambassador"
    assert summary.results[0].status in {"ok", "stuck", "blocked", "error", "max_steps"}


def test_evaluate_ci_gate_passes_when_blocked_is_expected() -> None:
    summary = ProbeSummary(
        total_runs=1,
        status_counts={"ok": 0, "stuck": 0, "blocked": 1, "error": 0, "max_steps": 0},
        results=(_probe_result("orcus", "blocked"),),
    )

    passed, failures = evaluate_ci_gate(summary, expected_blocked_cards={"orcus"})

    assert passed is True
    assert failures == ()


def test_evaluate_ci_gate_fails_for_unexpected_blocked() -> None:
    summary = ProbeSummary(
        total_runs=1,
        status_counts={"ok": 0, "stuck": 0, "blocked": 1, "error": 0, "max_steps": 0},
        results=(_probe_result("orcus", "blocked"),),
    )

    passed, failures = evaluate_ci_gate(summary, expected_blocked_cards={"ambassador"})

    assert passed is False
    assert any("unexpected blocked cards" in failure for failure in failures)


def test_evaluate_ci_gate_fails_for_non_progress_statuses() -> None:
    summary = ProbeSummary(
        total_runs=3,
        status_counts={"ok": 0, "stuck": 1, "blocked": 0, "error": 1, "max_steps": 1},
        results=(
            _probe_result("ambassador", "stuck"),
            _probe_result("noble", "error"),
            _probe_result("orcus", "max_steps"),
        ),
    )

    passed, failures = evaluate_ci_gate(summary, expected_blocked_cards=set())

    assert passed is False
    assert any("non-progress statuses present" in failure for failure in failures)
