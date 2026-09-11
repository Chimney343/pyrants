"""Pure replay discovery and loading for IS-MCTS replay artifacts.

Tk-free and pyspiel-free by construction: the viewer keeps its startup free of
the OpenSpiel import, and these helpers stay unit-testable headless.

Artifact layout (``artifacts/ismcts/runs/<ts>_<run_id>/game_XXXX/``):

- ``manifest.json``  run-scoped; ``schema_version`` + engine provenance + the
                     per-game inline ``setup_data_json`` (sibling of the game
                     dirs, not inside them)
- ``replay.json``    required; ``replay_context`` + ``replay_log`` + top-level
                     ``step_count`` / ``winner_id`` / ``final_scores``
- ``summary.json``   optional; labels + ``setup_data_sha256`` + ``outcome``;
                     written LAST, doubles as the completion marker
- ``decisions.jsonl`` optional; per-decision telemetry, line N <-> replay_log[N].

A game counts as complete only when ``summary.json`` exists and its
``stopped_reason == "terminal"`` (see :func:`is_complete_game`).

``decisions.jsonl`` lines carry additive fields: ``resolve_generic`` lines
(identified by the raw ``chosen_move``/``move_type``) additionally include a
human-readable ``chosen_label`` and a structured ``generic`` object
(``source_card_id``, ``op``, ``card_action_id``, ``current_option_id``,
``awaiting_option``, ``optional``, plus the move's own ``move_action_id`` /
``move_target_id`` / ``selection_index``).  ``chosen_move`` stays raw, and
non-generic lines never gain these fields; unknown/malformed fields and lines
are tolerated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from game_setup.market_setup import (
    combine_two_deck_market_setup,
    discover_full_deck_profiles,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BOARD_PATH = ROOT_DIR / "data" / "boards" / "tyrants_of_the_underdark.json"
DEFAULT_CARD_PATH = ROOT_DIR / "data" / "cards"
DEFAULT_SETUP_PATH = ROOT_DIR / "data" / "decks" / "base_setup.json"
DECKS_DIR = ROOT_DIR / "data" / "decks"

# The C engine is seeded with a mixed value, not replay_context.seed directly.
# Mirror openspiel_pyrants/state_c.py lines 16-21 (_public_to_seed) WITHOUT
# importing pyspiel. tests/test_replay_loader.py asserts parity with the
# OpenSpiel implementation — getting this wrong yields a plausible-but-different
# game that desyncs within a few moves.
ENGINE_SEED_MULTIPLIER = 2654435761
ENGINE_SEED_MASK = 0x7FFFFFFF


def engine_seed(shuffle_seed: int) -> int:
    """Return the C-engine randomness seed for an OpenSpiel chance action id."""
    return (int(shuffle_seed) * ENGINE_SEED_MULTIPLIER) & ENGINE_SEED_MASK


@dataclass(frozen=True)
class ReplayMeta:
    game_dir: Path
    run_id: str
    label: str            # "game_0003 · dragon/drow · seed 45 · 4p · 1026 moves · p2 win"
    player_ids: tuple[str, ...]
    deck_a_id: str
    deck_b_id: str
    shuffle_seed: int
    step_count: int
    outcome: str | None
    winner_id: str | None


@dataclass
class ReplayBundle:
    meta: ReplayMeta
    replay: dict
    summary: dict | None
    decisions: list[dict]                 # [] when decisions.jsonl is absent
    setup_json: str
    setup_sha_matches: bool | None        # None when summary.json has no sha
    board_path: Path
    card_path: Path
    setup_path: Path
    substituted_paths: tuple[str, ...] = field(default_factory=tuple)
    schema_version: int | None = None     # replay.json ``schema_version``; None = legacy
    manifest: dict | None = None          # sibling run manifest.json, if present


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _load_summary(game_dir: Path) -> dict | None:
    path = game_dir / "summary.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def is_complete_game(game_dir: Path) -> bool:
    """True only when ``summary.json`` exists, parses, and is terminal.

    A missing/malformed summary, ``"error"`` or ``"round_cap"`` all count as
    incomplete. This is the single completeness predicate shared by the replay
    viewer, ``scripts/verify_replays.py`` and the dataset builder.
    """
    summary = _load_summary(Path(game_dir))
    if summary is None:
        return False
    return summary.get("stopped_reason") == "terminal"


def _load_manifest(game_dir: Path) -> dict | None:
    path = game_dir.parent / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _manifest_setup(
    game_dir: Path,
    manifest: dict | None,
    recomposed: str,
    summary: dict | None,
) -> str:
    """Prefer the manifest's inline ``setup_data_json`` when its sha matches.

    Falls back to *recomposed* (the historical deck-id rebuild, G18) when the
    manifest is absent, has no entry for this game, or the inline JSON does not
    hash to the recorded/`summary` sha.
    """
    if not manifest:
        return recomposed
    for entry in manifest.get("games", []) or []:
        try:
            name = f"game_{int(entry.get('game_index')):04d}"
        except (TypeError, ValueError):
            continue
        if name != game_dir.name:
            continue
        inline = entry.get("setup_data_json")
        if not isinstance(inline, str) or not inline:
            return recomposed
        expected = entry.get("setup_data_sha256")
        if expected is not None and _sha256(inline) != expected:
            return recomposed
        if (
            summary
            and summary.get("setup_data_sha256")
            and _sha256(inline) != summary["setup_data_sha256"]
        ):
            return recomposed
        return inline
    return recomposed


def _load_decisions(game_dir: Path) -> list[dict]:
    path = game_dir / "decisions.jsonl"
    result: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    result.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return result


def _winner_label(winner_id: str | None, outcome: str | None) -> str:
    if winner_id:
        return f"{winner_id} win"
    if outcome:
        return outcome.replace("_", " ")
    return "ended"


def _build_meta(
    game_dir: Path,
    replay: dict,
    summary: dict | None,
) -> ReplayMeta:
    ctx = replay.get("replay_context", {})
    player_ids = tuple(str(pid) for pid in ctx.get("player_ids", ()))
    deck_a_id = str(ctx.get("deck_a_id", ""))
    deck_b_id = str(ctx.get("deck_b_id", ""))
    shuffle_seed = int(ctx.get("seed", 0))
    step_count = int(replay.get("step_count", 0))

    winner_id = replay.get("winner_id")
    if winner_id is None and summary and isinstance(summary.get("winner"), int):
        index = summary["winner"]
        if 0 <= index < len(player_ids):
            winner_id = player_ids[index]
    outcome = (summary or {}).get("outcome")

    label = (
        f"{game_dir.name} · {deck_a_id}/{deck_b_id} · seed {shuffle_seed} · "
        f"{len(player_ids)}p · {step_count} moves · {_winner_label(winner_id, outcome)}"
    )
    return ReplayMeta(
        game_dir=game_dir,
        run_id=str(replay.get("run_id", "")),
        label=label,
        player_ids=player_ids,
        deck_a_id=deck_a_id,
        deck_b_id=deck_b_id,
        shuffle_seed=shuffle_seed,
        step_count=step_count,
        outcome=outcome,
        winner_id=winner_id,
    )


def discover_replays(root: Path) -> list[ReplayMeta]:
    """Return every replay under *root*, newest-first.

    A directory with a missing or unreadable ``summary.json`` still yields a
    usable :class:`ReplayMeta` derived from ``replay.json`` alone.
    """
    candidates: list[tuple[Path, ReplayMeta]] = []
    for replay_path in sorted(root.rglob("replay.json")):
        try:
            replay = json.loads(replay_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        game_dir = replay_path.parent
        meta = _build_meta(game_dir, replay, _load_summary(game_dir))
        candidates.append((replay_path, meta))
    candidates.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)
    return [meta for _, meta in candidates]


def _resolve_path(ctx: dict, key: str, default: Path) -> tuple[Path, bool]:
    raw = ctx.get(key)
    if raw:
        candidate = Path(raw)
        if candidate.exists():
            return candidate, False
    return default, True


def _build_setup_json(setup_path: Path, ctx: dict) -> str:
    """Recompose the two-deck market setup for this replay's deck roster pair."""
    profiles = {profile.deck_id: profile for profile in discover_full_deck_profiles(DECKS_DIR)}
    deck_a = profiles.get(ctx.get("deck_a_id", ""))
    deck_b = profiles.get(ctx.get("deck_b_id", ""))
    try:
        base_setup = json.loads(setup_path.read_text(encoding="utf-8"))
    except Exception:
        return "{}"
    if deck_a is None or deck_b is None:
        return json.dumps(base_setup)
    market = combine_two_deck_market_setup(base_setup, deck_a, deck_b)
    return json.dumps(market.to_setup_data())


def load_replay(game_dir: Path) -> ReplayBundle:
    """Load one replay directory into a fully-resolved bundle.

    ``replay_context`` carries absolute paths from the producing machine; any
    path that does not exist here falls back to the repo defaults and is
    recorded in ``substituted_paths``.
    """
    replay = json.loads((game_dir / "replay.json").read_text(encoding="utf-8"))
    summary = _load_summary(game_dir)
    decisions = _load_decisions(game_dir)
    meta = _build_meta(game_dir, replay, summary)

    ctx = replay.get("replay_context", {})
    board_path, board_sub = _resolve_path(ctx, "board_path", DEFAULT_BOARD_PATH)
    card_path, card_sub = _resolve_path(ctx, "card_path", DEFAULT_CARD_PATH)
    setup_path, setup_sub = _resolve_path(ctx, "setup_path", DEFAULT_SETUP_PATH)
    substituted = tuple(
        name
        for name, flag in (
            ("board_path", board_sub),
            ("card_path", card_sub),
            ("setup_path", setup_sub),
        )
        if flag
    )

    manifest = _load_manifest(game_dir)
    setup_json = _manifest_setup(
        game_dir, manifest, _build_setup_json(setup_path, ctx), summary
    )

    setup_sha_matches = None
    if summary and summary.get("setup_data_sha256"):
        setup_sha_matches = _sha256(setup_json) == summary["setup_data_sha256"]

    schema_version = replay.get("schema_version")
    if not isinstance(schema_version, int):
        schema_version = None

    return ReplayBundle(
        meta=meta,
        replay=replay,
        summary=summary,
        decisions=decisions,
        setup_json=setup_json,
        setup_sha_matches=setup_sha_matches,
        board_path=board_path,
        card_path=card_path,
        setup_path=setup_path,
        substituted_paths=substituted,
        schema_version=schema_version,
        manifest=manifest,
    )