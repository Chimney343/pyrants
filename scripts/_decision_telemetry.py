"""Root-node search telemetry extraction for the IS-MCTS runner.

Pure and duck-typed on the stock ``ISMCTSBot``'s ``_root_node`` /
``child_info`` / ``visits`` / ``return_sum`` / ``total_visits`` attributes, so
it can be unit-tested without pyspiel. Implements Phase 2 (Layer 1) of
``docs/nn-training-data-tdd-plan.md``.
"""

from __future__ import annotations

_EMPTY_STATS = {
    "visit_counts": {},
    "q_values": {},
    "root_value": None,
    "total_visits": 0,
}


def extract_root_stats(bot, legal_ids) -> dict:
    """Return real root-search telemetry for one decision.

    Forced moves (``len(legal_ids) <= 1``) return the D6 all-empty shape even
    though the stock bot leaves a stale ``_root_node`` from the previous
    decision (G6). For non-forced moves the stock root has expanded at least
    one child; ``visit_counts`` covers *every* legal id (zeros included) and
    ``q_values`` only the visited ones, all as builtin JSON-safe scalars.

    ``root_value`` is ``sum(return_sum) / total_visits`` (i.e. the visit-
    weighted mean of ``q_values``) or ``None`` when nothing was visited.
    """
    ids = [int(a) for a in legal_ids]
    if len(ids) <= 1:
        return dict(_EMPTY_STATS)

    root = getattr(bot, "_root_node", None)
    if root is None:
        # A bot that never ran a search (e.g. a scripted test bot) has no root
        # at all; report the forced shape rather than raising.
        return dict(_EMPTY_STATS)

    child_info = getattr(root, "child_info", None) or {}
    total_visits = int(getattr(root, "total_visits", 0) or 0)

    visit_counts: dict[int, int] = {aid: 0 for aid in ids}
    q_values: dict[int, float] = {}
    return_sum_total = 0.0
    for action, child in child_info.items():
        aid = int(action)
        visits = int(child.visits)
        return_sum_total += float(child.return_sum)
        visit_counts[aid] = visits
        if visits > 0:
            q_values[aid] = float(child.return_sum) / visits

    if not child_info:
        return {
            "visit_counts": visit_counts,
            "q_values": q_values,
            "root_value": None,
            "total_visits": total_visits,
        }

    root_value = (return_sum_total / total_visits) if total_visits > 0 else None
    return {
        "visit_counts": visit_counts,
        "q_values": q_values,
        "root_value": root_value,
        "total_visits": total_visits,
    }
