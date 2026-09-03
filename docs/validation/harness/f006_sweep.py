"""F-006 uct_c calibration sweep: seat-swapped pairwise comparisons.

Usage: python f006_sweep.py [candidates_csv] [N_per_arm] [num_sims]
Reads/writes f006_sweep_results.json in this directory. See f006-fix-plan.md.
"""
import json
import multiprocessing as mp
import os
import sys
import time
from math import comb

VAL = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, VAL)


def one(job):
    from common import load, make_bot, play_game

    uct_a, uct_b, sims, seed, seat = job
    g = load(2)

    def mk(uct, bseed):
        return make_bot(g, sims, bseed, uct_c=uct)

    ucts = (uct_a, uct_b) if seat == 0 else (uct_b, uct_a)
    bots = [mk(ucts[0], seed * 991 + 1), mk(ucts[1], seed * 991 + 2)]
    t = time.perf_counter()
    r = play_game(g, bots, seed)
    dt = time.perf_counter() - t
    margin = r["returns"][0 if seat == 0 else 1]
    res = 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)
    return {"uct_a": uct_a, "uct_b": uct_b, "seed": seed, "seat": seat,
            "a_score": res, "margin": margin, "steps": r["steps"], "wall": dt}


def binom_p(k, n, p=0.5):
    if n == 0:
        return 1.0
    pm = [comb(n, i) * p**i * (1 - p)**(n - i) for i in range(n + 1)]
    obs = pm[k]
    return min(1.0, sum(x for x in pm if x <= obs * (1 + 1e-12)))


def summarize(tag, rows):
    n = len(rows)
    wins = sum(1 for r in rows if r["a_score"] == 1.0)
    losses = sum(1 for r in rows if r["a_score"] == 0.0)
    ties = sum(1 for r in rows if r["a_score"] == 0.5)
    mm = sum(r["margin"] for r in rows) / n
    p = binom_p(wins, wins + losses)
    print(f"{tag}: N={n} winrate={(wins + 0.5 * ties) / n:.3f} (W{wins}/L{losses}/T{ties}) "
          f"exact-binom p={p:.4g} on {wins + losses} decisive mean_margin={mm:+.2f}", flush=True)
    return {"tag": tag, "N": n, "W": wins, "L": losses, "T": ties, "p": p, "mean_margin": mm}


if __name__ == "__main__":
    candidates = [float(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else [0.7, 1.4, 2.8]
    n_per_arm = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    sims = int(sys.argv[3]) if len(sys.argv) > 3 else 200

    ordered = sorted(candidates)
    pool = mp.Pool(16)
    out = {}
    for i in range(len(ordered) - 1):
        a, b = ordered[i], ordered[i + 1]
        jobs = [(a, b, sims, 1000 + i // 2, i % 2) for i in range(n_per_arm)]
        t = time.perf_counter()
        rows = pool.map(one, jobs)
        out[f"{a}_vs_{b}"] = summarize(f"uct_c={a} vs uct_c={b}", rows)
        print(f"  elapsed {time.perf_counter() - t:.0f}s", flush=True)
    pool.close()
    pool.join()
    path = os.path.join(VAL, "f006_sweep_results.json")
    with open(path, "w") as f:
        f.write(json.dumps(out, indent=1))
    print("WROTE f006_sweep_results.json")
