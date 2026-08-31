import os
import sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

R = {}

# ---- INV-1 REPLAY DETERMINISM: same seed, same policy, two runs ----
seeds = list(range(1, 101))
det_fail = []
for sd in seeds:
    g = load(2)
    r1 = play_game(g, [make_bot(g, 20, 1000+sd), make_bot(g, 20, 2000+sd)], sd, record_actions=True)
    g2 = load(2)
    r2 = play_game(g2, [make_bot(g2, 20, 1000+sd), make_bot(g2, 20, 2000+sd)], sd, record_actions=True)
    same_acts = [a[1] for a in r1["actions"]] == [a[1] for a in r2["actions"]]
    same_ret = r1["returns"] == r2["returns"]
    if not (same_acts and same_ret):
        det_fail.append((sd, len(r1["actions"]), len(r2["actions"]), same_acts, same_ret,
                         r1["returns"], r2["returns"]))
R["INV1_replay_determinism"] = {"N": len(seeds), "seeds": seeds, "failures": det_fail,
                                "pass": not det_fail}
print("INV1 replay determinism:", "PASS" if not det_fail else f"FAIL {det_fail[:2]}", flush=True)

# ---- INV-2 CLONE INDEPENDENCE ----
clone_fail = []
NC = 0
for sd in seeds:
    g = load(2)
    s = fresh(g, sd)
    bots = [RandomBot(sd*7+i) for i in range(2)]
    for step in range(200):
        if s.is_terminal(): break
        cp = s.current_player()
        if cp < 0: break
        # every 20 steps do a clone-independence probe
        if step % 20 == 19:
            NC += 1
            before = fingerprint(s)
            c = s.clone()
            cbots = [RandomBot(999+i) for i in range(2)]
            for _ in range(15):
                if c.is_terminal(): break
                ccp = c.current_player()
                if ccp < 0: break
                c.apply_action(cbots[ccp].step(c))
            after = fingerprint(s)
            if before != after:
                clone_fail.append((sd, step))
        s.apply_action(bots[cp].step(s))
R["INV2_clone_independence"] = {"N": NC, "seeds": seeds, "failures": clone_fail,
                                "pass": not clone_fail}
print(f"INV2 clone independence: {'PASS' if not clone_fail else 'FAIL '+str(clone_fail[:3])} N={NC}", flush=True)

# ---- INV-3 LEGALITY over >=1000 sampled states ----
leg_states = 0
leg_empty = 0; leg_dup = 0; leg_range = 0
leg_ex = []
sd = 0
while leg_states < 1200:
    sd += 1
    g = load(2)
    s = fresh(g, sd)
    bots = [RandomBot(sd*13+i) for i in range(2)]
    for _ in range(2000):
        if s.is_terminal(): break
        cp = s.current_player()
        if cp < 0: break
        la = s.legal_actions()
        leg_states += 1
        if len(la) == 0:
            leg_empty += 1; leg_ex.append(("empty", sd, s._engine.phase.value))
        if len(set(la)) != len(la):
            leg_dup += 1; leg_ex.append(("dup", sd, la[:10]))
        nmoves = len(s._adapter.legal_moves())
        if any((a < 0 or a >= nmoves) for a in la):
            leg_range += 1; leg_ex.append(("range", sd, la[:10], nmoves))
        if leg_states >= 1200: break
        s.apply_action(bots[cp].step(s))
R["INV3_legality"] = {"N": leg_states, "seeds": f"1..{sd}", "empty": leg_empty,
                      "duplicates": leg_dup, "out_of_range": leg_range,
                      "examples": leg_ex[:5], "pass": leg_empty==0 and leg_dup==0 and leg_range==0}
print(f"INV3 legality: N={leg_states} empty={leg_empty} dup={leg_dup} oor={leg_range}", flush=True)

# ---- INV-6 CHANCE MASS ----
cm_nodes = 0; cm_bad = []
for sd in range(1, 31):
    g = load(2)
    s = g.new_initial_state()
    bots = [RandomBot(sd*3+i) for i in range(2)]
    for _ in range(600):
        if s.is_terminal(): break
        if s.is_chance_node():
            co = s.chance_outcomes()
            cm_nodes += 1
            tot = sum(p for _, p in co)
            if abs(tot - 1.0) > 1e-9:
                cm_bad.append((sd, len(co), tot))
            s.apply_action(co[sd % len(co)][0])
            continue
        cp = s.current_player()
        if cp < 0: break
        s.apply_action(bots[cp].step(s))
R["INV6_chance_mass"] = {"N_chance_nodes": cm_nodes, "seeds": "1..30",
                         "violations": cm_bad, "pass": not cm_bad}
print(f"INV6 chance mass: N={cm_nodes} bad={len(cm_bad)}", flush=True)

print(json.dumps(R, indent=1, default=str))
