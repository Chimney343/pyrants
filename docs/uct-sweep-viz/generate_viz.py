"""Generate visualisations for the IS-MCTS UCT-sweep experiments.

Reads the four completed runs under
``artifacts/ismcts/experiments/uct_sweep/`` (the incomplete 166-game run has no
``analysis.json`` and is skipped), aggregates the per-arm metrics, and writes a
self-contained interactive HTML report plus a ``data.json`` digest into this
folder.

Run::

    .venv/Scripts/python.exe docs/uct-sweep-viz/generate_viz.py

Outputs (in ``docs/uct-sweep-viz/``):

* ``uct_sweep_report.html`` — interactive report (plotly, self-contained)
* ``data.json``            — per-arm metrics used by the charts
"""

from __future__ import annotations

import json
from pathlib import Path

import plotly.graph_objects as go

OUT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
SWEEP_DIR = ROOT / "artifacts" / "ismcts" / "experiments" / "uct_sweep"

# Ordered mapping from run dir name -> (short label, colour, dash).
RUN_LABELS = {
    "20260913T084708Z_c9a0b0521267": ("ladder 0.3\u20132.5", "#1f77b4", "solid"),
    "20260913T225614Z_f6e033e4c40b": ("ladder 0.8\u201310", "#d62728", "solid"),
    "20260914T225504Z_ef6e0c8a5896": ("ladder 4\u20137", "#2ca02c", "solid"),
    "20260915T101726Z_75d0659a0c52": ("2v2  4 vs 7", "#9467bd", "solid"),
}

DEFAULT_UCT = 1.4
RECOMMENDED_UCT = 5.0


def _run_label(uct_per_seat: list[float]) -> str:
    unique = sorted(set(round(x, 6) for x in uct_per_seat))
    if len(unique) == 2 and uct_per_seat.count(unique[0]) == 2:
        return f"2v2  {unique[0]:g} vs {unique[1]:g}"
    return f"ladder {min(unique):g}\u2013{max(unique):g}"


def load_sweep_data() -> tuple[list[dict], dict]:
    """Return (records, meta). Each record is one (run, uct arm) observation."""
    records: list[dict] = []
    meta: dict = {"num_sims": None, "runs": []}

    for run_dir in sorted(p for p in SWEEP_DIR.iterdir() if p.is_dir()):
        analysis_path = run_dir / "analysis.json"
        config_path = run_dir / "experiment_config.json"
        if not analysis_path.exists() or not config_path.exists():
            continue

        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        config = json.loads(config_path.read_text(encoding="utf-8"))

        label = RUN_LABELS.get(run_dir.name, (run_dir.name, "#7f7f7f", "solid"))[0]
        color = RUN_LABELS.get(run_dir.name, ("", "#7f7f7f", "solid"))[1]
        dash = RUN_LABELS.get(run_dir.name, ("", "", "solid"))[2]
        uct_per_seat = config["uct_per_seat"]
        n_decided = analysis["n_decided"]
        n_games = analysis["n_games"]

        if meta["num_sims"] is None:
            meta["num_sims"] = config.get("num_sims")
        meta["runs"].append(
            {
                "dir": run_dir.name,
                "label": label,
                "arms": analysis["arms"],
                "n_games": n_games,
                "n_decided": n_decided,
                "decided_frac": round(n_decided / n_games, 4) if n_games else None,
            }
        )

        unique_ucts = sorted(set(round(x, 6) for x in uct_per_seat))
        is_2v2 = len(unique_ucts) == 2 and uct_per_seat.count(unique_ucts[0]) == 2

        for arm in analysis["arms"]:
            d = analysis["by_arm"][f"{arm:g}" if f"{arm:g}" in analysis["by_arm"] else str(arm)]
            ent = d["deck_recruited"]["normalized_entropy"]
            records.append(
                {
                    "run": run_dir.name,
                    "label": label,
                    "color": color,
                    "dash": dash,
                    "is_2v2": is_2v2,
                    "uct": arm,
                    "win_rate": d["win_rate"],
                    "ci_low": d["ci95_low"],
                    "ci_high": d["ci95_high"],
                    "mean_vp": d["mean_vp"],
                    "mean_rank": d["mean_rank"],
                    "entropy_mean": ent["mean"],
                    "entropy_sd": ent["sd"],
                    "n_decided": n_decided,
                }
            )

    return records, meta


def _style_axis(fig: go.Figure) -> None:
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=60, r=30, t=60, b=50),
        font=dict(size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
    )


def _add_uct_guides(fig: go.Figure) -> None:
    fig.add_vline(
        x=DEFAULT_UCT, line_dash="dot", line_color="#555555", line_width=1.2,
        annotation_text=f"current default {DEFAULT_UCT:g}",
        annotation_position="top", annotation_font_size=11,
    )
    fig.add_vline(
        x=RECOMMENDED_UCT, line_dash="dash", line_color="#2e7d32", line_width=2,
        annotation_text=f"recommended {RECOMMENDED_UCT:g}",
        annotation_position="bottom", annotation_font_size=11,
    )


def build_figures(records: list[dict]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    round_robin = [r for r in records if not r["is_2v2"]]
    two_v_two = [r for r in records if r["is_2v2"]]

    # 1. Win share (4-arm round-robin; baseline 25%).
    fig_win = go.Figure()
    for label in dict.fromkeys(r["label"] for r in round_robin):
        sub = [r for r in round_robin if r["label"] == label]
        sub.sort(key=lambda r: r["uct"])
        color = sub[0]["color"]
        x = [r["uct"] for r in sub]
        y = [100 * r["win_rate"] for r in sub]
        lo = [100 * (r["win_rate"] - r["ci_low"]) for r in sub]
        hi = [100 * (r["ci_high"] - r["win_rate"]) for r in sub]
        fig_win.add_trace(
            go.Scatter(
                x=x, y=y, mode="lines+markers", name=label,
                line=dict(color=color, width=2),
                marker=dict(size=9),
                error_y=dict(type="data", symmetric=False, array=hi, arrayminus=lo,
                             thickness=1.5, width=5, color=color),
                customdata=[r["n_decided"] for r in sub],
                hovertemplate="uct_c=%{x:g}<br>win share %{y:.1f}%<br>decided=%{customdata}<extra></extra>",
            )
        )
    fig_win.add_hline(y=25.0, line_dash="dot", line_color="#999999",
                      annotation_text="fair share (4-way)", annotation_font_size=11)
    fig_win.update_layout(
        title="Win share vs uct_c (4-arm round-robin, 200 sims)",
        xaxis_title="uct_c (UCB1 exploration constant)",
        yaxis_title="win share (%)",
        yaxis=dict(range=[15, 45]),
    )
    _add_uct_guides(fig_win)
    _style_axis(fig_win)
    figures["win_share"] = fig_win

    # 2. Mean VP (all runs, comparable scale).
    fig_vp = go.Figure()
    for label in dict.fromkeys(r["label"] for r in records):
        sub = sorted((r for r in records if r["label"] == label), key=lambda r: r["uct"])
        fig_vp.add_trace(
            go.Scatter(
                x=[r["uct"] for r in sub], y=[r["mean_vp"] for r in sub],
                mode="lines+markers", name=label,
                line=dict(color=sub[0]["color"], width=2),
                marker=dict(size=9),
                hovertemplate="uct_c=%{x:g}<br>mean VP %{y:.2f}<extra></extra>",
            )
        )
    fig_vp.update_layout(
        title="Mean final VP vs uct_c (all runs)",
        xaxis_title="uct_c", yaxis_title="mean VP per seat",
    )
    _add_uct_guides(fig_vp)
    _style_axis(fig_vp)
    figures["mean_vp"] = fig_vp

    # 3. Mean rank (lower is better; baseline 2.5).
    fig_rank = go.Figure()
    for label in dict.fromkeys(r["label"] for r in records):
        sub = sorted((r for r in records if r["label"] == label), key=lambda r: r["uct"])
        fig_rank.add_trace(
            go.Scatter(
                x=[r["uct"] for r in sub], y=[r["mean_rank"] for r in sub],
                mode="lines+markers", name=label,
                line=dict(color=sub[0]["color"], width=2),
                marker=dict(size=9),
                hovertemplate="uct_c=%{x:g}<br>mean rank %{y:.3f}<extra></extra>",
            )
        )
    fig_rank.add_hline(y=2.5, line_dash="dot", line_color="#999999",
                       annotation_text="fair (4-way)", annotation_font_size=11)
    fig_rank.update_layout(
        title="Mean rank vs uct_c (lower is better)",
        xaxis_title="uct_c", yaxis_title="mean rank (1 = 1st)",
        yaxis=dict(autorange="reversed"),
    )
    _add_uct_guides(fig_rank)
    _style_axis(fig_rank)
    figures["mean_rank"] = fig_rank

    # 4. Recruited deck diversity (normalized entropy).
    fig_ent = go.Figure()
    for label in dict.fromkeys(r["label"] for r in records):
        sub = sorted((r for r in records if r["label"] == label), key=lambda r: r["uct"])
        fig_ent.add_trace(
            go.Scatter(
                x=[r["uct"] for r in sub], y=[r["entropy_mean"] for r in sub],
                mode="lines+markers", name=label,
                line=dict(color=sub[0]["color"], width=2),
                marker=dict(size=9),
                error_y=dict(type="data", array=[r["entropy_sd"] for r in sub],
                             thickness=1.5, width=5, color=sub[0]["color"]),
                hovertemplate="uct_c=%{x:g}<br>recruited entropy %{y:.3f}<extra></extra>",
            )
        )
    fig_ent.update_layout(
        title="Deck diversity (recruited normalized entropy) vs uct_c",
        xaxis_title="uct_c", yaxis_title="recruited normalized entropy",
    )
    _add_uct_guides(fig_ent)
    _style_axis(fig_ent)
    figures["deck_diversity"] = fig_ent

    # 5. 2v2 head-to-head 4 vs 7.
    if two_v_two:
        sub = sorted(two_v_two, key=lambda r: r["uct"])
        fig_2v2 = go.Figure(
            go.Bar(
                x=[f"{r['uct']:g}" for r in sub],
                y=[100 * r["win_rate"] for r in sub],
                marker_color=[r["color"] for r in sub],
                text=[f"{100 * r['win_rate']:.1f}%" for r in sub],
                textposition="outside",
                hovertemplate="uct_c=%{x}<br>win %{y:.1f}%<extra></extra>",
            )
        )
        fig_2v2.add_hline(y=50.0, line_dash="dot", line_color="#999999",
                          annotation_text="coin-flip", annotation_font_size=11)
        fig_2v2.update_layout(
            title="Head-to-head 4 vs 7 (240 games, 2 seats each)",
            xaxis_title="uct_c", yaxis_title="win %",
            yaxis=dict(range=[0, 60]),
        )
        _style_axis(fig_2v2)
        figures["head_to_head_4_vs_7"] = fig_2v2

    return figures


_HEADLINE_HTML = """
<h1>IS-MCTS UCT sweep &mdash; which <code>uct_c</code> for NN-training data?</h1>
<p class="lede">
All runs share the production settings: <code>num_sims=200</code>, <code>random-c</code>
rollout evaluator, 4 players, rotating seats &mdash; so <code>uct_c</code> is the only
varying factor. ~98% of games are decided regardless of <code>uct_c</code> (no yield penalty).
</p>
<div class="callout">
<strong>Recommendation: <code>uct_c = 5.0</code></strong> for the NN-data rollout.
It is the measured strength peak (32.8% win share in the 0.8&ndash;10 ladder; 26.5% in the
4&ndash;7 ladder), decisively above the current default <code>1.4</code> (24.5% win share),
and safely below the over-exploration cliff at <code>10</code> (20.4%). The 4&ndash;7 band is a
statistical plateau; the diversity cost of 4&rarr;5 is ~1% relative entropy. Fallback band
<strong>4.0&ndash;5.0</strong>.
</div>
"""


def build_report(records: list[dict], figures: dict[str, go.Figure], meta: dict) -> str:
    divs = []
    for i, fig in enumerate(figures.values()):
        divs.append(fig.to_html(full_html=False, include_plotlyjs=(i == 0)))

    run_rows = "".join(
        f"<tr><td>{r['label']}</td><td>{r['n_games']}</td>"
        f"<td>{r['n_decided']}</td><td>{r['decided_frac']:.0%}</td>"
        f"<td>{', '.join(f'{a:g}' for a in r['arms'])}</td></tr>"
        for r in meta["runs"]
    )

    body = _HEADLINE_HTML + f"""
<h2>Runs reviewed</h2>
<table>
<thead><tr><th>ladder</th><th>games</th><th>decided</th><th>decided %</th><th>arms (uct_c)</th></tr></thead>
<tbody>{run_rows}</tbody>
</table>
""" + "".join(divs) + """
<p class="note">
Source: <code>artifacts/ismcts/experiments/uct_sweep/&lt;run&gt;/analysis.json</code>.
One additional run (166 games, no <code>analysis.json</code>) was incomplete and excluded.
</p>
"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UCT sweep &mdash; uct_c recommendation</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       max-width: 1080px; margin: 2rem auto; padding: 0 1.25rem; color: #1a1a1a; line-height: 1.5; }}
h1 {{ font-size: 1.5rem; }} h2 {{ margin-top: 2.5rem; font-size: 1.2rem; }}
.lede {{ color: #444; }}
.callout {{ background: #e8f5e9; border-left: 4px solid #2e7d32; padding: 0.75rem 1rem;
           border-radius: 4px; margin: 1rem 0; }}
table {{ border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }}
th, td {{ border: 1px solid #ddd; padding: 0.4rem 0.7rem; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #f5f5f5; }}
code {{ background: #f2f2f2; padding: 0 0.3rem; border-radius: 3px; }}
.note {{ color: #777; font-size: 0.85rem; margin-top: 2rem; }}
</style>
</head>
<body>{body}</body>
</html>"""


def write_outputs() -> None:
    records, meta = load_sweep_data()
    figures = build_figures(records)

    html = build_report(records, figures, meta)
    (OUT_DIR / "uct_sweep_report.html").write_text(html, encoding="utf-8")

    digest = {
        "meta": meta,
        "records": [
            {k: v for k, v in r.items() if k not in ("color", "dash", "is_2v2", "label")}
            for r in records
        ],
    }
    (OUT_DIR / "data.json").write_text(
        json.dumps(digest, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Wrote {OUT_DIR / 'uct_sweep_report.html'}")
    print(f"Wrote {OUT_DIR / 'data.json'}")
    print(f"{len(records)} arm observations across {len(meta['runs'])} runs "
          f"(num_sims={meta['num_sims']})")


if __name__ == "__main__":
    write_outputs()
