"""Read the engine's pending-generic-choice state into a plain dict.

The C ``GameState.pending_generic`` struct holds every card/action fact a
consumer needs to describe a ``resolve_generic`` decision — which card is
being resolved, which ``CardAction`` is currently executing, whether the
player is choosing a modal option — but it is only valid *before* the move
answering it is applied (``apply_resolve_generic_choice`` advances or clears
the pending state).  This module is the single reader for that pre-apply
window, shared by the legal-move label enricher (``view.py``) and the
IS-MCTS runner's decision telemetry (``scripts/run_ismcts.py``).

Kept import-light (no ``pyspiel``, no engine import beyond the existing
ctypes structs) so it stays testable in isolation.
"""

from __future__ import annotations

from .engine_bindings import sym_str


def read_pending_generic_context(state_ptr) -> dict | None:
    """Decode ``state_ptr.contents.pending_generic`` into a JSON-ready dict.

    Returns ``None`` when *state_ptr* is null or no generic choice is pending
    (``state_ptr.contents.pending_generic`` is null).  Otherwise decodes the
    ``PendingGenericChoiceState`` and, when an action is currently executing
    (not awaiting an option and ``next_action_index`` is in bounds), the
    active ``CardAction`` into:

    ``source_card_id``, ``op``, ``card_action_id``, ``current_option_id``,
    ``awaiting_option``, ``optional``

    Every sym-backed field is ``sym_str``-decoded and ``None``-safe.  A
    decode failure degrades to ``None`` rather than raising, mirroring the
    guards the legal-move walk already used.
    """
    try:
        if not state_ptr or not state_ptr.contents.pending_generic:
            return None
        pg = state_ptr.contents.pending_generic.contents

        awaiting_option = bool(pg.awaiting_option)
        op = None
        card_action_id = None
        optional = False
        if not awaiting_option:
            idx = pg.next_action_index
            if 0 <= idx < pg.current_action_count:
                action = pg.current_actions[idx]
                optional = bool(action.optional)
                op = sym_str(action.op)
                card_action_id = sym_str(action.action_id)

        return {
            "source_card_id": sym_str(pg.source_card_id),
            "op": op,
            "card_action_id": card_action_id,
            "current_option_id": sym_str(pg.current_option_id),
            "awaiting_option": awaiting_option,
            "optional": optional,
        }
    except Exception:
        return None
