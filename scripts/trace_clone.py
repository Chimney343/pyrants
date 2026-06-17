"""Trace exact clone() behavior."""
import sys, os
sys.path.insert(0, '.')
import openspiel_pyrants
import pyspiel
import copy

game = pyspiel.load_game('python_pyrants_c', {'num_players': '2'})
state = game.new_initial_state()
state.apply_action(42)

# Check what clone() actually does
original_clone = state.clone  # bound method

# Monkey-patch clone to trace
import types
real_clone = type(state).clone

def traced_clone(self):
    print(f'  clone() called on state with infostate_len={len(self.information_state_string())}')
    result = real_clone(self)
    print(f'  clone() returned state with infostate_len={len(result.information_state_string())}')
    print(f'  returned cp={result.current_player()}')
    return result

type(state).clone = traced_clone

# Now run resample_from_infostate
sampler = pyspiel.UniformProbabilitySampler(0., 1.)
cp = state.current_player()
print(f'Calling resample_from_infostate(cp={cp})')
resampled = state.resample_from_infostate(cp, sampler)
print(f'Resampled: cp={resampled.current_player()}, info_len={len(resampled.information_state_string())}')

# Now trace deepcopy
print(f'\nTracing deepcopy:')
real_deepcopy = type(state).__deepcopy__
def traced_deepcopy(self, memo):
    print(f'  __deepcopy__ called on state with infostate_len={len(self.information_state_string())}')
    result = real_deepcopy(self, memo)
    print(f'  __deepcopy__ returned state with infostate_len={len(result.information_state_string())}')
    return result
type(state).__deepcopy__ = traced_deepcopy

dc = copy.deepcopy(state)
print(f'Deepcopy result: cp={dc.current_player()}, info_len={len(dc.information_state_string())}')
