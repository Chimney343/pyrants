"""Core engine package for the Tyrants implementation."""

from engine.rules import apply, is_terminal, legal_moves, winner

__all__ = ["apply", "is_terminal", "legal_moves", "winner"]
