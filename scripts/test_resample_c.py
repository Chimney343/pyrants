"""Test infostate key match between root and resampled states."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import openspiel_pyrants  # registers C game
import pyspiel

game = pyspiel.load_game("python_pyrants_c", {"num_players": "2"})
state = game.new_initial_state()

# Apply chance action
state.apply_action(42)

# Apply a few moves
rng = __import__('numpy').random.RandomState(42)
for step in range(30):
    if state.is_terminal():
        break
    cp = state.current_player()
    if cp < 0:
        break
    legal = state.legal_actions()
    if not legal:
        break
    # Pick a play_card move if available, otherwise first legal
    chosen = legal[0]
    for aid in legal:
        act_str = state.action_to_string(cp, aid)
        if 'play_card' in act_str.lower():
            chosen = aid
            break
    state.apply_action(chosen)
    print(f"Step {step}: phase=unknown cp={cp} applied action={chosen} ({state.action_to_string(cp, chosen)[:60]}...)")

print(f"\nState terminal: {state.is_terminal()}")
if state.is_terminal():
    print(f"Returns: {state.returns()}")

# Now clone and compare infostate
print(f"\n=== Comparing infostate strings ===")
root_key = state.information_state_string()
print(f"Root infostate ({len(root_key)} chars):")
print(root_key[:500])
print("...")

# Clone via resample
import numpy as np
rng2 = np.random.RandomState(123)
sampled = state.resample_from_infostate(0, rng2)
sampled_key = sampled.information_state_string()
print(f"\nSampled infostate ({len(sampled_key)} chars):")
print(sampled_key[:500])
print("...")

if root_key == sampled_key:
    print("\nMATCH!")
else:
    print(f"\nMISMATCH! diff at:")
    for i, (a, b) in enumerate(zip(root_key, sampled_key)):
        if a != b:
            print(f"  pos {i}: {a!r} != {b!r}")
            print(f"  context: ...{root_key[max(0,i-30):i+30]}...")
            print(f"  context: ...{sampled_key[max(0,i-30):i+30]}...")
            break
