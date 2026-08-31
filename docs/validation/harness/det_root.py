import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import pyspiel

print("=== S1: pyspiel.UniformProbabilitySampler(0.,1.) draws, freshly constructed each time ===")
for trial in range(6):
    s=pyspiel.UniformProbabilitySampler(0.,1.)
    print(f"  fresh sampler trial{trial}: first 3 draws = {[round(s(),9) for _ in range(3)]}")

print("\n=== S2: is it callable / does it take the numpy branch? ===")
smp=pyspiel.UniformProbabilitySampler(0.,1.)
print("  hasattr(smp,'shuffle') =",hasattr(smp,'shuffle'),"  callable(smp) =",callable(smp))
print("  -> state_c.resample_from_infostate takes the",
      "numpy" if hasattr(smp,'shuffle') else ("callable(unseeded)" if callable(smp) else "seed=0"),"branch")

print("\n=== S3: seeds ISMCTS actually hands to engine_determinize ===")
g=load(2); s=fresh(g,7); b=RandomBot(7)
for _ in range(40):
    if s.is_terminal() or s.current_player()<0: break
    s.apply_action(b.step(s))
import openspiel_pyrants.state_c as SC
seeds_seen=[]
orig=SC.PyrantsCState.resample_from_infostate
def spy(self,player,rng):
    if callable(rng) and not hasattr(rng,'shuffle'):
        pass
    return orig(self,player,rng)
# instead directly emulate the seed derivation the code performs
for trial in range(3):
    smp=pyspiel.UniformProbabilitySampler(0.,1.)
    seeds_seen.append([int(smp()*2**63) for _ in range(4)])
for i,row in enumerate(seeds_seen): print(f"  run{i} first 4 determinization seeds: {row}")
print("  identical across runs?", len({tuple(r) for r in seeds_seen})==1)

print("\n=== S4: does --seed control determinization? two bots, SAME numpy seed ===")
outs=[]
for trial in range(6):
    bot=make_bot(g,20,4242)
    st=s.clone()
    _,ch=bot.step_with_policy(st)
    outs.append(int(ch))
print("  chosen action over 6 identically-seeded searches:",outs,"-> distinct:",len(set(outs)))

print("\n=== S5: control — force numpy branch by calling resample directly with RandomState ===")
res=[]
for trial in range(6):
    st=s.clone()
    d=st.resample_from_infostate(st.current_player(), np.random.RandomState(555))
    res.append(fp_hash(d))
print("  fp of determinization with RandomState(555) x6:",len(set(res)),"distinct ->",res[0])
