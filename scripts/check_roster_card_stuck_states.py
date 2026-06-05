"""Probe each roster card for non-terminal no-legal-move stuck states.

This checker guarantees every roster card is actually played at least once
by injecting the card into the active player's hand in a real seeded session.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from typing import Iterable, Literal

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.errors import IllegalMoveError, MissingRuleImplementationError, RuleViolationError, UnknownCardEffectError
from engine.moves import EndMainPhaseMove, Move, PlayCardMove
from engine.rules import apply
from game_session import GameSession
from game_view import build_game_view
DEFAULT_BOARD_PATH = ROOT_DIR / "data" / "boards" / "base_game.json"
DEFAULT_CARD_PATH = ROOT_DIR / "data" / "cards" / "catalog.json"
DEFAULT_SETUP_PATH = ROOT_DIR / "data" / "decks" / "base_setup.json"
DEFAULT_ROSTERS_PATH = ROOT_DIR / "data" / "decks" / "first_deck_rosters.json"
DEFAULT_JSON_OUT = ROOT_DIR / "artifacts" / "card_stuck_report.json"

ProbeStatus = Literal["ok", "stuck", "blocked", "error", "max_steps"]


@dataclass(frozen=True)
class ProbeResult:
    """Outcome for one card/seed probe run."""

    card_id: str
    seed: int
    status: ProbeStatus
    stopped_reason: str
    step_count: int
    phase: str
    current_player_id: str
    prompts: tuple[str, ...]
    trace: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class ProbeSummary:
    """Aggregated report payload."""

    total_runs: int
    status_counts: dict[str, int]
    results: tuple[ProbeResult, ...]


def iter_roster_card_ids(rosters_path: Path, *, include_duplicates: bool = False) -> list[str]:
    """Return card ids from roster decks in deterministic order."""

    payload = json.loads(rosters_path.read_text(encoding="utf-8"))
    decks = payload.get("decks")
    if not isinstance(decks, list):
        raise ValueError("rosters payload must contain a decks list")

    card_ids: list[str] = []
    seen: set[str] = set()

    for deck in decks:
        if not isinstance(deck, dict):
            continue
        entries = deck.get("entries", [])
        if not isinstance(entries, list):
            continue

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            card_id = str(entry.get("card_id", "")).strip()
            if not card_id:
                continue
            if include_duplicates:
                card_ids.append(card_id)
                continue
            if card_id in seen:
                continue
            seen.add(card_id)
            card_ids.append(card_id)

    return card_ids


def _seed_probe_session_for_card(
    card_id: str,
    *,
    board_path: Path,
    card_path: Path,
    setup_path: Path,
    seed: int,
    players: tuple[str, str] = ("p1", "p2"),
) -> GameSession:
    """Create deterministic game session and bias it toward legal action coverage."""

    session = GameSession.from_files(
        board_path=board_path,
        card_path=card_path,
        setup_path=setup_path,
        player_ids=players,
        seed=seed,
    )

    state = session.state
    active_id = state.current_player_id
    opponent_ids = [player_id for player_id in state.turn_order if player_id != active_id]
    opponent_id = opponent_ids[0] if opponent_ids else active_id

    active = state.players[active_id]
    opponent = state.players[opponent_id]

    # Ensure target card can be played and many action types have legal targets.
    active.hand = [card_id]
    active.deck = []
    active.discard_pile = []
    active.played_cards = []
    active.inner_circle = []
    active.barracks = max(active.barracks, 8)
    active.spies_available = max(active.spies_available, 2)

    state.resource_pool.power = 20
    state.resource_pool.influence = 20

    if not opponent.hand:
        opponent.hand = ["noble", "soldier"]

    for node in state.board.nodes.values():
        if node.troop_slots and all(slot_owner is None for slot_owner in node.troop_slots):
            node.troop_slots[0] = opponent_id
        node.spies.add(opponent_id)

    return session


def _select_progress_move(session: GameSession, ended_main_phase: bool) -> Move | None:
    """Pick deterministic progression move to resolve post-play consequences."""

    view = build_game_view(session)
    legal = view.legal_moves
    if not legal:
        return None

    priorities = (
        "resolve_generic_choice",
        "activate_card_ability",
        "decline_card_ability",
        "promote_card",
        "skip_promote",
        "resolve_end_of_turn",
        "resolve_cleanup",
    )

    for move_type in priorities:
        for legal_move in legal:
            if legal_move.move_type == move_type:
                return legal_move.move

    if not ended_main_phase and view.phase == "main":
        for legal_move in legal:
            if isinstance(legal_move.move, EndMainPhaseMove):
                return legal_move.move

    return None


def _probe_one_card(
    card_id: str,
    *,
    board_path: Path,
    card_path: Path,
    setup_path: Path,
    seed: int,
    max_steps: int,
) -> ProbeResult:
    trace: list[str] = []
    try:
        session = _seed_probe_session_for_card(
            card_id,
            board_path=board_path,
            card_path=card_path,
            setup_path=setup_path,
            seed=seed,
        )

        initial_view = build_game_view(session)
        play_move = next(
            (
                legal_move.move
                for legal_move in initial_view.legal_moves
                if isinstance(legal_move.move, PlayCardMove) and legal_move.move.card_id == card_id
            ),
            None,
        )
        if play_move is None:
            return ProbeResult(
                card_id=card_id,
                seed=seed,
                status="blocked",
                stopped_reason="play_move_not_legal",
                step_count=0,
                phase=initial_view.phase,
                current_player_id=initial_view.current_player_id,
                prompts=initial_view.prompts,
                trace=tuple(trace),
            )

        session.submit_move(play_move)
        trace.append(f"play_card:{card_id}")

        ended_main_phase = False
        for _ in range(max_steps):
            view = build_game_view(session)
            if view.is_terminal:
                return ProbeResult(
                    card_id=card_id,
                    seed=seed,
                    status="ok",
                    stopped_reason="terminal",
                    step_count=session.move_count,
                    phase=view.phase,
                    current_player_id=view.current_player_id,
                    prompts=view.prompts,
                    trace=tuple(trace[-12:]),
                )

            if not view.legal_moves:
                return ProbeResult(
                    card_id=card_id,
                    seed=seed,
                    status="stuck",
                    stopped_reason="non_terminal_no_legal_moves",
                    step_count=session.move_count,
                    phase=view.phase,
                    current_player_id=view.current_player_id,
                    prompts=view.prompts,
                    trace=tuple(trace[-12:]),
                )

            move = _select_progress_move(session, ended_main_phase)
            if move is None:
                return ProbeResult(
                    card_id=card_id,
                    seed=seed,
                    status="ok",
                    stopped_reason="stable_state",
                    step_count=session.move_count,
                    phase=view.phase,
                    current_player_id=view.current_player_id,
                    prompts=view.prompts,
                    trace=tuple(trace[-12:]),
                )

            if isinstance(move, EndMainPhaseMove):
                ended_main_phase = True

            trace.append(move.move_type)
            session.submit_move(move)

            after_view = build_game_view(session)
            if ended_main_phase and after_view.phase == "main" and after_view.current_player_id != initial_view.current_player_id:
                return ProbeResult(
                    card_id=card_id,
                    seed=seed,
                    status="ok",
                    stopped_reason="turn_completed",
                    step_count=session.move_count,
                    phase=after_view.phase,
                    current_player_id=after_view.current_player_id,
                    prompts=after_view.prompts,
                    trace=tuple(trace[-12:]),
                )

        final_view = build_game_view(session)
        return ProbeResult(
            card_id=card_id,
            seed=seed,
            status="max_steps",
            stopped_reason="resolution_budget_exhausted",
            step_count=session.move_count,
            phase=final_view.phase,
            current_player_id=final_view.current_player_id,
            prompts=final_view.prompts,
            trace=tuple(trace[-12:]),
        )

    except (MissingRuleImplementationError, UnknownCardEffectError) as error:
        fallback_view = build_game_view(session) if "session" in locals() else None
        return ProbeResult(
            card_id=card_id,
            seed=seed,
            status="blocked",
            stopped_reason="engine_not_implemented",
            step_count=session.move_count if "session" in locals() else 0,
            phase=fallback_view.phase if fallback_view is not None else "unknown",
            current_player_id=fallback_view.current_player_id if fallback_view is not None else "unknown",
            prompts=fallback_view.prompts if fallback_view is not None else tuple(),
            trace=tuple(trace[-12:]),
            error=str(error),
        )
    except (IllegalMoveError, RuleViolationError, ValueError) as error:
        fallback_view = build_game_view(session) if "session" in locals() else None
        return ProbeResult(
            card_id=card_id,
            seed=seed,
            status="error",
            stopped_reason="probe_exception",
            step_count=session.move_count if "session" in locals() else 0,
            phase=fallback_view.phase if fallback_view is not None else "unknown",
            current_player_id=fallback_view.current_player_id if fallback_view is not None else "unknown",
            prompts=fallback_view.prompts if fallback_view is not None else tuple(),
            trace=tuple(trace[-12:]),
            error=str(error),
        )


def run_probe(
    *,
    board_path: Path,
    card_path: Path,
    setup_path: Path,
    rosters_path: Path,
    seed: int,
    seed_count: int,
    max_steps: int,
    include_duplicates: bool,
    card_id: str | None,
) -> ProbeSummary:
    """Run probe over roster card ids and return report payload."""

    roster_card_ids = iter_roster_card_ids(rosters_path, include_duplicates=include_duplicates)
    if card_id is not None:
        roster_card_ids = [candidate for candidate in roster_card_ids if candidate == card_id]
        if not roster_card_ids:
            raise ValueError(f"Requested card_id '{card_id}' is not present in roster")

    results: list[ProbeResult] = []
    for card_index, target_card_id in enumerate(roster_card_ids):
        for seed_offset in range(max(seed_count, 1)):
            run_seed = seed + (card_index * max(seed_count, 1)) + seed_offset
            results.append(
                _probe_one_card(
                    target_card_id,
                    board_path=board_path,
                    card_path=card_path,
                    setup_path=setup_path,
                    seed=run_seed,
                    max_steps=max_steps,
                )
            )

    counts = Counter(result.status for result in results)
    return ProbeSummary(
        total_runs=len(results),
        status_counts={
            "ok": counts.get("ok", 0),
            "stuck": counts.get("stuck", 0),
            "blocked": counts.get("blocked", 0),
            "error": counts.get("error", 0),
            "max_steps": counts.get("max_steps", 0),
        },
        results=tuple(results),
    )


def summary_to_json_payload(summary: ProbeSummary) -> dict[str, object]:
    """Convert summary dataclass to JSON-serializable mapping."""

    return {
        "total_runs": summary.total_runs,
        "status_counts": dict(summary.status_counts),
        "results": [asdict(result) for result in summary.results],
    }


def _normalize_card_ids(card_ids: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for card_id in card_ids:
        candidate = card_id.strip()
        if candidate:
            normalized.add(candidate)
    return normalized


def _parse_csv_card_ids(raw: str) -> set[str]:
    if not raw.strip():
        return set()
    return _normalize_card_ids(raw.split(","))


def evaluate_ci_gate(
    summary: ProbeSummary,
    *,
    expected_blocked_cards: set[str] | None = None,
    fail_on_unexpected_blocked: bool = True,
) -> tuple[bool, tuple[str, ...]]:
    """Return CI pass/fail verdict and failure reasons for a probe summary."""

    expected_blocked = expected_blocked_cards or set()
    failures: list[str] = []

    stuck_count = summary.status_counts.get("stuck", 0)
    error_count = summary.status_counts.get("error", 0)
    max_steps_count = summary.status_counts.get("max_steps", 0)
    if stuck_count or error_count or max_steps_count:
        failures.append(
            "non-progress statuses present: "
            f"stuck={stuck_count}, error={error_count}, max_steps={max_steps_count}"
        )

    blocked_cards = {result.card_id for result in summary.results if result.status == "blocked"}
    unexpected_blocked = sorted(blocked_cards - expected_blocked)
    if fail_on_unexpected_blocked and unexpected_blocked:
        failures.append(
            "unexpected blocked cards: " + ", ".join(unexpected_blocked)
        )

    return (len(failures) == 0, tuple(failures))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe roster cards for stuck-state behavior")
    parser.add_argument("--rosters-path", type=Path, default=DEFAULT_ROSTERS_PATH)
    parser.add_argument("--board-path", type=Path, default=DEFAULT_BOARD_PATH)
    parser.add_argument("--card-path", type=Path, default=DEFAULT_CARD_PATH)
    parser.add_argument("--setup-path", type=Path, default=DEFAULT_SETUP_PATH)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--seed-count", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=120)
    parser.add_argument("--include-duplicates", action="store_true")
    parser.add_argument("--card-id")
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Exit non-zero when stuck/error/max_steps occur or blocked cards are unexpected.",
    )
    parser.add_argument(
        "--expected-blocked-cards",
        default="",
        help="Comma-separated blocked card ids that are expected and allowed in CI mode.",
    )
    parser.add_argument(
        "--allow-unexpected-blocked",
        action="store_true",
        help="In CI mode, do not fail when blocked cards are outside the expected list.",
    )
    return parser.parse_args()


def main() -> None:
    """Run card stuck probe and emit console summary + JSON report."""

    args = _parse_args()
    summary = run_probe(
        board_path=args.board_path,
        card_path=args.card_path,
        setup_path=args.setup_path,
        rosters_path=args.rosters_path,
        seed=args.seed,
        seed_count=args.seed_count,
        max_steps=args.max_steps,
        include_duplicates=args.include_duplicates,
        card_id=args.card_id,
    )

    payload = summary_to_json_payload(summary)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    counts = summary.status_counts
    print(
        " | ".join(
            [
                f"runs={summary.total_runs}",
                f"ok={counts['ok']}",
                f"stuck={counts['stuck']}",
                f"blocked={counts['blocked']}",
                f"error={counts['error']}",
                f"max_steps={counts['max_steps']}",
            ]
        )
    )
    print(f"report={args.json_out}")

    if args.ci:
        expected_blocked_cards = _parse_csv_card_ids(args.expected_blocked_cards)
        passed, failures = evaluate_ci_gate(
            summary,
            expected_blocked_cards=expected_blocked_cards,
            fail_on_unexpected_blocked=not args.allow_unexpected_blocked,
        )
        if passed:
            print("ci=pass")
            return

        for failure in failures:
            print(f"ci=fail | {failure}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
