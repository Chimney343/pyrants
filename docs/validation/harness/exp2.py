import sys, os, time, json
VAL=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,VAL)
from exp import one

if __name__ == "__main__":
    import multiprocessing as mp
    from math import comb
    def binom_p(k,n,p=0.5):
        if n==0: return 1.0
        pm=[comb(n,i)*p**i*(1-p)**(n-i) for i in range(n+1)]
        obs=pm[k]; return min(1.0,sum(x for x in pm if x<=obs*(1+1e-12)))
    def summarize(tag,rows):
        n=len(rows); w=sum(r["a_score"] for r in rows)
        W=sum(1 for r in rows if r["a_score"]==1.0); L=sum(1 for r in rows if r["a_score"]==0.0)
        T=sum(1 for r in rows if r["a_score"]==0.5)
        dec=sum(r["steps"] for r in rows)/n; wall=sum(r["wall"] for r in rows)
        mm=sum(r["margin"] for r in rows)/n
        p=binom_p(W,W+L)
        line=(f"{tag}: N={n} winrate={w/n:.3f} (W{W}/L{L}/T{T}) exact-binom p={p:.4g} on {W+L} decisive"
              f" mean_margin={mm:+.2f} mean_decisions={dec:.0f} cpu_wall={wall:.0f}s")
        print(line,flush=True)
        return {"tag":tag,"N":n,"winrate":w/n,"W":W,"L":L,"T":T,"p":p,"mean_margin":mm,
                "mean_decisions":dec,"cpu_wall_sec":wall}
    NG=int(sys.argv[1]); stage=sys.argv[2]
    pool=mp.Pool(16); out={}
    def run(tag,jobs):
        t=time.perf_counter(); rows=pool.map(one,jobs)
        r=summarize(tag,rows); r["elapsed_sec"]=round(time.perf_counter()-t,1)
        print(f"   elapsed {r['elapsed_sec']}s",flush=True); return r
    if stage=="s1":
        out["baseline_200"]=run("BASELINE ISMCTS(200) vs uniform-random",[("b",200,0,100+i//2,i%2) for i in range(NG)])
        for ns in (25,100):
            out[f"lad{ns}"]=run(f"LADDER ISMCTS({ns}) vs uniform-random",[("l",ns,0,300+i//2,i%2) for i in range(NG)])
    elif stage=="s2":
        out["lad400"]=run("LADDER ISMCTS(400) vs uniform-random",[("l",400,0,300+i//2,i%2) for i in range(NG)])
    elif stage=="s3":
        out["lad1600"]=run("LADDER ISMCTS(1600) vs uniform-random",[("l",1600,0,300+i//2,i%2) for i in range(NG)])
    elif stage=="s4":
        out["selfplay"]=run("SELF-PLAY ISMCTS(200) vs ISMCTS(200)",[("s",200,200,500+i//2,i%2) for i in range(NG)])
    elif stage=="s5":
        out["h2h"]=run("HEAD-TO-HEAD ISMCTS(1600) vs ISMCTS(100)",[("h",1600,100,700+i//2,i%2) for i in range(NG)])
    pool.close(); pool.join()
    f=os.path.join(VAL,f"res_{stage}.json"); open(f,"w").write(json.dumps(out,indent=1)); print("WROTE",f)
