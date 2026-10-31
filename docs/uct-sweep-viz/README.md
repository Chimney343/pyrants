# UCT-sweep visualisation

This folder contains a self-contained visualisation of the IS-MCTS **UCT sweep**
experiments (`artifacts/ismcts/experiments/uct_sweep/`), produced to answer: *which
`uct_c` should the production simulation rollout use to make the neural net trainable?*

## Contents

| File | What it is |
|------|-----------|
| `uct_sweep_report.html` | **Open this.** Interactive report (plotly, self-contained, ~4.3 MB) with all four charts + the run summary table. |
| `data.json` | Per-arm metrics (win share, Wilson 95% CI, mean VP, mean rank, recruited deck entropy ± sd) aggregated from the four completed runs. |
| `generate_viz.py` | Reproducible generator — reads the run `analysis.json` files and rewrites the report + data. |
| `uct_sweep_visualization.ipynb` | Notebook companion (workspace root) that runs the same generator. |

## How to regenerate

```bash
.venv/Scripts/python.exe docs/uct-sweep-viz/generate_viz.py
```

## What the data shows

All runs share `num_sims=200`, the `random-c` evaluator, 4 players, rotating seats —
so `uct_c` is the only varying factor, and ~98% of games are decided at every value
(no yield penalty). The strength curve is an inverted-U:

- **Below 2.5**: steep climb — `2.5` wins 34.2% vs the default `1.4`'s 24.5% and `0.3`'s 21.1%.
- **Peak ≈ 5**: `5` wins 32.8% (0.8–10 ladder) and 26.5% (4–7 ladder); best mean rank (2.33) across all runs.
- **4–7 plateau**: statistically tied (trend p = 0.96); `4` ≈ `7` head-to-head (51/49).
- **10 collapses**: 20.4% win share — over-exploration burns the 200-sim budget.
- **Deck diversity falls gently** with `uct_c` (recruited entropy 0.747 @ 0.8 → 0.702 @ 10).

## Recommendation

**`uct_c = 5.0`** for the NN-training rollout (fallback band **4.0–5.0**). It is the
measured strength peak, decisively above the current `1.4` default, safely below the
`10` cliff, and costs only ~1% relative deck diversity versus `4.0`.

*Note: the sweeps are calibrated at `num_sims=200`. If the production rollout changes the
search budget materially, re-run `just ismcts-uct --uct-per-seat "2.5,4.0,5.0,7.0"` at that
budget before locking the value.*
