import os
import sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import pyspiel
def raw(st): return st._adapter._state._s

print("########## F-002b reshuffle permutation is a pure fn of (shuffle_seed, shuffle_counter) ##########")
# Build a state, clone it twice, force IDENTICAL discard contents + empty deck in both,
# then drive draws until a reshuffle fires; compare resulting deck order.
def setup_reshuffle(sd, counter_override=None, seed_override=None):
    g=load(2); s=fresh(g,sd); b=RandomBot(sd*3)
    for _ in range(60):
        if s.is_terminal() or s.current_player()<0: break
        s.apply_action(b.step(s))
    if s.is_terminal() or s.current_player()<0: return None
    c=s.clone(); r=raw(c); p=r.players[0]
    # force a deterministic, identical discard pile and empty deck
    pool=[p.discard_pile[i] for i in range(p.discard_pile_count)]
    pool+=[p.deck[i] for i in range(p.deck_count)]
    pool+=[p.hand[i] for i in range(p.hand_count)]
    if len(pool)<6: return None
    pool=pool[:8]
    for i,sym in enumerate(pool): p.discard_pile[i]=sym
    p.discard_pile_count=len(pool); p.deck_count=0
    if counter_override is not None: r.shuffle_counter=counter_override
    if seed_override is not None: r.shuffle_seed=seed_override
    return c,g,pool

def force_draw_order(c):
    """Trigger the reshuffle by playing on; return deck order right after refill."""
    r=raw(c); p=r.players[0]
    b=RandomBot(4242)
    for _ in range(200):
        if c.is_terminal() or c.current_player()<0: break
        c.apply_action(b.step(c))
        p=raw(c).players[0]
        if p.deck_count>0 and p.discard_pile_count==0:
            return [str(p.deck[i]) for i in range(p.deck_count)]
    return None

rows=[]
for sd in (3,5,11):
    a=setup_reshuffle(sd); 
    if not a: continue
    c1,_,pool1=a
    a2=setup_reshuffle(sd)
    c2,_,pool2=a2
    a3=setup_reshuffle(sd, counter_override=raw(c1).shuffle_counter+1)
    c3,_,_=a3
    a4=setup_reshuffle(sd, seed_override=raw(c1).shuffle_seed ^ 0xDEADBEEF)
    c4,_,_=a4
    o1,o2,o3,o4=force_draw_order(c1),force_draw_order(c2),force_draw_order(c3),force_draw_order(c4)
    if o1 is None or o2 is None: continue
    rows.append((sd,o1==o2, None if o3 is None else o1==o3, None if o4 is None else o1==o4))
    print(f"  seed{sd}: same(seed,counter,contents) -> identical deck order: {o1==o2}"
          f" | counter+1 -> identical: {None if o3 is None else o1==o3}"
          f" | seed^const -> identical: {None if o4 is None else o1==o4}")
print(f"  N={len(rows)} controlled reshuffles")

print("\n########## F-009 max_chance_outcomes vs shuffle_seed_count (int params) ##########")
for cnt in (1000,5000):
    try:
        g=pyspiel.load_game("python_pyrants_c",{"num_players":pyspiel.GameParameter(2),
                                                "shuffle_seed_count":pyspiel.GameParameter(cnt)})
    except Exception:
        g=pyspiel.load_game(f"python_pyrants_c(num_players=2,shuffle_seed_count={cnt})")
    s=g.new_initial_state()
    print(f"  shuffle_seed_count={cnt}: len(chance_outcomes())={len(s.chance_outcomes())}"
          f"  game.max_chance_outcomes()={g.max_chance_outcomes()}"
          f"  legal_actions={len(s.legal_actions())}")

print("\n########## F-008 observed chance-node branching factor ##########")
g=load(2); s=g.new_initial_state()
print(f"  the ONE exposed chance node: len(chance_outcomes())={len(s.chance_outcomes())} (paper assumes <=4)")
