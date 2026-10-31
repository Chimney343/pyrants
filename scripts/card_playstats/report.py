"""pandas aggregation layer for the card play post-mortem notebook.

Kept separate from :mod:`scripts.card_playstats.extract` so the extraction
path stays pandas-free (the core engine/RL install need not pull in the
``analysis`` extra). Importing this module requires pandas.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

import pandas as pd

from .catalog import CardCatalog
from .extract import GameExtraction
from .metadata import RunMetadata

_CARD_TABLE_COLUMNS = [
    "card_id",
    "recruited",
    "appeared_in_hand",
    "played",
    "is_modal",
    "play_rate_given_recruited",
    "draw_rate_given_recruited",
    "recruited_never_played",
    "recruited_never_drawn",
]


def _seen_card_ids(extractions: Iterable[GameExtraction]) -> set[str]:
    seen: set[str] = set()
    for extraction in extractions:
        seen.update(extraction.recruited)
        seen.update(extraction.played)
        seen.update(extraction.hand_appearances)
        seen.update(extraction.modal_played)
        seen.update(extraction.modal_choices)
    return seen


def build_card_table(extractions: list[GameExtraction], catalog: CardCatalog) -> pd.DataFrame:
    """Per-card recruited / appeared-in-hand / played totals across games."""
    recruited: Counter = Counter()
    appeared: Counter = Counter()
    played: Counter = Counter()
    for extraction in extractions:
        recruited.update(extraction.recruited)
        appeared.update(extraction.hand_appearances)
        played.update(extraction.played)

    rows = []
    for card_id in _seen_card_ids(extractions):
        n_recruited = recruited.get(card_id, 0)
        n_appeared = appeared.get(card_id, 0)
        n_played = played.get(card_id, 0)
        rows.append(
            {
                "card_id": card_id,
                "recruited": n_recruited,
                "appeared_in_hand": n_appeared,
                "played": n_played,
                "is_modal": catalog.is_modal(card_id),
                "play_rate_given_recruited": (n_played / n_recruited) if n_recruited else 0.0,
                "draw_rate_given_recruited": (n_appeared / n_recruited) if n_recruited else 0.0,
                "recruited_never_played": n_recruited > 0 and n_played == 0,
                "recruited_never_drawn": n_recruited > 0 and n_appeared == 0,
            }
        )

    table = pd.DataFrame(rows, columns=_CARD_TABLE_COLUMNS)
    if table.empty:
        return table
    return table.sort_values(
        ["recruited", "played", "card_id"], ascending=[False, False, True]
    ).reset_index(drop=True)


def build_modal_choice_frames(
    extractions: list[GameExtraction],
    catalog: CardCatalog,
    card_ids: Iterable[str],
) -> dict[str, pd.DataFrame]:
    """One option-frequency frame per modal card, including never-picked cards."""
    totals: dict[str, Counter] = {}
    for extraction in extractions:
        for card_id, counts in extraction.modal_choices.items():
            totals.setdefault(card_id, Counter()).update(counts)

    frames: dict[str, pd.DataFrame] = {}
    for card_id in sorted(set(card_ids)):
        counts = totals.get(card_id, Counter())
        total = sum(counts.values())
        rows = [
            {
                "option_id": option_id,
                "label": catalog.label_for(card_id, option_id),
                "count": counts.get(option_id, 0),
                "share": (counts.get(option_id, 0) / total) if total else 0.0,
            }
            for option_id in sorted(catalog.option_ids(card_id))
        ]
        frames[card_id] = pd.DataFrame(rows, columns=["option_id", "label", "count", "share"])
    return frames


def build_overview_frames(metadatas: list[RunMetadata]) -> dict[str, pd.DataFrame]:
    """Per-run overview frames; runs are surfaced separately, never blended."""
    config_rows = [{"run_id": meta.run_id, **meta.config} for meta in metadatas]
    summary_rows = [
        {
            "run_id": meta.run_id,
            "num_games": meta.num_games,
            "complete_games": meta.complete_games,
            "incomplete_games": meta.incomplete_games,
            "engine_git_sha": meta.engine_git_sha,
            "engine_git_dirty": meta.engine_git_dirty,
        }
        for meta in metadatas
    ]

    seats = sorted({seat for meta in metadatas for seat in meta.win_rate_by_seat})
    win_rate_rows = [
        {
            "run_id": meta.run_id,
            **{f"seat_{seat}": meta.win_rate_by_seat.get(seat, 0.0) for seat in seats},
        }
        for meta in metadatas
    ]

    matchup_rows = [
        {"run_id": meta.run_id, "matchup": matchup, "count": count}
        for meta in metadatas
        for matchup, count in sorted(meta.matchup_counts.items())
    ]

    diversity_rows = [
        {
            "run_id": meta.run_id,
            "full": meta.mean_deck_entropy.get("full", 0.0),
            "recruited": meta.mean_deck_entropy.get("recruited", 0.0),
        }
        for meta in metadatas
    ]

    length_rows = [
        {"run_id": meta.run_id, "decision_count": length}
        for meta in metadatas
        for length in meta.game_lengths
    ]

    score_rows = [
        {"run_id": meta.run_id, "player_id": player_id, "mean_score": mean_score}
        for meta in metadatas
        for player_id, mean_score in sorted(meta.mean_score_by_seat.items())
    ]

    return {
        "config": pd.DataFrame(config_rows),
        "summary": pd.DataFrame(summary_rows),
        "win_rate_by_seat": pd.DataFrame(win_rate_rows),
        "matchups": pd.DataFrame(matchup_rows),
        "deck_diversity": pd.DataFrame(diversity_rows),
        "game_lengths": pd.DataFrame(length_rows),
        "mean_scores": pd.DataFrame(score_rows),
    }
