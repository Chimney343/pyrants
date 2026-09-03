"""Pure helpers for the IS-MCTS sims-vs-wins experiment.

Import-light (no ``pyspiel``, no ``numpy`` at module import time) so the
parsing and analysis logic stays testable in isolation, mirroring the
``scripts/_obs.py`` / ``scripts/_replay_payload.py`` pattern.

The statistical core is ``analyze``: it turns a list of per-game summary
dicts (each carrying ``num_sims_per_seat``, ``returns``, ``winner``, and
``stopped_reason``) into win rates per budget and per seat, Wilson 95% CIs,
mean final VP / mean rank per budget, and a within-game permutation trend
test for the hypothesis "larger simulation budget → higher final VP".
"""

from __future__ import annotations

import math
import random


def parse_sims_spec(spec: str, num_players: int) -> list[int]:
    """Parse and validate a comma-separated per-seat simulation budget spec.

    Returns a list of ``num_players`` positive integers. Raises ``ValueError``
    on an empty segment, a non-integer, a length mismatch with ``num_players``,
    or any budget < 1.
    """
    parts = [p.strip() for p in spec.split(",")]
    if any(p == "" for p in parts):
        raise ValueError(f"empty budget in spec {spec!r}")
    try:
        values = [int(p) for p in parts]
    except ValueError as exc:
        raise ValueError(f"non-integer budget in spec {spec!r}") from exc
    if len(values) != num_players:
        raise ValueError(
            f"expected {num_players} budgets for {num_players} players, got {len(values)}"
        )
    if any(v < 1 for v in values):
        raise ValueError(f"all budgets must be >= 1, got {values}")
    return values


def seat_budgets_for_game(base: list[int], game_index: int, rotate: bool) -> list[int]:
    """Return the per-seat budget list for game ``game_index``.

    Fixed (``rotate=False``) returns ``base`` unchanged. Rotated, seat ``i``
    receives ``base[(i + game_index) % len(base)]``, so over any ``len(base)``
    consecutive games every budget occupies every seat exactly once,
    deconfounding seat order (seat 0 always moves first) from budget strength.
    """
    if not rotate:
        return list(base)
    n = len(base)
    shift = game_index % n
    if shift == 0:
        return list(base)
    return base[shift:] + base[:shift]


# ---------------------------------------------------------------------------
# Statistics helpers (pure stdlib)
# ---------------------------------------------------------------------------


def _rank_asc(values: list[float]) -> list[float]:
    """Average ranks ascending (1 = smallest); ties share the mean rank."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _rank_desc(values: list[float]) -> list[float]:
    """Average ranks descending (1 = largest value)."""
    return _rank_asc([-v for v in values])


def _spearman(x: list[float], y: list[float]) -> float:
    """Spearman rank correlation between two equal-length vectors."""
    rx = _rank_asc(x)
    ry = _rank_asc(y)
    n = len(rx)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((rx[i] - mx) ** 2 for i in range(n))
    dy = sum((ry[i] - my) ** 2 for i in range(n))
    denom = math.sqrt(dx * dy)
    if denom == 0.0:
        return 0.0
    return num / denom


def _wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% confidence interval for a binomial proportion ``wins / n``."""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (center - margin, center + margin)


def analyze(
    summaries: list[dict],
    *,
    n_players: int,
    n_permutations: int = 10_000,
    seed: int = 0,
) -> dict:
    """Analyse per-game summaries into budget/seat win rates and a trend test.

    Primary win rates are computed over *decided* games only (``stopped_reason
    == "terminal"`` with a unique ``winner``). Ties, ``round_cap`` truncations,
    and ``error`` games (from ``GameRunFailedError`` partial summaries) are
    excluded from those rates but counted in ``exclusions``. Mean final VP /
    mean rank and the trend test use every game carrying a valid ``returns``
    list, which excludes error games (they have no terminal scores).

    The trend statistic is the mean over games of the Spearman rank
    correlation between ``log2(budget)`` and final VP. Its null permutes the
    budget→seat assignment *within each game* (preserving each game's score
    multiset and seat structure); ``n_permutations`` seeded permutations give
    a one-sided p-value (fraction of permuted statistics ≥ observed).
    """
    total = len(summaries)
    n_decided = 0
    n_ties = 0
    n_round_cap = 0
    n_errors = 0
    n_other = 0

    budgets: set[int] = set()
    for s in summaries:
        b = s.get("num_sims_per_seat")
        if isinstance(b, list) and b:
            budgets.update(int(x) for x in b)
    budgets = sorted(budgets)

    wins_by_budget: dict[int, int] = {}
    wins_by_seat: dict[int, int] = {}
    vp_sum: dict[int, float] = {}
    vp_count: dict[int, int] = {}
    rank_sum: dict[int, float] = {}
    rank_count: dict[int, int] = {}

    per_game: list[tuple[list[float], list[float]]] = []

    for s in summaries:
        stopped = s.get("stopped_reason")
        winner = s.get("winner")
        seat_budgets = s.get("num_sims_per_seat")
        returns = s.get("returns")

        if stopped == "error":
            n_errors += 1
        elif stopped == "round_cap":
            n_round_cap += 1
        elif stopped == "terminal" and winner is None:
            n_ties += 1
        elif stopped == "terminal" and winner is not None:
            n_decided += 1
        else:
            n_other += 1

        if stopped == "terminal" and winner is not None:
            wins_by_seat[winner] = wins_by_seat.get(winner, 0) + 1
            if isinstance(seat_budgets, list) and 0 <= winner < len(seat_budgets):
                b = int(seat_budgets[winner])
                wins_by_budget[b] = wins_by_budget.get(b, 0) + 1

        if (
            isinstance(returns, list)
            and len(returns) == n_players
            and isinstance(seat_budgets, list)
            and len(seat_budgets) == n_players
        ):
            ranks = _rank_desc([float(v) for v in returns])
            for seat in range(n_players):
                b = int(seat_budgets[seat])
                v = float(returns[seat])
                vp_sum[b] = vp_sum.get(b, 0.0) + v
                vp_count[b] = vp_count.get(b, 0) + 1
                rank_sum[b] = rank_sum.get(b, 0.0) + ranks[seat]
                rank_count[b] = rank_count.get(b, 0) + 1
            per_game.append(
                ([math.log2(int(x)) for x in seat_budgets], [float(v) for v in returns])
            )

    by_budget: dict[int, dict] = {}
    for b in budgets:
        w = wins_by_budget.get(b, 0)
        lo, hi = _wilson_ci(w, n_decided)
        by_budget[b] = {
            "wins": w,
            "decided": n_decided,
            "win_rate": round(w / n_decided, 4) if n_decided else 0.0,
            "ci95_low": round(lo, 4),
            "ci95_high": round(hi, 4),
            "mean_vp": round(vp_sum[b] / vp_count[b], 3) if vp_count.get(b) else None,
            "mean_rank": round(rank_sum[b] / rank_count[b], 3) if rank_count.get(b) else None,
            "vp_n": vp_count.get(b, 0),
        }

    by_seat: dict[int, dict] = {}
    for seat in range(n_players):
        w = wins_by_seat.get(seat, 0)
        lo, hi = _wilson_ci(w, n_decided)
        by_seat[seat] = {
            "wins": w,
            "decided": n_decided,
            "win_rate": round(w / n_decided, 4) if n_decided else 0.0,
            "ci95_low": round(lo, 4),
            "ci95_high": round(hi, 4),
        }

    observed = 0.0
    if per_game:
        observed = sum(_spearman(b, r) for b, r in per_game) / len(per_game)

    rng = random.Random(seed)
    count_ge = 0
    for _ in range(n_permutations):
        stat = 0.0
        for budgets_lg, returns in per_game:
            perm = rng.sample(budgets_lg, len(budgets_lg))
            stat += _spearman(perm, returns)
        if per_game:
            stat /= len(per_game)
        if stat >= observed:
            count_ge += 1
    p_value = count_ge / n_permutations if n_permutations else 1.0

    effective_frac = (n_decided / total) if total else 0.0

    return {
        "n_games": total,
        "n_decided": n_decided,
        "n_ties": n_ties,
        "n_round_cap": n_round_cap,
        "n_errors": n_errors,
        "n_other": n_other,
        "effective_n_frac": round(effective_frac, 4),
        "low_effective_n": total > 0 and effective_frac < 0.8,
        "budgets": budgets,
        "by_budget": by_budget,
        "by_seat": by_seat,
        "trend": {
            "statistic": round(observed, 4),
            "p_value": round(p_value, 4),
            "n_permutations": n_permutations,
            "n_games_used": len(per_game),
        },
        "exclusions": {
            "ties": n_ties,
            "round_cap": n_round_cap,
            "errors": n_errors,
            "other": n_other,
        },
    }
