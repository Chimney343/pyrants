"""Per-card play post-mortem analysis package.

See ``docs/card-playstats-plan.md``. Modules:

- :mod:`~scripts.card_playstats.discovery` — find IS-MCTS run folders
- :mod:`~scripts.card_playstats.catalog` — card/modal metadata from ``data/cards``
- :mod:`~scripts.card_playstats.extract` — per-game extraction (log + engine replay)
- :mod:`~scripts.card_playstats.metadata` — per-run collection metadata
- :mod:`~scripts.card_playstats.report` — pandas/plotly aggregation layer
"""

from __future__ import annotations
