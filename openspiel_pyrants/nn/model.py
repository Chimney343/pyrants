"""A deliberately minimal policy/value network for the trainability smoke test.

Not a real architecture — no card/board embeddings, no attention. It exists
only to answer "does the data pipeline (:mod:`.dataset`, :mod:`.targets`)
carry a learnable signal at all" (``scripts/train_nn_smoke.py``). A proper
model is future work once that question is settled.
"""

from __future__ import annotations

import torch
from torch import Tensor, nn

from .actions import NUM_GLOBAL_ACTIONS
from .observation import OBS_SIZE


class SmokeNet(nn.Module):
    """``BatchNorm1d -> Linear -> ReLU -> Linear -> ReLU`` trunk with a
    policy head (``NUM_GLOBAL_ACTIONS`` logits) and a value head (4 seats,
    ``tanh``-bounded to match :func:`.targets.value_targets`'s [-1, 1] range).

    ``BatchNorm1d`` on the raw observation stands in for feature
    normalization: most of ``OBS_SIZE``'s int16 features are small-magnitude
    counts/one-hots, and on a small corpus many card-id columns never vary
    (that card never appeared), which would make a precomputed std blow up
    without an epsilon guard. Batch statistics degrade safely on a constant
    column instead. This means ``batch_size`` must be >= 2 in training mode
    and callers must switch to ``eval()`` for validation/inference so the
    layer uses its running statistics rather than per-batch ones.
    """

    def __init__(self, hidden_dim: int = 256) -> None:
        super().__init__()
        self.norm = nn.BatchNorm1d(OBS_SIZE)
        self.trunk = nn.Sequential(
            nn.Linear(OBS_SIZE, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
        )
        self.policy_head = nn.Linear(hidden_dim, NUM_GLOBAL_ACTIONS)
        self.value_head = nn.Linear(hidden_dim, 4)

    def forward(self, obs: Tensor) -> tuple[Tensor, Tensor]:
        features = self.trunk(self.norm(obs))
        policy_logits = self.policy_head(features)
        value = torch.tanh(self.value_head(features))
        return policy_logits, value
