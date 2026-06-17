"""C-engine card scenario search and force-injection workflow.

Mirrors ``game_setup.scenario_generation.card_scenarios`` but uses
the C engine DLL instead of the Python engine.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from random import Random

from game_setup.market_setup import (
    SPECIAL_RECRUIT_IDS,
    combine_two_deck_market_setup,
    discover_full_deck_profiles,
)
from game_setup.scenario_generation.card_scenarios import (
    _resolve_two_deck_pairing,
    iter_roster_card_ids,
)

from .ce_api import CEngine, CMoveWrapper, CState
from .engine_bindings import _lib
from .session import CSession

FORCED_INJECTIONS_FILENAME = "forced_injections.json"

CARD_SCENARIO_PICK_WEIGHTS = {"recruit": 8.0, "play_card": 4.0, "other": 1.0}


def _classify_moves_c(
    engine: CEngine,
    moves: list[CMoveWrapper],
    target_card_id: str,
    state: CState,
) -> tuple[bool, bool, list[float]]:
    if engine.is_terminal(state):
        return False, False, [1.0] * len(moves)
    if state.phase != "main":
        return False, False, [1.0] * len(moves)

    current_idx = state.player_ids.index(state.current_player_id)
    target_in_hand = target_card_id in state.player_hand(current_idx)

    playable_now = False
    injectable = False
    weights: list[float] = []

    for move in moves:
        mt = move.move_type
        if mt == "recruit":
            weights.append(CARD_SCENARIO_PICK_WEIGHTS["recruit"])
        elif mt == "play_card":
            weights.append(CARD_SCENARIO_PICK_WEIGHTS["play_card"])
            injectable = True
            if target_in_hand and move.data.get("card_id") == target_card_id:
                playable_now = True
        else:
            weights.append(CARD_SCENARIO_PICK_WEIGHTS["other"])

    return playable_now, injectable, weights


def _pick_weighted_c(moves: list[CMoveWrapper], weights: list[float], rng: Random) -> CMoveWrapper:
    return rng.choices(moves, weights=weights, k=1)[0]


def _advance_through_setup_c(engine: CEngine, state: CState) -> CState:
    """Apply initial placements and draw. Transfers ownership: destroys
    the input state and returns the advanced state."""
    current = state
    while current.phase == "setup":
        moves = engine.legal_moves(current)
        placement_moves = [m for m in moves if m.move_type == "initial_placement"]
        if not placement_moves:
            break
        new_state = engine.apply(current, placement_moves[0])
        if new_state is None:
            break
        engine.destroy(current)
        current = new_state

    if current.phase == "draw":
        moves = engine.legal_moves(current)
        if moves:
            new_state = engine.apply(current, moves[0])
            if new_state is not None:
                engine.destroy(current)
                current = new_state

    return current


def _clone_state(state: CState) -> CState:
    cloned_ptr = _lib.engine_clone(state._ptr)
    return type(state)(cloned_ptr)


def _search_card_scenario_c(
    engine: CEngine,
    target_card_id: str,
    *,
    rosters_path: Path,
    player_ids: list[str],
    base_seed: int,
    max_attempts: int,
    max_steps_per_attempt: int,
    verbose: bool = False,
) -> tuple[CState | None, CState, list[str], list[str]]:
    roster_a_id, roster_b_id, special_stacks_present = _resolve_two_deck_pairing(
        rosters_path=rosters_path,
        target_card_id=target_card_id,
        base_seed=base_seed,
    )
    market_deck_ids = [roster_a_id, roster_b_id]

    if target_card_id in SPECIAL_RECRUIT_IDS:
        state = engine.create_game(player_ids, base_seed)
        return None, state, market_deck_ids, special_stacks_present

    fallback_state: CState | None = None

    for attempt in range(max_attempts):
        attempt_seed = base_seed + attempt * 10000
        rng = Random(attempt_seed)
        state = engine.create_game(player_ids, attempt_seed)

        for step in range(max_steps_per_attempt):
            moves = engine.legal_moves(state)
            if not moves:
                break
            playable_now, injectable, weights = _classify_moves_c(engine, moves, target_card_id, state)
            if playable_now:
                if verbose:
                    print(f"  found at attempt {attempt + 1}, step {step}")
                if fallback_state is not None:
                    engine.destroy(fallback_state)
                return state, state, market_deck_ids, special_stacks_present
            if injectable:
                if fallback_state is not None:
                    engine.destroy(fallback_state)
                fallback_state = _clone_state(state)
            picked = _pick_weighted_c(moves, weights, rng)
            new_state = engine.apply(state, picked)
            if new_state is None:
                continue
            engine.destroy(state)
            state = new_state

        if verbose:
            print(f"  attempt {attempt + 1}/{max_attempts} exhausted ({max_steps_per_attempt} steps)")

        if fallback_state is None:
            engine.destroy(state)
        else:
            engine.destroy(state)

    if fallback_state is None:
        seed = base_seed + max_attempts * 10000
        fallback_state = engine.create_game(player_ids, seed)

    return None, fallback_state, market_deck_ids, special_stacks_present


def _force_inject_into_hand_c(
    engine: CEngine,
    fallback_state: CState,
    *,
    target_card_id: str,
    injection_seed: int,
    max_attempts: int,
    max_steps_per_attempt: int,
) -> tuple[CState, dict[str, object]]:
    state = _clone_state(fallback_state)
    engine.destroy(fallback_state)

    state = _advance_through_setup_c(engine, state)
    rng = Random(injection_seed)
    turn_order = state.player_ids
    current_pid = state.current_player_id
    current_index = turn_order.index(current_pid) if current_pid in turn_order else 0

    for cycle in range(len(turn_order)):
        candidate_id = turn_order[(current_index + cycle) % len(turn_order)]
        candidate_idx = state.player_ids.index(candidate_id)
        player_hand = state.player_hand(candidate_idx)
        if player_hand:
            hand_index = rng.randrange(len(player_hand))
            replaced_card_id = player_hand[hand_index]

            target_sym = _lib.intern(target_card_id.encode())
            state._s.players[candidate_idx].hand[hand_index] = target_sym

            note = {
                "card_id": target_card_id,
                "target_player_id": candidate_id,
                "original_current_player_id": state.current_player_id,
                "replaced_card_id": replaced_card_id,
                "replaced_hand_index": hand_index,
                "attempts_exhausted": max_attempts,
                "max_steps_per_attempt": max_steps_per_attempt,
                "note": "Target card was force-injected after reachable search exhausted all attempts.",
            }
            return state, note

    engine.destroy(state)
    raise ValueError("cannot force inject — no player has a non-empty hand")


def ensure_card_scenario_c(
    target_card_id: str,
    *,
    board_path: Path | None = None,
    card_path: Path | None = None,
    setup_path: Path | None = None,
    rosters_path: Path | None = None,
    player_ids: list[str] | None = None,
    base_seed: int = 0,
    max_attempts: int = 20,
    max_steps_per_attempt: int = 1000,
    verbose: bool = False,
) -> tuple[CState, dict[str, object] | None, list[str], list[str]]:
    players = player_ids or ["p1", "p2", "p3", "p4"]
    rp = rosters_path or Path("data/decks")

    bp = str(board_path) if board_path else "data/boards/tyrants_of_the_underdark.json"
    cp = str(card_path) if card_path else "data/cards/catalog.json"
    sp = str(setup_path) if setup_path else "data/decks/base_setup.json"

    roster_a_id, roster_b_id, special_stacks_present = _resolve_two_deck_pairing(
        rosters_path=rp,
        target_card_id=target_card_id,
        base_seed=base_seed,
    )

    from game_setup.market_setup import DeckProfile
    profiles = discover_full_deck_profiles(rp)
    profile_map: dict[str, DeckProfile] = {p.deck_id: p for p in profiles}
    deck_a = profile_map[roster_a_id]
    deck_b = profile_map[roster_b_id]

    import json as _json
    base_setup_data = _json.loads(Path(sp).read_text(encoding="utf-8"))
    market_setup = combine_two_deck_market_setup(base_setup_data, deck_a, deck_b)
    setup_data = market_setup.to_setup_data()
    setup_data["setup_id"] = "card_scenario_setup"
    setup_data_json = _json.dumps(setup_data)

    engine = CEngine()
    engine.initialize(
        catalog_path=cp,
        board_path=bp,
        setup_path=sp,
        setup_data_json=setup_data_json,
    )

    found_state, fallback_state, market_deck_ids, special_stacks = _search_card_scenario_c(
        engine,
        target_card_id,
        rosters_path=rp,
        player_ids=players,
        base_seed=base_seed,
        max_attempts=max_attempts,
        max_steps_per_attempt=max_steps_per_attempt,
        verbose=verbose,
    )

    if found_state is not None:
        return found_state, None, market_deck_ids, special_stacks

    injected_state, note = _force_inject_into_hand_c(
        engine,
        fallback_state,
        target_card_id=target_card_id,
        injection_seed=base_seed + 999_999,
        max_attempts=max_attempts,
        max_steps_per_attempt=max_steps_per_attempt,
    )
    if verbose:
        print("  injected into current player hand")
    return injected_state, note, market_deck_ids, special_stacks


def save_c_scenario(
    c_state: CState,
    path: Path,
    *,
    scenario_id: str,
    description: str,
    tags: list[str],
    card_under_test: str,
    market_deck_ids: list[str],
    special_stacks_present: list[str],
    move_count: int = 0,
    is_terminal: bool = False,
    pretty: bool = False,
) -> None:
    raw = CSession.save_to_string(c_state, move_count=move_count, is_terminal=is_terminal)
    payload = json.loads(raw)
    meta = payload.setdefault("metadata", {})
    meta["scenario_id"] = scenario_id
    meta["description"] = description
    meta["tags"] = tags
    meta["card_under_test"] = card_under_test
    meta["market_deck_ids"] = market_deck_ids
    meta["special_stacks_present"] = special_stacks_present
    if pretty:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")


def write_forced_injection_notes(output_dir: Path, notes: list[dict[str, object]]) -> Path:
    path = output_dir / FORCED_INJECTIONS_FILENAME
    path.write_text(json.dumps(notes, indent=2) + "\n", encoding="utf-8")
    return path


def generate_card_scenarios_c(
    output_dir: Path,
    *,
    board_path: Path | None = None,
    card_path: Path | None = None,
    setup_path: Path | None = None,
    rosters_path: Path | None = None,
    player_ids: list[str] | None = None,
    base_seed: int = 0,
    max_attempts: int = 20,
    max_steps_per_attempt: int = 1000,
    card_ids: list[str] | None = None,
    workers: int = 1,
    pretty: bool = False,
) -> tuple[list[Path], list[str]]:
    players = player_ids or ["p1", "p2", "p3", "p4"]
    rp = rosters_path or Path("data/decks")
    target_ids = card_ids if card_ids is not None else iter_roster_card_ids(rp)
    output_dir.mkdir(parents=True, exist_ok=True)

    if workers > 1:
        raise NotImplementedError(
            "Parallel workers are not yet supported by the C engine path; "
            "use --engine python or --workers 1."
        )

    saved: list[Path] = []
    missing: list[str] = []
    forced_injections: list[dict[str, object]] = []

    try:
        from tqdm import tqdm
        card_iter = tqdm(target_ids, desc="Generating scenarios", unit="card")
    except ImportError:
        card_iter = target_ids

    for index, card_id in enumerate(card_iter):
        try:
            state, injection_note, market_deck_ids, special_stacks_present = ensure_card_scenario_c(
                card_id,
                board_path=board_path,
                card_path=card_path,
                setup_path=setup_path,
                rosters_path=rp,
                player_ids=list(players),
                base_seed=base_seed,
                max_attempts=max_attempts,
                max_steps_per_attempt=max_steps_per_attempt,
                verbose=False,
            )
        except Exception:
            missing.append(card_id)
            continue

        with contextlib.suppress(AttributeError, Exception):
            card_iter.set_postfix_str(card_id)

        padded_index = str(index + 1).zfill(3)
        filename = f"{padded_index}_seed_{base_seed}_{card_id}.json"
        path = output_dir / filename
        tags: list[str] = ["generated", "cards", "reachable", "playable_now"]
        description = f"Reachable 4-player Tyrants scenario for {card_id}"
        if injection_note is not None:
            tags = ["generated", "cards", "forced_injection"]
            description = f"Forced-injection fallback scenario for {card_id} after reachable search exhaustion"
            forced_injections.append({**injection_note, "scenario_file": filename})

        save_c_scenario(
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
        state.destroy()
        saved.append(path)

    write_forced_injection_notes(output_dir, forced_injections)
    return saved, missing
