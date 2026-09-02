"""Shared market-setup logic for two-deck combined markets.

Used by game-viewer, IS-MCTS runner, scenario generator, and random-walk
script. Each caller keeps its own selection policy but delegates the "given
two 40-card rosters, build the combined market" work here.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from random import Random

from game_setup.loaders import load_deck_rosters

logger = logging.getLogger(__name__)

SPECIAL_RECRUIT_IDS: frozenset[str] = frozenset({"house_guard", "priestess_of_lolth", "insane_outcast"})

DEMONS_DECK_ID = "demons"

HOUSE_GUARD_RECRUIT_SLOT = 100
PRIESTESS_RECRUIT_SLOT = 101
INSANE_OUTCAST_RECRUIT_SLOT = 102

_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECKS_DIR = _ROOT / "data" / "decks"


@dataclass(frozen=True)
class DeckProfile:
    """One selectable market half deck from roster data."""

    deck_id: str
    label: str
    total_cards: int
    entries: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class SpecialStackSpec:
    """One special-recruit stack (slot → card, with a total count)."""

    market_slot: int
    card_id: str
    stack_total: int

    def to_dict(self) -> dict[str, object]:
        return {
            "market_slot": self.market_slot,
            "card_id": self.card_id,
            "stack_total": self.stack_total,
        }


@dataclass(frozen=True)
class MarketSetup:
    """Built two-deck combined market ready for game construction."""

    setup_id: str
    market_deck_id: str
    starter_deck: dict[str, object]
    market_deck_entries: tuple[tuple[str, int], ...]
    market_row_size: int
    special_stacks: tuple[SpecialStackSpec, ...]

    def to_setup_data(self) -> dict[str, object]:
        return {
            "setup_id": self.setup_id,
            "starter_deck": self.starter_deck,
            "market_deck": {
                "deck_id": self.market_deck_id,
                "entries": [
                    {"card_id": card_id, "count": count}
                    for card_id, count in self.market_deck_entries
                ],
            },
            "market_row_size": self.market_row_size,
            "special_stacks": [spec.to_dict() for spec in self.special_stacks],
        }


def discover_full_deck_profiles(decks_dir: Path) -> tuple[DeckProfile, ...]:
    """Load 40-card ``kind: full_deck`` rosters, excluding special-recruit stacks."""
    raw_decks = load_deck_rosters(decks_dir)
    profiles: list[DeckProfile] = []

    for raw_deck in raw_decks:
        if not isinstance(raw_deck, dict):
            continue
        kind = raw_deck.get("kind")
        total_cards = raw_deck.get("total_cards")
        deck_id = raw_deck.get("deck_id")
        if kind != "full_deck" or total_cards != 40 or deck_id in SPECIAL_RECRUIT_IDS:
            continue

        name = raw_deck.get("name")
        entries = raw_deck.get("entries")
        if not isinstance(name, str) or not isinstance(entries, list):
            continue

        normalized_entries: list[tuple[str, int]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            card_id = entry.get("card_id")
            count = entry.get("count")
            if not isinstance(card_id, str) or not isinstance(count, int):
                continue
            normalized_entries.append((card_id, count))

        if sum(count for _, count in normalized_entries) != 40:
            continue

        profiles.append(
            DeckProfile(
                deck_id=deck_id,
                label=f"{name} ({deck_id})",
                total_cards=40,
                entries=tuple(normalized_entries),
            )
        )

    profiles.sort(key=lambda p: p.deck_id)
    return tuple(profiles)


def load_special_stack_counts(decks_dir: Path | None = None) -> dict[str, int]:
    """Read each special-recruit stack's total from its single_card_stack roster."""
    decks = load_deck_rosters(decks_dir or DEFAULT_DECKS_DIR)
    counts: dict[str, int] = {}
    for deck in decks:
        deck_id = deck.get("deck_id")
        if deck_id not in SPECIAL_RECRUIT_IDS:
            continue
        total = deck.get("total_cards")
        if isinstance(total, int) and total > 0:
            counts[str(deck_id)] = total
    return counts


def compute_special_stacks(
    deck_a_id: str,
    deck_b_id: str,
    decks_dir: Path | None = None,
) -> tuple[SpecialStackSpec, ...]:
    """Return the special-recruit stacks for a two-deck market.

    House Guard and Priestess of Lolth are always present; Insane Outcast is
    present iff the Demons half-deck is one of the two market decks (rulebook:
    "If you're playing with the Demons half-deck, put the Insane Outcast cards
    face up"). Totals are read from the roster files.
    """
    counts = load_special_stack_counts(decks_dir)
    specs = [
        SpecialStackSpec(
            market_slot=HOUSE_GUARD_RECRUIT_SLOT,
            card_id="house_guard",
            stack_total=counts["house_guard"],
        ),
        SpecialStackSpec(
            market_slot=PRIESTESS_RECRUIT_SLOT,
            card_id="priestess_of_lolth",
            stack_total=counts["priestess_of_lolth"],
        ),
    ]
    if DEMONS_DECK_ID in {deck_a_id, deck_b_id}:
        specs.append(
            SpecialStackSpec(
                market_slot=INSANE_OUTCAST_RECRUIT_SLOT,
                card_id="insane_outcast",
                stack_total=counts["insane_outcast"],
            )
        )
    return tuple(specs)


def combine_two_deck_market_setup(
    base_setup: dict[str, object],
    deck_a: DeckProfile,
    deck_b: DeckProfile,
) -> MarketSetup:
    combined_counts: dict[str, int] = {}
    for card_id, count in (*deck_a.entries, *deck_b.entries):
        combined_counts[card_id] = combined_counts.get(card_id, 0) + count

    market_entries = tuple(sorted((card_id, count) for card_id, count in combined_counts.items()))

    starter_deck = base_setup.get("starter_deck")
    if not isinstance(starter_deck, dict):
        raise ValueError("Base setup file must define starter_deck")

    setup_id = f"{deck_a.deck_id}_{deck_b.deck_id}"
    market_deck_id = f"market_{deck_a.deck_id}_{deck_b.deck_id}"
    market_row_size = base_setup.get("market_row_size", 6)
    if not isinstance(market_row_size, int):
        market_row_size = 6
    special_stacks = compute_special_stacks(deck_a.deck_id, deck_b.deck_id)

    return MarketSetup(
        setup_id=setup_id,
        market_deck_id=market_deck_id,
        starter_deck=starter_deck,
        market_deck_entries=market_entries,
        market_row_size=market_row_size,
        special_stacks=special_stacks,
    )


def pick_random_pair(
    profiles: Sequence[DeckProfile],
    rng: Random,
) -> tuple[DeckProfile, DeckProfile]:
    if len(profiles) < 1:
        raise ValueError("No full deck profiles available")
    if len(profiles) == 1:
        return (profiles[0], profiles[0])
    a, b = rng.sample(list(profiles), 2)
    return (a, b)


def pick_pair_for_target(
    profiles: Sequence[DeckProfile],
    target_card_id: str,
    rng: Random,
) -> tuple[DeckProfile, DeckProfile]:
    if len(profiles) < 1:
        raise ValueError("No full deck profiles available")

    roster_a: DeckProfile | None = None
    if target_card_id not in SPECIAL_RECRUIT_IDS:
        for profile in profiles:
            entry_ids = {entry[0] for entry in profile.entries}
            if target_card_id in entry_ids:
                roster_a = profile
                break

    if roster_a is None:
        roster_a = rng.choice(list(profiles))

    eligible_b = [p for p in profiles if p.deck_id != roster_a.deck_id]
    if eligible_b:
        roster_b = rng.choice(eligible_b)
    else:
        logger.warning(
            "Only one full_deck roster (%s) available; duplicating for two-deck market",
            roster_a.deck_id,
        )
        roster_b = roster_a

    return (roster_a, roster_b)
