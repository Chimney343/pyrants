"""Pure helpers for the IS-MCTS UCT-sweep experiment.

Import-light (no ``pyspiel``, no ``numpy`` at module import time) so the
parsing, deck-diversity, and analysis logic stays testable in isolation,
mirroring the ``scripts/_obs.py`` / ``scripts/_sims_vs_wins.py`` pattern.

The statistical core is ``analyze_uct``: it turns a list of per-game summary
dicts (each carrying ``uct_c_per_seat``, ``final_vp_per_seat``,
``final_deck_metrics``, ``winner``, and ``stopped_reason``) into win rates per
UCT arm and per seat, Wilson 95% CIs, mean VP share / mean raw VP / mean rank
per arm, full + recruited deck-diversity means ± sd per arm, two within-game
permutation trend tests (UCT vs VP share and UCT vs recruited entropy), and a
games-needed projection.

Unlike ``_sims_vs_wins.analyze``, win rates here are keyed on the per-seat UCB1
constant (``uct_c_per_seat``), not the simulation budget. VP-share means always
come from ``final_vp_per_seat`` (raw, non-negative VP per seat), never from
``returns`` — for n==2 ``returns`` is a zero-sum margin, not raw VP, so it
cannot be divided by a table total.
"""

from __future__ import annotations

import math
import random

from scripts._sims_vs_wins import _rank_desc, _spearman, _wilson_ci

_METRIC_KEYS = (
    "unique_count",
    "deck_size",
    "unique_ratio",
    "shannon_entropy",
    "normalized_entropy",
    "simpson",
)


def parse_uct_spec(spec: str, num_players: int) -> list[float]:
    """Parse and validate a comma-separated per-seat UCB1 constant spec.

    Returns a list of ``num_players`` positive floats. Raises ``ValueError`` on
    an empty segment, a non-float, a length mismatch with ``num_players``, or
    any value <= 0 (or non-finite).
    """
    parts = [p.strip() for p in spec.split(",")]
    if any(p == "" for p in parts):
        raise ValueError(f"empty uct value in spec {spec!r}")
    try:
        values = [float(p) for p in parts]
    except ValueError as exc:
        raise ValueError(f"non-float uct value in spec {spec!r}") from exc
    if len(values) != num_players:
        raise ValueError(
            f"expected {num_players} uct values for {num_players} players, got {len(values)}"
        )
    if any((not math.isfinite(v)) or v <= 0 for v in values):
        raise ValueError(f"all uct values must be finite and > 0, got {values}")
    return values


def _diversity(card_ids: list[str]) -> dict:
    """Compute the six deck-diversity metrics for a card-id multiset."""
    n = len(card_ids)
    if n == 0:
        return {
            "unique_count": 0,
            "deck_size": 0,
            "unique_ratio": 0.0,
            "shannon_entropy": 0.0,
            "normalized_entropy": 0.0,
            "simpson": 0.0,
        }
    counts: dict[str, int] = {}
    for c in card_ids:
        counts[c] = counts.get(c, 0) + 1
    k = len(counts)
    entropy = 0.0
    simpson_sum = 0.0
    for c in counts:
        p = counts[c] / n
        entropy -= p * math.log2(p)
        simpson_sum += p * p
    normalized = entropy / math.log2(n) if n >= 2 else 0.0
    return {
        "unique_count": k,
        "deck_size": n,
        "unique_ratio": k / n,
        "shannon_entropy": entropy,
        "normalized_entropy": normalized,
        "simpson": 1.0 - simpson_sum,
    }


def deck_variety_metrics(
    card_ids: list[str], starter_counts: dict[str, int] | None = None
) -> dict:
    """Compute diversity for the full deck and the recruited-only deck.

    ``full`` is the diversity of the whole ``card_ids`` multiset. ``recruited``
    is the diversity of the multiset with ``starter_counts`` removed (the clean
    signal for how deck-building choices shaped the deck). If any starter count
    exceeds the observed count (a starter card left the deck — should not
    happen), ``recruited_degraded`` is set true and the recruited metrics fall
    back to the full-deck metrics.
    """
    full = _diversity(card_ids)
    if not starter_counts:
        return {"full": full, "recruited": full, "recruited_degraded": False}

    counts: dict[str, int] = {}
    for c in card_ids:
        counts[c] = counts.get(c, 0) + 1

    degraded = False
    recruited: list[str] = []
    for c, cnt in counts.items():
        sub = starter_counts.get(c, 0)
        if sub > cnt:
            degraded = True
            sub = cnt
        recruited.extend([c] * (cnt - sub))

    recruited_metrics = full if degraded else _diversity(recruited)
    return {
        "full": full,
        "recruited": recruited_metrics,
        "recruited_degraded": degraded,
    }


def required_decided_games(
    target_half_width: float, p: float = 0.25, z: float = 1.96
) -> int:
    """Smallest n such that the Wilson 95% CI half-width at ``p`` is <= target.

    Bisection over the exact Wilson formula (same expression as
    ``_wilson_ci``'s margin), not the normal approximation.
    """
    if target_half_width <= 0:
        raise ValueError("target_half_width must be positive")
    if not (0.0 < p < 1.0):
        raise ValueError("p must be in (0, 1)")

    def half_width(n: int) -> float:
        z2 = z * z
        denom = 1 + z2 / n
        return z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom

    lo, hi = 1, 1
    while half_width(hi) > target_half_width:
        hi *= 2
    while lo < hi:
        mid = (lo + hi) // 2
        if half_width(mid) <= target_half_width:
            hi = mid
        else:
            lo = mid + 1
    return lo


def _mean_sd(values: list[float]) -> tuple[float | None, float | None]:
    """Sample mean and sample standard deviation (ddof=1) of a value list."""
    n = len(values)
    if n == 0:
        return (None, None)
    mean = sum(values) / n
    if n == 1:
        return (mean, 0.0)
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return (mean, math.sqrt(var))


def _permutation_trend(
    per_game: list[tuple[list[float], list[float]]],
    n_permutations: int,
    seed: int,
) -> dict:
    """One-sided within-game permutation test on mean per-game Spearman."""
    if not per_game:
        return {
            "statistic": 0.0,
            "p_value": 1.0,
            "n_permutations": n_permutations,
            "n_games_used": 0,
        }
    observed = sum(_spearman(x, y) for x, y in per_game) / len(per_game)
    rng = random.Random(seed)
    count_ge = 0
    for _ in range(n_permutations):
        stat = 0.0
        for x, y in per_game:
            perm = rng.sample(x, len(x))
            stat += _spearman(perm, y)
        stat /= len(per_game)
        if stat >= observed:
            count_ge += 1
    p_value = count_ge / n_permutations if n_permutations else 1.0
    return {
        "statistic": round(observed, 4),
        "p_value": round(p_value, 4),
        "n_permutations": n_permutations,
        "n_games_used": len(per_game),
    }


def analyze_uct(
    summaries: list[dict],
    *,
    n_players: int,
    n_permutations: int = 10_000,
    seed: int = 0,
) -> dict:
    """Analyse per-game summaries into UCT-arm/seat win rates and trend tests.

    Win rates are computed over *decided* games only (``stopped_reason ==
    "terminal"`` with a unique ``winner``). Ties, ``round_cap`` truncations, and
    ``error`` games are excluded from those rates but counted in ``exclusions``.

    VP-share means use ``final_vp_per_seat`` (seat-ordered raw VP). A game whose
    total table VP is zero is flagged (``n_zero_vp``) and excluded from share
    means and the share trend test (its shares are undefined); raw VP and rank
    still accumulate. Mean raw VP and mean rank use every game carrying a valid
    ``final_vp_per_seat`` list.

    Deck diversity is aggregated per arm from games carrying a valid
    ``final_deck_metrics`` list (seat-ordered), for both the ``full`` and
    ``recruited`` metric sets, as mean ± sd over seat observations.

    Two one-sided trend tests permute the UCT→seat assignment within each game:
    UCT vs VP share, and UCT vs ``recruited.normalized_entropy``.
    """
    total = len(summaries)
    n_decided = n_ties = n_round_cap = n_errors = n_other = 0
    n_zero_vp = 0

    arms: set[float] = set()
    for s in summaries:
        u = s.get("uct_c_per_seat")
        if isinstance(u, list) and u:
            for x in u:
                arms.add(round(float(x), 6))
    arms_sorted = sorted(arms)

    wins_by_arm: dict[float, int] = {}
    wins_by_seat: dict[int, int] = {}
    vp_share_sum: dict[float, float] = {}
    vp_share_count: dict[float, int] = {}
    vp_sum: dict[float, float] = {}
    vp_count: dict[float, int] = {}
    rank_sum: dict[float, float] = {}
    rank_count: dict[float, int] = {}

    deck_values: dict[float, dict[str, dict[str, list[float]]]] = {
        arm: {
            mset: {k: [] for k in _METRIC_KEYS} for mset in ("full", "recruited")
        }
        for arm in arms_sorted
    }

    per_game_vp: list[tuple[list[float], list[float]]] = []
    per_game_entropy: list[tuple[list[float], list[float]]] = []

    for s in summaries:
        stopped = s.get("stopped_reason")
        winner = s.get("winner")
        seat_uct = s.get("uct_c_per_seat")
        vp = s.get("final_vp_per_seat")
        deck_metrics = s.get("final_deck_metrics")

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
            if isinstance(seat_uct, list) and 0 <= winner < len(seat_uct):
                arm = round(float(seat_uct[winner]), 6)
                wins_by_arm[arm] = wins_by_arm.get(arm, 0) + 1

        valid_uct = isinstance(seat_uct, list) and len(seat_uct) == n_players
        valid_vp = isinstance(vp, list) and len(vp) == n_players

        if valid_uct and valid_vp:
            total_vp = sum(vp)
            if total_vp == 0:
                n_zero_vp += 1
                shares = [0.0] * n_players
                shares_valid = False
            else:
                shares = [float(vp[i]) / total_vp for i in range(n_players)]
                shares_valid = True
            ranks = _rank_desc([float(v) for v in vp])
            for seat in range(n_players):
                arm = round(float(seat_uct[seat]), 6)
                vp_sum[arm] = vp_sum.get(arm, 0.0) + float(vp[seat])
                vp_count[arm] = vp_count.get(arm, 0) + 1
                rank_sum[arm] = rank_sum.get(arm, 0.0) + ranks[seat]
                rank_count[arm] = rank_count.get(arm, 0) + 1
                if shares_valid:
                    vp_share_sum[arm] = vp_share_sum.get(arm, 0.0) + shares[seat]
                    vp_share_count[arm] = vp_share_count.get(arm, 0) + 1
            if shares_valid:
                per_game_vp.append(([float(x) for x in seat_uct], shares))

        valid_deck = (
            isinstance(deck_metrics, list) and len(deck_metrics) == n_players
        )
        if valid_uct and valid_deck:
            entropies: list[float] = []
            deck_ok = True
            for dm in deck_metrics:
                rec = dm.get("recruited") if isinstance(dm, dict) else None
                if not isinstance(rec, dict) or "normalized_entropy" not in rec:
                    deck_ok = False
                    break
                entropies.append(float(rec["normalized_entropy"]))
            if deck_ok:
                per_game_entropy.append(
                    ([float(x) for x in seat_uct], entropies)
                )
            for seat in range(n_players):
                arm = round(float(seat_uct[seat]), 6)
                dm = deck_metrics[seat]
                if not isinstance(dm, dict):
                    continue
                for mset in ("full", "recruited"):
                    sub = dm.get(mset)
                    if not isinstance(sub, dict):
                        continue
                    for k in _METRIC_KEYS:
                        if k in sub:
                            deck_values[arm][mset][k].append(float(sub[k]))

    by_arm: dict[float, dict] = {}
    for arm in arms_sorted:
        w = wins_by_arm.get(arm, 0)
        lo, hi = _wilson_ci(w, n_decided)
        entry: dict = {
            "wins": w,
            "decided": n_decided,
            "win_rate": round(w / n_decided, 4) if n_decided else 0.0,
            "ci95_low": round(lo, 4),
            "ci95_high": round(hi, 4),
            "mean_vp_share": (
                round(vp_share_sum[arm] / vp_share_count[arm], 4)
                if vp_share_count.get(arm)
                else None
            ),
            "mean_vp": (
                round(vp_sum[arm] / vp_count[arm], 3)
                if vp_count.get(arm)
                else None
            ),
            "mean_rank": (
                round(rank_sum[arm] / rank_count[arm], 3)
                if rank_count.get(arm)
                else None
            ),
            "vp_share_n": vp_share_count.get(arm, 0),
        }
        for mset, key in (("full", "deck_full"), ("recruited", "deck_recruited")):
            agg: dict[str, dict] = {}
            for k in _METRIC_KEYS:
                mean, sd = _mean_sd(deck_values[arm][mset][k])
                agg[k] = {
                    "mean": round(mean, 6) if mean is not None else None,
                    "sd": round(sd, 6) if sd is not None else None,
                    "n": len(deck_values[arm][mset][k]),
                }
            entry[key] = agg
        by_arm[arm] = entry

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

    effective_frac = (n_decided / total) if total else 0.0

    req_10 = required_decided_games(0.10)
    req_8 = required_decided_games(0.08)
    req_5 = required_decided_games(0.05)

    def _project(required: int) -> int | None:
        if effective_frac <= 0:
            return None
        return math.ceil(required / effective_frac)

    return {
        "n_games": total,
        "n_decided": n_decided,
        "n_ties": n_ties,
        "n_round_cap": n_round_cap,
        "n_errors": n_errors,
        "n_other": n_other,
        "n_zero_vp": n_zero_vp,
        "effective_n_frac": round(effective_frac, 4),
        "low_effective_n": total > 0 and effective_frac < 0.8,
        "arms": arms_sorted,
        "by_arm": by_arm,
        "by_seat": by_seat,
        "trend_vp_share": _permutation_trend(per_game_vp, n_permutations, seed),
        "trend_entropy": _permutation_trend(
            per_game_entropy, n_permutations, seed + 1
        ),
        "exclusions": {
            "ties": n_ties,
            "round_cap": n_round_cap,
            "errors": n_errors,
            "other": n_other,
            "zero_vp": n_zero_vp,
        },
        "games_needed": {
            "achieved_n_decided": n_decided,
            "decided_fraction": round(effective_frac, 4),
            "required_10pp": req_10,
            "required_8pp": req_8,
            "required_5pp": req_5,
            "projected_total_games_10pp": _project(req_10),
            "projected_total_games_8pp": _project(req_8),
            "projected_total_games_5pp": _project(req_5),
        },
    }
