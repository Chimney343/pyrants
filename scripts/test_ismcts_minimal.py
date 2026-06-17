"""Minimal reproduction of IS-MCTS assertion failure."""
import sys, os
sys.path.insert(0, '.')

import openspiel_pyrants
import pyspiel
import numpy as np
from open_spiel.python.algorithms.ismcts import ISMCTSBot, ISMCTSFinalPolicyType
from open_spiel.python.algorithms.mcts import RandomRolloutEvaluator

game = pyspiel.load_game('python_pyrants_c', {'num_players': '2'})
state = game.new_initial_state()
state.apply_action(42)

print(f"current_player={state.current_player()}")
print(f"legal_actions count={len(state.legal_actions())}")
print(f"infostate[:250]={state.information_state_string()[:250]}")
print(f"infostate chars={len(state.information_state_string())}")

rng = np.random.RandomState(42)
bot = ISMCTSBot(
    game=game,
    evaluator=RandomRolloutEvaluator(n_rollouts=1, random_state=rng),
    uct_c=1.4,
    max_simulations=3,
    max_world_samples=100,
    random_state=rng,
    final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
)

try:
    policy, chosen = bot.step_with_policy(state)
    print(f"SUCCESS: policy len={len(policy)}, chosen={chosen}")
except AssertionError as e:
    print("AssertionError!")
    # Diagnose
    cp = state.current_player()
    root_key = (cp, state.information_state_string(cp))
    
    # First resample (what IS-MCTS does)
    sampler = pyspiel.UniformProbabilitySampler(0., 1.)
    resampled = state.resample_from_infostate(cp, sampler)
    
    # sample_root_state with max_world_samples > 0 does: append resample, return clone
    # Actually, sample_root_state does resample then clone of resample
    # Let's check the intermediate
    resampled_key = (resampled.current_player(), resampled.information_state_string(resampled.current_player()))
    print(f"resampled_key matches root: {root_key == resampled_key}")
    
    if root_key != resampled_key:
        print(f"  cp: {root_key[0]} vs {resampled_key[0]}")
        print(f"  str eq: {root_key[1] == resampled_key[1]}")
    
    # Now check the clone of resampled (what IS-MCTS actually uses)
    double_clone = resampled.clone()
    dc_key = (double_clone.current_player(), double_clone.information_state_string(double_clone.current_player()))
    print(f"double_clone_key matches root: {root_key == dc_key}")
    
    if root_key != dc_key:
        print(f"  cp: {root_key[0]} vs {dc_key[0]}")
        print(f"  str eq: {root_key[1] == dc_key[1]}")
except Exception as e:
    print(f"Other error: {type(e).__name__}: {e}")
