"""Check MRO and find clone() definition."""
import sys, os
sys.path.insert(0, '.')
import openspiel_pyrants
import pyspiel

game = pyspiel.load_game('python_pyrants_c', {'num_players': '2'})
state = game.new_initial_state()
state.apply_action(42)

print("MRO:")
for cls in type(state).__mro__:
    print(f"  {cls.__module__}.{cls.__qualname__}")

# Find where clone() is defined
for cls in type(state).__mro__:
    if 'clone' in cls.__dict__:
        print(f"\nclone() defined in: {cls.__module__}.{cls.__qualname__}")
        import inspect
        try:
            print(inspect.getsource(cls.clone))
        except:
            print("  (C++ method, source unavailable)")
