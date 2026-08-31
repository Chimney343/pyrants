import os
import sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
for ns in (25,100,400,1600):
    g=load(2); t=time.perf_counter()
    r=play_game(g,[make_bot(g,ns,1),make_bot(g,ns,2)],42)
    dt=time.perf_counter()-t
    print(f"num_sims={ns:5d}  wall={dt:7.2f}s  decisions={r['steps']:4d}  ret={r['returns']}  stopped={r['stopped']}",flush=True)
