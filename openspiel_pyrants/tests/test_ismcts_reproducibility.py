"""IS-MCTS reproducibility tests for F-010.

Locks in the fix that makes IS-MCTS determinization reproducible from ``--seed``.

F-010: the stock ``ISMCTSBot`` resampler draws its determinization seed from an
unseeded ``pyspiel.UniformProbabilitySampler``, so two identically-seeded runs
diverge. The fix is (a) a factory (``make_ismcts_bot``) that always installs a
seeded resampler, and (b) a guard in ``PyrantsCState.resample_from_infostate``
that rejects a bare callable so the defective path can never be reached silently.

See ``docs/validation/f010-fix-plan.md``. T1/T5/T6 are controls: they pass both
before and after the fix and guard against over-fixing (world collapse).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_c_game(num_players: int = 2):
    return pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})


def _mid_game_state(game, shuffle_seed=42, n_moves=40):
    """A state a few plies past the initial chance node, with a live adapter."""
    state = game.new_initial_state()
    state.apply_action(shuffle_seed)
    rng = np.random.RandomState(shuffle_seed)
    for _ in range(n_moves):
        if state.is_terminal():
            break
        cp = state.current_player()
        if cp < 0:
            break
        legal = state.legal_actions()
        if not legal:
            break
        state.apply_action(int(rng.choice(legal)))
    return state


def _omniscient_fingerprint(state) -> str:
    """Fingerprint that reveals hidden-zone contents across every player.

    The public/infostate view is identical across determinizations of one info
    set (that is the point), so an omniscient fingerprint — every player's
    private view plus the public dict — is required to observe that two
    determinizations landed in different worlds.
    """
    parts = []
    for pid in state._game.get_player_ids():
        parts.append(state._adapter.private_view_json(pid))
    parts.append(json.dumps(state._adapter._build_public_dict(), sort_keys=True))
    parts.append("|".join(str(m) for m in state._adapter.legal_moves()))
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _play_with_bots(game, bots, shuffle_seed):
    state = game.new_initial_state()
    state.apply_action(shuffle_seed)
    actions = []
    n = game.num_players()
    while not state.is_terminal():
        cp = state.current_player()
        if cp < 0 or cp >= n:
            break
        _, a = bots[cp].step_with_policy(state)
        actions.append(int(a))
        state.apply_action(int(a))
    return actions, state.returns()


@pytest.mark.skipif(
    os.environ.get("PYRANTS_SKIP_ISMCTS") == "1",
    reason="PYRANTS_SKIP_ISMCTS=1 set",
)
class TestISMCTSReproducibility:
    def test_resample_with_random_state_is_deterministic(self, requires_c_engine):
        """T1 — control: the seeded-numpy branch was always reproducible."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        p = state.current_player()
        if p < 0:
            pytest.skip("game ended early")
        fps = {
            _omniscient_fingerprint(state.resample_from_infostate(p, np.random.RandomState(123)))
            for _ in range(5)
        }
        assert len(fps) == 1

    def test_unseeded_sampler_is_rejected(self, requires_c_engine):
        """T2 — a bare callable sampler must not be able to reach determinize()."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        p = state.current_player()
        if p < 0:
            pytest.skip("game ended early")
        with pytest.raises(TypeError):
            state.resample_from_infostate(p, pyspiel.UniformProbabilitySampler(0.0, 1.0))

    def test_search_reproducible_from_fixed_root(self, requires_c_engine):
        """T3 — identically-seeded bots on one root give identical action + policy."""
        from open_spiel.python.algorithms.ismcts import ISMCTSFinalPolicyType

        from openspiel_pyrants import make_ismcts_bot
        from openspiel_pyrants.c_rollout_evaluator import CRolloutEvaluator

        game = _load_c_game(2)
        root = _mid_game_state(game)
        if root.current_player() < 0:
            pytest.skip("game ended early")

        results = []
        for _ in range(5):
            bot = make_ismcts_bot(
                game=game,
                seed=4242,
                num_sims=8,
                uct_c=1.4,
                max_world_samples=-1,
                final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
                evaluator=CRolloutEvaluator(
                    max_length=0, random_state=np.random.RandomState(4242)
                ),
            )
            policy, chosen = bot.step_with_policy(root.clone())
            results.append(
                (
                    int(chosen),
                    tuple(sorted((int(a), round(float(p), 6)) for a, p in policy)),
                )
            )
        assert len(set(results)) == 1, f"distinct (chosen, policy) pairs: {len(set(results))}"

    def test_full_game_replay_is_deterministic(self, requires_c_engine):
        """T4 — same seed, two full games, identical action sequence and returns."""
        from open_spiel.python.algorithms.ismcts import ISMCTSFinalPolicyType

        from openspiel_pyrants import make_ismcts_bot
        from openspiel_pyrants.c_rollout_evaluator import CRolloutEvaluator

        def build_bots(game, seed):
            return [
                make_ismcts_bot(
                    game=game,
                    seed=seed + i,
                    num_sims=8,
                    uct_c=1.4,
                    max_world_samples=-1,
                    final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
                    evaluator=CRolloutEvaluator(
                        max_length=0, random_state=np.random.RandomState(seed + i)
                    ),
                )
                for i in range(2)
            ]

        for sd in range(1, 6):
            game = _load_c_game(2)
            acts1, ret1 = _play_with_bots(game, build_bots(game, 1000 + sd), sd)
            game2 = _load_c_game(2)
            acts2, ret2 = _play_with_bots(game2, build_bots(game2, 1000 + sd), sd)
            assert acts1 == acts2, f"seed {sd}: action sequences differ"
            assert ret1 == ret2, f"seed {sd}: returns differ"

    def test_different_seeds_diverge(self, requires_c_engine):
        """T5 — anti-over-fix: distinct seeds must still produce distinct games."""
        from open_spiel.python.algorithms.ismcts import ISMCTSFinalPolicyType

        from openspiel_pyrants import make_ismcts_bot
        from openspiel_pyrants.c_rollout_evaluator import CRolloutEvaluator

        def build_bots(game, seed):
            return [
                make_ismcts_bot(
                    game=game,
                    seed=seed + i,
                    num_sims=8,
                    uct_c=1.4,
                    max_world_samples=-1,
                    final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
                    evaluator=CRolloutEvaluator(
                        max_length=0, random_state=np.random.RandomState(seed + i)
                    ),
                )
                for i in range(2)
            ]

        acts_a, _ = _play_with_bots(
            _load_c_game(2), build_bots(_load_c_game(2), 1000), 42
        )
        acts_b, _ = _play_with_bots(
            _load_c_game(2), build_bots(_load_c_game(2), 2000), 42
        )
        assert acts_a != acts_b

    def test_determinizations_remain_diverse(self, requires_c_engine):
        """T6 — gate G2: world diversity must not collapse under the fix."""
        game = _load_c_game(2)
        state = game.new_initial_state()
        state.apply_action(42)
        rng = np.random.RandomState(7)

        distinct_counts = []
        for step in range(200):
            if state.is_terminal():
                break
            cp = state.current_player()
            if cp < 0:
                break
            if step % 6 == 5:  # probe an info set every 6 steps
                fps = {
                    _omniscient_fingerprint(
                        state.resample_from_infostate(cp, np.random.RandomState(1000 + k))
                    )
                    for k in range(12)
                }
                distinct_counts.append(len(fps))
                if len(distinct_counts) >= 8:
                    break
            state.apply_action(int(rng.choice(state.legal_actions())))

        assert len(distinct_counts) >= 3, "not enough info sets probed"
        mean = sum(distinct_counts) / len(distinct_counts)
        assert mean >= 8.0, f"mean distinct worlds {mean:.2f} < 8"
        assert all(c > 1 for c in distinct_counts), (
            f"singleton info sets present: {distinct_counts}"
        )

    def test_cli_run_is_reproducible(self, requires_c_engine, tmp_path):
        """T7 — end-to-end: same --seed into two dirs reproduces decisions + outcome."""
        import csv

        def run_once(out_dir):
            cmd = [
                sys.executable,
                "-m",
                "scripts.run_ismcts",
                "--num-sims",
                "8",
                "--num-games",
                "1",
                "--seed",
                "4242",
                "--num-players",
                "2",
                "--workers",
                "1",
                "--game",
                "python_pyrants_c",
                "--output-dir",
                str(out_dir),
                "--no-plots",
            ]
            subprocess.run(
                cmd,
                cwd=str(_REPO_ROOT),
                check=True,
                capture_output=True,
                text=True,
                timeout=1800,
            )
            decisions_path = out_dir / "game_0000" / "decisions.jsonl"
            chosen = [
                json.loads(line)["chosen_action_id"]
                for line in decisions_path.open(encoding="utf-8")
            ]
            with (out_dir / "summary.csv").open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            outcome = [row["outcome"] for row in rows]
            return chosen, outcome

        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        chosen1, outcome1 = run_once(d1)
        chosen2, outcome2 = run_once(d2)
        assert chosen1 == chosen2
        assert outcome1 == outcome2
