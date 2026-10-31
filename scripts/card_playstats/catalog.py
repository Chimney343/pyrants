"""Card catalog metadata: which cards are modal and what their options are.

Loads ``data/cards/*.json`` once and exposes the only fact the play analysis
needs — whether a card presents a choice of options — plus each option's
``option_id``. Option labels fall back to the raw ``option_id`` because most
modal cards ship without a human label (only a couple do).

Both ``modal_choice`` and ``repeat_choice`` cards present options to the
engine (``engine_c/generic_runtime.c`` sets ``awaiting_option`` for
``EXEC_MODAL`` and ``EXEC_REPEAT`` alike), so both are treated as modal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SKIP_FILES = frozenset({"manifest.json", "cards_OCR.json"})
MODAL_KINDS = frozenset({"modal_choice", "repeat_choice"})


@dataclass(frozen=True)
class CardInfo:
    card_id: str
    is_modal: bool
    options: tuple[tuple[str, str], ...]  # (option_id, label)

    @property
    def option_ids(self) -> frozenset[str]:
        return frozenset(option_id for option_id, _ in self.options)

    def label_for(self, option_id: str) -> str:
        for declared, label in self.options:
            if declared == option_id:
                return label
        return option_id


class CardCatalog:
    """Read-only mapping of ``card_id -> CardInfo``."""

    def __init__(self, cards: dict[str, CardInfo]) -> None:
        self._cards = cards

    @classmethod
    def from_dir(cls, card_path: Path) -> CardCatalog:
        card_path = Path(card_path)
        cards: dict[str, CardInfo] = {}
        for path in sorted(card_path.glob("*.json")):
            if path.name in SKIP_FILES:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            card_id = data.get("card_id")
            if not isinstance(card_id, str) or not card_id:
                card_id = path.stem
            cards[card_id] = _card_info(card_id, data)
        return cls(cards)

    def get(self, card_id: str) -> CardInfo | None:
        return self._cards.get(card_id)

    def is_modal(self, card_id: str) -> bool:
        info = self._cards.get(card_id)
        return bool(info and info.is_modal)

    def option_ids(self, card_id: str) -> frozenset[str]:
        info = self._cards.get(card_id)
        return info.option_ids if info else frozenset()

    def label_for(self, card_id: str, option_id: str) -> str:
        info = self._cards.get(card_id)
        return info.label_for(option_id) if info else option_id

    def modal_card_ids(self) -> set[str]:
        return {card_id for card_id, info in self._cards.items() if info.is_modal}

    def __contains__(self, card_id: object) -> bool:
        return card_id in self._cards

    def __len__(self) -> int:
        return len(self._cards)


def _card_info(card_id: str, data: dict) -> CardInfo:
    model = data.get("execution_model")
    model = model if isinstance(model, dict) else {}
    is_modal = model.get("kind") in MODAL_KINDS
    options: list[tuple[str, str]] = []
    if is_modal:
        for option in model.get("options") or []:
            if not isinstance(option, dict):
                continue
            option_id = option.get("option_id")
            if not isinstance(option_id, str) or not option_id:
                continue
            label = option.get("label")
            options.append((option_id, label if isinstance(label, str) and label else option_id))
    return CardInfo(card_id=card_id, is_modal=is_modal, options=tuple(options))


def load_catalog(card_path: Path) -> CardCatalog:
    """Load ``data/cards`` into a :class:`CardCatalog`."""
    return CardCatalog.from_dir(card_path)
