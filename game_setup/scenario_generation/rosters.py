"""Engine-agnostic roster and card-scenario helpers.

These helpers were extracted from the legacy Python scenario generator so the
surviving C-engine scenario search (``engine_c/bindings/scenario_search``) and
the ``generate_card_scenarios`` script can share a single source of truth
without importing the deprecated Python engine.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from random import Random
from typing import Any

from game_setup.loaders import load_deck_rosters
from game_setup.market_setup import (
    compute_special_stacks,
    discover_full_deck_profiles,
    pick_pair_for_target,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOARD_PATH = ROOT / "data" / "boards" / "tyrants_of_the_underdark.json"
DEFAULT_CARD_PATH = ROOT / "data" / "cards"
DEFAULT_SETUP_PATH = ROOT / "data" / "decks" / "base_setup.json"
DEFAULT_ROSTERS_PATH = ROOT / "data" / "decks"
FORCED_INJECTIONS_FILENAME = "forced_injections.json"


@dataclass
class StopConditions:
    require_spy_on_board: bool = False
    require_aspect: str | None = None
    require_aspect_count: int = 0


def _stable_hash(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")


@lru_cache(maxsize=4)
def _cached_roster_decks(rosters_path_str: str) -> list[dict[str, Any]]:
    return load_deck_rosters(Path(rosters_path_str))


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


def write_forced_injection_notes(output_dir: Path, notes: list[dict[str, object]]) -> Path:
    path = output_dir / FORCED_INJECTIONS_FILENAME
    path.write_text(json.dumps(notes, indent=2) + "\n", encoding="utf-8")
    return path
