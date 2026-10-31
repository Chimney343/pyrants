"""Per-run collection metadata for the play post-mortem.

Metadata is kept **per run**, never blended, when several folders with
different configs are selected: the overview surfaces each run's config,
completion, win rate by seat, deck matchups, score/length distributions,
move-type mix and deck diversity separately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .catalog import CardCatalog
from .discovery import RunFolder
from .extract import market_card_ids_from_setup


@dataclass
class RunMetadata:
    run_dir: str
    run_id: str
    config: dict
    engine_git_sha: str | None
    engine_git_dirty: bool | None
    num_games: int
    complete_games: int
    incomplete_games: int
    winner_counts_by_seat: dict[int, int]
    win_rate_by_seat: dict[int, float]
    matchup_counts: dict[str, int]
    deck_counts: dict[str, int]
    move_type_totals: dict[str, int]
    game_lengths: list[int]
    mean_score_by_seat: dict[str, float]
    mean_deck_entropy: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "run_dir": self.run_dir,
            "run_id": self.run_id,
            "config": dict(self.config),
            "engine_git_sha": self.engine_git_sha,
            "engine_git_dirty": self.engine_git_dirty,
            "num_games": self.num_games,
            "complete_games": self.complete_games,
            "incomplete_games": self.incomplete_games,
            "winner_counts_by_seat": {str(k): v for k, v in self.winner_counts_by_seat.items()},
            "win_rate_by_seat": {str(k): v for k, v in self.win_rate_by_seat.items()},
            "matchup_counts": dict(self.matchup_counts),
            "deck_counts": dict(self.deck_counts),
            "move_type_totals": dict(self.move_type_totals),
            "game_lengths": list(self.game_lengths),
            "mean_score_by_seat": dict(self.mean_score_by_seat),
            "mean_deck_entropy": dict(self.mean_deck_entropy),
        }

    @classmethod
    def from_dict(cls, data: dict) -> RunMetadata:
        return cls(
            run_dir=data["run_dir"],
            run_id=data.get("run_id", ""),
            config=dict(data.get("config") or {}),
            engine_git_sha=data.get("engine_git_sha"),
            engine_git_dirty=data.get("engine_git_dirty"),
            num_games=int(data.get("num_games", 0)),
            complete_games=int(data.get("complete_games", 0)),
            incomplete_games=int(data.get("incomplete_games", 0)),
            winner_counts_by_seat={
                int(k): int(v) for k, v in (data.get("winner_counts_by_seat") or {}).items()
            },
            win_rate_by_seat={
                int(k): float(v) for k, v in (data.get("win_rate_by_seat") or {}).items()
            },
            matchup_counts=dict(data.get("matchup_counts") or {}),
            deck_counts=dict(data.get("deck_counts") or {}),
            move_type_totals=dict(data.get("move_type_totals") or {}),
            game_lengths=[int(v) for v in (data.get("game_lengths") or [])],
            mean_score_by_seat=dict(data.get("mean_score_by_seat") or {}),
            mean_deck_entropy=dict(data.get("mean_deck_entropy") or {}),
        )


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def market_card_ids(run_folder: RunFolder) -> set[str]:
    """Every card_id that was eligible in the run's market decks.

    Reads ``manifest.games[].setup_data_json`` (the per-game market deck
    composition plus special stacks), so modal-card coverage can be read from
    the data rather than a hardcoded list.
    """
    card_ids: set[str] = set()
    for game in run_folder.manifest.get("games") or []:
        if not isinstance(game, dict):
            continue
        raw = game.get("setup_data_json")
        if isinstance(raw, str) and raw:
            card_ids.update(market_card_ids_from_setup(raw))
    return card_ids


def modal_market_card_ids(run_folders: list[RunFolder], catalog: CardCatalog) -> set[str]:
    """Modal cards that appeared in any selected run's market decks."""
    ids: set[str] = set()
    for folder in run_folders:
        ids |= {card_id for card_id in market_card_ids(folder) if catalog.is_modal(card_id)}
    return ids


def run_metadata(run_folder: RunFolder) -> RunMetadata:
    """Aggregate one run's completed games into :class:`RunMetadata`."""
    winner_counts: dict[int, int] = {}
    matchup_counts: dict[str, int] = {}
    deck_counts: dict[str, int] = {}
    move_type_totals: dict[str, int] = {}
    game_lengths: list[int] = []
    score_totals: dict[str, float] = {}
    score_counts: dict[str, int] = {}
    entropy_totals = {"full": 0.0, "recruited": 0.0}
    entropy_samples = {"full": 0, "recruited": 0}
    decided = 0
    num_players = 0

    for game_dir in run_folder.complete_game_dirs:
        summary = _read_json(game_dir / "summary.json")
        if summary is None:
            continue

        summary_players = summary.get("num_players")
        if isinstance(summary_players, int):
            num_players = max(num_players, summary_players)

        winner = summary.get("winner")
        if isinstance(winner, int):
            winner_counts[winner] = winner_counts.get(winner, 0) + 1
            decided += 1

        deck_a = summary.get("deck_a_id")
        deck_b = summary.get("deck_b_id")
        if isinstance(deck_a, str) and isinstance(deck_b, str):
            matchup_counts[f"{deck_a} vs {deck_b}"] = matchup_counts.get(f"{deck_a} vs {deck_b}", 0) + 1
        for deck_id in (deck_a, deck_b):
            if isinstance(deck_id, str):
                deck_counts[deck_id] = deck_counts.get(deck_id, 0) + 1

        counts = summary.get("move_type_counts")
        if isinstance(counts, dict):
            for move_type, value in counts.items():
                if isinstance(value, int):
                    move_type_totals[move_type] = move_type_totals.get(move_type, 0) + value

        decision_count = summary.get("decision_count")
        if isinstance(decision_count, int):
            game_lengths.append(decision_count)

        scores = summary.get("final_scores_per_player")
        if isinstance(scores, dict):
            for player_id, value in scores.items():
                if isinstance(value, (int, float)):
                    score_totals[str(player_id)] = score_totals.get(str(player_id), 0.0) + float(value)
                    score_counts[str(player_id)] = score_counts.get(str(player_id), 0) + 1

        metrics = summary.get("final_deck_metrics")
        if isinstance(metrics, list):
            for seat_metric in metrics:
                if not isinstance(seat_metric, dict):
                    continue
                for variant in ("full", "recruited"):
                    block = seat_metric.get(variant)
                    if isinstance(block, dict) and isinstance(block.get("shannon_entropy"), (int, float)):
                        entropy_totals[variant] += float(block["shannon_entropy"])
                        entropy_samples[variant] += 1

    configured_players = run_folder.config.get("num_players")
    if isinstance(configured_players, int):
        num_players = max(num_players, configured_players)

    win_rate = (
        {seat: winner_counts.get(seat, 0) / decided for seat in range(num_players)}
        if decided
        else {}
    )
    mean_score = {
        player_id: score_totals[player_id] / score_counts[player_id]
        for player_id in score_totals
        if score_counts.get(player_id)
    }
    mean_entropy = {
        variant: entropy_totals[variant] / entropy_samples[variant]
        for variant in ("full", "recruited")
        if entropy_samples[variant]
    }

    return RunMetadata(
        run_dir=str(run_folder.run_dir),
        run_id=run_folder.run_id,
        config=run_folder.config,
        engine_git_sha=run_folder.manifest.get("engine_git_sha"),
        engine_git_dirty=run_folder.manifest.get("engine_git_dirty"),
        num_games=len(run_folder.game_dirs),
        complete_games=len(run_folder.complete_game_dirs),
        incomplete_games=len(run_folder.incomplete_game_dirs),
        winner_counts_by_seat=winner_counts,
        win_rate_by_seat=win_rate,
        matchup_counts=matchup_counts,
        deck_counts=deck_counts,
        move_type_totals=move_type_totals,
        game_lengths=game_lengths,
        mean_score_by_seat=mean_score,
        mean_deck_entropy=mean_entropy,
    )


def metadata_for_selection(run_folders: list[RunFolder]) -> list[RunMetadata]:
    """Per-run metadata, unblended, for every selected folder."""
    return [run_metadata(folder) for folder in run_folders]
