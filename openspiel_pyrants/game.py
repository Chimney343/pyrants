"""PyrantsGame(pyspiel.Game) — registers pyrants as ``python_pyrants``.

Two-player, base game, base board, EXPLICIT_STOCHASTIC (single chance node for
the initial shuffle seed).  No observer in this first pass.
"""

from __future__ import annotations

from pathlib import Path

import pyspiel

from game_setup.loaders import build_game_definition_from_files
from openspiel_pyrants.action_encoding import NUM_DISTINCT_ACTIONS

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_DEFAULT_BOARD = _DATA_DIR / "boards" / "tyrants_of_the_underdark.json"
_DEFAULT_CARDS = _DATA_DIR / "cards" / "catalog.json"
_DEFAULT_SETUP = _DATA_DIR / "decks" / "base_setup.json"

_DEFAULT_PARAMS = {
    "board_path": str(_DEFAULT_BOARD),
    "card_path": str(_DEFAULT_CARDS),
    "setup_path": str(_DEFAULT_SETUP),
    "player_ids": "p0:p1",
    "shuffle_seed_count": 1000,
}

_GAME_TYPE = pyspiel.GameType(
    short_name="python_pyrants",
    long_name="Python Tyrants of the Underdark",
    dynamics=pyspiel.GameType.Dynamics.SEQUENTIAL,
    chance_mode=pyspiel.GameType.ChanceMode.EXPLICIT_STOCHASTIC,
    information=pyspiel.GameType.Information.IMPERFECT_INFORMATION,
    utility=pyspiel.GameType.Utility.ZERO_SUM,
    reward_model=pyspiel.GameType.RewardModel.TERMINAL,
    max_num_players=2,
    min_num_players=2,
    provides_information_state_string=True,
    provides_information_state_tensor=False,
    provides_observation_string=True,
    provides_observation_tensor=False,
    parameter_specification={
        "board_path": str(_DEFAULT_BOARD),
        "card_path": str(_DEFAULT_CARDS),
        "setup_path": str(_DEFAULT_SETUP),
        "player_ids": "p0:p1",
        "shuffle_seed_count": 1000,
    },
)

_GAME_INFO = pyspiel.GameInfo(
    num_distinct_actions=NUM_DISTINCT_ACTIONS,
    max_chance_outcomes=1000,
    num_players=2,
    min_utility=-200.0,
    max_utility=200.0,
    utility_sum=0.0,
    max_game_length=4096,
)


class PyrantsGame(pyspiel.Game):
    def __init__(self, params=None):
        super().__init__(_GAME_TYPE, _GAME_INFO, params or dict())
        resolved = dict(_DEFAULT_PARAMS)
        resolved.update(self.get_parameters())
        self._params = resolved

        self._definition = build_game_definition_from_files(
            Path(resolved["board_path"]),
            Path(resolved["card_path"]),
            Path(resolved["setup_path"]),
        )
        self._player_ids = tuple(
            pid.strip() for pid in resolved["player_ids"].split(":") if pid.strip()
        )
        self._shuffle_seed_count = int(resolved["shuffle_seed_count"])

    def __deepcopy__(self, memo):
        cls = type(self)
        new_game = cls.__new__(cls)
        new_game.__init__(self.get_parameters())
        memo[id(self)] = new_game
        return new_game

    def _init_attrs(self):
        if not hasattr(self, "_player_ids"):
            resolved = dict(_DEFAULT_PARAMS)
            resolved.update(self.get_parameters())
            self._params = resolved
            self._definition = build_game_definition_from_files(
                Path(resolved["board_path"]),
                Path(resolved["card_path"]),
                Path(resolved["setup_path"]),
            )
            self._player_ids = tuple(
                pid.strip() for pid in resolved["player_ids"].split(":") if pid.strip()
            )
            self._shuffle_seed_count = int(resolved["shuffle_seed_count"])

    def get_definition(self):
        self._init_attrs()
        return self._definition

    def get_player_ids(self):
        self._init_attrs()
        return self._player_ids

    def get_shuffle_seed_count(self):
        self._init_attrs()
        return self._shuffle_seed_count

    def new_initial_state(self):
        from openspiel_pyrants.state import PyrantsState

        return PyrantsState(self)

    def make_py_observer(self, iig_obs_type=None, params=None):
        from openspiel_pyrants.observer import PyrantsObserver

        return PyrantsObserver(params)
