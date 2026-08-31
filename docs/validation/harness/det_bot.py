import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

# Build one fixed mid-game state
g=load(2); s=fresh(g,7); b=RandomBot(7)
for _ in range(40):
    if s.is_terminal() or s.current_player()<0: break
    s.apply_action(b.step(s))
print("state fp:",fp_hash(s),"legal:",len(s.legal_actions()),"player:",s.current_player())

print("\n=== B1: same fixed state, N identically-seeded fresh bots, compare chosen action ===")
for nsims in (20,200):
    res=[]
    for trial in range(10):
        st=s.clone()
        bot=make_bot(g,nsims,4242)
        pol,ch=bot.step_with_policy(st)
        res.append((int(ch),tuple(sorted((int(a),round(float(p),6)) for a,p in pol))))
    chosen={r[0] for r in res}; pols={r[1] for r in res}
    print(f"  num_sims={nsims} N=10 seed=4242 -> distinct chosen={len(chosen)} {sorted(chosen)}, distinct policies={len(pols)}")

print("\n=== B2: does the ROOT STATE mutate during search? ===")
for nsims in (20,200):
    st=s.clone(); before=fp_hash(st)
    bot=make_bot(g,nsims,4242); bot.step_with_policy(st)
    after=fp_hash(st)
    print(f"  num_sims={nsims}: root fp before={before} after={after} {'MUTATED' if before!=after else 'intact'}")

print("\n=== B3: repeat B1 but with root passed as the SAME object each trial ===")
st=s.clone()
res=[]
for trial in range(10):
    bot=make_bot(g,20,4242)
    _,ch=bot.step_with_policy(st)
    res.append(int(ch))
print("  chosen sequence over 10 trials on one shared root:",res)

print("\n=== B4: factory-built bot, same seed each trial (probe) ===")
for trial in range(5):
    from open_spiel.python.algorithms.ismcts import ISMCTSFinalPolicyType
    from openspiel_pyrants.c_rollout_evaluator import CRolloutEvaluator
    from openspiel_pyrants.ismcts_factory import make_ismcts_bot
    bot=make_ismcts_bot(game=g,seed=4242,num_sims=20,uct_c=1.4,max_world_samples=-1,
                        final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
                        evaluator=CRolloutEvaluator(0,np.random.RandomState(4242)))
    st=s.clone(); _,ch=bot.step_with_policy(st)
    print(f"  trial{trial}: chosen={int(ch)} nodes={len(bot._nodes)}")
