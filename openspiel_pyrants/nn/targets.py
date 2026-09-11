"""Value/policy target math. Pure numpy; applied at load time by ``load_shard``.

Shards store raw inputs (final scores, legal ids, visits, q) so changing the
normalisation here never requires a dataset rebuild (D11).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

VALUE_SCALE = 40.0
SIMS_WEIGHT_SATURATION = 200


def value_targets(scores: Sequence[float], num_players: int) -> np.ndarray:
    """Return the length-4 value target for a rotated score vector.

    ``scores`` is in seat order with the acting seat first (the builder
    rotates). Two players use the antisymmetric ``tanh((mine - theirs)/40)``;
    three to four use ``clip((score - mean(others))/40, -1, 1)`` per seat.
    Absent seats are zero.
    """
    out = np.zeros(4, dtype=np.float32)
    n = int(num_players)
    if n < 2:
        return out
    values = [float(s) for s in scores[:n]]
    if n == 2:
        diff = values[0] - values[1]
        out[0] = np.tanh(diff / VALUE_SCALE)
        out[1] = np.tanh(-diff / VALUE_SCALE)
        return out
    for i in range(n):
        others = [values[j] for j in range(n) if j != i]
        mean_others = sum(others) / len(others)
        out[i] = float(np.clip((values[i] - mean_others) / VALUE_SCALE, -1.0, 1.0))
    return out


def merge_duplicates(
    gids: Sequence[int],
    visits: Sequence[float],
    q_values: Sequence[float] | None = None,
):
    """Collapse multiple legal ids mapping to one global id.

    Returns ``(unique_gids, summed_visits, weighted_q)`` where ``weighted_q`` is
    the visit-weighted mean of ``q_values`` (or ``None`` when not given).
    """
    order: list[int] = []
    visit_sum: dict[int, float] = {}
    q_num: dict[int, float] = {}
    q_den: dict[int, float] = {}
    for i, gid in enumerate(gids):
        gid = int(gid)
        if gid not in visit_sum:
            visit_sum[gid] = 0.0
            q_num[gid] = 0.0
            q_den[gid] = 0.0
            order.append(gid)
        v = float(visits[i]) if i < len(visits) else 0.0
        visit_sum[gid] += v
        if q_values is not None and i < len(q_values):
            q_num[gid] += float(q_values[i]) * v
            q_den[gid] += v

    if q_values is None:
        weighted_q = None
    else:
        weighted_q = {
            gid: (q_num[gid] / q_den[gid] if q_den[gid] > 0 else 0.0) for gid in order
        }
    return order, [visit_sum[gid] for gid in order], weighted_q


def policy_target(gids: Sequence[int], visits: Sequence[float], num_actions: int = 2048) -> np.ndarray:
    """Visit distribution over global ids; sums to 1 (or all zeros)."""
    out = np.zeros(num_actions, dtype=np.float32)
    unique, summed, _ = merge_duplicates(gids, visits)
    total = sum(summed)
    if total <= 0:
        return out
    for gid, v in zip(unique, summed, strict=False):
        out[gid] = v / total
    return out


def sample_weight(sims_requested: float) -> float:
    """Per-sample weight, monotone in the requested sims budget."""
    return float(min(max(sims_requested, 0), SIMS_WEIGHT_SATURATION)) / SIMS_WEIGHT_SATURATION
