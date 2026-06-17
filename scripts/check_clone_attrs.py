"""Check clone() preserves Python attributes."""
import sys, os
sys.path.insert(0, '.')
import openspiel_pyrants
import pyspiel

game = pyspiel.load_game('python_pyrants_c', {'num_players': '2'})
state = game.new_initial_state()
state.apply_action(42)

c = state.clone()
print(f"clone has _adapter: {hasattr(c, '_adapter')}")
print(f"clone _adapter is None: {c._adapter is None}")
print(f"clone _move_log: {c._move_log}")
print(f"clone _history_actions: {c._history_actions}")
print(f"clone _shuffle_seed: {c._shuffle_seed}")
print(f"clone is_terminal: {c.is_terminal()}")
print(f"clone current_player: {c.current_player()}")
print(f"clone info len: {len(c.information_state_string())}")

# What does IS-MCTS get?
sampler = pyspiel.UniformProbabilitySampler(0., 1.)
r = state.resample_from_infostate(0, sampler)
print(f"\nresampled is_terminal: {r.is_terminal()}")
print(f"resampled current_player: {r.current_player()}")
print(f"resampled info len: {len(r.information_state_string())}")
