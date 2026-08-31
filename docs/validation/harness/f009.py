import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import pyspiel
print("########## F-009 ##########")
for cnt in (1000, 5000, 250):
    g=pyspiel.load_game("python_pyrants_c",{"num_players":"2","shuffle_seed_count":cnt})
    s=g.new_initial_state()
    n=len(s.chance_outcomes())
    print(f"  shuffle_seed_count={cnt:5d} -> len(chance_outcomes())={n:5d}  "
          f"game.max_chance_outcomes()={g.max_chance_outcomes():5d}  "
          f"len(legal_actions())={len(s.legal_actions()):5d}  "
          f"CONSISTENT={n==g.max_chance_outcomes()}")
    # is an out-of-declared-range action actually applyable?
    if n > g.max_chance_outcomes():
        try:
            s2=g.new_initial_state(); s2.apply_action(n-1)
            print(f"     applying outcome id {n-1} (>= max_chance_outcomes) SUCCEEDED -> {str(s2)[:60]!r}")
        except Exception as e:
            print(f"     applying outcome id {n-1} raised {type(e).__name__}: {e}")
