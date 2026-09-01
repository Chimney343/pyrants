"""F-004 utility-contract gate probe: T5 (returns within declared bounds) and
T6 (insane_outcast stress probe).

Script, not pytest — mirrors the ``f011_timing.py`` precedent for large-N /
potentially-slow measurements that do not belong in the pytest budget.

Two sections:

* T5 — for num_players in {2,3,4}, play N=50 terminal random-policy games and
  report every ``returns()`` entry against the *declared* contract
  (``utility_sum``/``min_utility``/``max_utility``). This is gate G3's own
  threshold (N >= 50). n==2 additionally checks ``sum(returns) == 0.0``.

* T6 — the insane_outcast stress probe (gate G4). Two parts:
    1. A greedy play probe that preferentially plays every
       ``give_insane_outcast_*`` card whenever legal, to measure the largest
       accumulation of the game's only negative-``deck_vp`` card that actual
       play reaches.
    2. A direct-struct-injection upper-bound proxy that force-mints
       ``insane_outcast`` into one player's discard pile at the 30-copy design
       intent (``special_stack_config``, ``engine_c/helpers.c:266``) and beyond,
       and reports the resulting ``compute_final_scores`` value against -50.0.

The fix itself touches only ``GameInfo`` metadata (``game_c.py``), so T6's
numbers must be identical pre- and post-fix: it probes *engine* behaviour,
not the declaration being fixed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402
from common import RandomBot, load, play_game  # noqa: E402

from engine_c.bindings.engine_bindings import _lib  # noqa: E402

INSANE_GIVERS = {
    "ghoul",
    "demogorgon",
    "derro",
    "gibbering_mouther",
    "myconid_adult",
    "myconid_sovereign",
}

N_T5 = 50
N_T6 = 200


class GreedyInsaneOutcastBot:
    """Prefer playing a ``give_insane_outcast_*`` card; otherwise uniform random."""

    def __init__(self, seed):
        self.rng = np.random.RandomState(seed)

    def step_with_policy(self, state):
        legal = state.legal_actions()
        for aid in legal:
            mv = state.decode_action(int(aid))
            if mv.move_type == "play_card" and mv.data.get("card_id") in INSANE_GIVERS:
                return [(x, 1.0 / len(legal)) for x in legal], int(aid)
        aid = int(self.rng.choice(legal))
        return [(x, 1.0 / len(legal)) for x in legal], aid

    def step(self, state):
        return self.step_with_policy(state)[1]


def _inject_insane_outcasts(state, pid, count):
    idx = state._adapter.player_index(pid)
    ps = state._adapter._state._s.players[idx]
    for j in range(min(count, 80)):
        ps.discard_pile[j] = _lib.intern(b"insane_outcast")
    ps.discard_pile_count = min(count, 80)


def section_t5():
    print("########## T5 returns-within-declared-bounds ##########")
    for npl in (2, 3, 4):
        g = load(npl)
        lo = g.min_utility()
        hi = g.max_utility()
        us = g.utility_sum()
        out_of_bounds = 0
        sum_violations = 0
        all_returns = []
        for sd in range(1, N_T5 + 1):
            bots = [RandomBot(sd * 100 + i) for i in range(npl)]
            r = play_game(g, bots, sd)
            rets = r["returns"]
            all_returns.extend(rets)
            for v in rets:
                if v < lo or v > hi:
                    out_of_bounds += 1
            if npl == 2 and abs(sum(rets)) > 1e-9:
                sum_violations += 1
        print(
            f"  num_players={npl} utility_sum={us!r} min={lo} max={hi} "
            f"N={N_T5} games"
        )
        print(
            f"    min(returns)={min(all_returns)} max(returns)={max(all_returns)} "
            f"out_of_bounds={out_of_bounds}"
        )
        if npl == 2:
            print(f"    n==2 sum(returns)==0.0 violations={sum_violations}/{N_T5}")


def section_t6():
    print("########## T6 insane_outcast stress probe ##########")
    for npl in (2, 3, 4):
        g = load(npl)
        worst_return = None
        for sd in range(1, N_T6 + 1):
            bots = [GreedyInsaneOutcastBot(sd * 1000 + i) for i in range(npl)]
            r = play_game(g, bots, sd)
            rets = r["returns"]
            mn = min(rets)
            if worst_return is None or mn < worst_return:
                worst_return = mn
        print(f"  num_players={npl} N={N_T6} greedy games")
        print(f"    worst min(returns)={worst_return}  (declared floor: {g.min_utility()})")

    print("  --- direct injection upper bound ---")
    for npl in (2, 3, 4):
        g = load(npl)
        for k in (30, 50, 80):
            state = g.new_initial_state()
            state.apply_action(42)
            pid = state._game.get_player_ids()[0]
            _inject_insane_outcasts(state, pid, k)
            scores = state._adapter.final_scores()
            score0 = scores[state._game.get_player_ids()[0]]
            if npl == 2:
                p0 = scores[state._game.get_player_ids()[0]]
                p1 = scores[state._game.get_player_ids()[1]]
                ret = float(p0 - p1)
                label = f"n==2 diff={ret}"
            else:
                ret = float(score0)
                label = f"n>2 raw={ret}"
            print(
                f"    num_players={npl} inject={k} insane_outcast -> "
                f"final_score[0]={score0} ({label})"
            )


if __name__ == "__main__":
    section_t5()
    print()
    section_t6()
