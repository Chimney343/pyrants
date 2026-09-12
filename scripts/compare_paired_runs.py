"""Paired A/B of two IS-MCTS runs that played the *same* games (same seed, flags).

The wall-time plan's byte-identical options (A1, A3, A4, A5 in
``docs/ismcts-walltime-plan.md``) promise two things at once: the search is
unchanged and it is faster. Re-playing a baseline run's games with the
candidate build gives both in one measurement, because determinism (G0) makes
each ``game_index`` do exactly the same decisions and sims on both sides:

* **G-I content identity** — per game, ``decisions.jsonl`` and ``replay.json``
  are equal after dropping the fields the runner stamps per run (``run_id`` and
  wall-clock timings), and ``final_decks.json`` is byte-equal.
* **G4 throughput** — per game, the paired ``wall_time_sec`` ratio (same work,
  so the ratio is the per-simulation lever plus scheduling noise), and at run
  level ``games/h`` from the manifest ``created_utc`` to the last file write.

Usage:
    python scripts/compare_paired_runs.py --baseline <run_dir> --candidate <run_dir>
        [--json out.json] [--md out.md]

Exit code 0 when every paired game is content-identical; 1 otherwise. The
speed-up is reported, not gated — the option's landing note decides.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

RUN_STAMPED_DECISION_FIELDS = ("run_id", "wall_time_ms")
RUN_STAMPED_REPLAY_FIELDS = ("run_id",)
# Config keys that legitimately differ between a baseline and its paired re-run.
CONFIG_IGNORE = {"output_dir", "log_level", "worker_log_level", "json_logs", "no_plots"}


def _load_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _game_dirs(run_dir: Path) -> dict[int, Path]:
    out: dict[int, Path] = {}
    for d in sorted(run_dir.glob("game_*")):
        if (d / "summary.json").exists():
            out[int(d.name.split("_", 1)[1])] = d
    return out


def _run_wall_sec(run_dir: Path, manifest: dict) -> float | None:
    """Seconds from the manifest's created_utc to the newest file in the run."""
    created = manifest.get("created_utc")
    if not created:
        return None
    t0 = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    newest = max(p.stat().st_mtime for p in run_dir.rglob("*") if p.is_file())
    return newest - t0.timestamp()


def _decisions_equal(a: Path, b: Path) -> tuple[bool, str]:
    with a.open(encoding="utf-8") as fa, b.open(encoding="utf-8") as fb:
        for i, (la, lb) in enumerate(zip(fa, fb, strict=False)):
            da, db = json.loads(la), json.loads(lb)
            for k in RUN_STAMPED_DECISION_FIELDS:
                da.pop(k, None)
                db.pop(k, None)
            if da != db:
                diff = sorted(k for k in set(da) | set(db) if da.get(k) != db.get(k))
                return False, f"line {i}: fields differ {diff}"
        extra_a = sum(1 for _ in fa)
        extra_b = sum(1 for _ in fb)
    if extra_a or extra_b:
        return False, f"line count differs (+{extra_a} baseline, +{extra_b} candidate)"
    return True, ""


def _replay_equal(a: Path, b: Path) -> tuple[bool, str]:
    ra, rb = _load_json(a), _load_json(b)
    for r in (ra, rb):
        for k in RUN_STAMPED_REPLAY_FIELDS:
            r.pop(k, None)
        for entry in r.get("replay_log", []):
            for k in RUN_STAMPED_REPLAY_FIELDS:
                entry.pop(k, None)
    if ra == rb:
        return True, ""
    diff = sorted(k for k in set(ra) | set(rb) if ra.get(k) != rb.get(k))
    return False, f"fields differ {diff}"


def compare(baseline: Path, candidate: Path) -> dict:
    mb, mc = _load_json(baseline / "manifest.json"), _load_json(candidate / "manifest.json")
    cfg_b, cfg_c = mb.get("config", {}), mc.get("config", {})
    config_diffs = sorted(
        k for k in set(cfg_b) | set(cfg_c)
        if k not in CONFIG_IGNORE and cfg_b.get(k) != cfg_c.get(k)
    )

    gb, gc = _game_dirs(baseline), _game_dirs(candidate)
    paired = sorted(set(gb) & set(gc))
    games = []
    for gi in paired:
        sb, sc = _load_json(gb[gi] / "summary.json"), _load_json(gc[gi] / "summary.json")
        dec_ok, dec_why = _decisions_equal(gb[gi] / "decisions.jsonl", gc[gi] / "decisions.jsonl")
        rep_ok, rep_why = _replay_equal(gb[gi] / "replay.json", gc[gi] / "replay.json")
        decks_ok = _sha256(gb[gi] / "final_decks.json") == _sha256(gc[gi] / "final_decks.json")
        wb, wc = float(sb["wall_time_sec"]), float(sc["wall_time_sec"])
        games.append({
            "game_index": gi,
            "decision_count": sb["decision_count"],
            "decision_count_equal": sb["decision_count"] == sc["decision_count"],
            "wall_baseline_sec": wb,
            "wall_candidate_sec": wc,
            "wall_ratio": wb / wc if wc else None,
            "sims_per_sec_baseline": sb.get("sims_per_sec_avg"),
            "sims_per_sec_candidate": sc.get("sims_per_sec_avg"),
            "latency_p50_baseline_ms": (sb.get("move_latency_ms") or {}).get("p50"),
            "latency_p50_candidate_ms": (sc.get("move_latency_ms") or {}).get("p50"),
            "decisions_identical": dec_ok,
            "replay_identical": rep_ok,
            "final_decks_identical": decks_ok,
            "detail": "; ".join(x for x in (dec_why, rep_why) if x),
        })

    ratios = [g["wall_ratio"] for g in games if g["wall_ratio"]]
    workers_b = cfg_b.get("workers")
    workers_c = cfg_c.get("workers")
    wall_b = _run_wall_sec(baseline, mb)
    wall_c = _run_wall_sec(candidate, mc)
    sum_b = sum(g["wall_baseline_sec"] for g in games)
    sum_c = sum(g["wall_candidate_sec"] for g in games)
    n = len(games)

    def games_per_hour(total_sec: float | None, count: int) -> float | None:
        return round(count * 3600.0 / total_sec, 1) if total_sec else None

    return {
        "baseline": {
            "run_dir": str(baseline), "run_id": mb.get("run_id"),
            "engine_git_sha": mb.get("engine_git_sha"), "engine_dll_sha256": mb.get("engine_dll_sha256"),
            "workers": workers_b, "games": len(gb),
            "run_wall_sec": round(wall_b, 1) if wall_b else None,
            "games_per_hour_run": games_per_hour(wall_b, len(gb)),
            "games_per_hour_ideal": games_per_hour(sum_b / workers_b, n) if workers_b and n else None,
        },
        "candidate": {
            "run_dir": str(candidate), "run_id": mc.get("run_id"),
            "engine_git_sha": mc.get("engine_git_sha"), "engine_dll_sha256": mc.get("engine_dll_sha256"),
            "workers": workers_c, "games": len(gc),
            "run_wall_sec": round(wall_c, 1) if wall_c else None,
            "games_per_hour_run": games_per_hour(wall_c, len(gc)),
            "games_per_hour_ideal": games_per_hour(sum_c / workers_c, n) if workers_c and n else None,
        },
        "config_diffs": config_diffs,
        "paired_games": n,
        "unpaired_baseline": sorted(set(gb) - set(gc)),
        "unpaired_candidate": sorted(set(gc) - set(gb)),
        "content_identical": all(
            g["decisions_identical"] and g["replay_identical"] and g["final_decks_identical"]
            and g["decision_count_equal"] for g in games
        ) and n > 0,
        "wall_ratio": {
            "median": round(statistics.median(ratios), 3) if ratios else None,
            "mean": round(statistics.fmean(ratios), 3) if ratios else None,
            "min": round(min(ratios), 3) if ratios else None,
            "max": round(max(ratios), 3) if ratios else None,
            "sum_ratio": round(sum_b / sum_c, 3) if sum_c else None,
        },
        "games": games,
    }


def render_md(r: dict) -> str:
    b, c = r["baseline"], r["candidate"]
    lines = [
        f"Paired comparison: baseline `{b['run_id']}` vs candidate `{c['run_id']}` "
        f"({r['paired_games']} paired games)",
        "",
        "| | baseline | candidate |",
        "|---|---|---|",
        f"| engine git sha | `{(b['engine_git_sha'] or '')[:12]}` | `{(c['engine_git_sha'] or '')[:12]}` |",
        f"| DLL sha256 | `{(b['engine_dll_sha256'] or '')[:12]}...` | `{(c['engine_dll_sha256'] or '')[:12]}...` |",
        f"| workers / games | {b['workers']} / {b['games']} | {c['workers']} / {c['games']} |",
        f"| run wall | {b['run_wall_sec']} s | {c['run_wall_sec']} s |",
        f"| games/h (run wall) | {b['games_per_hour_run']} | {c['games_per_hour_run']} |",
        f"| games/h (ideal, sum of game wall / workers) | {b['games_per_hour_ideal']} | {c['games_per_hour_ideal']} |",
        "",
        f"Config diffs (search-relevant): {r['config_diffs'] or 'none'}",
        f"Content identical on all paired games: **{r['content_identical']}**",
        f"Per-game wall ratio (baseline / candidate): median **{r['wall_ratio']['median']}**, "
        f"mean {r['wall_ratio']['mean']}, min {r['wall_ratio']['min']}, max {r['wall_ratio']['max']}; "
        f"sum-wall ratio {r['wall_ratio']['sum_ratio']}",
        "",
        "| game | decisions | wall base (s) | wall cand (s) | ratio | sims/s base | sims/s cand | identical |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for g in r["games"]:
        ident = "yes" if (g["decisions_identical"] and g["replay_identical"]
                          and g["final_decks_identical"] and g["decision_count_equal"]) else f"NO ({g['detail']})"
        lines.append(
            f"| {g['game_index']} | {g['decision_count']} | {g['wall_baseline_sec']:.0f} | "
            f"{g['wall_candidate_sec']:.0f} | {g['wall_ratio']:.2f} | {g['sims_per_sec_baseline']} | "
            f"{g['sims_per_sec_candidate']} | {ident} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", required=True, type=Path)
    ap.add_argument("--candidate", required=True, type=Path)
    ap.add_argument("--json", type=Path, help="write the full result here")
    ap.add_argument("--md", type=Path, help="write the markdown table here")
    args = ap.parse_args(argv)

    result = compare(args.baseline, args.candidate)
    md = render_md(result)
    print(md)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.md:
        args.md.write_text(md, encoding="utf-8")
    if result["config_diffs"]:
        print(f"WARNING: search-relevant config differs: {result['config_diffs']}", file=sys.stderr)
    return 0 if result["content_identical"] else 1


if __name__ == "__main__":
    sys.exit(main())
