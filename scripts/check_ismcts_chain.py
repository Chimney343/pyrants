"""Exact IS-MCTS sampling chain test."""
import sys, os
sys.path.insert(0, '.')
import openspiel_pyrants
import pyspiel

game = pyspiel.load_game('python_pyrants_c', {'num_players': '2'})
state = game.new_initial_state()
state.apply_action(42)

root_key = (state.current_player(), state.information_state_string())
print(f'Root: cp={root_key[0]}, info_len={len(root_key[1])}')

# IS-MCTS sample_root_state chain (max_world_samples > 0, first call)
sampler = pyspiel.UniformProbabilitySampler(0., 1.)

# Step 1: self.resample_from_infostate(state)
#   -> state.resample_from_infostate(cp, sampler)
#   -> self.clone()
cp = state.current_player()
resampled = state.resample_from_infostate(cp, sampler)
rk = (resampled.current_player(), resampled.information_state_string())
print(f'Resampled: cp={rk[0]}, info_len={len(rk[1])}, match={root_key == rk}')

# Step 2: clone of resampled (self._root_samples[-1].clone())
working = resampled.clone()
wk = (working.current_player(), working.information_state_string())
print(f'Working: cp={wk[0]}, info_len={len(wk[1])}, match={root_key == wk}')

# What about self.get_state_key?
# Bot's get_state_key returns (cp, information_state_string(cp))
# But observation_string might differ from information_state_string
print(f'\nobservation_string len: {len(state.observation_string())}')
print(f'info_state_string len: {len(state.information_state_string())}')
print(f'Same: {state.observation_string() == state.information_state_string()}')

# And for the working state:
print(f'working obs len: {len(working.observation_string())}')
print(f'working obs == working info: {working.observation_string() == working.information_state_string()}')
print(f'working obs == root info: {working.observation_string() == state.information_state_string()}')
