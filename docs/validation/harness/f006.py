import os
import sys, math, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
# Quantify: is uct_c=1.4 on the same scale as this game's Q-values?
qspread=[]; expl=[]; N=0
for sd in range(1,40):
    g=load(2); s=fresh(g,sd); b=RandomBot(sd*3)
    for _ in range(35):
        if s.is_terminal() or s.current_player()<0: break
        s.apply_action(b.step(s))
    if s.is_terminal() or s.current_player()<0: continue
    if len(s.legal_actions())<2: continue
    bot=make_bot(g,200,sd)
    bot.step_with_policy(s.clone())
    if not hasattr(bot,'_root_node'): continue
    node=bot._root_node
    vals=[c.return_sum/c.visits for c in node.child_info.values() if c.visits>0]
    if len(vals)<2: continue
    N+=1
    qspread.append(max(vals)-min(vals))
    tv=node.total_visits
    expl.append(statistics.mean(1.4*math.sqrt(math.log(tv)/c.visits)
                                for c in node.child_info.values() if c.visits>0))
print(f"N={N} root nodes (num_sims=200, uct_c=1.4)")
print(f"  Q-value spread (max-min child value): mean={statistics.mean(qspread):.2f} median={statistics.median(qspread):.2f} max={max(qspread):.2f}")
print(f"  UCT exploration bonus 1.4*sqrt(ln N/n): mean={statistics.mean(expl):.3f}")
print(f"  ratio exploitation:exploration = {statistics.mean(qspread)/statistics.mean(expl):.1f} : 1")
print(f"  uct_c that would equalise them  = {1.4*statistics.mean(qspread)/statistics.mean(expl):.1f}")
print(f"  paper's calibrated c = 0.7 (rewards normalised to +/-1); this game's rewards are raw VP differentials")
