"""Regression guard for the C rollout's placeholder-move defect.

``legal_pending_generic_choice_moves`` emits a placeholder MOVE_RESOLVE_GENERIC
move tagged ``target_id="unavailable"`` for every non-viable modal option, so
the Tkinter viewer can grey the option out; ``engine_apply`` refuses those same
moves.  ``engine_random_rollout`` used to sample uniformly from the unfiltered
``engine_legal_moves`` output, so at a mid-game position it picked a placeholder
most of the time, got NULL back and broke out of the loop a few steps in — 85-93%
of leaf evaluations returned a score for a barely-advanced state instead of a
played-out one.

The defect is invisible on ``data/decks/base_setup.json``: its 10-card market
(10x priestess_of_lolth) ends games in about four rounds, before the modal cards
whose options go non-viable are ever recruited.  These tests therefore build the
same two-deck 74-card market ``scripts/run_ismcts.py`` runs on, which is where
the defect actually bites.
"""

from __future__ import annotations

import json
from pathlib import Path
from random import Random

import numpy as np
import pytest

import pyspiel

import openspiel_pyrants  # noqa: F401  (registers python_pyrants_c)
from game_setup.market_setup import (
    combine_two_deck_market_setup,
    discover_full_deck_profiles,
    pick_random_pair,
)
from game_setup.scenario_generation.rosters import DEFAULT_ROSTERS_PATH

BASE_SETUP_PATH = Path(__file__).resolve().parents[2] / "data" / "decks" / "base_setup.json"


def _real_market_setup_json(seed: int = 42) -> str:
    """The market ``_build_ismcts_setup_json`` hands the runner, same seeding."""
    profiles = discover_full_deck_profiles(DEFAULT_ROSTERS_PATH)
    if len(profiles) < 2:
        pytest.skip("needs at least two full deck profiles")
    base = json.loads(BASE_SETUP_PATH.read_text(encoding="utf-8"))
    deck_a, deck_b = pick_random_pair(profiles, Random(seed))
    return json.dumps(combine_two_deck_market_setup(base, deck_a, deck_b).to_setup_data())


def _midgame_state(num_players: int, plies: int = 40, seed: int = 42):
    game = pyspiel.load_game(
        "python_pyrants_c",
        {"num_players": str(num_players), "setup_data_json": _real_market_setup_json(seed)},
    )
    state = game.new_initial_state()
    state.apply_action(seed)
    rng = np.random.RandomState(seed)
    for _ in range(plies):
        if state.is_terminal():
            break
        actions = state.legal_actions(state.current_player())
        if not actions:
            break
        state.apply_action(int(rng.choice(actions)))
    assert not state.is_terminal(), "fixture should still be mid-game"
    return state


@pytest.mark.parametrize("num_players", [2, 4])
def test_rollouts_reach_terminal_on_the_real_market(requires_c_engine, num_players):
    """Every unbounded rollout plays out. Before the fix: 22% at 4p, 26% at 2p."""
    state = _midgame_state(num_players)  # keep alive: __del__ frees the C state
    adapter = state._adapter
    terminal = sum(adapter.random_rollout(1000 + i, 0)[0] for i in range(30))
    assert terminal == 30, f"{30 - terminal}/30 rollouts aborted early"


def test_rollout_scores_vary(requires_c_engine):
    """Aborted rollouts all returned the same value; played-out ones spread out.

    A leaf evaluator whose every sample is identical tells UCT nothing, so the
    spread is the property that actually matters here, not just the flag.
    """
    state = _midgame_state(2)  # keep alive: __del__ frees the C state
    adapter = state._adapter
    margins = []
    for i in range(30):
        _terminal, scores = adapter.random_rollout(2000 + i, 0)
        p0, p1 = adapter.player_ids
        margins.append(scores[p0] - scores[p1])
    assert len(set(margins)) > 5, f"leaf values barely vary: {sorted(set(margins))}"


def test_legal_moves_still_report_placeholders(requires_c_engine):
    """The filter belongs to the consumers, not the generator.

    The viewer greys these options out, so they must keep coming back from
    ``legal_moves()``; it is the rollout and ``compute_c_action_map`` that drop
    them.  If this ever stops holding, the fix moved to the wrong layer.
    """
    state = _midgame_state(2, plies=40)
    rng = np.random.RandomState(7)
    seen = False
    for _ in range(2000):
        if state.is_terminal():
            break
        moves = state._adapter.legal_moves()
        if any(
            m.move_type == "resolve_generic" and m.data.get("target_id") == "unavailable"
            for m in moves
        ):
            seen = True
            break
        actions = state.legal_actions(state.current_player())
        state.apply_action(int(rng.choice(actions)))
    assert seen, "no placeholder move observed — fixture no longer covers the defect"
