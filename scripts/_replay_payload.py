"""Replay payload builders for IS-MCTS runs. Pure helpers — no OpenSpiel imports.

Extracted from scripts/run_ismcts.py so the payload logic is testable
without pulling in pyspiel/numpy/structlog/tqdm.
"""

from __future__ import annotations

from pathlib import Path


def compute_final_scores(state) -> dict:
    """Backend-aware compute_final_scores.

    When ``state._adapter`` is present (C engine), delegates to the adapter.
    Otherwise calls ``engine.scoring.compute_final_scores`` on the wrapped state.
    """
    if hasattr(state, "_adapter") and state._adapter is not None:
        return state._adapter.final_scores()
    from engine.scoring import compute_final_scores as _py_compute_final_scores
    return _py_compute_final_scores(state._engine)


def resolve_winner_id(state, winner: int | None, num_players: int) -> str | None:
    """Backend-aware winner_id resolution.

    Prefers the C-engine adapter's ``winner()`` when available (authoritative),
    falling back to the OpenSpiel wrapper's ``get_player_ids()`` index lookup.
    """
    if winner is None:
        return None
    if hasattr(state, "_adapter") and state._adapter is not None:
        return state._adapter._engine.winner(state._adapter._state)
    return state._game.get_player_ids()[winner]


def build_replay_payload(
    *,
    run_id: str,
    stopped_reason: str,
    max_rounds: int,
    step_count: int,
    is_terminal: bool,
    winner_id: str | None,
    final_scores: dict,
    replay_log: list[dict],
    shuffle_seed: int,
    deck_a_id: str,
    deck_b_id: str,
    board_path: str,
    card_path: str,
    setup_path: str,
    player_ids: list[str],
    final_round_num: int = 0,
    final_phase: str = "",
    game_path: Path | None = None,
) -> dict:
    """Build the dict that gets serialised as replay.json.

    Mutates *replay_log* in place: appends a ``__terminal__`` marker entry when
    ``stopped_reason == "terminal"`` and ``is_terminal`` is true, so consumers
    have an explicit end-of-game boundary.
    """
    if stopped_reason == "terminal" and is_terminal:
        replay_log.append({
            "run_id": run_id,
            "step_index": step_count,
            "player_id": None,
            "round_number": final_round_num,
            "phase": final_phase,
            "prompts": [],
            "move_type": "__terminal__",
            "label": "game_over",
            "payload": {"move_type": "__terminal__"},
        })

    return {
        "run_id": run_id,
        "stopped_reason": stopped_reason,
        "max_rounds": max_rounds,
        "step_count": step_count,
        "is_terminal": is_terminal,
        "winner_id": winner_id,
        "final_scores": final_scores,
        "replay_log": replay_log,
        "replay_context": {
            "board_path": board_path,
            "card_path": card_path,
            "setup_path": setup_path,
            "player_ids": player_ids,
            "seed": shuffle_seed,
            "deck_a_id": deck_a_id,
            "deck_b_id": deck_b_id,
        },
    }
