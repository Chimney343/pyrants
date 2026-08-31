import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

print("=== L1: pure engine, fixed action-index sequence, 2 replays ===")
fails=0
for sd in range(1,11):
    g=load(2); s=fresh(g,sd)
    seq=[]; b=RandomBot(sd)
    for _ in range(120):
        if s.is_terminal() or s.current_player()<0: break
        a=b.step(s); seq.append(a); s.apply_action(a)
    fpA=fp_hash(s)
    g2=load(2); s2=fresh(g2,sd)
    for a in seq:
        if s2.is_terminal() or s2.current_player()<0: break
        if a not in s2.legal_actions():
            print(f"  seed{sd}: action {a} illegal on replay at step {seq.index(a)}"); break
        s2.apply_action(a)
    fpB=fp_hash(s2)
    if fpA!=fpB: fails+=1; print(f"  seed{sd}: FP DIFFER {fpA} vs {fpB} len={len(seq)}")
print(f"L1 engine replay: {'PASS' if fails==0 else f'FAIL {fails}/10'}  N=10")

print("=== L2: RandomBot self-play, same seeds, 2 runs ===")
fails=0
for sd in range(1,11):
    g=load(2); r1=play_game(g,[RandomBot(100+sd),RandomBot(200+sd)],sd,record_actions=True)
    g2=load(2); r2=play_game(g2,[RandomBot(100+sd),RandomBot(200+sd)],sd,record_actions=True)
    if [a[1] for a in r1["actions"]]!=[a[1] for a in r2["actions"]] or r1["returns"]!=r2["returns"]:
        fails+=1; print(f"  seed{sd}: n1={r1['steps']} n2={r2['steps']} ret {r1['returns']} vs {r2['returns']}")
print(f"L2 RandomBot replay: {'PASS' if fails==0 else f'FAIL {fails}/10'}  N=10")

print("=== L3: ISMCTS random-py evaluator, same seeds, 2 runs ===")
fails=0
for sd in range(1,6):
    g=load(2); r1=play_game(g,[make_bot(g,20,1000+sd,evaluator="random-py"),make_bot(g,20,2000+sd,evaluator="random-py")],sd,record_actions=True)
    g2=load(2); r2=play_game(g2,[make_bot(g2,20,1000+sd,evaluator="random-py"),make_bot(g2,20,2000+sd,evaluator="random-py")],sd,record_actions=True)
    if [a[1] for a in r1["actions"]]!=[a[1] for a in r2["actions"]] or r1["returns"]!=r2["returns"]:
        fails+=1; print(f"  seed{sd}: n1={r1['steps']} n2={r2['steps']} ret {r1['returns']} vs {r2['returns']}")
print(f"L3 ISMCTS(random-py) replay: {'PASS' if fails==0 else f'FAIL {fails}/5'}  N=5")

print("=== L4: adapter.random_rollout determinism, same seed same state ===")
g=load(2); s=fresh(g,7)
b=RandomBot(7)
for _ in range(40):
    if s.is_terminal() or s.current_player()<0: break
    s.apply_action(b.step(s))
outs=[s._adapter.random_rollout(12345,0) for _ in range(8)]
uniq={repr(o) for o in outs}
print(f"L4 random_rollout(seed=12345) x8 on one state -> {len(uniq)} distinct results  N=8")
for o in list(uniq)[:3]: print("   ",o)

print("=== L5: CRolloutEvaluator.evaluate determinism, fresh RandomState each time ===")
from openspiel_pyrants.c_rollout_evaluator import CRolloutEvaluator
vals=[]
for _ in range(8):
    ev=CRolloutEvaluator(max_length=0,random_state=np.random.RandomState(99))
    vals.append(tuple(ev.evaluate(s)))
print(f"L5 evaluate() x8 with identical RandomState(99) -> {len(set(vals))} distinct: {set(list(vals)[:4])}  N=8")
