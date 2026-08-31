import sys, os, time, json
VAL=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,VAL)

def one(job):
    from common import load, make_bot, RandomBot, play_game
    kind, sims_a, sims_b, seed, seat = job
    g = load(2)
    def mk(spec, bseed):
        return RandomBot(bseed) if spec == 0 else make_bot(g, spec, bseed)
    # seat=0 -> agent A in seat 0; seat=1 -> swapped
    specs = (sims_a, sims_b) if seat == 0 else (sims_b, sims_a)
    bots = [mk(specs[0], seed*991+1), mk(specs[1], seed*991+2)]
    t = time.perf_counter()
    r = play_game(g, bots, seed)
    dt = time.perf_counter()-t
    ret = r["returns"]
    a_idx = 0 if seat == 0 else 1
    margin = ret[a_idx]
    res = 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)
    return {"kind":kind,"sims_a":sims_a,"sims_b":sims_b,"seed":seed,"seat":seat,
            "a_score":res,"margin":margin,"steps":r["steps"],"stopped":r["stopped"],"wall":dt}

if __name__ == "__main__":
    import multiprocessing as mp
    from math import comb
    def binom_p(k, n, p=0.5):   # two-sided exact
        if n == 0: return 1.0
        pm = [comb(n,i)*p**i*(1-p)**(n-i) for i in range(n+1)]
        obs = pm[k]
        return min(1.0, sum(x for x in pm if x <= obs*(1+1e-12)))
    def summarize(tag, rows):
        n=len(rows); w=sum(r["a_score"] for r in rows)
        wins=sum(1 for r in rows if r["a_score"]==1.0)
        losses=sum(1 for r in rows if r["a_score"]==0.0)
        ties=sum(1 for r in rows if r["a_score"]==0.5)
        wall=sum(r["wall"] for r in rows)
        dec=n and sum(r["steps"] for r in rows)/n
        p=binom_p(wins, wins+losses)
        print(f"  {tag}: N={n} winrate={w/n:.3f} (W{wins}/L{losses}/T{ties}) "
              f"exact-binomial p={p:.4g} (on {wins+losses} decisive) mean_decisions={dec:.0f} wall={wall:.0f}s",flush=True)
        return {"tag":tag,"N":n,"winrate":w/n,"W":wins,"L":losses,"T":ties,"p":p,
                "mean_decisions":dec,"wall_sec":wall}

    NG = int(sys.argv[1]) if len(sys.argv)>1 else 48
    STAGE = sys.argv[2] if len(sys.argv)>2 else "all"
    out={}
    pool = mp.Pool(16)
    if STAGE in ("all","cheap"):
     print(f"=== BASELINE SANITY: ISMCTS(200) vs uniform-random, seat-swapped, {NG} games ===",flush=True)
    jobs=[("base",200,0,100+i//2,i%2) for i in range(NG)]
    t=time.perf_counter(); rows=pool.map(one,jobs)
    out["baseline"]=summarize("ISMCTS200_vs_random",rows); print(f"  ({time.perf_counter()-t:.0f}s)",flush=True)

    print(f"=== BUDGET MONOTONICITY vs fixed uniform-random baseline, seat-swapped ===",flush=True)
    lad=[]
    for ns in (25,100,400,1600):
        jobs=[("lad",ns,0,300+i//2,i%2) for i in range(NG)]
        t=time.perf_counter(); rows=pool.map(one,jobs)
        lad.append(summarize(f"ISMCTS{ns}_vs_random",rows)); print(f"  ({time.perf_counter()-t:.0f}s)",flush=True)
    out["ladder"]=lad

    print(f"=== SELF-PLAY CALIBRATION: ISMCTS(200) vs ISMCTS(200), seat-swapped ===",flush=True)
    jobs=[("self",200,200,500+i//2,i%2) for i in range(NG)]
    t=time.perf_counter(); rows=pool.map(one,jobs)
    out["selfplay"]=summarize("ISMCTS200_selfplay",rows); print(f"  ({time.perf_counter()-t:.0f}s)",flush=True)

    print(f"=== HEAD-TO-HEAD: ISMCTS(1600) vs ISMCTS(100), seat-swapped ===",flush=True)
    jobs=[("h2h",1600,100,700+i//2,i%2) for i in range(NG)]
    t=time.perf_counter(); rows=pool.map(one,jobs)
    out["h2h"]=summarize("ISMCTS1600_vs_ISMCTS100",rows); print(f"  ({time.perf_counter()-t:.0f}s)",flush=True)

    pool.close(); pool.join()
    open(os.path.join(VAL,"exp_results.json"),"w").write(json.dumps(out,indent=1))
    print("WROTE exp_results.json")
