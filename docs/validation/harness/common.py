"""Shared helpers for the empirical validation battery. Read-only on repo source."""
import hashlib, json, sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
import numpy as np
import openspiel_pyrants  # registers python_pyrants_c
import pyspiel

def load(num_players=2, **params):
    p = {"num_players": str(num_players)}
    p.update({k: str(v) for k, v in params.items()})
    return pyspiel.load_game("python_pyrants_c", p)

def fresh(game, shuffle_seed=42):
    s = game.new_initial_state()
    s.apply_action(shuffle_seed)
    return s

def fingerprint(state):
    """Omniscient state fingerprint: every player's private view + public dict +
    turn pointers + full legal-move label list. Two states with the same
    fingerprint are indistinguishable through the entire public binding API."""
    if state._adapter is None:
        return "NOADAPTER"
    a = state._adapter
    parts = []
    for pid in state._game.get_player_ids():
        parts.append(a.private_view_json(pid))
    parts.append(json.dumps(a._build_public_dict(), sort_keys=True))
    parts.append(f"{a.phase()}|{a.current_player_id()}|{a.round_number()}|{a.is_terminal()}")
    parts.append("|".join(str(m) for m in a.legal_moves()))
    return "\x1f".join(parts)

def fp_hash(state):
    return hashlib.sha256(fingerprint(state).encode()).hexdigest()[:16]

def make_bot(game, num_sims, seed, uct_c=1.4, evaluator="random-c"):
    from open_spiel.python.algorithms.ismcts import ISMCTSFinalPolicyType
    from openspiel_pyrants.ismcts_factory import make_ismcts_bot
    rng = np.random.RandomState(seed)
    if evaluator == "random-c":
        from openspiel_pyrants.c_rollout_evaluator import CRolloutEvaluator
        ev = CRolloutEvaluator(max_length=0, random_state=rng)
    else:
        from open_spiel.python.algorithms.mcts import RandomRolloutEvaluator
        ev = RandomRolloutEvaluator(n_rollouts=1, max_length=None, random_state=rng)
    return make_ismcts_bot(game=game, seed=seed, num_sims=num_sims, uct_c=uct_c,
                           max_world_samples=-1,
                           final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
                           evaluator=ev)

class RandomBot:
    """Uniform-random over legal actions."""
    def __init__(self, seed):
        self.rng = np.random.RandomState(seed)
    def step_with_policy(self, state):
        la = state.legal_actions()
        a = int(self.rng.choice(la))
        return [(x, 1.0/len(la)) for x in la], a
    def step(self, state):
        return self.step_with_policy(state)[1]

def play_game(game, bots, shuffle_seed, max_rounds=0, record_actions=False):
    """Mirrors scripts/run_ismcts.py's loop. Returns dict of outcome."""
    s = fresh(game, shuffle_seed)
    acts = []
    n = game.num_players()
    steps = 0
    while not s.is_terminal():
        if max_rounds > 0 and s._engine.round_number > max_rounds:
            return {"returns": s.returns(), "actions": acts, "steps": steps,
                    "stopped": "round_cap", "scores": s.final_scores()}
        cp = s.current_player()
        if cp < 0 or cp >= n:
            return {"returns": s.returns(), "actions": acts, "steps": steps,
                    "stopped": f"bad_player:{cp}", "scores": s.final_scores()}
        _, a = bots[cp].step_with_policy(s)
        if record_actions:
            acts.append((cp, int(a), s.move_to_str(s.decode_action(int(a)))))
        s.apply_action(int(a))
        steps += 1
    return {"returns": s.returns(), "actions": acts, "steps": steps,
            "stopped": "terminal", "scores": s.final_scores()}
