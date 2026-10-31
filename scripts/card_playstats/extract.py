"""Per-game extraction for the card play post-mortem.

Two passes per game:

1. **Cheap log pass** — group ``recruit`` / ``play_card`` events from
   ``replay_log`` by ``payload.card_id``.
2. **Engine-replay pass** — drive :class:`interface.replay_player.ReplayPlayer`
   step by step and multiset-diff each seat's hand against its previous
   snapshot, yielding an authoritative per-copy *hand appearance* (draw) count.
   There is no explicit draw event in the log, so this is the only way to know
   whether a recruited card was ever even seen.

Modal choices are resolved from ``decisions.jsonl`` when present, else from the
replay log (see :func:`resolve_modal_choices`).

Results are cached per game directory under ``cache_dir`` keyed on the game
directory path and ``replay.json`` mtime, so re-analyzing overlapping folder
selections never re-pays the engine-replay cost.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from interface.replay_loader import ReplayBundle, is_complete_game, load_replay

from .catalog import CardCatalog

CACHE_FORMAT_VERSION = 2
_ACTION_ID_RE = re.compile(r"action_id='([^']*)'")


class ExtractionSanityError(RuntimeError):
    """A per-game count derived from the log disagrees with ``summary.json``."""


@dataclass
class GameExtraction:
    """Per-game per-card play statistics plus run context."""

    game_dir: str
    run_id: str
    recruited: dict[str, int]
    played: dict[str, int]
    hand_appearances: dict[str, int]
    modal_played: dict[str, int]
    modal_choices: dict[str, dict[str, int]]
    modal_source: str
    warnings: list[str]
    winner_seat: int | None
    num_players: int
    outcome: str | None
    final_scores: dict[str, int]
    step_count: int
    deck_a_id: str
    deck_b_id: str
    decision_count: int
    move_type_counts: dict[str, int]
    complete: bool
    engine_replayed: bool
    market_card_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cache_format_version": CACHE_FORMAT_VERSION,
            "game_dir": self.game_dir,
            "run_id": self.run_id,
            "recruited": dict(self.recruited),
            "played": dict(self.played),
            "hand_appearances": dict(self.hand_appearances),
            "modal_played": dict(self.modal_played),
            "modal_choices": {card: dict(counts) for card, counts in self.modal_choices.items()},
            "modal_source": self.modal_source,
            "warnings": list(self.warnings),
            "winner_seat": self.winner_seat,
            "num_players": self.num_players,
            "outcome": self.outcome,
            "final_scores": dict(self.final_scores),
            "step_count": self.step_count,
            "deck_a_id": self.deck_a_id,
            "deck_b_id": self.deck_b_id,
            "decision_count": self.decision_count,
            "move_type_counts": dict(self.move_type_counts),
            "complete": self.complete,
            "engine_replayed": self.engine_replayed,
            "market_card_ids": list(self.market_card_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> GameExtraction:
        return cls(
            game_dir=data["game_dir"],
            run_id=data.get("run_id", ""),
            recruited=dict(data.get("recruited") or {}),
            played=dict(data.get("played") or {}),
            hand_appearances=dict(data.get("hand_appearances") or {}),
            modal_played=dict(data.get("modal_played") or {}),
            modal_choices={
                card: dict(counts) for card, counts in (data.get("modal_choices") or {}).items()
            },
            modal_source=data.get("modal_source", "none"),
            warnings=list(data.get("warnings") or []),
            winner_seat=data.get("winner_seat"),
            num_players=int(data.get("num_players", 0)),
            outcome=data.get("outcome"),
            final_scores={str(k): int(v) for k, v in (data.get("final_scores") or {}).items()},
            step_count=int(data.get("step_count", 0)),
            deck_a_id=data.get("deck_a_id", ""),
            deck_b_id=data.get("deck_b_id", ""),
            decision_count=int(data.get("decision_count", 0)),
            move_type_counts=dict(data.get("move_type_counts") or {}),
            complete=bool(data.get("complete", False)),
            engine_replayed=bool(data.get("engine_replayed", False)),
            market_card_ids=[str(card) for card in (data.get("market_card_ids") or [])],
        )

    @staticmethod
    def check_move_event_totals(
        *,
        recruited: dict[str, int],
        played: dict[str, int],
        move_type_counts: dict[str, int],
    ) -> None:
        """Fail loud when grouped log counts disagree with ``summary.json``."""
        expected_recruit = move_type_counts.get("recruit")
        if expected_recruit is not None and sum(recruited.values()) != expected_recruit:
            raise ExtractionSanityError(
                f"recruit total {sum(recruited.values())} != summary {expected_recruit}"
            )
        expected_play = move_type_counts.get("play_card")
        if expected_play is not None and sum(played.values()) != expected_play:
            raise ExtractionSanityError(
                f"play_card total {sum(played.values())} != summary {expected_play}"
            )

    @staticmethod
    def modal_warnings(
        modal_played: dict[str, int],
        modal_choices: dict[str, dict[str, int]],
    ) -> list[str]:
        """One warning per modal card whose picks resolved != times played.

        Iterates the union of both sides so a resolved pick with no top-level
        ``play_card`` event (a modal invoked by another card's effect) is still
        surfaced rather than silently inflating the option distribution.
        """
        warnings: list[str] = []
        for card_id in sorted(set(modal_played) | set(modal_choices)):
            times_played = modal_played.get(card_id, 0)
            resolved = sum((modal_choices.get(card_id) or {}).values())
            if resolved != times_played:
                warnings.append(
                    f"modal_mismatch: {card_id} played {times_played} but resolved {resolved}"
                )
        return warnings


def count_move_events(replay_log: Iterable[dict]) -> tuple[Counter, Counter]:
    """Group ``recruit`` and ``play_card`` events by ``payload.card_id``."""
    recruited: Counter = Counter()
    played: Counter = Counter()
    for entry in replay_log:
        payload = entry.get("payload") or {}
        move_type = payload.get("move_type")
        card_id = payload.get("card_id")
        if not isinstance(card_id, str) or not card_id:
            continue
        if move_type == "recruit":
            recruited[card_id] += 1
        elif move_type == "play_card":
            played[card_id] += 1
    return recruited, played


def count_modal_plays(replay_log: Iterable[dict], catalog: CardCatalog) -> Counter:
    """Count ``play_card`` events for modal cards only."""
    modal_played: Counter = Counter()
    for entry in replay_log:
        payload = entry.get("payload") or {}
        if payload.get("move_type") != "play_card":
            continue
        card_id = payload.get("card_id")
        if isinstance(card_id, str) and catalog.is_modal(card_id):
            modal_played[card_id] += 1
    return modal_played


def market_card_ids_from_setup(setup_json: str) -> list[str]:
    """Card ids eligible in a game's market (deck entries + special stacks)."""
    try:
        setup = json.loads(setup_json)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(setup, dict):
        return []
    card_ids: set[str] = set()
    market = setup.get("market_deck")
    if isinstance(market, dict):
        for entry in market.get("entries") or []:
            if isinstance(entry, dict) and isinstance(entry.get("card_id"), str):
                card_ids.add(entry["card_id"])
    for stack in setup.get("special_stacks") or []:
        if isinstance(stack, dict) and isinstance(stack.get("card_id"), str):
            card_ids.add(stack["card_id"])
    return sorted(card_ids)


def _parse_action_id(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    match = _ACTION_ID_RE.search(text)
    return match.group(1) if match else None


def _resolve_from_decisions(
    decisions: list[dict], catalog: CardCatalog
) -> dict[str, Counter]:
    choices: dict[str, Counter] = {}
    for line in decisions:
        pending = line.get("pending_context") or {}
        generic = line.get("generic") or {}
        awaiting = pending.get("awaiting_option", generic.get("awaiting_option"))
        if awaiting is not True:
            continue
        card_id = pending.get("source_card_id") or generic.get("source_card_id")
        if not isinstance(card_id, str) or not catalog.is_modal(card_id):
            continue
        option_id = generic.get("move_action_id") or pending.get("move_action_id")
        if not isinstance(option_id, str) or not option_id:
            option_id = _parse_action_id(line.get("chosen_move"))
        if option_id not in catalog.option_ids(card_id):
            continue
        choices.setdefault(card_id, Counter())[option_id] += 1
    return choices


def _resolve_from_log(replay_log: list[dict], catalog: CardCatalog) -> tuple[dict[str, Counter], list[str]]:
    choices: dict[str, Counter] = {}
    plays: Counter = Counter()
    for index, entry in enumerate(replay_log):
        payload = entry.get("payload") or {}
        if payload.get("move_type") != "play_card":
            continue
        card_id = payload.get("card_id")
        if not isinstance(card_id, str) or not catalog.is_modal(card_id):
            continue
        plays[card_id] += 1
        choices.setdefault(card_id, Counter())

        option_ids = catalog.option_ids(card_id)
        player = entry.get("player_id")
        picked: str | None = None
        for later in replay_log[index + 1 :]:
            later_payload = later.get("payload") or {}
            if later.get("player_id") != player:
                continue
            later_type = later_payload.get("move_type")
            if later_type in ("play_card", "recruit"):
                break
            if later_type == "resolve_generic_choice":
                action_id = later_payload.get("action_id")
                if action_id in option_ids:
                    picked = action_id
                    break
        if picked is not None:
            choices[card_id][picked] += 1

    warnings = GameExtraction.modal_warnings(plays, choices)
    return choices, warnings


def resolve_modal_choices(
    replay_log: list[dict],
    decisions: list[dict],
    catalog: CardCatalog,
) -> tuple[dict[str, Counter], str, list[str]]:
    """Resolve which modal option was picked each time a modal card was played.

    Returns ``(choices, source, warnings)`` where *source* is ``"decisions"``
    when ``decisions.jsonl`` supplied the picks, ``"fallback"`` when the replay
    log heuristic was used, and ``"none"`` when there were neither modal plays
    nor decision telemetry.
    """
    if decisions:
        return _resolve_from_decisions(decisions, catalog), "decisions", []
    choices, warnings = _resolve_from_log(replay_log, catalog)
    if not choices:
        return {}, "none", []
    return choices, "fallback", warnings


def count_hand_appearances(bundle: ReplayBundle) -> Counter:
    """Multiset-diff each seat's hand after every applied step.

    A card_id whose count rose relative to the seat's previous snapshot
    contributes that many appearances. This is the authoritative per-copy draw
    count, since the log has no explicit draw event.
    """
    from interface.replay_player import ReplayPlayer  # lazy: keeps DLL import off module load

    player = ReplayPlayer(bundle)
    appearances: Counter = Counter()
    try:
        state = player.session.state
        previous = [Counter(state.player_hand(seat)) for seat in range(state.player_count)]
        while player.step_forward():
            state = player.session.state
            for seat in range(state.player_count):
                current = Counter(state.player_hand(seat))
                for card_id, gained in (current - previous[seat]).items():
                    appearances[card_id] += gained
                previous[seat] = current
    finally:
        player.close()
    return appearances


def _cache_key(game_dir: Path) -> str:
    replay_path = game_dir / "replay.json"
    try:
        mtime = replay_path.stat().st_mtime_ns
    except OSError:
        mtime = 0
    digest = hashlib.sha1(
        f"{game_dir.resolve()}|{mtime}|{CACHE_FORMAT_VERSION}".encode()
    ).hexdigest()
    return digest


def _cache_path(cache_dir: Path, game_dir: Path) -> Path:
    return Path(cache_dir) / f"{_cache_key(game_dir)}.json"


def extract_game(
    game_dir: Path,
    catalog: CardCatalog,
    *,
    cache_dir: Path | None = None,
    engine: bool = True,
    hand_counter: Callable[[ReplayBundle], Counter] | None = None,
) -> GameExtraction:
    """Extract one game's play statistics, optionally through a disk cache."""
    game_dir = Path(game_dir)
    cache_file = _cache_path(cache_dir, game_dir) if cache_dir else None
    if cache_file is not None and cache_file.is_file():
        try:
            return GameExtraction.from_dict(json.loads(cache_file.read_text(encoding="utf-8")))
        except Exception:
            pass  # corrupt/legacy cache entry: fall through and recompute

    bundle = load_replay(game_dir)
    replay = bundle.replay
    replay_log = list(replay.get("replay_log", ()))
    summary = bundle.summary or {}

    recruited, played = count_move_events(replay_log)
    modal_played = count_modal_plays(replay_log, catalog)
    choices, modal_source, modal_warn = resolve_modal_choices(
        replay_log, bundle.decisions, catalog
    )

    move_type_counts = summary.get("move_type_counts")
    move_type_counts = move_type_counts if isinstance(move_type_counts, dict) else {}
    if move_type_counts:
        GameExtraction.check_move_event_totals(
            recruited=recruited, played=played, move_type_counts=move_type_counts
        )

    warnings = list(
        dict.fromkeys([*modal_warn, *GameExtraction.modal_warnings(modal_played, choices)])
    )

    replay_hand = hand_counter or count_hand_appearances
    engine_replayed = bool(engine)
    hand_appearances = replay_hand(bundle) if engine else Counter()

    winner_seat = summary.get("winner") if isinstance(summary.get("winner"), int) else None
    player_ids = list(bundle.meta.player_ids)
    num_players = summary.get("num_players")
    if not isinstance(num_players, int):
        num_players = len(player_ids)

    final_scores = summary.get("final_scores_per_player")
    if not isinstance(final_scores, dict):
        final_scores = replay.get("final_scores") or {}
    final_scores = {str(k): int(v) for k, v in final_scores.items() if isinstance(v, (int, float))}

    decision_count = summary.get("decision_count")
    if not isinstance(decision_count, int):
        decision_count = len(bundle.decisions)

    extraction = GameExtraction(
        game_dir=str(game_dir),
        run_id=bundle.meta.run_id,
        recruited=dict(recruited),
        played=dict(played),
        hand_appearances=dict(hand_appearances),
        modal_played=dict(modal_played),
        modal_choices={card: dict(counts) for card, counts in choices.items()},
        modal_source=modal_source,
        warnings=warnings,
        winner_seat=winner_seat,
        num_players=num_players,
        outcome=summary.get("outcome") or bundle.meta.outcome,
        final_scores=final_scores,
        step_count=int(replay.get("step_count", bundle.meta.step_count)),
        deck_a_id=bundle.meta.deck_a_id,
        deck_b_id=bundle.meta.deck_b_id,
        decision_count=decision_count,
        move_type_counts=move_type_counts,
        complete=is_complete_game(game_dir),
        engine_replayed=engine_replayed,
        market_card_ids=market_card_ids_from_setup(bundle.setup_json),
    )

    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(extraction.to_dict()), encoding="utf-8")

    return extraction
