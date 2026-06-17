"""Check state.clone() behavior."""
import sys, os
sys.path.insert(0, '.')
import openspiel_pyrants
import pyspiel
import copy

game = pyspiel.load_game('python_pyrants_c', {'num_players': '2'})
state = game.new_initial_state()
state.apply_action(42)

print(f'type(state): {type(state)}')
print(f'clone method: {type(state).clone}')

c1 = state.clone()
c2 = copy.deepcopy(state)
print(f'clone() type: {type(c1)}')
print(f'deepcopy() type: {type(c2)}')

# Compare keys
root_key = (state.current_player(), state.information_state_string())
c1_key = (c1.current_player(), c1.information_state_string())
c2_key = (c2.current_player(), c2.information_state_string())

print(f'Root key len: {len(root_key[1])}')
print(f'clone() key len: {len(c1_key[1])}')
print(f'deepcopy() key len: {len(c2_key[1])}')
print(f'clone() matches root: {root_key == c1_key}')
print(f'deepcopy() matches root: {root_key == c2_key}')
