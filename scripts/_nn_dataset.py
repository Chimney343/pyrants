"""Pure dataset-building parts: validation and per-game sample iteration.

Kept separate from the CLI (``scripts/build_nn_dataset.py``) so the hard logic
is unit-testable without argparse. Implements Phase 4 of
``docs/nn-training-data-tdd-plan.md``.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from engine_c.bindings.c_adapter import CEngineAdapter
from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.pending_context import read_pending_generic_context_full
from interface.replay_loader import engine_seed, load_replay
from interface.replay_player import ReplayDesyncError, find_matching_move
from openspiel_pyrants.nn.actions import action_context, move_to_global_action
from openspiel_pyrants.nn.dataset import Sample
from openspiel_pyrants.nn.observation import encode_observation, seat_order
from openspiel_pyrants.nn.targets import merge_duplicates

MAX_SEATS = 4


def report_metrics(dataset_dir) -> dict:
    """Label-sanity metrics over a dataset's shards (Phase 5 acceptance)."""
    from openspiel_pyrants.nn.dataset import load_shard

    dataset_dir = Path(dataset_dir)
    manifest = _load_json(dataset_dir / "manifest.json") or {}
    value_sum = np.zeros(MAX_SEATS, dtype=np.float64)
    value_n = np.zeros(MAX_SEATS, dtype=np.int64)
    samples = 0
    argmax_hits = argmax_total = 0
    argmax_hits_200 = argmax_total_200 = 0
    n_legal_raw_total = 0

    for shard in manifest.get("shards", ()):
        data = load_shard(dataset_dir / shard["file"])
        policy = data["policy"]
        value = data["value"]
        seat_mask = data["meta"]["seat_mask"]
        chosen = data["meta"]["chosen_gid"]
        sims = data["meta"]["sims_requested"]
        n_legal_raw = data["meta"]["n_legal_raw"]
        for i in range(policy.shape[0]):
            samples += 1
            n_legal_raw_total += int(n_legal_raw[i])
            for seat in range(MAX_SEATS):
                if seat_mask[i][seat]:
                    value_sum[seat] += value[i][seat]
                    value_n[seat] += 1
            if policy[i].sum() > 0:
                hit = int(np.argmax(policy[i])) == int(chosen[i])
                argmax_total += 1
                argmax_hits += int(hit)
                if int(sims[i]) >= 200:
                    argmax_total_200 += 1
                    argmax_hits_200 += int(hit)

    return {
        "samples": samples,
        "value_mean_per_seat": [
            float(value_sum[j] / value_n[j]) if value_n[j] else 0.0
            for j in range(MAX_SEATS)
        ],
        "policy_argmax_match_frac": (
            argmax_hits / argmax_total if argmax_total else None
        ),
        "policy_argmax_match_frac_sims_ge_200": (
            argmax_hits_200 / argmax_total_200 if argmax_total_200 else None
        ),
        "argmax_n": argmax_total,
        "argmax_n_sims_ge_200": argmax_total_200,
        "n_legal_raw_mean": (n_legal_raw_total / samples) if samples else None,
        "pair_move_merge_frac": manifest.get("pair_move_merge_frac"),
        "leak_check": manifest.get("leak_check", {}),
        "counts": manifest.get("counts", {}),
    }


class AlignmentError(RuntimeError):
    """The engine's legal moves do not match the logged decision line."""

    def __init__(self, game_dir, node: int, expected, actual) -> None:
        self.game_dir = game_dir
        self.node = node
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"alignment mismatch in {game_dir} at node {node}: "
            f"expected {expected!r} got {actual!r}"
        )


@dataclass
class GameCheck:
    ok: bool
    reasons: list[str]
    schema_version: int | None
    run_id: str | None


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def validate_game_dir(game_dir, *, allow_legacy: bool) -> GameCheck:
    """Validate one game directory against the layer-0/1 contracts."""
    game_dir = Path(game_dir)
    replay = _load_json(game_dir / "replay.json")
    if not isinstance(replay, dict):
        return GameCheck(False, ["missing replay.json"], None, None)

    run_id = replay.get("run_id")
    schema_version = replay.get("schema_version")
    if not isinstance(schema_version, int):
        schema_version = None

    reasons: list[str] = []
    if schema_version != 2 and not allow_legacy:
        reasons.append("legacy schema")

    summary = _load_json(game_dir / "summary.json")
    if not isinstance(summary, dict):
        reasons.append("missing summary")
    else:
        if summary.get("run_id") != run_id:
            reasons.append("run_id mismatch")
        if summary.get("stopped_reason") != "terminal":
            reasons.append(f"stopped_reason={summary.get('stopped_reason')!r}")

    decisions = _load_jsonl(game_dir / "decisions.jsonl")
    if not decisions:
        reasons.append("missing decisions")
    elif any(d.get("run_id") != run_id for d in decisions):
        reasons.append("run_id mismatch")

    if int(replay.get("step_count", -1)) != len(decisions):
        reasons.append("decision count mismatch")

    try:
        bundle = load_replay(game_dir)
        if bundle.setup_sha_matches is False:
            reasons.append("setup sha mismatch")
    except Exception as exc:  # noqa: BLE001 - validation must never raise
        reasons.append(f"load error: {exc}")

    # De-duplicate while preserving order.
    seen: list[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.append(reason)
    return GameCheck(not seen, seen, schema_version, run_id)


def _legacy_visits(decision: dict) -> dict[int, int]:
    total = int(decision.get("sims_requested", 1) or 1) - 1
    visits: dict[int, int] = {}
    for key, prob in (decision.get("policy") or {}).items():
        product = float(prob) * total
        rounded = int(round(product))
        if abs(product - rounded) > 1e-6:
            raise ValueError(
                f"legacy policy is not integral in sims-1: {key}={prob} × {total}"
            )
        visits[int(key)] = rounded
    return visits


def _rotate_scores(final_scores: dict, order, num_players: int) -> list[float]:
    rotated = [float(final_scores.get(pid, 0)) for pid in order[:num_players]]
    rotated.extend([0.0] * (MAX_SEATS - num_players))
    return rotated


def _pair_source_destination(payload, ctx):
    """``(kind, destination, source)`` for a destination-keyed pair move, else None."""
    op = ctx.pending_op
    if op == "move_troop":
        target = payload.get("target_id") or ""
        if target.count(":") < 2:
            return None
        src_slot, dst, _dst_slot = target.split(":", 2)
        return ("move_troop", dst, f"{payload.get('action_id')}:{src_slot}")
    if op == "place_spy" and payload.get("target_id"):
        return ("place_spy", payload.get("action_id"), payload.get("target_id"))
    return None


def _has_pair_merge(gids, payloads, ctx) -> bool:
    """True when two legal moves differ only in a destination-keyed pair's source.

    Takes the already-mapped *gids* so ``move_to_global_action`` is not run a
    second time for the pair-merge probe.
    """
    groups: dict[int, list] = {}
    for gid, payload in zip(gids, payloads, strict=True):
        groups.setdefault(gid, []).append(payload)
    for group in groups.values():
        if len(group) < 2:
            continue
        infos = [_pair_source_destination(p, ctx) for p in group]
        if all(info is not None for info in infos) and len({(i[0], i[1]) for i in infos}) == 1:
            return True
    return False


def iter_samples(
    bundle,
    *,
    allow_legacy: bool,
    keep_forced: bool,
    leak_check_rng=None,
    leak_check_limit: int = 5,
    game_idx: int = 0,
):
    """Yield one :class:`Sample` per decision of *bundle*.

    Drives a fresh ``CEngineAdapter`` through the replay, asserting the engine's
    legal payloads equal the logged ``legal_moves_payload`` (or the logged
    ``legal_moves`` strings in legacy mode) before encoding.
    """
    engine = CEngine()
    engine.initialize(
        catalog_path=str(bundle.card_path),
        board_path=str(bundle.board_path),
        setup_path=str(bundle.setup_path),
        setup_data_json=bundle.setup_json,
    )
    player_ids = list(bundle.meta.player_ids)
    n = len(player_ids)
    seed = engine_seed(bundle.meta.shuffle_seed)
    adapter = CEngineAdapter(engine.create_game(player_ids, seed), engine, player_ids, seed)

    uct_c = float(bundle.summary.get("uct_c", 0.0)) if bundle.summary else 0.0
    final_scores = bundle.replay.get("final_scores", {}) or {}
    log = [
        e
        for e in bundle.replay.get("replay_log", ())
        if e.get("payload", {}).get("move_type") != "__terminal__"
    ]
    decisions = bundle.decisions
    leak_done = 0

    try:
        for i, entry in enumerate(log):
            decision = decisions[i] if i < len(decisions) else {}
            cp = entry.get("player_id") or adapter.state.current_player_id

            moves = list(adapter.legal_moves())
            payloads = [move.to_payload() for move in moves]

            if allow_legacy:
                expected = decision.get("legal_moves")
                actual = [str(move) for move in moves]
                if expected is not None and actual != expected:
                    raise AlignmentError(bundle.meta.game_dir, i, expected, actual)
            else:
                expected = decision.get("legal_moves_payload")
                if expected is None or payloads != expected:
                    raise AlignmentError(bundle.meta.game_dir, i, expected, payloads)

            pending_ctx = read_pending_generic_context_full(adapter._state._ptr)
            ctx = action_context(adapter, cp, pending_ctx)
            obs = encode_observation(adapter, cp, pending_ctx)
            n_legal_raw = len(payloads)

            forced = len(moves) <= 1
            if allow_legacy:
                # Forced decisions carry no search; the v2 runner records
                # total_visits 0 / visit_counts {} for them, so legacy recovery
                # must do the same rather than trusting the uniform policy.
                visits_by_id = {} if forced else _legacy_visits(decision)
                q_by_id: dict[int, float] = {}
                total_visits = 0 if forced else max(
                    0, int(decision.get("sims_requested", 1) or 1) - 1
                )
                root_value = None
            else:
                visits_by_id = {
                    int(k): int(v) for k, v in (decision.get("visit_counts") or {}).items()
                }
                q_by_id = {
                    int(k): float(v) for k, v in (decision.get("q_values") or {}).items()
                }
                total_visits = int(decision.get("total_visits") or 0)
                raw_root = decision.get("root_value")
                root_value = float(raw_root) if raw_root is not None else None

            gids: list[int] = []
            per_id_visits: list[int] = []
            per_id_q: list[float] = []
            for idx, payload in enumerate(payloads):
                gids.append(move_to_global_action(payload, ctx))
                per_id_visits.append(int(visits_by_id.get(idx, 0)))
                per_id_q.append(float(q_by_id.get(idx, 0.0)))

            pair_merge = _has_pair_merge(gids, payloads, ctx)

            unique_gids, summed_visits, weighted_q = merge_duplicates(
                gids, per_id_visits, per_id_q
            )
            legal_q = [float(weighted_q[g]) for g in unique_gids] if weighted_q else [
                0.0 for _ in unique_gids
            ]

            match = find_matching_move(moves, entry["payload"])
            if match is None:
                raise ReplayDesyncError(
                    i, entry["payload"], [m.to_payload() for m in moves[:10]]
                )
            chosen_gid = move_to_global_action(match.to_payload(), ctx)

            leak_checked = False
            leak_mismatch = False
            if leak_check_rng is not None and leak_done < leak_check_limit:
                det = adapter.determinize(cp, int(leak_check_rng.randint(0, 2**31 - 1)))
                if det is not None:
                    obs_det = encode_observation(det, cp, pending_ctx)
                    leak_checked = True
                    leak_mismatch = not np.array_equal(obs, obs_det)
                    leak_done += 1
                    det.destroy()

            if keep_forced or not forced:
                yield Sample(
                    obs=obs,
                    legal_ids=[int(g) for g in unique_gids],
                    legal_visits=[int(v) for v in summed_visits],
                    legal_q=legal_q,
                    chosen_gid=int(chosen_gid),
                    root_value=root_value,
                    total_visits=total_visits,
                    forced=forced,
                    final_scores=_rotate_scores(
                        final_scores, seat_order(adapter, cp), n
                    ),
                    seat_mask=[True] * n + [False] * (MAX_SEATS - n),
                    acting_seat=adapter.player_index(cp),
                    num_players=n,
                    sims_requested=int(decision.get("sims_requested", 0) or 0),
                    uct_c=uct_c,
                    game_idx=game_idx,
                    node=int(decision.get("node", i)),
                    phase=str(entry.get("phase", "")),
                    move_type=str(entry.get("move_type", "")),
                    n_legal_raw=n_legal_raw,
                    pair_merge=pair_merge,
                    leak_checked=leak_checked,
                    leak_mismatch=leak_mismatch,
                )
            adapter.apply(match)
    finally:
        adapter.destroy()


@dataclass
class BuildResult:
    samples: list[Sample]
    accepted: list[dict]
    rejected: list[dict]
    game_dirs: list[Path]


def game_dirs_for_run(run_path) -> list[Path]:
    """Every ``game_*`` directory under *run_path*.

    *run_path* is either a specific run directory (has its own
    ``manifest.json``, with ``game_*`` subdirectories directly inside) or a
    base directory containing several run directories (falls back to
    scanning for ``replay.json`` anywhere underneath).
    """
    run_path = Path(run_path)
    if not run_path.exists():
        return []
    if (run_path / "manifest.json").exists():
        return sorted(p for p in run_path.glob("game_*") if p.is_dir())
    return sorted(p.parent for p in run_path.rglob("replay.json"))


def build_dataset_from_runs(
    runs,
    *,
    allow_legacy_schema: bool = False,
    keep_forced: bool = False,
    leak_check: int = 0,
    strict: bool = False,
    seed: int = 42,
) -> BuildResult:
    """Replay every accepted game under *runs* into a flat ``Sample`` list.

    *runs* is a list of run directories (or bases containing several — see
    :func:`game_dirs_for_run`). Shared by the CLI dataset builder
    (``scripts/build_nn_dataset.py``) and any other caller (e.g. the
    trainability smoke test) that wants ``Sample`` objects without going
    through argparse or persisting shards. ``game_idx`` is assigned by a
    single ``enumerate()`` over every game directory across all of *runs*,
    not reset per run, so samples stay groupable by game regardless of how
    many run folders were combined.
    """
    game_dirs: list[Path] = []
    for run in runs:
        game_dirs.extend(game_dirs_for_run(run))

    rng = random.Random(seed) if leak_check > 0 else None
    samples: list[Sample] = []
    accepted: list[dict] = []
    rejected: list[dict] = []

    for game_idx, game_dir in enumerate(game_dirs):
        check = validate_game_dir(game_dir, allow_legacy=allow_legacy_schema)
        if not check.ok:
            rejected.append({
                "game_dir": str(game_dir),
                "run_id": check.run_id,
                "schema_version": check.schema_version,
                "reasons": check.reasons,
            })
            continue
        bundle = load_replay(game_dir)
        try:
            game_samples = list(iter_samples(
                bundle,
                allow_legacy=allow_legacy_schema,
                keep_forced=keep_forced,
                leak_check_rng=rng,
                leak_check_limit=leak_check,
                game_idx=game_idx,
            ))
        except (ReplayDesyncError, AlignmentError, ValueError) as exc:
            if strict:
                raise
            rejected.append({
                "game_dir": str(game_dir),
                "run_id": check.run_id,
                "schema_version": check.schema_version,
                "reasons": [f"{type(exc).__name__}: {exc}"],
            })
            continue
        accepted.append({
            "game_dir": str(game_dir),
            "run_id": check.run_id,
            "samples": len(game_samples),
        })
        samples.extend(game_samples)

    return BuildResult(samples=samples, accepted=accepted, rejected=rejected, game_dirs=game_dirs)
