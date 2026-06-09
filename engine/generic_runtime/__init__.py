"""Generic structured-card interpreter — private runtime for data-driven card actions."""

from engine.generic_runtime._resolve import (
    _action_requires_selection,
    _apply_resolve_generic_choice,
    _legal_pending_generic_choice_moves,
    _resolve_generic_execution,
)

__all__ = [
    "_action_requires_selection",
    "_apply_resolve_generic_choice",
    "_legal_pending_generic_choice_moves",
    "_resolve_generic_execution",
]
