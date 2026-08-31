import os
import sys, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import pyspiel
from openspiel_pyrants.action_encoding_c import compute_c_action_map

def raw(st): return st._adapter._state._s

print("########## F-001 action-ID stability across determinizations ##########")
tot=0; idx_tot=0; idx_diff=0; len_diff=0; ex=[]
for sd in range(1,60):
    g=load(2); s=fresh(g,sd); b=RandomBot(sd*5)
    for step in range(200):
        if s.is_terminal() or s.current_player()<0: break
        if step%11==10:
            p=s.current_player()
            d1=s.resample_from_infostate(p,np.random.RandomState(11))
            d2=s.resample_from_infostate(p,np.random.RandomState(77))
            m1=compute_c_action_map(d1._adapter); m2=compute_c_action_map(d2._adapter)
            tot+=1
            if len(m1)!=len(m2): len_diff+=1
            for i in range(min(len(m1),len(m2))):
                idx_tot+=1
                a=str(m1[i][1]); b2=str(m2[i][1])
                if a!=b2:
                    idx_diff+=1
                    if len(ex)<4: ex.append((sd,step,i,a,b2))
        s.apply_action(b.step(s))
print(f"  N infosets={tot}  indices compared={idx_tot}")
print(f"  indices whose move CHANGED between two determinizations: {idx_diff} ({100*idx_diff/max(idx_tot,1):.2f}%)")
print(f"  infosets where legal-action COUNT differed: {len_diff}/{tot}")
for e in ex: print("   e.g. seed",e[0],"step",e[1],"idx",e[2],":",e[3],"  VS  ",e[4])

print("\n########## F-002 shuffle_seed/shuffle_counter not rerolled by determinize ##########")
same=0; tot2=0; exs=[]
for sd in range(1,40):
    g=load(2); s=fresh(g,sd); b=RandomBot(sd*3)
    for step in range(150):
        if s.is_terminal() or s.current_player()<0: break
        if step%13==12:
            p=s.current_player()
            r0=raw(s)
            d1=s.resample_from_infostate(p,np.random.RandomState(101))
            d2=s.resample_from_infostate(p,np.random.RandomState(202))
            tot2+=1
            a,b2,c0=raw(d1),raw(d2),r0
            if a.shuffle_seed==b2.shuffle_seed==c0.shuffle_seed and a.shuffle_counter==b2.shuffle_counter==c0.shuffle_counter:
                same+=1
            if len(exs)<3: exs.append((c0.shuffle_seed,c0.shuffle_counter,a.shuffle_seed,a.shuffle_counter,b2.shuffle_seed,b2.shuffle_counter))
        s.apply_action(b.step(s))
print(f"  N={tot2}  determinizations preserving root (shuffle_seed,shuffle_counter) EXACTLY: {same}/{tot2}")
for e in exs: print(f"   root=({e[0]},{e[1]})  det1=({e[2]},{e[3]})  det2=({e[4]},{e[5]})")

print("\n########## F-003 shuffle_counter advances with no chance node ##########")
adv=0; adv_at_chance=0; tot3=0
for sd in range(1,40):
    g=load(2); s=fresh(g,sd); b=RandomBot(sd*9)
    for step in range(300):
        if s.is_terminal() or s.current_player()<0: break
        pre=raw(s).shuffle_counter; was_chance=s.is_chance_node()
        s.apply_action(b.step(s))
        if s._adapter is None: continue
        post=raw(s).shuffle_counter; tot3+=1
        if post!=pre:
            adv+=1
            if was_chance: adv_at_chance+=1
print(f"  N transitions={tot3}  shuffle_counter advanced on {adv} of them")
print(f"  of those advances, preceded by is_chance_node()==True: {adv_at_chance}")

print("\n########## F-004 returns()/utility contract for 3-4 players ##########")
for npl in (2,3,4):
    g=load(npl)
    gi=g.get_type(); 
    print(f"  --- num_players={npl}  utility_sum={g.utility_sum()} min_utility={g.min_utility()} max_utility={g.max_utility()} type={gi.utility}")
    sums=[]; mins=[]
    for sd in range(1,9):
        r=play_game(g,[RandomBot(sd*100+i) for i in range(npl)],sd)
        sums.append(sum(r["returns"])); mins.append(min(r["returns"]))
    print(f"     N=8 terminal returns: sum(returns) values={sums}")
    print(f"     min(returns) values={mins}   any negative={any(m<0 for m in mins)}")

print("\n########## F-005 first player always player_ids[0] ##########")
firsts=collections.Counter()
for ss in [0,1,2,7,42,99,123,500,777,999]:
    g=load(2); s=g.new_initial_state(); s.apply_action(ss)
    firsts[s._adapter.current_player_id()]+=1
print(f"  N=10 shuffle_seeds {[0,1,2,7,42,99,123,500,777,999]} -> current_player_id counts: {dict(firsts)}")

print("\n########## F-009 max_chance_outcomes vs shuffle_seed_count ##########")
for cnt in (1000,5000):
    g=pyspiel.load_game("python_pyrants_c",{"num_players":"2","shuffle_seed_count":str(cnt)})
    s=g.new_initial_state()
    print(f"  shuffle_seed_count={cnt}: len(chance_outcomes())={len(s.chance_outcomes())}  game.max_chance_outcomes()={g.max_chance_outcomes()}")
