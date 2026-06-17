"""Protocol defining the session interface used by the game viewer.

Both game_session.GameSession and engine_c.bindings.session.CSession
satisfy this protocol, allowing the viewer to swap backends via
the --engine flag.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class SessionLike(Protocol):
    @property
    def state(self) -> object: ...
    @property
    def move_count(self) -> int: ...
    def is_terminal(self) -> bool: ...
    def legal_moves(self) -> list: ...
    def submit_move(self, move) -> object | None: ...
    def save(self, path: str) -> None: ...
    @classmethod
    def load(cls, path: str, **kwargs) -> "SessionLike": ...
