"""Trainability smoke test for the NN pipeline.

Builds training samples directly from one or more IS-MCTS sim run folders
(no separate ``build_nn_dataset`` step required), trains a small
``SmokeNet`` (:mod:`openspiel_pyrants.nn.model`), and reports whether the
resulting policy/value losses beat closed-form baselines. This answers "does
the encoder/target pipeline carry a learnable signal at all" — it is not a
real training loop and the printed verdict is informational only (the
process exits 0 regardless of the verdict).

Usage:
    python -m scripts.train_nn_smoke --runs artifacts/ismcts/runs/<ts>_<id>
    python -m scripts.train_nn_smoke --runs artifacts/ismcts/runs/<a> artifacts/ismcts/quick/<b>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from scripts._nn_dataset import build_dataset_from_runs  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a tiny network on IS-MCTS sim data as a trainability smoke test."
    )
    parser.add_argument("--runs", nargs="+", type=Path, required=True,
                        help="Sim run directories (or bases containing them).")
    parser.add_argument("--allow-legacy-schema", action="store_true",
                        help="Accept pre-v2 games and recover visits from policy.")
    parser.add_argument("--keep-forced", action="store_true",
                        help="Keep forced decisions (default: drop them).")
    parser.add_argument("--leak-check", type=int, default=0,
                        help="Re-encode N random nodes after determinize (per game).")
    parser.add_argument("--strict", action="store_true",
                        help="Raise on a desync/alignment failure instead of skipping the game.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--hidden-dim", type=int, default=256)
    parser.add_argument("--val-frac", type=float, default=0.15,
                        help="Fraction of samples held out for validation, split by whole games.")
    parser.add_argument("--value-loss-weight", type=float, default=1.0)
    parser.add_argument("--max-samples", type=int, default=None,
                        help="Cap the total samples used, subsampling whole games.")
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--save", type=Path, default=None,
                        help="Optional path to save the trained model's state dict.")
    return parser.parse_args()


def _select(data: dict, mask: np.ndarray) -> dict:
    """Subset every array in a ``load_shard``/``arrays_from_samples``-shaped
    dict (including its ``meta`` sub-dict) by a boolean row mask."""
    idx = np.nonzero(mask)[0]

    def _sub(value):
        if isinstance(value, list):
            return [value[i] for i in idx]
        return value[idx]

    return {
        "obs": data["obs"][idx],
        "legal_mask": data["legal_mask"][idx],
        "policy": data["policy"][idx],
        "value": data["value"][idx],
        "weight": data["weight"][idx],
        "meta": {k: _sub(v) for k, v in data["meta"].items()},
    }


def _subsample_whole_games(data: dict, max_samples: int, seed: int) -> dict:
    """Keep whole games (shuffled) until ``max_samples`` is reached, so a
    downstream group split still groups cleanly."""
    game_idx = data["meta"]["game_idx"]
    if len(game_idx) <= max_samples:
        return data
    unique_games = np.unique(game_idx)
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(unique_games)
    keep: list[int] = []
    running = 0
    for g in shuffled:
        if running >= max_samples:
            break
        keep.append(int(g))
        running += int(np.sum(game_idx == g))
    return _select(data, np.isin(game_idx, keep))


def _group_split(game_idx: np.ndarray, val_frac: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Split sample indices by whole games (not individual samples) — decisions
    within one game are highly correlated, so a per-sample split would leak.

    Returns (train_mask, val_mask). Both always keep >= 1 game when there are
    >= 2 distinct games and ``val_frac`` > 0; with a single game (or
    ``val_frac == 0``), everything goes to train.
    """
    unique_games = np.unique(game_idx)
    if len(unique_games) <= 1:
        return np.ones(len(game_idx), dtype=bool), np.zeros(len(game_idx), dtype=bool)

    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(unique_games)
    target_val = val_frac * len(game_idx)

    val_games: list[int] = []
    running = 0
    for g in shuffled:
        if running >= target_val:
            break
        if len(val_games) >= len(unique_games) - 1:
            break
        val_games.append(int(g))
        running += int(np.sum(game_idx == g))

    val_mask = np.isin(game_idx, val_games)
    return ~val_mask, val_mask


def _policy_loss_terms(logits, policy, legal_mask):
    """Per-row masked cross-entropy, plus which rows have a nonzero target
    (rows with zero total visits carry an all-zero target and must not
    contribute to the loss)."""
    import torch

    masked_logits = logits.masked_fill(~legal_mask, -1e9)
    log_probs = torch.log_softmax(masked_logits, dim=1)
    per_row = -(policy * log_probs).sum(dim=1)
    valid = policy.sum(dim=1) > 0
    return per_row, valid


def _value_loss_terms(pred, target, seat_mask):
    """Per-row value MSE, averaged only over the seats that are actually
    present in that sample (absent seats carry a padded-zero target)."""
    seat_mask_f = seat_mask.float()
    sq_err = (pred - target) ** 2 * seat_mask_f
    denom = seat_mask_f.sum(dim=1).clamp(min=1.0)
    return sq_err.sum(dim=1) / denom


def _weighted_mean(per_row, weight):
    import torch

    total_weight = weight.sum().clamp(min=1e-8)
    return torch.sum(per_row * weight) / total_weight


def _uniform_policy_baseline(data: dict) -> float | None:
    """Closed-form cross-entropy of a uniform distribution over legal actions
    against the logged visit-distribution target: since the target sums to
    1, CE reduces to ``log(n_legal)`` regardless of the target's shape."""
    valid = data["policy"].sum(axis=1) > 0
    if not valid.any():
        return None
    n_legal = data["legal_mask"].sum(axis=1)
    return float(np.log(np.clip(n_legal[valid], 1, None)).mean())


def _mean_value_baseline(train_data: dict, val_data: dict) -> float:
    """Predict-the-train-mean value baseline, fit on train and scored on val
    (never fit on val) — the same weighted/seat-masked formula as the value
    loss itself, so it's a fair comparison."""
    seat_mask = train_data["meta"]["seat_mask"].astype(np.float64)
    weight = train_data["weight"].astype(np.float64)[:, None] * seat_mask
    denom = weight.sum(axis=0)
    denom = np.where(denom > 0, denom, 1.0)
    seat_mean = (train_data["value"] * weight).sum(axis=0) / denom

    val_seat_mask = val_data["meta"]["seat_mask"].astype(np.float64)
    sq_err = (seat_mean[None, :] - val_data["value"]) ** 2 * val_seat_mask
    per_row = sq_err.sum(axis=1) / np.clip(val_seat_mask.sum(axis=1), 1, None)
    return float(np.average(per_row, weights=val_data["weight"]))


def _run_epoch(model, loader, optimizer, value_loss_weight, device, *, train: bool):
    import torch

    model.train(train)
    total_policy = total_value = total_weight = 0.0
    context = torch.enable_grad() if train else torch.no_grad()
    with context:
        for obs, legal_mask, policy, value, weight, seat_mask in loader:
            obs = obs.to(device)
            legal_mask = legal_mask.to(device)
            policy = policy.to(device)
            value = value.to(device)
            weight = weight.to(device)
            seat_mask = seat_mask.to(device)

            logits, pred_value = model(obs)
            policy_terms, valid = _policy_loss_terms(logits, policy, legal_mask)
            value_terms = _value_loss_terms(pred_value, value, seat_mask)

            policy_loss = _weighted_mean(policy_terms, weight * valid.float())
            value_loss = _weighted_mean(value_terms, weight)

            if train:
                optimizer.zero_grad()
                (policy_loss + value_loss_weight * value_loss).backward()
                optimizer.step()

            batch_weight = weight.sum().item()
            total_policy += policy_loss.item() * batch_weight
            total_value += value_loss.item() * batch_weight
            total_weight += batch_weight

    if total_weight <= 0:
        return float("nan"), float("nan")
    return total_policy / total_weight, total_value / total_weight


def main() -> int:
    args = _parse_args()

    try:
        import torch
        from torch.utils.data import DataLoader, TensorDataset

        from openspiel_pyrants.nn.model import SmokeNet
    except ImportError:
        print(
            "torch is required for this script — install the optional 'nn' "
            "dependency group (e.g. `uv sync --extra nn` or `pip install -e '.[nn]'`).",
            file=sys.stderr,
        )
        return 2

    from openspiel_pyrants.nn.dataset import arrays_from_samples

    result = build_dataset_from_runs(
        args.runs,
        allow_legacy_schema=args.allow_legacy_schema,
        keep_forced=args.keep_forced,
        leak_check=args.leak_check,
        strict=args.strict,
        seed=args.seed,
    )
    print(
        f"games accepted={len(result.accepted)} rejected={len(result.rejected)} "
        f"samples={len(result.samples)}",
        file=sys.stderr,
    )
    if not result.samples:
        print("no samples to train on — check --runs and the rejection reasons above.",
              file=sys.stderr)
        return 2

    data = arrays_from_samples(result.samples)
    if args.max_samples is not None:
        data = _subsample_whole_games(data, args.max_samples, args.seed)

    train_mask, val_mask = _group_split(data["meta"]["game_idx"], args.val_frac, args.seed)
    train_data = _select(data, train_mask)
    val_data = _select(data, val_mask) if val_mask.any() else None

    n_train_games = len(np.unique(train_data["meta"]["game_idx"]))
    if val_data is None:
        print(f"only {n_train_games} accepted game(s) — skipping validation split.",
              file=sys.stderr)
    else:
        n_val_games = len(np.unique(val_data["meta"]["game_idx"]))
        print(f"train: {len(train_data['obs'])} samples / {n_train_games} games   "
              f"val: {len(val_data['obs'])} samples / {n_val_games} games",
              file=sys.stderr)

    if len(train_data["obs"]) < 2:
        print("fewer than 2 training samples — cannot train (BatchNorm1d needs "
              "a batch size >= 2).", file=sys.stderr)
        return 2

    device = torch.device(args.device)
    model = SmokeNet(hidden_dim=args.hidden_dim).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    def _to_loader(d: dict, *, batch_size: int, shuffle: bool, drop_last: bool) -> DataLoader:
        dataset = TensorDataset(
            torch.from_numpy(d["obs"]),
            torch.from_numpy(d["legal_mask"]),
            torch.from_numpy(d["policy"]),
            torch.from_numpy(d["value"]),
            torch.from_numpy(d["weight"]),
            torch.from_numpy(d["meta"]["seat_mask"]),
        )
        generator = torch.Generator().manual_seed(args.seed)
        return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle,
                           drop_last=drop_last, generator=generator)

    train_batch_size = max(2, min(args.batch_size, len(train_data["obs"])))
    train_loader = _to_loader(train_data, batch_size=train_batch_size, shuffle=True, drop_last=True)
    val_loader = None
    if val_data is not None:
        val_batch_size = max(1, min(args.batch_size, len(val_data["obs"])))
        val_loader = _to_loader(val_data, batch_size=val_batch_size, shuffle=False, drop_last=False)

    for epoch in range(1, args.epochs + 1):
        train_policy, train_value = _run_epoch(
            model, train_loader, optimizer, args.value_loss_weight, device, train=True
        )
        line = f"epoch {epoch:3d}  train_policy={train_policy:.4f} train_value={train_value:.4f}"
        if val_loader is not None:
            val_policy, val_value = _run_epoch(
                model, val_loader, optimizer, args.value_loss_weight, device, train=False
            )
            line += f"  val_policy={val_policy:.4f} val_value={val_value:.4f}"
        print(line)

    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), args.save)
        print(f"saved model state dict to {args.save}", file=sys.stderr)

    if val_loader is not None:
        uniform_baseline = _uniform_policy_baseline(val_data)
        value_baseline = _mean_value_baseline(train_data, val_data)
        final_val_policy, final_val_value = _run_epoch(
            model, val_loader, optimizer, args.value_loss_weight, device, train=False
        )
        print("--- baselines ---")
        if uniform_baseline is not None:
            policy_verdict = "BETTER" if final_val_policy < uniform_baseline else "NOT better"
            print(f"policy: val={final_val_policy:.4f} vs uniform-baseline={uniform_baseline:.4f}"
                  f"  -> {policy_verdict} than baseline")
        value_verdict = "BETTER" if final_val_value < value_baseline else "NOT better"
        print(f"value:  val={final_val_value:.4f} vs mean-baseline={value_baseline:.4f}"
              f"  -> {value_verdict} than baseline")
    else:
        print("--- baselines ---")
        print("no validation split available — no verdict computed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
