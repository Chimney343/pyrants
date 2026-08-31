import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
def raw(st): return st._adapter._state._s

def prep(sd, steps, counter_delta=0, seed_xor=0):
    """Mid-game state; empty every player's deck and install a fixed discard pile,
    so the next draw MUST reshuffle. Optionally perturb shuffle_seed/counter."""
    g=load(2); s=fresh(g,sd); b=RandomBot(sd*3)
    for _ in range(steps):
        if s.is_terminal() or s.current_player()<0: break
        s.apply_action(b.step(s))
    if s.is_terminal() or s.current_player()<0: return None
    c=s.clone(); r=raw(c)
    for pi in range(r.player_count):
        p=r.players[pi]
        pool=[p.discard_pile[i] for i in range(p.discard_pile_count)]+[p.deck[i] for i in range(p.deck_count)]
        if len(pool)<6: return None
        pool=pool[:8]
        for i,sym in enumerate(pool): p.discard_pile[i]=sym
        p.discard_pile_count=len(pool); p.deck_count=0
    r.shuffle_counter=r.shuffle_counter+counter_delta
    if seed_xor: r.shuffle_seed=r.shuffle_seed ^ seed_xor
    return c

def first_reshuffle_deck(c):
    """Step with a FIXED policy until shuffle_counter increments; return deck order."""
    b=RandomBot(4242); prev=raw(c).shuffle_counter
    for _ in range(300):
        if c.is_terminal() or c.current_player()<0: return None
        c.apply_action(b.step(c))
        if c._adapter is None: return None
        r=raw(c)
        if r.shuffle_counter!=prev:
            out=[]
            for pi in range(r.player_count):
                p=r.players[pi]
                out.append([str(p.deck[i]) for i in range(p.deck_count)])
            return (r.shuffle_counter, out)
    return None

rows=[]
for sd in (3,5,11,17,23,29,31,37):
  for steps in (40,60):
    base=prep(sd,steps); 
    if base is None: continue
    dup =prep(sd,steps)
    cplus=prep(sd,steps,counter_delta=1)
    sxor =prep(sd,steps,seed_xor=0xDEADBEEF)
    o1=first_reshuffle_deck(base); o2=first_reshuffle_deck(dup)
    o3=first_reshuffle_deck(cplus); o4=first_reshuffle_deck(sxor)
    if o1 is None or o2 is None: continue
    same_dup = (o1[1]==o2[1])
    same_cnt = None if o3 is None else (o1[1]==o3[1])
    same_sed = None if o4 is None else (o1[1]==o4[1])
    rows.append((same_dup,same_cnt,same_sed))
    print(f"  seed{sd} steps{steps}: identical(seed,counter,contents)->same deck order: {same_dup}"
          f" | counter+1 -> same: {same_cnt} | seed^const -> same: {same_sed}")
n=len(rows)
print(f"\n  N={n} controlled reshuffles")
print(f"  same (seed,counter,contents) -> identical permutation: {sum(1 for r in rows if r[0])}/{n}")
cn=[r for r in rows if r[1] is not None]
print(f"  shuffle_counter+1 -> permutation CHANGED: {sum(1 for r in cn if not r[1])}/{len(cn)}")
sn=[r for r in rows if r[2] is not None]
print(f"  shuffle_seed^const -> permutation CHANGED: {sum(1 for r in sn if not r[2])}/{len(sn)}")
