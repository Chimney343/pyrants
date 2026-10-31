"""Shard writing/loading for the NN dataset (layer 2b).

Shards store raw inputs (obs, legal ids/visits/q, final scores) as compact numpy
arrays; value/policy targets and sample weights are computed at load time so a
change to the target math never requires a rebuild (D11).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .actions import ACTION_LAYOUT, ACTION_SPACE_VERSION, NUM_GLOBAL_ACTIONS
from .index import CARD_INDEX_SHA, EFFECT_INDEX_SHA, NODE_INDEX_SHA, OP_INDEX_SHA
from .observation import ENCODER_VERSION, OBS_LAYOUT, OBS_SIZE
from .targets import policy_target, sample_weight, value_targets

PHASES = ("setup", "draw", "main", "end_of_turn", "cleanup", "game_over")
MOVE_TYPES = (
    "play_card",
    "recruit",
    "promote_card",
    "skip_promote",
    "initial_placement",
    "deploy",
    "assassinate",
    "return_spy",
    "resolve_generic",
    "activate_ability",
    "decline_ability",
    "end_main_phase",
    "resolve_end_of_turn",
    "resolve_cleanup",
    "__terminal__",
)


def phase_id(phase: str) -> int:
    return PHASES.index(phase) if phase in PHASES else len(PHASES) - 1


def move_type_id(move_type: str) -> int:
    return MOVE_TYPES.index(move_type) if move_type in MOVE_TYPES else len(MOVE_TYPES) - 1


@dataclass
class Sample:
    obs: np.ndarray
    legal_ids: list[int]
    legal_visits: list[int]
    legal_q: list[float]
    chosen_gid: int
    root_value: float | None
    total_visits: int
    forced: bool
    final_scores: list[float]  # rotated, length 4
    seat_mask: list[bool]
    acting_seat: int
    num_players: int
    sims_requested: int
    uct_c: float
    game_idx: int
    node: int
    phase: str
    move_type: str
    n_legal_raw: int = 0
    pair_merge: bool = False
    leak_checked: bool = False
    leak_mismatch: bool = False


def _sample_fields(samples: list[Sample]) -> dict[str, np.ndarray]:
    """Raw per-sample arrays (no computed targets) — the shard's on-disk shape.

    Shared by :func:`_write_one_shard` (persists these via ``np.savez_compressed``)
    and :func:`arrays_from_samples` (feeds them straight into :func:`_compute_arrays`
    without a disk round trip), so both paths build the exact same raw fields.
    """
    n = len(samples)
    nnz = sum(len(s.legal_ids) for s in samples)

    obs = np.zeros((n, OBS_SIZE), dtype=np.int16)
    legal_row_ptr = np.zeros(n + 1, dtype=np.int64)
    legal_ids = np.zeros(nnz, dtype=np.int32)
    legal_visits = np.zeros(nnz, dtype=np.int32)
    legal_q = np.zeros(nnz, dtype=np.float32)
    chosen_gid = np.zeros(n, dtype=np.int32)
    root_value = np.full(n, np.nan, dtype=np.float32)
    total_visits = np.zeros(n, dtype=np.int32)
    forced = np.zeros(n, dtype=bool)
    final_scores = np.zeros((n, 4), dtype=np.int16)
    seat_mask = np.zeros((n, 4), dtype=bool)
    acting_seat = np.zeros(n, dtype=np.int8)
    num_players = np.zeros(n, dtype=np.int8)
    sims_requested = np.zeros(n, dtype=np.int16)
    uct_c = np.zeros(n, dtype=np.float32)
    game_idx = np.zeros(n, dtype=np.int32)
    node = np.zeros(n, dtype=np.int32)
    phase = np.zeros(n, dtype=np.int8)
    move_type = np.zeros(n, dtype=np.int8)
    n_legal_raw = np.zeros(n, dtype=np.int32)
    pair_merge = np.zeros(n, dtype=bool)

    cursor = 0
    for i, s in enumerate(samples):
        obs[i] = s.obs
        legal_ids[cursor:cursor + len(s.legal_ids)] = s.legal_ids
        legal_visits[cursor:cursor + len(s.legal_visits)] = s.legal_visits
        legal_q[cursor:cursor + len(s.legal_q)] = s.legal_q
        cursor += len(s.legal_ids)
        legal_row_ptr[i + 1] = cursor
        chosen_gid[i] = s.chosen_gid
        if s.root_value is not None:
            root_value[i] = s.root_value
        total_visits[i] = s.total_visits
        forced[i] = s.forced
        final_scores[i] = np.clip(s.final_scores[:4], -32768, 32767).astype(np.int16)
        seat_mask[i] = s.seat_mask[:4]
        acting_seat[i] = s.acting_seat
        num_players[i] = s.num_players
        sims_requested[i] = s.sims_requested
        uct_c[i] = s.uct_c
        game_idx[i] = s.game_idx
        node[i] = s.node
        phase[i] = phase_id(s.phase)
        move_type[i] = move_type_id(s.move_type)
        n_legal_raw[i] = s.n_legal_raw
        pair_merge[i] = s.pair_merge

    return {
        "obs": obs,
        "legal_row_ptr": legal_row_ptr,
        "legal_ids": legal_ids,
        "legal_visits": legal_visits,
        "legal_q": legal_q,
        "chosen_gid": chosen_gid,
        "root_value": root_value,
        "total_visits": total_visits,
        "forced": forced,
        "final_scores": final_scores,
        "seat_mask": seat_mask,
        "acting_seat": acting_seat,
        "num_players": num_players,
        "sims_requested": sims_requested,
        "uct_c": uct_c,
        "game_idx": game_idx,
        "node": node,
        "phase": phase,
        "move_type": move_type,
        "n_legal_raw": n_legal_raw,
        "pair_merge": pair_merge,
    }


def _write_one_shard(path: Path, samples: list[Sample]) -> None:
    fields = _sample_fields(samples)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **fields)


def write_shards(
    samples,
    out_dir,
    *,
    dataset_id: str,
    shard_size: int,
    sources,
) -> dict:
    """Write every sample into ``shard_XXXX.npz`` files and a manifest.

    Returns the manifest dict (also written to ``out_dir/manifest.json``).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    materialized = list(samples)
    shard_size = max(1, int(shard_size))

    shards: list[dict] = []
    for shard_index, start in enumerate(range(0, len(materialized), shard_size)):
        chunk = materialized[start:start + shard_size]
        name = f"shard_{shard_index:04d}.npz"
        _write_one_shard(out_dir / name, chunk)
        shards.append({"file": name, "rows": len(chunk)})

    forced_count = sum(1 for s in materialized if s.forced)
    leak_checked = sum(1 for s in materialized if s.leak_checked)
    leak_mismatches = sum(1 for s in materialized if s.leak_mismatch)
    non_forced = [s for s in materialized if not s.forced]
    pair_move_merge_frac = (
        sum(1 for s in non_forced if s.pair_merge) / len(non_forced)
        if non_forced
        else None
    )

    manifest = {
        "dataset_id": dataset_id,
        "encoder_version": ENCODER_VERSION,
        "action_space_version": ACTION_SPACE_VERSION,
        "card_index_sha": CARD_INDEX_SHA,
        "node_index_sha": NODE_INDEX_SHA,
        "op_index_sha": OP_INDEX_SHA,
        "effect_index_sha": EFFECT_INDEX_SHA,
        "obs_layout": {k: list(v) for k, v in OBS_LAYOUT.items()},
        "action_layout": {k: list(v) for k, v in ACTION_LAYOUT.items()},
        "sources": sources,
        "pair_move_merge_frac": pair_move_merge_frac,
        "counts": {
            "games": len({s.game_idx for s in materialized}),
            "samples": len(materialized),
            "forced": forced_count,
        },
        "shards": shards,
        "phases": list(PHASES),
        "move_types": list(MOVE_TYPES),
        "leak_check": {"nodes": leak_checked, "mismatches": leak_mismatches},
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _compute_arrays(fields: dict[str, np.ndarray]) -> dict:
    """Compute policy/value/weight targets from raw per-sample fields.

    Shared by :func:`load_shard` (fields read from an ``.npz`` shard) and
    :func:`arrays_from_samples` (fields built directly from in-memory
    ``Sample`` objects via :func:`_sample_fields`), so both can never compute
    different targets from the same underlying data (D11).
    """
    obs = fields["obs"].astype(np.float32)
    row_ptr = fields["legal_row_ptr"]
    legal_ids = fields["legal_ids"]
    legal_visits = fields["legal_visits"]
    chosen = fields["chosen_gid"]
    final_scores = fields["final_scores"]
    players = fields["num_players"]
    sims = fields["sims_requested"]

    n = obs.shape[0]
    legal_mask = np.zeros((n, NUM_GLOBAL_ACTIONS), dtype=bool)
    policy = np.zeros((n, NUM_GLOBAL_ACTIONS), dtype=np.float32)
    value = np.zeros((n, 4), dtype=np.float32)
    weight = np.zeros(n, dtype=np.float32)
    for i in range(n):
        ids = legal_ids[row_ptr[i]:row_ptr[i + 1]]
        visits = legal_visits[row_ptr[i]:row_ptr[i + 1]]
        legal_mask[i, ids] = True
        policy[i] = policy_target(ids, visits, NUM_GLOBAL_ACTIONS)
        value[i] = value_targets(final_scores[i], int(players[i]))
        weight[i] = sample_weight(int(sims[i]))

    meta = {
        "chosen_gid": chosen.copy(),
        "node": fields["node"].copy(),
        "game_idx": fields["game_idx"].copy(),
        "forced": fields["forced"].copy(),
        "acting_seat": fields["acting_seat"].copy(),
        "seat_mask": fields["seat_mask"].copy(),
        "num_players": players.copy(),
        "total_visits": fields["total_visits"].copy(),
        "root_value": fields["root_value"].copy(),
        "phase": [PHASES[int(p)] for p in fields["phase"]],
        "move_type": [MOVE_TYPES[int(m)] for m in fields["move_type"]],
        "legal_row_ptr": row_ptr.copy(),
        "legal_ids": legal_ids.copy(),
        "legal_visits": legal_visits.copy(),
        "legal_q": fields["legal_q"].astype(np.float32).copy(),
        "sims_requested": sims.copy(),
        "uct_c": fields["uct_c"].copy(),
        "n_legal_raw": fields["n_legal_raw"].copy(),
        "pair_merge": fields["pair_merge"].copy(),
    }
    return {
        "obs": obs,
        "legal_mask": legal_mask,
        "policy": policy,
        "value": value,
        "weight": weight,
        "meta": meta,
    }


def load_shard(path) -> dict:
    """Load one shard and compute float targets at load time."""
    with np.load(Path(path)) as data:
        fields = {k: data[k] for k in data.files}
    return _compute_arrays(fields)


def arrays_from_samples(samples: list[Sample]) -> dict:
    """In-memory equivalent of ``write_shards()`` + :func:`load_shard` for a
    ``Sample`` list — skips the ``.npz`` round trip. Shares :func:`_compute_arrays`
    with :func:`load_shard` so the persisted-dataset and in-memory paths can
    never compute different policy/value/weight targets from the same samples.
    """
    return _compute_arrays(_sample_fields(samples))
