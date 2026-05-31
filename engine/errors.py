"""Typed exceptions for rules and move validation failures."""


class RuleViolationError(Exception):
    """Raised when a move violates enforced game rules."""


class IllegalMoveError(RuleViolationError):
    """Raised when a move is not legal in the current state."""


class MissingRuleImplementationError(NotImplementedError):
    """Raised for rule areas that are intentionally blocked by unresolved source gaps."""


class UnknownCardEffectError(RuleViolationError):
    """Raised when a card references an unregistered effect handler."""
