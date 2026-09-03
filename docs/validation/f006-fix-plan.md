# F-006 Fix Plan — Expose and Calibrate `uct_c`

**Defect:** `docs/validation/findings.md` § F-006 (MAJOR) — `scripts/run_ismcts.py` defaults
`uct_c=1.4` (generic √2 UCT) instead of the paper's calibrated `0.7`
(`docs/ismcts-paper.md` § IV-A: "The value of 0.7 was thus used for all algorithms in all
experiments in this paper"). No sweep artifact, doc, or commit anywhere in the repo shows `1.4`
was ever chosen deliberately for this game. Measured root Q-value spread is 9.22 against a mean
exploration bonus of 1.443 (`docs/validation/harness/f006.py`) — exploitation outweighs
exploration 6.4:1, where the paper's `0.7` assumed rewards normalised to ±1. Per
`verdict.md` §5, this is now the **sole remaining condition before GO** — F-011, F-004, F-002,
and F-010 are all resolved, and F-003 is explicitly out of scope by owner direction
(ADR-0002).

**Scope note — two distinct jobs, both required.** "Exposing" `uct_c` (making it reachable from
the command line without editing code) and "calibrating" it (actually determining a better value)
are different activities, and shipping only the first would leave F-006 permanently open with no
path to closing it — the finding's own gate in `verdict.md` §5 condition 4 is explicit: *"a
documented sweep artifact, with the chosen value beating its neighbours seat-swapped at
N ≥ 200 per arm."* This plan does both, in that order, because the sweep cannot run without the
exposure existing first.

---

## 0. Mandatory process constraints

1. **Justfile changes are additive-only.** Every existing `just ismcts*` invocation that omits
   the new argument must keep behaving byte-identically — default stays `"1.4"`. No recipe's
   existing positional/named argument order changes.
2. **This change will be reviewed** (Phase 4).
3. **`docs/validation/verdict.md` and `findings.md` must be updated with the sweep's actual
   result** (Phase 5) — not merely "the flag now exists." An unexecuted sweep does not close this
   finding.
4. **The sweep is a measurement, not a foregone conclusion.** If it finds `1.4` already beats or
   ties its neighbours, that is a legitimate, honest close for F-006 — do not force a different
   default just to show something changed.

---

## 1. Current state (verified this session, not assumed)

- `scripts/run_ismcts.py:151` already exposes `--uct-c` (`type=float, default=1.4`), threaded
  unmodified into every `make_ismcts_bot(uct_c=uct_c, ...)` call site
  (`run_ismcts.py:395,573,746,1005,1041,1096`). **Nothing here needs to change.**
- `docs/validation/harness/common.py:37` — `make_bot(game, num_sims, seed, uct_c=1.4, ...)`
  already accepts a per-call override.
- **The actual gap is the `justfile` layer.** Of the three recipes that invoke
  `scripts.run_ismcts` (`justfile:63,66,72` — `ismcts`, `ismcts-quick`, `ismcts-perf`), only
  `ismcts-perf` has a `*args` passthrough that could reach `--uct-c` today, and only if the
  caller already knows the flag name; `ismcts` and `ismcts-quick` have no way to override it at
  all. Every `just ismcts`/`just ismcts-quick` invocation is silently locked to `1.4`.
- **No existing harness compares different `uct_c` values head-to-head.** `docs/validation/
  harness/exp.py`/`exp2.py` (the scripts behind the STRENGTH rows INV-7/8/9) call `make_bot(g,
  spec, bseed)` with no `uct_c` argument, so every arm in every existing sweep silently uses the
  `1.4` default. Varying `num_sims` per arm is proven infrastructure; varying `uct_c` per arm is
  not — it must be added, not just invoked.
- `docs/validation/harness/f006.py` already computed one data point: `uct_c that would equalise`
  Q-value spread and exploration bonus ≈ `1.4 * 9.22 / 1.443 ≈ 8.9` at the time of filing. This is
  a useful sweep candidate, not a substitute for an empirical result — the finding's own steelman
  explicitly allows that a game with un-normalised, hundreds-scale VP rewards could legitimately
  want a different constant than the paper's ±1-normalised domain, which is exactly what a
  seat-swapped head-to-head settles and a formula alone cannot.

---

## 2. Acceptance gates

| Gate | Threshold |
|---|---|
| G1 Justfile exposure | Supplying `uct_c` on `ismcts`/`ismcts-quick` (trailing positional, e.g. `just ismcts-quick 1 2 0.7`) and `--uct-c` through `ismcts-perf`'s `*args` actually changes the value used — verified by inspecting `run_ismcts.py`'s own `summary.csv` `uct_c` column (`run_ismcts.py:869,882` already writes this column), not by trusting the flag was passed. Omitting the override reproduces today's byte-identical behavior. |
| G2 Sweep infrastructure exists | A new, committed, reproducible harness script that builds two independently-`uct_c`-configured bots and plays seat-swapped games — same pattern as `exp.py`'s `sims_a`/`sims_b`, generalised to `uct_a`/`uct_b`. |
| G3 Calibration gate (`verdict.md` §5 condition 4, verbatim) | Chosen value beats its immediate neighbours, seat-swapped, N ≥ 200 per arm, with exact-binomial significance reported — same statistical method already used for INV-7/8/9. |
| G4 No regression | This plan touches no production simulation code (`engine_c/`, `openspiel_pyrants/` are untouched) — only `justfile` and a new `docs/validation/harness/*.py` file. The always-on battery (INV-1/2/3/6) and existing suites are expected to be completely unaffected; re-run once as a sanity check, not because there's a plausible mechanism for them to move. |

---

## 3. Phase 1 — Expose (justfile)

Add a named `uct_c="1.4"` parameter to the two recipes that build ISMCTS bots without a
variadic, forwarded as `--uct-c {{uct_c}}`. `ismcts-perf` is **unchanged** — it already has an
`*args` variadic that reaches `--uct-c` directly, and inserting a named parameter before the
variadic would shift every trailing flag-arg invocation under just's positional binding (see the
review correction below).

> **Invocation syntax on this repo's just 1.43.0.** Recipe parameters are positional; the
> `name=value` form is not an override (named-option parameters need just 1.46+ `[arg]`
> attributes). A trailing parameter is supplied positionally: `just ismcts 200 1 42
> artifacts/out 1 2 0.7` sets `uct_c=0.7`. Omitting it reproduces the default.

```diff
 ismcts num_sims="200" num_games="4" seed="42" output_dir="artifacts/ismcts" workers="16" num_players="4":
-    & {{python}} -m scripts.run_ismcts --num-sims {{num_sims}} --num-games {{num_games}} --seed {{seed}} --output-dir {{output_dir}} --workers {{workers}} --num-players {{num_players}} --game python_pyrants_c
+ismcts num_sims="200" num_games="4" seed="42" output_dir="artifacts/ismcts" workers="16" num_players="4" uct_c="1.4":
+    & {{python}} -m scripts.run_ismcts --num-sims {{num_sims}} --num-games {{num_games}} --seed {{seed}} --output-dir {{output_dir}} --workers {{workers}} --num-players {{num_players}} --uct-c {{uct_c}} --game python_pyrants_c

 ismcts-quick workers="1" num_players="2":
-    & {{python}} -m scripts.run_ismcts --num-sims 2 --num-games 1 --seed 42 --workers {{workers}} --num-players {{num_players}} --game python_pyrants_c
+ismcts-quick workers="1" num_players="2" uct_c="1.4":
+    & {{python}} -m scripts.run_ismcts --num-sims 2 --num-games 1 --seed 42 --workers {{workers}} --num-players {{num_players}} --uct-c {{uct_c}} --game python_pyrants_c

 ismcts-perf num_players="2" *args:
     & {{python}} -m cProfile -o artifacts/ismcts/performance_testing/cprofile.pstats -m scripts.run_ismcts --num-sims 10 --num-games 1 --seed 42 --num-players {{num_players}} --max-rounds 10 --output-dir artifacts/ismcts/performance_testing --workers 1 --game python_pyrants_c {{args}}
```

**Review correction (2026-09-02):** `ismcts-perf` is left **unchanged** from its original
signature. Adding a named `uct_c` between `num_players` and the `*args` variadic would have
silently shifted every trailing flag-arg invocation under just 1.43's positional binding —
`just ismcts-perf 2 --max-rounds 5` would bind `--max-rounds` as `uct_c` — a latent interface
regression for the recipe's documented `*args` passthrough. `uct_c` remains reachable there as
`just ismcts-perf 2 --uct-c <value>` through the existing variadic. The F-006 goal (expose
`uct_c` on the three recipes) is met without touching `ismcts-perf`'s signature.

`ismcts-perf`'s named parameters must stay before its `*args` variadic — same position `just`
already requires for `num_players`, so this is not a new constraint.

---

## 4. Phase 2 — Verify the wire, not just the diff

Cheap, catches a silent no-op (the flag parses but doesn't reach the bot): run `just
ismcts-quick 1 1 0.7` and `just ismcts-quick 1 1 2.0` (positional `uct_c` on just 1.43) and
confirm `summary.csv`'s `uct_c` column reads `0.7` and `2.0` respectively, not `1.4` in both.
Then run `just ismcts-quick` with no trailing `uct_c` at all and confirm `summary.csv` still
reads `1.4` — the default path must be untouched (G1). Repeat for the multi-worker `ismcts`
recipe (`just ismcts 2 1 42 <outdir> 1 2 0.7`) and confirm its `summary.csv` also records the
override. `ismcts-perf` is a cProfile harness (writes no `summary.csv` by design); dry-run
inspection of the `*args` passthrough is sufficient for it.

---

## 5. Phase 3 — Build the sweep harness

New file: `docs/validation/harness/f006_sweep.py`, following `exp.py`'s exact existing pattern
(same `play_game`/`make_bot`/`mp.Pool(16)`/`binom_p` machinery the STRENGTH-row scripts already
use, so a reviewer already familiar with `exp.py` recognizes the shape immediately) generalised
to vary `uct_c` instead of `num_sims` per arm:

```python
import sys, os, time, json
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
    bots = [mk(ucts[0], seed*991+1), mk(ucts[1], seed*991+2)]
    t = time.perf_counter()
    r = play_game(g, bots, seed)
    dt = time.perf_counter() - t
    margin = r["returns"][0 if seat == 0 else 1]
    res = 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)
    return {"uct_a": uct_a, "uct_b": uct_b, "seed": seed, "seat": seat,
            "a_score": res, "margin": margin, "steps": r["steps"], "wall": dt}

if __name__ == "__main__":
    import multiprocessing as mp

    def binom_p(k, n, p=0.5):
        if n == 0:
            return 1.0
        pm = [comb(n, i) * p**i * (1 - p)**(n - i) for i in range(n + 1)]
        obs = pm[k]
        return min(1.0, sum(x for x in pm if x <= obs * (1 + 1e-12)))

    def summarize(tag, rows):
        n = len(rows)
        W = sum(1 for r in rows if r["a_score"] == 1.0)
        L = sum(1 for r in rows if r["a_score"] == 0.0)
        T = sum(1 for r in rows if r["a_score"] == 0.5)
        mm = sum(r["margin"] for r in rows) / n
        p = binom_p(W, W + L)
        print(f"{tag}: N={n} winrate={(W+0.5*T)/n:.3f} (W{W}/L{L}/T{T}) "
              f"exact-binom p={p:.4g} on {W+L} decisive mean_margin={mm:+.2f}", flush=True)
        return {"tag": tag, "N": n, "W": W, "L": L, "T": T, "p": p, "mean_margin": mm}

    candidates = [float(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else [0.7, 1.4, 2.8]
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    sims = int(sys.argv[3]) if len(sys.argv) > 3 else 200

    ordered = sorted(candidates)
    pool = mp.Pool(16)
    out = {}
    for a, b in zip(ordered, ordered[1:]):
        jobs = [(a, b, sims, 1000 + i // 2, i % 2) for i in range(N)]
        t = time.perf_counter()
        rows = pool.map(one, jobs)
        out[f"{a}_vs_{b}"] = summarize(f"uct_c={a} vs uct_c={b}", rows)
        print(f"  elapsed {time.perf_counter()-t:.0f}s", flush=True)
    pool.close()
    pool.join()
    open(os.path.join(VAL, "f006_sweep_results.json"), "w").write(json.dumps(out, indent=1))
    print("WROTE f006_sweep_results.json")
```

**Candidate set (starting point, adjust after Phase 2's timing):** `0.7` (paper's value), `1.4`
(current default, must be included as the baseline it needs to beat), and one value above —
either the `f006.py`-computed equalizing estimate (re-run fresh in this phase, since it's cheap
and the current number should not be trusted from the original filing without re-checking) or a
round `2.8` (2×) if the equalizing estimate is impractically large. Compares only *adjacent*
pairs in sorted order (`zip(ordered, ordered[1:])`), matching the gate's own "beats its
neighbours" wording literally rather than an all-pairs tournament.

**Cost, estimated before committing to the full candidate set:** the recorded 1,600-sim
self-play cost is ~142s/game (`verdict.md` §1 INV-7 detail); at `num_sims=200` (8× fewer
simulations, not perfectly linear per INV-10's mildly-superlinear note) a game is roughly
15–25s. With `mp.Pool(16)`, N=200 games per neighbour-pair is very roughly 200×20s/16 ≈ 4-5
minutes; a 3-candidate set (2 neighbour-pairs) is ~10 minutes total. **Time the first pairing
before running the rest** and cut `N`'s per-pair cost (not below the gate's own N≥200 floor) or
the candidate set size if the estimate is badly off, rather than discovering a multi-hour job
partway through.

---

## 6. Phase 4 — Run it, review

1. `.venv/Scripts/python.exe -u docs/validation/harness/f006_sweep.py "0.7,1.4,2.8" 200 200`
   (or the adjusted candidate set from Phase 3's cost check).
2. Confirm G1 (Phase 2's wire-check), G2 (the script exists and ran to completion, producing
   `f006_sweep_results.json`), and G3 (a value beats its immediate neighbour(s) with the
   exact-binomial `p` reported — not just a higher raw win rate).
3. Re-run the always-on battery once (`inv_a.py`) as a G4 sanity check — expected unchanged,
   since nothing in `engine_c/` or `openspiel_pyrants/` is touched.
4. Standard review pass (per this repo's `/code-review` convention) on the `justfile` diff and
   the new harness file — low-risk surface (tooling + a read-only measurement script), but still
   required per constraint 2.

---

## 7. Phase 5 — Update the ledger (required)

1. **`docs/validation/findings.md`** — F-006 `Status:` becomes `**CONFIRMED — CALIBRATED**
   (<value>)`, with the sweep's actual numbers appended (N, seeds, win rate, p), keeping the
   original Q-value-spread evidence intact.
2. **`docs/validation/verdict.md`** — strike condition 4 in §5, record the chosen `uct_c` and the
   sweep artifact's location, and — since this was stated to be the last remaining blocking
   condition — flip the top-level verdict to reflect whatever conditions actually remain (none,
   if this is genuinely the last one; re-check §5 at that time rather than assuming).
3. If the sweep finds `1.4` already beats its neighbours, record that outcome plainly — it closes
   F-006 just as validly as picking a new value (constraint 4).

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Justfile flag parses but doesn't reach the bot (silent no-op) | Phase 2's explicit `summary.csv` column check, not just a diff read |
| Sweep cost blows past a reasonable session budget | Time the first neighbour-pair before committing to the full set (Phase 3) |
| Candidate set is too coarse to find a real optimum | Documented as a starting point, not the final word — Phase 5's ledger entry should note if a follow-up finer sweep is warranted, same honesty standard F-013's residual-gap reporting used |
| `uct_c` interacts with `num_sims` (optimal constant shifts with budget) | Out of scope for this plan — sweep is run at the project's standard `num_sims=200`, matching INV-7/8/9's own methodology; a budget-dependent sweep would be a separate, explicitly scoped follow-up |

## 9. Out of scope

Any change to `engine_c/`, `openspiel_pyrants/`, or `scripts/run_ismcts.py` — the flag and its
plumbing already exist there; this plan only reaches the `justfile` layer and adds a new,
self-contained harness script. Re-deriving `uct_c` per `num_players` (2 vs. 3–4) — the sweep runs
at 2 players only, matching every existing STRENGTH-row measurement (INV-7/8/9); a 4-player sweep
would need its own scoping given the project's own default (`just ismcts` runs `num_players=4`).
F-003, F-005, F-009, F-012, F-013, F-014, F-015 — unrelated, each already tracked in `verdict.md`
§5 or as non-blocking debt.
