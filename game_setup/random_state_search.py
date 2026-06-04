"""Constrained random state search for exploratory testing."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from random import Random

from engine.moves import PlayCardMove, RecruitMove
from engine.rules import apply, legal_moves
from engine.state import GameState, build_initial_game_state


def _base_state_paths() -> tuple[Path, Path, Path]:
    base = Path(__file__).resolve().parents[1]
    return (
        base / "data" / "boards" / "base_game.json",
        base / "data" / "cards" / "catalog.json",
        base / "data" / "decks" / "base_setup.json",
    )


def _fresh_initial_state(
    player_ids: list[str] | None = None,
    seed: int = 0,
) -> GameState:
    from game_setup.loaders import create_game_state_from_files

    board_path, card_path, setup_path = _base_state_paths()
    return create_game_state_from_files(
        board_path=board_path,
        card_path=card_path,
        setup_path=setup_path,
        player_ids=player_ids or ["p1", "p2"],
        seed=seed,
    )


def find_state(
    predicate: Callable[[GameState], bool],
    *,
    seed: int = 0,
    max_steps: int = 500,
    player_ids: list[str] | None = None,
    initial_seed: int | None = None,
) -> GameState | None:
    """Walk random legal moves until a predicate matches, within a step budget.

    Returns the first matching state, or None if the budget is exhausted.
    Deterministic by seed.
    """
    init_seed = initial_seed if initial_seed is not None else seed
    rng = Random(seed)
    state = _fresh_initial_state(player_ids=player_ids, seed=init_seed)

    if predicate(state):
        return state

    for _ in range(max_steps):
        moves = list(legal_moves(state))
        if not moves:
            return None
        state = apply(state, rng.choice(moves))
        if predicate(state):
            return state

    return None


def find_state_and_save(
    predicate: Callable[[GameState], bool],
    save_path: Path,
    *,
    seed: int = 0,
    max_steps: int = 500,
    player_ids: list[str] | None = None,
    initial_seed: int | None = None,
    scenario_id: str = "generated",
    description: str = "",
) -> GameState | None:
    """Like find_state, but persist the result as a scenario fixture."""
    from game_setup.scenarios import save_game_state

    state = find_state(
        predicate,
        seed=seed,
        max_steps=max_steps,
        player_ids=player_ids,
        initial_seed=initial_seed,
    )
    if state is None:
        return None

    save_game_state(
        state,
        save_path,
        scenario_id=scenario_id,
        description=description or f"Generated with seed={seed}, max_steps={max_steps}",
        tags=["generated"],
    )
    return state


def generate_states(
    count: int,
    *,
    seed: int = 0,
    max_steps_per_state: int = 100,
    player_ids: list[str] | None = None,
    initial_seed: int | None = None,
) -> list[GameState]:
    """Generate `count` random valid states by walking legal moves.

    Each generated state is independent: a fresh initial state is created and
    walked for `max_steps_per_state` random moves.
    Deterministic by seed.
    """
    rng = Random(seed)
    result: list[GameState] = []

    for _ in range(count):
        init_seed = initial_seed if initial_seed is not None else rng.randint(0, 2**31 - 1)
        state = _fresh_initial_state(player_ids=player_ids, seed=init_seed)
        walk_steps = rng.randint(1, max_steps_per_state)
        for _ in range(walk_steps):
            moves = list(legal_moves(state))
            if not moves:
                break
            state = apply(state, rng.choice(moves))
        result.append(state)

    return result


# ---------------------------------------------------------------------------
# Common predicates for card testing
# ---------------------------------------------------------------------------


def has_card_in_hand(card_id: str, player_id: str = "p1") -> Callable[[GameState], bool]:
    """Return predicate: player has `card_id` in hand."""

    def predicate(state: GameState) -> bool:
        return card_id in state.players[player_id].hand

    return predicate


def has_card_in_market(card_id: str) -> Callable[[GameState], bool]:
    """Return predicate: `card_id` is in the market row."""

    def predicate(state: GameState) -> bool:
        return card_id in state.market.row

    return predicate


def has_enemy_troop_at_site(
    site_id: str, enemy_player_id: str, spy_player_id: str = "p1"
) -> Callable[[GameState], bool]:
    """Return predicate: enemy troop occupies a slot and friendly spy is present."""

    def predicate(state: GameState) -> bool:
        node = state.board.nodes[site_id]
        has_enemy = enemy_player_id in node.troop_slots
        has_spy = spy_player_id in node.spies
        return has_enemy and has_spy

    return predicate
