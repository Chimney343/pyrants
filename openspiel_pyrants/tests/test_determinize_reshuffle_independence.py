"""F-002 Part A tests — determinization must decouple the shared mid-game
reshuffle/forced-discard RNG stream (``shuffle_seed``/``shuffle_counter``).

See ``docs/validation/f002-f003-fix-plan.md`` Part A. T-A3 is the RED test:
two ``resample_from_infostate`` calls from one info-state root must yield
different ``(shuffle_seed, shuffle_counter)`` pairs. T-A4/T-A5 are
due-diligence controls (reproducibility, market-deck regression) written
before the fix that could break them.
"""

from __future__ import annotations

import numpy as np
import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401


def _load_c_game(num_players: int = 2):
    return pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})


def _hetero_market_setup_json() -> str:
    import json

    return json.dumps(
        {
            "setup_id": "test_hetero_market",
            "starter_deck": {
                "deck_id": "starter_deck",
                "entries": [
                    {"card_id": "noble", "count": 7},
                    {"card_id": "soldier", "count": 3},
                ],
            },
            "market_deck": {
                "deck_id": "test_market",
                "entries": [
                    {"card_id": "noble", "count": 5},
                    {"card_id": "soldier", "count": 5},
                    {"card_id": "advance_scout", "count": 5},
                ],
            },
            "market_row_size": 6,
        }
    )


def _mid_game_state(game, shuffle_seed=42, n_moves=40):
    """A state a few plies past the initial chance node, with a live adapter."""
    state = game.new_initial_state()
    state.apply_action(shuffle_seed)
    rng = np.random.RandomState(shuffle_seed)
    for _ in range(n_moves):
        if state.is_terminal():
            break
        cp = state.current_player()
        if cp < 0:
            break
        legal = state.legal_actions()
        if not legal:
            break
        state.apply_action(int(rng.choice(legal)))
    return state


class TestDeterminizeReshuffleIndependence:
    def test_resample_from_infostate_decouples_reshuffle_stream(self, requires_c_engine):
        """T-A3 — two resamples of one info-set root must not share the stream."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        p = state.current_player()
        if p < 0:
            pytest.skip("game ended early")

        d1 = state.resample_from_infostate(p, np.random.RandomState(11))
        d2 = state.resample_from_infostate(p, np.random.RandomState(22))
        assert d1._adapter is not None
        assert d2._adapter is not None

        s1 = d1._adapter._state._s
        s2 = d2._adapter._state._s
        root = state._adapter._state._s

        assert (s1.shuffle_seed, s1.shuffle_counter) != (s2.shuffle_seed, s2.shuffle_counter)
        assert (s1.shuffle_seed, s1.shuffle_counter) != (root.shuffle_seed, root.shuffle_counter)
        assert (s2.shuffle_seed, s2.shuffle_counter) != (root.shuffle_seed, root.shuffle_counter)

    def test_resample_from_infostate_same_seed_reproducible(self, requires_c_engine):
        """T-A4 — same seed applied twice yields the identical stream (F-010 tie-in)."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        p = state.current_player()
        if p < 0:
            pytest.skip("game ended early")

        d1 = state.resample_from_infostate(p, np.random.RandomState(11))
        d2 = state.resample_from_infostate(p, np.random.RandomState(11))
        s1 = d1._adapter._state._s
        s2 = d2._adapter._state._s
        assert (s1.shuffle_seed, s1.shuffle_counter) == (s2.shuffle_seed, s2.shuffle_counter)

    def test_market_deck_reshuffle_unaffected(self, requires_c_engine):
        """T-A5 — the adjacent market-deck reshuffle keeps its multiset (GA4 guard)."""
        game = pyspiel.load_game(
            "python_pyrants_c",
            {"num_players": "2", "setup_data_json": _hetero_market_setup_json()},
        )
        state = game.new_initial_state()
        state.apply_action(42)
        p = state.current_player()
        assert p >= 0

        adapter = state._adapter
        original = adapter.state.market_deck()
        assert len(original) > 1

        d1 = state.resample_from_infostate(p, np.random.RandomState(11))
        d2 = state.resample_from_infostate(p, np.random.RandomState(22))

        assert sorted(d1._adapter.state.market_deck()) == sorted(original)
        assert sorted(d2._adapter.state.market_deck()) == sorted(original)
