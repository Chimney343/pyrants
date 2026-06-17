"""Deep trace of IS-MCTS run_search to find where root_samples become terminal."""
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

# Monkey-patch sample_root_state to trace
real_sample = bot.sample_root_state
def traced_sample(s):
    result = real_sample(s)
    print(f"  sample_root_state: len(root_samples)={len(bot._root_samples)}")
    if len(bot._root_samples) > 0:
        last = bot._root_samples[-1]
        print(f"    last in samples: cp={last.current_player()}, term={last.is_terminal()}")
    print(f"    result: cp={result.current_player()}, info_len={len(result.information_state_string())}, term={result.is_terminal()}")
    return result
bot.sample_root_state = traced_sample

# Monkey-patch run_simulation
real_sim = bot.run_simulation
def traced_sim(sampled_state):
    print(f"  run_simulation: cp={sampled_state.current_player()}, term={sampled_state.is_terminal()}")
    return real_sim(sampled_state)
bot.run_simulation = traced_sim

# Monkey-patch resample_from_infostate
real_resample = bot.resample_from_infostate
def traced_resample(s):
    result = real_resample(s)
    print(f"  resample_from_infostate: result cp={result.current_player()}, term={result.is_terminal()}")
    return result
bot.resample_from_infostate = traced_resample

# Also trace state.resample_from_infostate
real_state_resample = type(state).resample_from_infostate
def traced_state_resample(self, player, rng):
    result = real_state_resample(self, player, rng)
    print(f"  state.resample: result cp={result.current_player()}, term={result.is_terminal()}")
    return result
type(state).resample_from_infostate = traced_state_resample

print("Calling run_search...")
try:
    result = bot.run_search(state)
    print(f"SUCCESS")
except AssertionError:
    print(f"FAILED")
    print(f"\n_root_samples contents:")
    for i, rs in enumerate(bot._root_samples):
        print(f"  [{i}]: cp={rs.current_player()}, term={rs.is_terminal()}, info_len={len(rs.information_state_string())}")
