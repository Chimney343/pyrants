import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

def raw(st): return st._adapter._state._s

# ---- Part 1 (GA1): field-invariance collision rate at gate N >= 100 ----
same = 0; tot2 = 0; exs = []
sd = 0
while tot2 < 100 and sd < 200:
    sd += 1
    g = load(2); s = fresh(g, sd); b = RandomBot(sd * 3)
    for step in range(150):
        if s.is_terminal() or s.current_player() < 0: break
        if step % 13 == 12:
            p = s.current_player()
            r0 = raw(s)
            d1 = s.resample_from_infostate(p, np.random.RandomState(101))
            d2 = s.resample_from_infostate(p, np.random.RandomState(202))
            tot2 += 1
            a, b2, c0 = raw(d1), raw(d2), r0
            if (a.shuffle_seed == b2.shuffle_seed == c0.shuffle_seed
                    and a.shuffle_counter == b2.shuffle_counter == c0.shuffle_counter):
                same += 1
            if len(exs) < 3:
                exs.append((c0.shuffle_seed, c0.shuffle_counter,
                            a.shuffle_seed, a.shuffle_counter,
                            b2.shuffle_seed, b2.shuffle_counter))
        s.apply_action(b.step(s))
print(f"GA1: N={tot2}  determinizations preserving root (shuffle_seed,shuffle_counter) EXACTLY: {same}/{tot2}")
for e in exs:
    print(f"   root=({e[0]},{e[1]})  det1=({e[2]},{e[3]})  det2=({e[4]},{e[5]})")

# ---- Part 2 (GA3): first forced reshuffle permutation across two determinizations ----

def prep(sd, steps, dseed):
    """Play to a mid-game root, determinize with dseed, then empty every deck and
    install a fixed discard pile so the next draw MUST reshuffle. Returns a
    determinized state or None."""
    g = load(2); s = fresh(g, sd); b = RandomBot(sd * 3)
    for _ in range(steps):
        if s.is_terminal() or s.current_player() < 0: break
        s.apply_action(b.step(s))
    if s.is_terminal() or s.current_player() < 0: return None
    p = s.current_player()
    d = s.resample_from_infostate(p, np.random.RandomState(dseed))
    r = raw(d)
    for pi in range(r.player_count):
        pl = r.players[pi]
        pool = [pl.discard_pile[i] for i in range(pl.discard_pile_count)] + \
               [pl.deck[i] for i in range(pl.deck_count)]
        if len(pool) < 6: return None
        pool = pool[:8]
        for i, sym in enumerate(pool): pl.discard_pile[i] = sym
        pl.discard_pile_count = len(pool); pl.deck_count = 0
    return d

def first_reshuffle_deck(c):
    """Step with a FIXED policy until shuffle_counter increments; return deck order."""
    b = RandomBot(4242); prev = raw(c).shuffle_counter
    for _ in range(300):
        if c.is_terminal() or c.current_player() < 0: return None
        c.apply_action(b.step(c))
        if c._adapter is None: return None
        r = raw(c)
        if r.shuffle_counter != prev:
            out = []
            for pi in range(r.player_count):
                pl = r.players[pi]
                out.append([str(pl.deck[i]) for i in range(pl.deck_count)])
            return (r.shuffle_counter, out)
    return None

rows = []
for sd in (3, 5, 11, 17, 23, 29, 31, 37):
    for steps in (40, 60):
        da = prep(sd, steps, 101)
        db = prep(sd, steps, 202)
        if da is None or db is None: continue
        oa = first_reshuffle_deck(da); ob = first_reshuffle_deck(db)
        if oa is None or ob is None: continue
        same_deck = (oa[1] == ob[1])
        rows.append(same_deck)
        print(f"  seed{sd} steps{steps}: determinize(101) vs determinize(202) -> first reshuffle deck order same: {same_deck}")
n = len(rows)
print(f"\nGA3: N={n} controlled determinize->reshuffle pairs")
print(f"  distinct determinization seeds -> reshuffle permutation CHANGED: {sum(1 for r in rows if not r)}/{n}")
