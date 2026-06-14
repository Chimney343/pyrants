"""Card-scenario generation: search and force-injection workflow."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from random import Random
from typing import Any

from engine.moves import InitialPlacementMove, PlayCardMove, RecruitMove
from engine.rules import apply, is_terminal, legal_moves
from engine.state import (
    BoardDefinition,
    CardCatalog,
    GameDefinition,
    GameState,
    SetupDefinition,
    TurnPhase,
    build_initial_game_state,
)
from game_setup.loaders import load_deck_rosters
from game_setup.market_setup import (
    SPECIAL_RECRUIT_IDS,
    DeckProfile,
    combine_two_deck_market_setup,
    compute_special_stacks,
    discover_full_deck_profiles,
    pick_pair_for_target,
)
from game_setup.scenarios import save_game_state

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOARD_PATH = ROOT / "data" / "boards" / "tyrants_of_the_underdark.json"
DEFAULT_CARD_PATH = ROOT / "data" / "cards" / "catalog.json"
DEFAULT_SETUP_PATH = ROOT / "data" / "decks" / "base_setup.json"
DEFAULT_ROSTERS_PATH = ROOT / "data" / "decks"
FORCED_INJECTIONS_FILENAME = "forced_injections.json"


def _stable_hash(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")


def _resolve_two_deck_pairing(
    *,
    rosters_path: Path,
    target_card_id: str,
    base_seed: int,
) -> tuple[str, str, list[str]]:
    profiles = discover_full_deck_profiles(rosters_path)
    if not profiles:
        raise ValueError("No full_deck rosters found for market construction")

    pair_rng = Random(base_seed ^ _stable_hash(target_card_id))
    deck_a, deck_b = pick_pair_for_target(profiles, target_card_id, pair_rng)
    roster_a_id = deck_a.deck_id
    roster_b_id = deck_b.deck_id
    special_stacks = list(compute_special_stacks(roster_a_id, roster_b_id))
    return roster_a_id, roster_b_id, special_stacks


def _json_loads(text: str) -> Any:
    try:
        import orjson
        return orjson.loads(text)
    except ImportError:
        return json.loads(text)


@lru_cache(maxsize=4)
def _cached_board(board_path_str: str) -> BoardDefinition:
    return BoardDefinition.model_validate(_json_loads(Path(board_path_str).read_text(encoding="utf-8")))


@lru_cache(maxsize=4)
def _cached_catalog(card_path_str: str) -> CardCatalog:
    return CardCatalog.model_validate(_json_loads(Path(card_path_str).read_text(encoding="utf-8")))


@lru_cache(maxsize=4)
def _cached_base_setup(setup_path_str: str) -> dict[str, Any]:
    return _json_loads(Path(setup_path_str).read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def _cached_roster_decks(rosters_path_str: str) -> list[dict[str, Any]]:
    return load_deck_rosters(Path(rosters_path_str))


@lru_cache(maxsize=4)
def _cached_starter_deck_ids(setup_path_str: str) -> frozenset[str]:
    base_setup = _cached_base_setup(setup_path_str)
    return frozenset({
        str(entry.get("card_id", "")).strip()
        for entry in base_setup.get("starter_deck", {}).get("entries", ())
        if isinstance(entry, dict)
    })


def iter_roster_card_ids(decks_dir: Path) -> list[str]:
    """Return unique card ids from roster decks in deterministic order."""
    decks = _cached_roster_decks(str(decks_dir))
    if not decks:
        raise ValueError(f"No deck roster files found in {decks_dir}")
    card_ids: list[str] = []
    seen: set[str] = set()
    for deck in decks:
        for entry in deck.get("entries", ()):
            if not isinstance(entry, dict):
                continue
            card_id = str(entry.get("card_id", "")).strip()
            if not card_id or card_id in seen:
                continue
            seen.add(card_id)
            card_ids.append(card_id)
    return card_ids


def _build_card_scenario_setup(
    *,
    board_path: Path = DEFAULT_BOARD_PATH,
    card_path: Path = DEFAULT_CARD_PATH,
    setup_path: Path = DEFAULT_SETUP_PATH,
    rosters_path: Path = DEFAULT_ROSTERS_PATH,
    player_ids: list[str],
    seed: int,
    roster_a_id: str,
    roster_b_id: str,
) -> GameState:
    """Build an initial state with the specified two-deck market."""
    board = _cached_board(str(board_path))
    catalog = _cached_catalog(str(card_path))
    base_setup_data = _cached_base_setup(str(setup_path))

    profiles = discover_full_deck_profiles(rosters_path)
    profile_map: dict[str, DeckProfile] = {p.deck_id: p for p in profiles}

    deck_a = profile_map.get(roster_a_id)
    deck_b = profile_map.get(roster_b_id)
    if deck_a is None or deck_b is None:
        raise ValueError(f"Deck profile not found: {roster_a_id=}, {roster_b_id=}")

    market_setup = combine_two_deck_market_setup(base_setup_data, deck_a, deck_b)
    setup_data = market_setup.to_setup_data()
    setup_data["setup_id"] = "card_scenario_setup"

    setup_definition = SetupDefinition.model_validate(setup_data)
    definition = GameDefinition(
        definition_id="card_scenario",
        board=board,
        catalog=catalog,
        setup=setup_definition,
    )
    return build_initial_game_state(definition, player_ids, shuffle_seed=seed)


def _build_card_scenario_setup_legacy(
    *,
    board_path: Path = DEFAULT_BOARD_PATH,
    card_path: Path = DEFAULT_CARD_PATH,
    setup_path: Path = DEFAULT_SETUP_PATH,
    rosters_path: Path = DEFAULT_ROSTERS_PATH,
    player_ids: list[str],
    seed: int,
    target_card_id: str | None = None,
) -> GameState:
    """Build an initial state with roster market coverage (legacy filter policy).

    If `target_card_id` is provided, only roster decks containing that card
    are included in the market. For special-recruit cards a fallback deck is used.
    """
    board = _cached_board(str(board_path))
    catalog = _cached_catalog(str(card_path))
    base_setup_data = _cached_base_setup(str(setup_path))
    roster_decks = _cached_roster_decks(str(rosters_path))
    starter_deck_ids = _cached_starter_deck_ids(str(setup_path))

    combined: dict[str, int] = {}
    for deck in roster_decks:
        if not isinstance(deck, dict) or deck.get("kind") != "full_deck":
            continue
        if (
            target_card_id is not None
            and target_card_id not in SPECIAL_RECRUIT_IDS
            and target_card_id not in starter_deck_ids
        ):
            deck_card_ids = {
                str(entry.get("card_id", "")).strip()
                for entry in deck.get("entries", ())
                if isinstance(entry, dict)
            }
            if target_card_id not in deck_card_ids:
                continue
        for entry in deck.get("entries", ()):
            if not isinstance(entry, dict):
                continue
            card_id = str(entry.get("card_id", "")).strip()
            count = int(entry.get("count", 0))
            if card_id and count > 0:
                combined[card_id] = combined.get(card_id, 0) + count

    if not combined:
        first_deck = roster_decks[0] if roster_decks else None
        if first_deck and isinstance(first_deck, dict) and first_deck.get("kind") == "full_deck":
            for entry in first_deck.get("entries", ()):
                if not isinstance(entry, dict):
                    continue
                card_id = str(entry.get("card_id", "")).strip()
                count = int(entry.get("count", 0))
                if card_id and count > 0:
                    combined[card_id] = combined.get(card_id, 0) + count

    setup_data: dict[str, object] = {
        "setup_id": "card_scenario_setup",
        "starter_deck": base_setup_data["starter_deck"],
        "market_deck": {
            "deck_id": "card_scenario_market",
            "entries": [{"card_id": card_id, "count": count} for card_id, count in combined.items()],
        },
        "market_row_size": base_setup_data.get("market_row_size", 6),
    }

    setup_definition = SetupDefinition.model_validate(setup_data)
    definition = GameDefinition(
        definition_id="card_scenario",
        board=board,
        catalog=catalog,
        setup=setup_definition,
    )
    return build_initial_game_state(definition, player_ids, shuffle_seed=seed)


def _classify_moves(
    moves: list[object],
    target_card_id: str,
    state: GameState,
    board_id: str,
) -> tuple[bool, bool, list[float]]:
    """Single-pass classifier: returns (playable_now, injectable, weights)."""
    if state.definition.board.board_id != board_id:
        return False, False, [1.0] * len(moves)
    if is_terminal(state):
        return False, False, [1.0] * len(moves)
    if state.phase != TurnPhase.MAIN:
        return False, False, [1.0] * len(moves)

    current_player = state.players[state.current_player_id]
    target_in_hand = target_card_id in current_player.hand

    playable_now = False
    injectable = False
    weights: list[float] = []

    for move in moves:
        if isinstance(move, RecruitMove):
            weights.append(8.0)
        elif isinstance(move, PlayCardMove):
            weights.append(4.0)
            injectable = True
            if target_in_hand and move.card_id == target_card_id:
                playable_now = True
        else:
            weights.append(1.0)

    return playable_now, injectable, weights


def _pick_weighted(moves: list[object], weights: list[float], rng: Random) -> object:
    """Select a move using precomputed weights."""
    return rng.choices(moves, weights=weights, k=1)[0]


def _search_card_scenario(
    target_card_id: str,
    *,
    board_path: Path = DEFAULT_BOARD_PATH,
    card_path: Path = DEFAULT_CARD_PATH,
    setup_path: Path = DEFAULT_SETUP_PATH,
    rosters_path: Path = DEFAULT_ROSTERS_PATH,
    player_ids: list[str] | None = None,
    base_seed: int = 0,
    max_attempts: int = 20,
    max_steps_per_attempt: int = 1000,
    verbose: bool = False,
    legacy_market: bool = False,
) -> tuple[GameState | None, GameState, list[str], list[str]]:
    players = player_ids or ["p1", "p2", "p3", "p4"]
    board_id = _cached_board(str(board_path)).board_id
    fallback_state: GameState | None = None

    market_deck_ids: list[str]
    special_stacks_present: list[str]
    if legacy_market:
        market_deck_ids = []
        special_stacks_present = []
    else:
        roster_a_id, roster_b_id, special_stacks_present = _resolve_two_deck_pairing(
            rosters_path=rosters_path,
            target_card_id=target_card_id,
            base_seed=base_seed,
        )
        market_deck_ids = [roster_a_id, roster_b_id]

    if not legacy_market and target_card_id in SPECIAL_RECRUIT_IDS:
        state = _build_card_scenario_setup(
            board_path=board_path,
            card_path=card_path,
            setup_path=setup_path,
            rosters_path=rosters_path,
            player_ids=players,
            seed=base_seed,
            roster_a_id=roster_a_id,
            roster_b_id=roster_b_id,
        )
        return None, state, market_deck_ids, special_stacks_present

    for attempt in range(max_attempts):
        attempt_seed = base_seed + attempt * 10000
        rng = Random(attempt_seed)
        if legacy_market:
            state = _build_card_scenario_setup_legacy(
                board_path=board_path,
                card_path=card_path,
                setup_path=setup_path,
                rosters_path=rosters_path,
                player_ids=players,
                seed=attempt_seed,
                target_card_id=target_card_id,
            )
        else:
            state = _build_card_scenario_setup(
                board_path=board_path,
                card_path=card_path,
                setup_path=setup_path,
                rosters_path=rosters_path,
                player_ids=players,
                seed=attempt_seed,
                roster_a_id=roster_a_id,
                roster_b_id=roster_b_id,
            )

        for step in range(max_steps_per_attempt):
            moves = list(legal_moves(state))
            if not moves:
                break
            playable_now, injectable, weights = _classify_moves(moves, target_card_id, state, board_id)
            if playable_now:
                if verbose:
                    print(f"  found at attempt {attempt + 1}, step {step}")
                return state, state, market_deck_ids, special_stacks_present
            if injectable:
                fallback_state = state
            state = apply(state, _pick_weighted(moves, weights, rng))

        if verbose:
            print(f"  attempt {attempt + 1}/{max_attempts} exhausted ({max_steps_per_attempt} steps)")

    if fallback_state is None:
        seed = base_seed + max_attempts * 10000
        if legacy_market:
            fallback_state = _build_card_scenario_setup_legacy(
                board_path=board_path,
                card_path=card_path,
                setup_path=setup_path,
                rosters_path=rosters_path,
                player_ids=players,
                seed=seed,
                target_card_id=target_card_id,
            )
        else:
            fallback_state = _build_card_scenario_setup(
                board_path=board_path,
                card_path=card_path,
                setup_path=setup_path,
                rosters_path=rosters_path,
                player_ids=players,
                seed=seed,
                roster_a_id=roster_a_id,
                roster_b_id=roster_b_id,
            )

    return None, fallback_state, market_deck_ids, special_stacks_present


def _advance_through_setup(state: GameState) -> GameState:
    """Apply initial placements and draw starting hands until the state reaches MAIN phase."""
    from engine.helpers import _legal_initial_placement_node_ids
    from engine.phases import advance_phase

    current = state.model_copy(deep=True)
    while current.phase == TurnPhase.SETUP:
        node_ids = _legal_initial_placement_node_ids(current)
        if not node_ids:
            break
        move = InitialPlacementMove(
            player_id=current.current_player_id,
            target_node_id=node_ids[0],
        )
        current = apply(current, move)
    if current.phase == TurnPhase.DRAW:
        current = advance_phase(current)
    return current


def _force_inject_card_into_current_hand(
    state: GameState,
    *,
    target_card_id: str,
    injection_seed: int,
    max_attempts: int,
    max_steps_per_attempt: int,
) -> tuple[GameState, dict[str, object]]:
    updated = _advance_through_setup(state)
    rng = Random(injection_seed)

    for cycle in range(len(updated.turn_order)):
        candidate_id = updated.turn_order[
            (updated.turn_order.index(updated.current_player_id) + cycle) % len(updated.turn_order)
        ]
        player = updated.players[candidate_id]
        if player.hand:
            hand_index = rng.randrange(len(player.hand))
            replaced_card_id = player.hand[hand_index]
            player.hand[hand_index] = target_card_id

            note = {
                "card_id": target_card_id,
                "target_player_id": candidate_id,
                "original_current_player_id": updated.current_player_id,
                "replaced_card_id": replaced_card_id,
                "replaced_hand_index": hand_index,
                "attempts_exhausted": max_attempts,
                "max_steps_per_attempt": max_steps_per_attempt,
                "note": "Target card was force-injected after reachable search exhausted all attempts.",
            }
            return updated, note

    raise ValueError("cannot force inject — no player has a non-empty hand")


def find_card_scenario(
    target_card_id: str,
    *,
    board_path: Path = DEFAULT_BOARD_PATH,
    card_path: Path = DEFAULT_CARD_PATH,
    setup_path: Path = DEFAULT_SETUP_PATH,
    rosters_path: Path = DEFAULT_ROSTERS_PATH,
    player_ids: list[str] | None = None,
    base_seed: int = 0,
    max_attempts: int = 20,
    max_steps_per_attempt: int = 1000,
    verbose: bool = False,
) -> GameState | None:
    """Search for a reachable state where `target_card_id` is playable."""
    found_state, _fallback_state, _market_deck_ids, _special_stacks_present = _search_card_scenario(
        target_card_id,
        board_path=board_path,
        card_path=card_path,
        setup_path=setup_path,
        rosters_path=rosters_path,
        player_ids=player_ids,
        base_seed=base_seed,
        max_attempts=max_attempts,
        max_steps_per_attempt=max_steps_per_attempt,
        verbose=verbose,
    )
    return found_state


def ensure_card_scenario(
    target_card_id: str,
    *,
    board_path: Path = DEFAULT_BOARD_PATH,
    card_path: Path = DEFAULT_CARD_PATH,
    setup_path: Path = DEFAULT_SETUP_PATH,
    rosters_path: Path = DEFAULT_ROSTERS_PATH,
    player_ids: list[str] | None = None,
    base_seed: int = 0,
    max_attempts: int = 20,
    max_steps_per_attempt: int = 1000,
    verbose: bool = False,
    legacy_market: bool = False,
) -> tuple[GameState, dict[str, object] | None, list[str], list[str]]:
    found_state, fallback_state, market_deck_ids, special_stacks_present = _search_card_scenario(
        target_card_id,
        board_path=board_path,
        card_path=card_path,
        setup_path=setup_path,
        rosters_path=rosters_path,
        player_ids=player_ids,
        base_seed=base_seed,
        max_attempts=max_attempts,
        max_steps_per_attempt=max_steps_per_attempt,
        verbose=verbose,
        legacy_market=legacy_market,
    )
    if found_state is not None:
        return found_state, None, market_deck_ids, special_stacks_present

    injected_state, note = _force_inject_card_into_current_hand(
        fallback_state,
        target_card_id=target_card_id,
        injection_seed=base_seed + 999_999,
        max_attempts=max_attempts,
        max_steps_per_attempt=max_steps_per_attempt,
    )
    if verbose:
        print("  injected into current player hand")
    return injected_state, note, market_deck_ids, special_stacks_present


def write_forced_injection_notes(output_dir: Path, notes: list[dict[str, object]]) -> Path:
    path = output_dir / FORCED_INJECTIONS_FILENAME
    path.write_text(json.dumps(notes, indent=2) + "\n", encoding="utf-8")
    return path


def _worker_generate_card(args: tuple) -> dict[str, object]:
    (index, card_id, board_path_str, card_path_str, setup_path_str, rosters_path_str,
     player_ids, base_seed, max_attempts, max_steps_per_attempt, out_dir_str, pretty,
     legacy_market) = args

    card_seed = base_seed
    state, injection_note, market_deck_ids, special_stacks_present = ensure_card_scenario(
        card_id,
        board_path=Path(board_path_str),
        card_path=Path(card_path_str),
        setup_path=Path(setup_path_str),
        rosters_path=Path(rosters_path_str),
        player_ids=list(player_ids),
        base_seed=card_seed,
        max_attempts=max_attempts,
        max_steps_per_attempt=max_steps_per_attempt,
        verbose=False,
        legacy_market=legacy_market,
    )

    padded_index = str(index + 1).zfill(3)
    filename = f"{padded_index}_seed_{card_seed}_{card_id}.json"
    path = Path(out_dir_str) / filename

    tags = ["generated", "cards", "reachable", "playable_now"]
    description = f"Reachable 4-player Tyrants scenario for {card_id}"
    if injection_note is not None:
        tags = ["generated", "cards", "forced_injection"]
        description = f"Forced-injection fallback scenario for {card_id} after reachable search exhaustion"

    save_game_state(
        state,
        path,
        scenario_id=f"card_{card_id}",
        description=description,
        tags=tags,
        card_under_test=card_id,
        market_deck_ids=market_deck_ids,
        special_stacks_present=special_stacks_present,
        pretty=pretty,
    )
    return {
        "index": index,
        "card_id": card_id,
        "card_seed": card_seed,
        "filename": filename,
        "injection_note": injection_note,
    }


def generate_card_scenarios(
    output_dir: Path,
    *,
    board_path: Path = DEFAULT_BOARD_PATH,
    card_path: Path = DEFAULT_CARD_PATH,
    setup_path: Path = DEFAULT_SETUP_PATH,
    rosters_path: Path = DEFAULT_ROSTERS_PATH,
    player_ids: list[str] | None = None,
    base_seed: int = 0,
    max_attempts: int = 20,
    max_steps_per_attempt: int = 1000,
    card_ids: list[str] | None = None,
    workers: int = 1,
    pretty: bool = False,
    legacy_market: bool = False,
) -> tuple[list[Path], list[str]]:
    """Generate one scenario per card id and save to `output_dir`."""
    players = tuple(player_ids or ["p1", "p2", "p3", "p4"])
    target_ids = card_ids if card_ids is not None else iter_roster_card_ids(rosters_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved: list[Path] = []
    missing: list[str] = []
    forced_injections: list[dict[str, object]] = []

    workers = max(1, min(workers, os.cpu_count() or 1))

    if workers == 1:
        try:
            from tqdm import tqdm  # noqa: PLC0415

            card_iter = tqdm(target_ids, desc="Generating scenarios", unit="card")
        except ImportError:
            card_iter = target_ids

        for index, card_id in enumerate(card_iter):
            card_seed = base_seed
            state, injection_note, market_deck_ids, special_stacks_present = ensure_card_scenario(
                target_card_id=card_id,
                board_path=board_path,
                card_path=card_path,
                setup_path=setup_path,
                rosters_path=rosters_path,
                player_ids=list(players),
                base_seed=card_seed,
                max_attempts=max_attempts,
                max_steps_per_attempt=max_steps_per_attempt,
                verbose=False,
                legacy_market=legacy_market,
            )
            with contextlib.suppress(AttributeError):
                card_iter.set_postfix_str(card_id)

            padded_index = str(index + 1).zfill(3)
            filename = f"{padded_index}_seed_{card_seed}_{card_id}.json"
            path = output_dir / filename
            tags = ["generated", "cards", "reachable", "playable_now"]
            description = f"Reachable 4-player Tyrants scenario for {card_id}"
            if injection_note is not None:
                tags = ["generated", "cards", "forced_injection"]
                description = f"Forced-injection fallback scenario for {card_id} after reachable search exhaustion"
                forced_injections.append({**injection_note, "scenario_file": filename})

            save_game_state(
                state,
                path,
                scenario_id=f"card_{card_id}",
                description=description,
                tags=tags,
                card_under_test=card_id,
                market_deck_ids=market_deck_ids,
                special_stacks_present=special_stacks_present,
                pretty=pretty,
            )
            saved.append(path)

        write_forced_injection_notes(output_dir, forced_injections)
        return saved, missing

    tasks = [
        (i, card_id,
         str(board_path), str(card_path), str(setup_path), str(rosters_path),
         players, base_seed, max_attempts, max_steps_per_attempt,
         str(output_dir), pretty, legacy_market)
        for i, card_id in enumerate(target_ids)
    ]

    try:
        from tqdm import tqdm

        progress = tqdm(total=len(tasks), desc="Generating scenarios", unit="card")
    except ImportError:
        progress = None

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_worker_generate_card, task): task for task in tasks}
        for future in as_completed(futures):
            result = future.result()
            saved.append(output_dir / str(result["filename"]))
            note = result.get("injection_note")
            if note is not None:
                forced_injections.append({**note, "scenario_file": str(result["filename"])})
            if progress is not None:
                progress.update(1)
                progress.set_postfix_str(str(result["card_id"]))

    if progress is not None:
        progress.close()

    forced_injections.sort(key=lambda n: str(n.get("card_id", "")))
    write_forced_injection_notes(output_dir, forced_injections)
    return saved, missing


@dataclass(frozen=True)
class CardScenarioGenerator:
    board_path: Path = DEFAULT_BOARD_PATH
    card_path: Path = DEFAULT_CARD_PATH
    setup_path: Path = DEFAULT_SETUP_PATH
    rosters_path: Path = DEFAULT_ROSTERS_PATH
    player_ids: tuple[str, ...] = ("p1", "p2", "p3", "p4")
    base_seed: int = 0
    max_attempts: int = 20
    max_steps_per_attempt: int = 1000
    legacy_market: bool = False

    def find(self, target_card_id: str, *, verbose: bool = False) -> GameState | None:
        return find_card_scenario(
            target_card_id,
            board_path=self.board_path,
            card_path=self.card_path,
            setup_path=self.setup_path,
            rosters_path=self.rosters_path,
            player_ids=list(self.player_ids),
            base_seed=self.base_seed,
            max_attempts=self.max_attempts,
            max_steps_per_attempt=self.max_steps_per_attempt,
            verbose=verbose,
        )

    def ensure(self, target_card_id: str, *, verbose: bool = False) -> tuple[GameState, dict[str, object] | None, list[str], list[str]]:
        return ensure_card_scenario(
            target_card_id,
            board_path=self.board_path,
            card_path=self.card_path,
            setup_path=self.setup_path,
            rosters_path=self.rosters_path,
            player_ids=list(self.player_ids),
            base_seed=self.base_seed,
            max_attempts=self.max_attempts,
            max_steps_per_attempt=self.max_steps_per_attempt,
            verbose=verbose,
            legacy_market=self.legacy_market,
        )

    def generate(
        self,
        output_dir: Path,
        *,
        card_ids: list[str] | None = None,
        workers: int = 1,
        pretty: bool = False,
    ) -> tuple[list[Path], list[str]]:
        return generate_card_scenarios(
            output_dir,
            board_path=self.board_path,
            card_path=self.card_path,
            setup_path=self.setup_path,
            rosters_path=self.rosters_path,
            player_ids=list(self.player_ids),
            base_seed=self.base_seed,
            max_attempts=self.max_attempts,
            max_steps_per_attempt=self.max_steps_per_attempt,
            card_ids=card_ids,
            workers=workers,
            pretty=pretty,
            legacy_market=self.legacy_market,
        )

    def iter_card_ids(self) -> list[str]:
        return iter_roster_card_ids(self.rosters_path)
