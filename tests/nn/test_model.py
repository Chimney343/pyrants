"""SmokeNet shape/range sanity checks — the trainability smoke test's model."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from openspiel_pyrants.nn.actions import NUM_GLOBAL_ACTIONS  # noqa: E402
from openspiel_pyrants.nn.model import SmokeNet  # noqa: E402
from openspiel_pyrants.nn.observation import OBS_SIZE  # noqa: E402


def test_forward_shapes() -> None:
    model = SmokeNet(hidden_dim=16)
    obs = torch.randn(4, OBS_SIZE)
    policy_logits, value = model(obs)
    assert policy_logits.shape == (4, NUM_GLOBAL_ACTIONS)
    assert value.shape == (4, 4)


def test_value_output_bounded() -> None:
    model = SmokeNet(hidden_dim=16)
    obs = torch.randn(8, OBS_SIZE) * 1000  # large magnitudes to stress tanh bound
    _, value = model(obs)
    assert torch.all(value >= -1.0) and torch.all(value <= 1.0)


def test_tolerates_batch_size_two() -> None:
    """BatchNorm1d's training-mode floor."""
    model = SmokeNet(hidden_dim=8)
    obs = torch.randn(2, OBS_SIZE)
    policy_logits, value = model(obs)
    assert policy_logits.shape == (2, NUM_GLOBAL_ACTIONS)
    assert value.shape == (2, 4)


def test_eval_mode_accepts_batch_size_one() -> None:
    """In eval mode BatchNorm1d uses running stats, so batch size 1 is fine."""
    model = SmokeNet(hidden_dim=8)
    model.eval()
    obs = torch.randn(1, OBS_SIZE)
    with torch.no_grad():
        policy_logits, value = model(obs)
    assert policy_logits.shape == (1, NUM_GLOBAL_ACTIONS)
    assert value.shape == (1, 4)
