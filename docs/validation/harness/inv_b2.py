import os
import sys, json, hashlib, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from scripts._state_snapshot import _tier2_snapshot
def board_fp(st): return hashlib.sha256(json.dumps(_tier2_snapshot(st._adapter),sort_keys=True).encode()).hexdigest()[:16]

# Decisive test: SAME move type, DIFFERENT target site -> board differs.
# Does information_state_string / private_view_json distinguish them?
pairs=0; invisible=0; visible=0; ex=[]
histdiff=0
for sd in range(1,140):
    g=load(2); s=fresh(g,sd); b=RandomBot(sd*17)
    for step in range(300):
        if s.is_terminal() or s.current_player()<0: break
        p=s.current_player(); pid=g.get_player_ids()[p]
        groups={}
        for aid in s.legal_actions():
            mv=s.decode_action(int(aid))
            groups.setdefault(mv.move_type,[]).append(int(aid))
        for mt,aids in groups.items():
            if not any(t in mt.lower() for t in ("troop","spy","place","deploy")): continue
            if len(aids)<2: continue
            for a1,a2 in itertools.combinations(aids[:4],2):
                c1=s.clone(); c1.apply_action(a1)
                c2=s.clone(); c2.apply_action(a2)
                if c1.current_player()<0 or c2.current_player()<0: continue
                if board_fp(c1)==board_fp(c2): continue   # need boards to actually differ
                pairs+=1
                pv1=c1._adapter.private_view_json(pid); pv2=c2._adapter.private_view_json(pid)
                if pv1==pv2:
                    invisible+=1
                    if len(ex)<4: ex.append((sd,step,mt,str(s.decode_action(a1)),str(s.decode_action(a2))))
                else: visible+=1
                if c1.information_state_string(p)!=c2.information_state_string(p): histdiff+=1
            break
        s.apply_action(b.step(s))
        if pairs>=400: break
    if pairs>=400: break
print(f"INV4b-DECISIVE same-move-type/different-site pairs with DIFFERENT board: N={pairs}")
print(f"  private_view_json IDENTICAL (board invisible to observer): {invisible}")
print(f"  private_view_json differs (board visible):                 {visible}")
print(f"  information_state_string differs (any cause incl. history): {histdiff}")
for e in ex: print("   e.g.",e)
