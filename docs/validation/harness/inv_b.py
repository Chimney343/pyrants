import os
import sys, json, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from scripts._state_snapshot import _tier2_snapshot

def board_fp(st):
    return hashlib.sha256(json.dumps(_tier2_snapshot(st._adapter),sort_keys=True).encode()).hexdigest()[:16]

def sample_states(nseeds, every, cap):
    out=[]
    for sd in range(1,nseeds+1):
        g=load(2); s=fresh(g,sd); b=RandomBot(sd*31)
        for step in range(400):
            if s.is_terminal() or s.current_player()<0: break
            if step%every==every-1: out.append((sd,step,s.clone(),g))
            s.apply_action(b.step(s))
            if len(out)>=cap: return out
    return out

S = sample_states(90, 7, 1000)
print(f"sampled {len(S)} mid-game states")

# ---- INV4a: hidden-info differences must NOT change InformationStateString(p) ----
leak=0; N4a=0; ex=[]
for sd,step,st,g in S[:300]:
    p=st.current_player()
    if p<0: continue
    base=st.information_state_string(p)
    d1=st.resample_from_infostate(p,np.random.RandomState(11))
    d2=st.resample_from_infostate(p,np.random.RandomState(22))
    N4a+=1
    a,b_=d1.information_state_string(p),d2.information_state_string(p)
    if not(a==b_==base):
        leak+=1
        if len(ex)<3: ex.append((sd,step,a==b_,a==base))
print(f"INV4a leakage(hidden differs -> string must match): N={N4a} violations={leak} {ex[:2]}")

# ---- INV4b: observable differences MUST change InformationStateString(p) ----
# board is fully public; find state pairs with same infostate string but different board
seen={}; collide=0; N4b=0; bex=[]
for sd,step,st,g in S:
    p=st.current_player()
    if p<0: continue
    N4b+=1
    key=(p,st.information_state_string(p))
    bf=board_fp(st)
    if key in seen:
        if seen[key]!=bf:
            collide+=1
            if len(bex)<3: bex.append((sd,step))
    else: seen[key]=bf
print(f"INV4b distinguishability via infostate-key collision: N={N4b} unique_keys={len(seen)} same-key-different-board={collide}")

# direct: does private_view_json (the only non-history part) contain ANY board field?
pv=json.loads(S[0][2]._adapter.private_view_json('p1'))
board_keys=[k for k in list(pv.keys())+list(pv['public'].keys()) if any(t in k.lower() for t in ('site','board','node','control','troop','spy','spies_on'))]
print(f"INV4b board fields present in private_view_json: {board_keys}  (public keys: {sorted(pv['public'].keys())})")

# ---- INV4b-2: apply a board-mutating move, does infostate change beyond history? ----
changed=0; unchanged=0; N4b2=0
for sd,step,st,g in S[:400]:
    p=st.current_player()
    if p<0: continue
    for aid in st.legal_actions():
        mv=st.move_to_str(st.decode_action(int(aid)))
        if any(t in mv.lower() for t in ("troop","spy","assassinate","place")):
            b0=board_fp(st); pv0=st._adapter.private_view_json(st._game.get_player_ids()[p])
            c=st.clone(); c.apply_action(int(aid))
            if c.current_player()<0: break
            b1=board_fp(c); pv1=c._adapter.private_view_json(st._game.get_player_ids()[p])
            if b0!=b1:
                N4b2+=1
                if pv0==pv1: unchanged+=1
                else: changed+=1
            break
print(f"INV4b-2 board-mutating moves: N={N4b2} board changed & private_view UNCHANGED={unchanged}, also changed={changed}")

# ---- INV5: determinisation consistency ----
K=12; N5=0; worlds=[]; badcount=0; badhist=0; bex2=[]
for sd,step,st,g in S[:200]:
    p=st.current_player()
    if p<0: continue
    N5+=1
    pid=st._game.get_player_ids()[p]
    base=json.loads(st._adapter.private_view_json(pid))
    fps=set()
    for k in range(K):
        d=st.resample_from_infostate(p,np.random.RandomState(1000+k))
        fps.add(fp_hash(d))
        dv=json.loads(d._adapter.private_view_json(pid))
        # own hand + zone counts must be conserved
        if (dv["hand"]!=base["hand"] or dv["deck_size"]!=base["deck_size"]
            or dv["discard_size"]!=base["discard_size"]
            or dv["public"]["public_player_summaries"]!=base["public"]["public_player_summaries"]):
            badcount+=1
            if len(bex2)<2: bex2.append((sd,step,k))
        if d.history_str()!=st.history_str(): badhist+=1
    worlds.append(len(fps))
import statistics
print(f"INV5 determinisation: N={N5} K={K} distinct_worlds mean={statistics.mean(worlds):.2f} min={min(worlds)} max={max(worlds)} singleton_infosets={sum(1 for w in worlds if w==1)}")
print(f"INV5 conservation violations={badcount}/{N5*K}, history mismatches={badhist}/{N5*K} {bex2}")
