"""PyrantsCGame(pyspiel.Game) — registers the C-engine backend as ``python_pyrants_c``.

Mirrors ``game.py`` but creates ``PyrantsCState`` and holds a ``CEngine`` instance.
"""

from __future__ import annotations

from pathlib import Path

import pyspiel

from engine_c.bindings.ce_api import CEngine
from openspiel_pyrants.action_encoding_c import NUM_DISTINCT_ACTIONS

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_DEFAULT_BOARD = _DATA_DIR / "boards" / "tyrants_of_the_underdark.json"
_DEFAULT_CARDS = _DATA_DIR / "cards" / "catalog.json"
_DEFAULT_SETUP = _DATA_DIR / "decks" / "base_setup.json"

_DEFAULT_PARAMS = {
    "board_path": str(_DEFAULT_BOARD),
    "card_path": str(_DEFAULT_CARDS),
    "setup_path": str(_DEFAULT_SETUP),
    "setup_data_json": "",
    "player_ids": "p0:p1",
    "shuffle_seed_count": 1000,
    "num_players": "2",
}

_LEGACY_PLAYER_IDS = _DEFAULT_PARAMS["player_ids"]


def _build_c_game_type(num_players: int) -> pyspiel.GameType:
    utility = (
        pyspiel.GameType.Utility.ZERO_SUM
        if num_players == 2
        else pyspiel.GameType.Utility.GENERAL_SUM
    )
    return pyspiel.GameType(
        short_name="python_pyrants_c",
        long_name="Pyrants (C engine) — Tyrants of the Underdark",
        dynamics=pyspiel.GameType.Dynamics.SEQUENTIAL,
        chance_mode=pyspiel.GameType.ChanceMode.EXPLICIT_STOCHASTIC,
        information=pyspiel.GameType.Information.IMPERFECT_INFORMATION,
        utility=utility,
        reward_model=pyspiel.GameType.RewardModel.TERMINAL,
        max_num_players=4,
        min_num_players=2,
        provides_information_state_string=True,
        provides_information_state_tensor=False,
        provides_observation_string=True,
        provides_observation_tensor=False,
        parameter_specification={
            "board_path": str(_DEFAULT_BOARD),
            "card_path": str(_DEFAULT_CARDS),
            "setup_path": str(_DEFAULT_SETUP),
            "setup_data_json": "",
            "player_ids": _LEGACY_PLAYER_IDS,
            "shuffle_seed_count": 1000,
            "num_players": "2",
        },
    )


def _build_c_game_info(num_players: int) -> pyspiel.GameInfo:
    max_utility = 200.0 if num_players == 2 else 400.0
    return pyspiel.GameInfo(
        num_distinct_actions=NUM_DISTINCT_ACTIONS,
        max_chance_outcomes=1000,
        num_players=num_players,
        min_utility=-max_utility,
        max_utility=max_utility,
        utility_sum=0.0,
        max_game_length=4096,
    )


def _resolve_player_ids(resolved: dict, num_players: int) -> tuple[str, ...]:
    player_ids_raw: str = resolved.get("player_ids", "")
    if player_ids_raw and player_ids_raw != _LEGACY_PLAYER_IDS:
        player_ids = tuple(pid.strip() for pid in player_ids_raw.split(":") if pid.strip())
        if len(player_ids) != num_players:
            raise ValueError(
                f"player_ids length {len(player_ids)} != num_players {num_players}"
            )
        return player_ids
    return tuple(f"p{i}" for i in range(1, num_players + 1))


def _parse_num_players(resolved: dict) -> int:
    num_players = int(resolved.get("num_players", 2))
    if not (2 <= num_players <= 4):
        raise ValueError(f"num_players must be 2–4, got {num_players}")
    return num_players


class PyrantsCGame(pyspiel.Game):
    def __init__(self, params=None):
        resolved = dict(_DEFAULT_PARAMS)
        resolved.update(params or dict())

        num_players = _parse_num_players(resolved)
        player_ids = _resolve_player_ids(resolved, num_players)

        game_type = _build_c_game_type(num_players)
        game_info = _build_c_game_info(num_players)
        super().__init__(game_type, game_info, resolved)

        self._params = resolved
        self._player_ids = player_ids
        self._num_players = num_players
        self._shuffle_seed_count = int(resolved["shuffle_seed_count"])

        self._c_engine = CEngine()
        self._c_engine.initialize(
            catalog_path=resolved["card_path"],
            board_path=resolved["board_path"],
            setup_path=resolved["setup_path"],
            setup_data_json=resolved.get("setup_data_json", ""),
        )

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
            self._num_players = _parse_num_players(resolved)
            self._player_ids = _resolve_player_ids(resolved, self._num_players)
            self._shuffle_seed_count = int(resolved["shuffle_seed_count"])
            self._c_engine = CEngine()
            self._c_engine.initialize(
                catalog_path=resolved["card_path"],
                board_path=resolved["board_path"],
                setup_path=resolved["setup_path"],
            )

    def get_definition(self):
        return None

    def get_player_ids(self):
        self._init_attrs()
        return self._player_ids

    def get_shuffle_seed_count(self):
        self._init_attrs()
        return self._shuffle_seed_count

    def new_initial_state(self):
        from openspiel_pyrants.state_c import PyrantsCState

        return PyrantsCState(self)

    def make_py_observer(self, iig_obs_type=None, params=None):
        from openspiel_pyrants.observer_c import PyrantsCObserver

        return PyrantsCObserver(params)
