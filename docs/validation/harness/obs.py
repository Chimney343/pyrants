import os
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
def raw(st): return st._adapter._state._s

print("########## OBS-1: is a player's OWN discard-pile content in their information state? ##########")
inv=0; vis=0; N=0
for sd in range(1,120):
    g=load(2); s=fresh(g,sd); b=RandomBot(sd*7)
    for step in range(200):
        if s.is_terminal() or s.current_player()<0: break
        p=s.current_player(); pid=g.get_player_ids()[p]
        r=raw(s); pl=r.players[p]
        if pl.discard_pile_count>=2:
            a=s.clone(); ra=raw(a).players[p]
            x,y=ra.discard_pile[0],ra.discard_pile[1]
            if str(x)!=str(y):
                ra.discard_pile[0],ra.discard_pile[1]=y,x   # permute own discard only
                N+=1
                if s._adapter.private_view_json(pid)==a._adapter.private_view_json(pid): inv+=1
                else: vis+=1
                break
        s.apply_action(b.step(s))
    if N>=200: break
print(f"  N={N} own-discard permutations: information state IDENTICAL (content invisible)={inv}, differs={vis}")

print("\n########## OBS-2: devour pile content? ##########")
pv=None
g=load(2); s=fresh(g,3); b=RandomBot(9)
for _ in range(80):
    if s.is_terminal() or s.current_player()<0: break
    s.apply_action(b.step(s))
pv=json.loads(s._adapter.private_view_json('p1'))
print("  keys exposing identities:", sorted([k for k,v in pv.items() if isinstance(v,list)]))
print("  keys exposing only COUNTS:", sorted([k for k,v in pv.items() if isinstance(v,int)]))

print("\n########## RESOURCE STABILITY: memory + wall vs simulation budget ##########")
import tracemalloc, time, gc
for ns in (25,100,400,1600):
    gc.collect(); tracemalloc.start()
    g=load(2); st=fresh(g,42); bt=RandomBot(1)
    for _ in range(30):
        if st.is_terminal() or st.current_player()<0: break
        st.apply_action(bt.step(st))
    base=tracemalloc.get_traced_memory()[0]
    bot=make_bot(g,ns,7)
    t=time.perf_counter(); bot.step_with_policy(st); dt=time.perf_counter()-t
    cur,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
    print(f"  num_sims={ns:5d}: one search wall={dt:7.3f}s  py_peak_delta={(peak-base)/1024:9.1f} KiB  "
          f"tree_nodes={len(bot._nodes):5d}  node_pool={len(bot._node_pool):5d}")
    gc.collect()
