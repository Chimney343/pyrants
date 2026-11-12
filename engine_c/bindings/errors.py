"""The game handle's failure family (ADR-0011, brief F1).

One family, one base class, everything a ``RuntimeError`` so every existing
``except RuntimeError`` call site keeps working. This module is a leaf: it
imports nothing from ``engine_c.bindings``, so ``ce_api`` and ``handle`` can
both use it without an import cycle.

``EngineError`` is the base and is not for catching; catch the subclass that
names the failure.
"""

from __future__ import annotations


class EngineError(RuntimeError):
    """Base of every engine failure. Not for catching."""


class EngineSetupFailed(EngineError):
    """A game could not be set up: definition load, setup JSON, or state create."""


class EngineApplyRejected(EngineError):
    """``engine_apply`` returned NULL, so the move is not legal in this state."""


class EngineCloneFailed(EngineError):
    """``engine_clone`` returned NULL. A clone never aliases its original (F-042)."""


class EngineDeterminizeFailed(EngineError):
    """``engine_determinize`` returned NULL."""


class EngineDestroyedError(EngineError):
    """The handle was destroyed and can no longer be used."""


class MoveCapacityError(EngineError):
    """A move query found more moves than the frozen capacity can represent.

    The capacity is the NN action space, a wire format. A state that needs
    more moves cannot be described by an OpenSpiel action id, so callers must
    see this rather than a truncated list.
    """

    def __init__(self, query: str, needed: int, capacity: int) -> None:
        self.query = query
        self.needed = needed
        self.capacity = capacity
        super().__init__(
            f"{query} query returned {needed} moves, above the frozen capacity "
            f"{capacity}; the move would have been truncated silently before F-038"
        )
