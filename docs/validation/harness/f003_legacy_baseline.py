"""Phase 0 (Part B): frozen legacy-path baseline for F-003's ten call sites.

Captures the outcome the CURRENT inline-RNG path produces at each of the ten
docs/validation/f002-f003-fix-plan.md Section 1(b) sites, keyed by
(site, shuffle_seed, shuffle_counter), before any Part B GREEN code exists.
This is destructive to defer: once Part B's chance-node conversion lands,
the inline-RNG path is deleted and there is nothing left to diff against
(fix-plan Sec 13 second paragraph / completion-plan Step 3).

Two sites (draw_cards_state, reshuffle_discard_into_deck) are pure engine
mechanics, reached via direct struct injection (empty deck + discard pile).
The other five captured here (apply_force_discard, and the neogi/
mindwitness/chuul/nothic generic_runtime.c variants) each need a specific
card scenario -- see docs/validation/f002-f003-completion-plan.md Sec 2.4
for the card->site trace this script's scenarios are built from.

rules.c:530-538 is NOT captured as an independent site: F-015 (findings.md)
traced it to be an unguarded SECOND firing of the identical neogi action,
not a distinct event -- its "legacy" outcome is captured as the second
(F015_second_fire_*) fields on the neogi row below, explicitly labeled as
the F-015 bug rather than ground truth Part B must preserve (M4 is expected
to delete this second firing, per completion-plan Sec 2.3's correction to
the original plan's D5).
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from engine_c.bindings.engine_bindings import PHASE_MAIN
from engine_c.bindings.c_adapter import CEngineAdapter
from engine_c.bindings.session import CSession
from openspiel_pyrants.state_c import PyrantsCState
from tests.c_engine.card_test_helpers import _make_engine, make_card_test_session


def raw(st):
    return st._adapter._state._s


def _wrap_as_pyspiel(session, num_players):
    """Wrap a CSession-built scenario's live GameState as a PyrantsCState,
    the same construction resample_from_infostate() uses (state_c.py:307-338)."""
    game = load(num_players)
    adapter = CEngineAdapter(session._state, session._engine, session._player_ids, session._seed)
    state = PyrantsCState.__new__(PyrantsCState)
    pyspiel.State.__init__(state, game)
    state._game = game
    state._pending_initial_chance = False
    state._cached_indexed_moves = None
    state._shuffle_seed = session._seed
    state._move_log = []
    state._history_actions = []
    state._adapter = adapter
    return state


def _find_and_apply(state, predicate):
    state.legal_actions()
    indexed = state._cached_indexed_moves
    for i, entry in enumerate(indexed):
        move = entry[1]
        if predicate(move):
            state.apply_action(i)
            return True
    return False


def _play_card(state, card_id):
    return _find_and_apply(state, lambda m: m.move_type == "play_card" and m.data.get("card_id") == card_id)


def _resolve_action_id(state, action_id):
    return _find_and_apply(state, lambda m: m.move_type == "resolve_generic" and m.data.get("action_id") == action_id)


def _resolve_any(state):
    return _find_and_apply(state, lambda m: m.move_type == "resolve_generic")


rows = []
errors = []


# --- Site 1: draw_cards_state (state.c:29-40) -- the automatic per-turn draw ---
def capture_draw_cards_state(seed):
    g = load(2)
    s = fresh(g, seed)
    b = RandomBot(seed * 7)
    for _ in range(15):
        if s.is_terminal() or s.current_player() < 0:
            return None
        s.apply_action(b.step(s))
    if s.is_terminal() or s.current_player() < 0:
        return None
    r = raw(s)
    cur = r.current_player_id
    target_idx = next((pi for pi in range(r.player_count) if r.players[pi].player_id != cur), None)
    if target_idx is None:
        return None
    p = r.players[target_idx]
    pool = [p.discard_pile[i] for i in range(p.discard_pile_count)] + [p.deck[i] for i in range(p.deck_count)]
    if len(pool) < 3:
        return None
    pool = pool[:8]
    for i, sym in enumerate(pool):
        p.discard_pile[i] = sym
    p.discard_pile_count = len(pool)
    p.deck_count = 0
    before_counter = r.shuffle_counter
    s._cached_indexed_moves = None
    for _ in range(30):
        if s.is_terminal() or s.current_player() < 0:
            return None
        r2 = raw(s)
        if r2.shuffle_counter != before_counter:
            after_deck = [str(r2.players[target_idx].deck[i]) for i in range(r2.players[target_idx].deck_count)]
            return {
                "site": "draw_cards_state", "seed": seed, "shuffle_seed": r2.shuffle_seed,
                "shuffle_counter_before": before_counter, "shuffle_counter_after": r2.shuffle_counter,
                "resulting_deck_order": after_deck,
            }
        legal = s.legal_actions()
        if not legal:
            return None
        s.apply_action(legal[0])
    return None


# --- Site 2: reshuffle_discard_into_deck (state.c:219-231), via rules.c:629 cleanup draw ---
def capture_reshuffle_discard(seed):
    g = load(2)
    s = fresh(g, seed)
    b = RandomBot(seed * 11)
    for _ in range(15):
        if s.is_terminal() or s.current_player() < 0:
            return None
        s.apply_action(b.step(s))
    if s.is_terminal() or s.current_player() < 0:
        return None
    r = raw(s)
    cur = r.current_player_id
    target_idx = next((pi for pi in range(r.player_count) if r.players[pi].player_id == cur), None)
    if target_idx is None:
        return None
    p = r.players[target_idx]
    pool = [p.discard_pile[i] for i in range(p.discard_pile_count)] + [p.deck[i] for i in range(p.deck_count)]
    if len(pool) < 3:
        return None
    pool = pool[:8]
    for i, sym in enumerate(pool):
        p.discard_pile[i] = sym
    p.discard_pile_count = len(pool)
    p.deck_count = 0
    before_counter = r.shuffle_counter
    s._cached_indexed_moves = None
    for _ in range(20):
        if s.is_terminal() or s.current_player() < 0:
            return None
        legal_moves = s.legal_actions()
        if not legal_moves:
            return None
        s.apply_action(legal_moves[0])
        r2 = raw(s)
        if r2.shuffle_counter != before_counter:
            after_deck = [str(r2.players[target_idx].deck[i]) for i in range(r2.players[target_idx].deck_count)]
            return {
                "site": "reshuffle_discard_into_deck", "seed": seed, "shuffle_seed": r2.shuffle_seed,
                "shuffle_counter_before": before_counter, "shuffle_counter_after": r2.shuffle_counter,
                "resulting_deck_order": after_deck,
            }
    return None


# --- Site 3: apply_force_discard (actions.c:404-413, random branch), via cranium_rats ---
def capture_force_discard(seed):
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["cranium_rats"], "p2": ["noble", "noble", "noble", "noble", "noble"]},
        current_player="p1", seed=seed,
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    state = _wrap_as_pyspiel(session, 2)
    before_counter = raw(state).shuffle_counter
    if not _play_card(state, "cranium_rats"):
        return None
    for _ in range(4):
        r = raw(state)
        if not r.pending_generic:
            break
        if not _resolve_any(state):
            break
    r = raw(state)
    return {
        "site": "apply_force_discard", "seed": seed, "shuffle_seed": r.shuffle_seed,
        "shuffle_counter_before": before_counter, "shuffle_counter_after": r.shuffle_counter,
        "p2_hand_count_after": r.players[1].hand_count,
    }


# --- Sites 4-7: the four generic_runtime.c mass-discard variants ---
def capture_neogi(seed):
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["neogi"], "p2": ["noble", "noble", "noble", "noble"]},
        current_player="p1", seed=seed,
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    state = _wrap_as_pyspiel(session, 2)
    before_counter = raw(state).shuffle_counter
    if not _play_card(state, "neogi"):
        return None
    for _ in range(6):
        r = raw(state)
        if not r.pending_generic:
            break
        if not _resolve_any(state):
            break
    r = raw(state)
    first_fire_counter = r.shuffle_counter
    first_fire_hand = r.players[1].hand_count
    _find_and_apply(state, lambda m: m.move_type == "end_main_phase")
    r2 = raw(state)
    return {
        "site": "neogi_mass_discard", "seed": seed, "shuffle_seed": r.shuffle_seed,
        "shuffle_counter_before": before_counter,
        "shuffle_counter_after_first_fire": first_fire_counter, "p2_hand_after_first_fire": first_fire_hand,
        "F015_second_fire_shuffle_counter": r2.shuffle_counter, "F015_second_fire_p2_hand": r2.players[1].hand_count,
        "note": "F-015: two discards fire for one neogi play; Part B M4 is expected to leave only the first.",
    }


def capture_mindwitness():
    from pathlib import Path
    scenario = Path("data/scenarios/test_card_generation/013_seed_4_mindwitness.json")
    session = CSession.load(str(scenario))
    num_players = session._state._ptr.contents.player_count
    state = _wrap_as_pyspiel(session, num_players)
    if not _play_card(state, "mindwitness"):
        return None
    r = raw(state)
    before_counter = r.shuffle_counter
    state.legal_actions()
    n_candidates = len(state._cached_indexed_moves)
    # Not every assassinate target's owner has 3+ cards (the discard condition
    # gate) -- try each candidate on a clone until one actually fires a discard.
    for idx in range(n_candidates):
        trial = state.clone()
        trial.apply_action(idx)
        rt = raw(trial)
        if rt.shuffle_counter != before_counter:
            return {
                "site": "mindwitness_conditional_owner_discard", "seed": "scenario_013",
                "shuffle_seed": rt.shuffle_seed,
                "shuffle_counter_before": before_counter, "shuffle_counter_after": rt.shuffle_counter,
            }
    return None


def capture_chuul(seed):
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2", "p3"],
        hand={"p1": ["chuul"], "p2": ["noble"] * 4, "p3": ["noble"] * 2},
        troops={"p2": {"site_gauntlgrym": ["p2", "p3"]}},
        current_player="p1", seed=seed,
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    state = _wrap_as_pyspiel(session, 3)
    if not _play_card(state, "chuul"):
        return None
    r = raw(state)
    before_counter = r.shuffle_counter
    if not _resolve_action_id(state, "site_gauntlgrym"):
        return None
    r = raw(state)
    return {
        "site": "chuul_local_discard", "seed": seed, "shuffle_seed": r.shuffle_seed,
        "shuffle_counter_before": before_counter, "shuffle_counter_after": r.shuffle_counter,
    }


def capture_nothic(seed):
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2", "p3"],
        hand={"p1": ["nothic"], "p2": ["noble"] * 4, "p3": ["noble"] * 2},
        deck={"p1": ["soldier"]},
        spies={"site_gauntlgrym": ["p1"]},
        current_player="p1", seed=seed,
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    state = _wrap_as_pyspiel(session, 3)
    if not _play_card(state, "nothic"):
        return None
    if not _resolve_action_id(state, "option_2"):
        return None
    r = raw(state)
    before_counter = r.shuffle_counter
    if not _resolve_action_id(state, "site_gauntlgrym"):
        return None
    r = raw(state)
    return {
        "site": "nothic_mass_discard", "seed": seed, "shuffle_seed": r.shuffle_seed,
        "shuffle_counter_before": before_counter, "shuffle_counter_after": r.shuffle_counter,
    }


for sd in range(11, 11 + 8 * 5, 5):
    try:
        row = capture_draw_cards_state(sd)
        if row:
            rows.append(row)
    except Exception as e:
        errors.append(f"draw_cards_state seed={sd}: {e}")

for sd in range(13, 13 + 8 * 5, 5):
    try:
        row = capture_reshuffle_discard(sd)
        if row:
            rows.append(row)
    except Exception as e:
        errors.append(f"reshuffle_discard_into_deck seed={sd}: {e}")

for sd in (1, 2, 3, 4, 5, 6, 7, 8):
    try:
        row = capture_force_discard(sd)
        if row:
            rows.append(row)
    except Exception as e:
        errors.append(f"apply_force_discard seed={sd}: {e}")

for sd in (1, 2, 3, 4, 5):
    for fn in (capture_neogi, capture_chuul, capture_nothic):
        try:
            row = fn(sd)
            if row:
                rows.append(row)
        except Exception as e:
            errors.append(f"{fn.__name__} seed={sd}: {e}")

try:
    row = capture_mindwitness()
    if row:
        rows.append(row)
except Exception as e:
    errors.append(f"capture_mindwitness: {e}")

sites_seen = sorted(set(r["site"] for r in rows))
print(f"# F-003 Part B Phase 0: frozen legacy-path baseline")
print(f"# {len(rows)} rows captured across {len(sites_seen)} sites: {sites_seen}")
if errors:
    print(f"# {len(errors)} capture attempts errored (printed to stderr, not fatal)")
    for e in errors:
        print(f"#   {e}", file=sys.stderr)
for row in rows:
    print(json.dumps(row, sort_keys=True))
