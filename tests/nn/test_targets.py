"""T3.12-T3.14 — value/policy targets and sample weights."""

from __future__ import annotations

import numpy as np
import pytest

from openspiel_pyrants.nn.targets import (
    merge_duplicates,
    policy_target,
    sample_weight,
    value_targets,
)


def test_value_targets() -> None:
    v = value_targets([100, 60], 2)
    assert v.shape == (4,)
    assert v[0] == pytest.approx(np.tanh((100 - 60) / 40))
    assert v[1] == pytest.approx(-v[0])
    assert v[2] == 0.0 and v[3] == 0.0

    # Antisymmetry in both argument orders.
    a, b = 120, 40
    fwd = value_targets([a, b], 2)
    rev = value_targets([b, a], 2)
    assert fwd[0] == -rev[0]

    # 3-4 players: clip((s - mean(others))/40), absent seats zero.
    scores = [30, 10, 50, 0]
    v4 = value_targets(scores, 4)
    for i in range(4):
        others = [scores[j] for j in range(4) if j != i]
        expected = np.clip((scores[i] - np.mean(others)) / 40, -1.0, 1.0)
        assert v4[i] == pytest.approx(expected, abs=1e-6)

    v3 = value_targets([30, 10, 50], 3)
    assert v3[3] == 0.0


def test_policy_target_and_legal_mask() -> None:
    # Two legal ids mapping to one global id sum their visits and weight the Q.
    order, visits, weighted_q = merge_duplicates([5, 5, 7], [2, 3, 5], [1.0, -1.0, 0.5])
    assert order == [5, 7]
    assert visits == [5.0, 5.0]
    assert weighted_q[5] == (1.0 * 2 + -1.0 * 3) / 5
    assert weighted_q[7] == 0.5

    target = policy_target([5, 5, 7], [2, 3, 5], num_actions=16)
    assert target.sum() == 1.0
    assert target[5] == 0.5
    assert target[7] == 0.5
    assert np.count_nonzero(target) == 2

    # Zero visits -> all zeros, not a division by zero.
    zero = policy_target([1, 2], [0, 0], num_actions=16)
    assert zero.sum() == 0.0


def test_sample_weight_monotone_in_sims() -> None:
    assert sample_weight(50) < sample_weight(100) < sample_weight(200)
    assert sample_weight(200) <= sample_weight(400)
    assert sample_weight(0) == 0.0
