"""Compare infostate strings to find the 4-char difference."""
import sys, os, copy
sys.path.insert(0, '.')
import openspiel_pyrants
import pyspiel

game = pyspiel.load_game('python_pyrants_c', {'num_players': '2'})
state = game.new_initial_state()
state.apply_action(42)

# Compare clone() vs deepcopy() infostates
c = state.clone()
dc = copy.deepcopy(state)

root_info = state.information_state_string()
clone_info = c.information_state_string()
dc_info = dc.information_state_string()

print(f'root:   {len(root_info)} chars')
print(f'clone:  {len(clone_info)} chars, match={root_info == clone_info}')
print(f'dc:     {len(dc_info)} chars, match={root_info == dc_info}')

# Find 4-char diff
print(f'\nRoot repr: {root_info!r}')
print(f'\nClone repr: {clone_info!r}')
print(f'\nDC repr: {dc_info!r}')

# Find diff position
for i in range(max(len(root_info), len(dc_info))):
    rc = root_info[i] if i < len(root_info) else '<EOF>'
    dc = dc_info[i] if i < len(dc_info) else '<EOF>'
    if rc != dc:
        print(f'First diff at pos {i}: root[{i}]={rc!r} dc[{i}]={dc!r}')
        print(f'Root context: ...{root_info[max(0,i-30):i+30]}...')
        print(f'DC context:   ...{dc_info[max(0,i-30):i+30]}...')
        break
