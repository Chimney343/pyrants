import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

def raw(st): return st._adapter._state._s

# GB1: every shuffle_counter advance must be preceded by is_chance_node()==True.
# Mirrors findings.py's F-003 loop, re-run at gate N >= 2000 transitions.
adv = 0; adv_at_chance = 0; tot3 = 0
sd = 0
while tot3 < 2000 and sd < 200:
    sd += 1
    g = load(2); s = fresh(g, sd); b = RandomBot(sd * 9)
    for step in range(300):
        if s.is_terminal() or s.current_player() < 0: break
        pre = raw(s).shuffle_counter; was_chance = s.is_chance_node()
        s.apply_action(b.step(s))
        if s._adapter is None: continue
        post = raw(s).shuffle_counter; tot3 += 1
        if post != pre:
            adv += 1
            if was_chance: adv_at_chance += 1
print(f"GB1: N transitions={tot3}  shuffle_counter advanced on {adv} of them")
print(f"  of those advances, preceded by is_chance_node()==True: {adv_at_chance}")
print(f"  RESULT: {'PASS' if adv == adv_at_chance else 'FAIL'} (need 100% preceded, got {adv_at_chance}/{adv})")
