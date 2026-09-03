"""Headless replay stepping: CSession lifecycle, step/seek, desync detection.

Tk-free and pyspiel-free. Rebuilds a session from scratch on every seek via
*destroy -> create -> fast-forward* (measured ~80 ms worst case for a 1000-step
game), which is why no snapshot/undo machinery is needed.
"""

from __future__ import annotations

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.session import CSession

from .replay_loader import ReplayBundle, engine_seed


class ReplayDesyncError(RuntimeError):
    """A logged move does not match any live legal move at a replayed step."""

    def __init__(self, step_index: int, expected: dict, legal: list[dict]) -> None:
        self.step_index = step_index
        self.expected = expected
        self.legal = legal
        super().__init__(
            f"Replay desync at step {step_index}: no legal move matches {expected!r}"
        )


class ReplayPlayer:
    """Step/seek a loaded replay by re-simulating it through the C engine."""

    def __init__(self, bundle: ReplayBundle) -> None:
        self.bundle = bundle
        self._log = [
            entry
            for entry in bundle.replay.get("replay_log", ())
            if entry.get("payload", {}).get("move_type") != "__terminal__"
        ]

        # One CEngine for the whole player lifetime; rebuilds reuse it.
        self._engine = CEngine()
        self._engine.initialize(
            catalog_path=str(bundle.card_path),
            board_path=str(bundle.board_path),
            setup_path=str(bundle.setup_path),
            setup_data_json=bundle.setup_json,
        )
        self._session: CSession | None = None
        self._index = 0
        self._rebuild()

    @property
    def index(self) -> int:
        """Moves applied so far, 0..total_steps."""
        return self._index

    @property
    def total_steps(self) -> int:
        """Number of logged moves; excludes the ``__terminal__`` sentinel."""
        return len(self._log)

    @property
    def session(self) -> CSession:
        return self._session

    @property
    def is_terminal(self) -> bool:
        return self._session.is_terminal()

    def entry_at(self, i: int) -> dict | None:
        if 0 <= i < len(self._log):
            return self._log[i]
        return None

    def decision_at(self, i: int) -> dict | None:
        if 0 <= i < len(self.bundle.decisions):
            return self.bundle.decisions[i]
        return None

    def next_entry(self) -> dict | None:
        return self.entry_at(self._index)

    def _rebuild(self) -> None:
        if self._session is not None:
            self._session.destroy()
            self._session = None
        self._session = CSession(
            self._engine,
            list(self.bundle.meta.player_ids),
            seed=engine_seed(self.bundle.meta.shuffle_seed),
        )
        self._index = 0

    def _apply_entry(self, entry: dict) -> None:
        expected = entry["payload"]
        moves = self._session.legal_moves()
        match = next((m for m in moves if m.to_payload() == expected), None)
        if match is None or self._session.submit_move(match) is None:
            raise ReplayDesyncError(
                entry["step_index"],
                expected,
                [m.to_payload() for m in moves[:10]],
            )

    def reset(self) -> None:
        self.seek(0)

    def step_forward(self) -> bool:
        """Apply the next logged move; returns False at the end."""
        if self._index >= self.total_steps:
            return False
        self._apply_entry(self._log[self._index])
        self._index += 1
        return True

    def step_back(self) -> None:
        self.seek(self._index - 1)

    def seek(self, i: int) -> None:
        """Clamp to [0, total_steps], rebuild, and fast-forward to step *i*.

        On desync the session is left at the last good state and the exception
        carries the faulty step.
        """
        target = max(0, min(i, self.total_steps))
        self._rebuild()
        for entry in self._log[:target]:
            self._apply_entry(entry)
            self._index += 1

    def close(self) -> None:
        if self._session is not None:
            self._session.destroy()
            self._session = None
        self._engine = None  # arena freed when the CEngine is collected