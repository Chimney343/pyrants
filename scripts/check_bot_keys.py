"""Check bot.get_state_key specifically."""
import sys, os
sys.path.insert(0, '.')
import openspiel_pyrants
import pyspiel
from open_spiel.python.algorithms.ismcts import ISMCTSBot, ISMCTSFinalPolicyType
from open_spiel.python.algorithms.mcts import RandomRolloutEvaluator
import numpy as np

game = pyspiel.load_game('python_pyrants_c', {'num_players': '2'})
state = game.new_initial_state()
state.apply_action(42)

rng = np.random.RandomState(42)
bot = ISMCTSBot(
    game=game,
    evaluator=RandomRolloutEvaluator(n_rollouts=1, random_state=rng),
    uct_c=1.4,
    max_simulations=3,
    max_world_samples=100,  # same as run_ismcts default? No, run_ismcts uses 1000
    random_state=rng,
    final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
)

# What bot.get_state_key returns
root_key = bot.get_state_key(state)
print(f'bot.get_state_key(root): cp={root_key[0]}, len={len(root_key[1])}')

# What sample_root_state produces (manually replicate)
sampler = pyspiel.UniformProbabilitySampler(0., 1.)
cp = state.current_player()
resampled = state.resample_from_infostate(cp, sampler)
working = resampled.clone()
wk = bot.get_state_key(working)
print(f'bot.get_state_key(working): cp={wk[0]}, len={len(wk[1])}')
print(f'Match: {root_key == wk}')

# Check the bot's internal methods
print(f'\nbot._use_observation_string: {bot._use_observation_string}')
print(f'bot._resampler_cb: {bot._resampler_cb}')
print(f'bot._max_world_samples: {bot._max_world_samples}')
print(f'len(bot._root_samples): {len(bot._root_samples)}')

# Manually call sample_root_state
sampled = bot.sample_root_state(state)
sk = bot.get_state_key(sampled)
print(f'\nAfter sample_root_state:')
print(f'sampled_key: cp={sk[0]}, len={len(sk[1])}')
print(f'Match with root: {root_key == sk}')

# Try run_search directly
bot.reset()
try:
    result = bot.run_search(state)
    print(f'run_search SUCCESS')
except AssertionError:
    print(f'run_search FAILED with AssertionError')
    # Let's check what happened
    print(f'  root_samples after failure: {len(bot._root_samples)}')
    if len(bot._root_samples) > 0:
        for i, rs in enumerate(bot._root_samples):
            rk2 = bot.get_state_key(rs)
            print(f'  root_samples[{i}]: cp={rk2[0]}, len={len(rk2[1])}, match={root_key == rk2}')
