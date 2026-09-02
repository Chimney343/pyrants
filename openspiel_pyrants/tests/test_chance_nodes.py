"""RED tests for F-003 Part B: mid-game random events as OpenSpiel chance nodes.

Pre-GREEN (no `PendingChanceState`/`MOVE_RESOLVE_CHANCE` machinery exists yet —
see docs/validation/f002-f003-completion-plan.md Sec 2.3/2.4), every test in
this file is expected to FAIL: `is_chance_node()`/`chance_outcomes()` are
still gated solely on `_pending_initial_chance` (`state_c.py:202-210`), which
is False for the entire mid-game, so every assertion below that expects a
chance node to appear mid-game currently sees `is_chance_node()==False`.

T-B1/T-B2/T-B5 correspond to `docs/validation/f002-f003-fix-plan.md` Sec 14's
RED-test table. T-B4 is `docs/validation/harness/f003_chance_nodes.py` (a
script, not a pytest test, per the fix plan's own table) and is not
duplicated here. T-B3's behavior-preservation comparison depends on Part B's
actual `apply_resolve_chance` semantics, which do not exist yet as code (only
as a proposed design, completion-plan Sec 2.3) -- it asserts the same
pre-fix RED condition as T-B1/T-B2 and leaves the post-GREEN comparison
against the frozen legacy baseline for whoever lands M1-M4 to complete once
the real outcome-index semantics exist to compare against.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401
from engine_c.bindings.c_adapter import CEngineAdapter
from engine_c.bindings.engine_bindings import PHASE_MAIN
from engine_c.bindings.session import CSession
from openspiel_pyrants.state_c import PyrantsCState
from tests.c_engine.card_test_helpers import _make_engine, make_card_test_session

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASELINE_PATH = _REPO_ROOT / "docs" / "validation" / "baseline" / "f003_legacy_path.pre.txt"
_MINDWITNESS_SCENARIO = _REPO_ROOT / "data" / "scenarios" / "test_card_generation" / "013_seed_4_mindwitness.json"


def _load_c_game(num_players: int = 2):
    return pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})


class _RandomBot:
    """Uniform-random over legal actions -- local copy of
    docs/validation/harness/common.py's RandomBot, self-contained here since
    docs/validation/harness is a standalone script tree, not an importable
    package this test suite should depend on."""

    def __init__(self, seed: int):
        import numpy as np

        self.rng = np.random.RandomState(seed)

    def step(self, state):
        legal = state.legal_actions()
        return int(self.rng.choice(legal))


def raw(state):
    """Direct struct access -- mirrors harness/common.py's raw() and
    test_observation_completeness.py::_force_discard's access chain."""
    return state._adapter._state._s


def _wrap_as_pyspiel(session: CSession, num_players: int):
    """Wrap a CSession-built scenario's live GameState as a PyrantsCState,
    the same construction resample_from_infostate() uses (state_c.py:307-338).
    Lets T-B1/T-B3/T-B5 reuse tests/c_engine/card_test_helpers.py's proven
    scenario-construction pattern (built for CSession) through the
    is_chance_node()/chance_outcomes() OpenSpiel-level API, which only
    PyrantsCState exposes.
    """
    game = _load_c_game(num_players)
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


def _find_and_apply(state, predicate) -> bool:
    state.legal_actions()
    indexed = state._cached_indexed_moves
    for i, entry in enumerate(indexed):
        move = entry[1]
        if predicate(move):
            state.apply_action(i)
            return True
    return False


def _play_card(state, card_id: str) -> bool:
    return _find_and_apply(state, lambda m: m.move_type == "play_card" and m.data.get("card_id") == card_id)


def _resolve_action_id(state, action_id: str) -> bool:
    return _find_and_apply(
        state, lambda m: m.move_type == "resolve_generic" and m.data.get("action_id") == action_id
    )


def _load_legacy_baseline() -> list[dict]:
    rows = []
    with open(_BASELINE_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("{"):
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Scenario builders -- one per §1(b) site this file exercises, following the
# card->site trace in docs/validation/f002-f003-completion-plan.md Sec 2.4.
# ---------------------------------------------------------------------------


def _chuul_scenario():
    """Reaches generic_runtime.c local_discard (Chuul) -- mirrors
    tests/c_engine/test_card_chuul.py's proven-working CSession scenario."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2", "p3"],
        hand={"p1": ["chuul"], "p2": ["noble"] * 4, "p3": ["noble"] * 2},
        troops={"p2": {"site_gauntlgrym": ["p2", "p3"]}},
        current_player="p1",
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    return _wrap_as_pyspiel(session, 3)


def _nothic_scenario():
    """Reaches generic_runtime.c mass_discard (Nothic option_2)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2", "p3"],
        hand={"p1": ["nothic"], "p2": ["noble"] * 4, "p3": ["noble"] * 2},
        deck={"p1": ["soldier"]},
        spies={"site_gauntlgrym": ["p1"]},
        current_player="p1",
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    return _wrap_as_pyspiel(session, 3)


def _neogi_scenario():
    """Reaches generic_runtime.c end_of_turn_mass_discard (Neogi) -- also the
    site behind rules.c:530-538 (F-015: the SAME action fires a second time
    at real end-of-turn; not modeled as a distinct site here, see Sec 2.4)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["neogi"], "p2": ["noble", "noble", "noble", "noble"]},
        current_player="p1",
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    return _wrap_as_pyspiel(session, 2)


def _cranium_rats_scenario():
    """Reaches actions.c apply_force_discard's random branch (source_fragment
    "targeted_discard", matching the function's own code comment)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["cranium_rats"], "p2": ["noble", "noble", "noble", "noble", "noble"]},
        current_player="p1",
    )
    s = session._state._ptr.contents
    s.phase = PHASE_MAIN
    return _wrap_as_pyspiel(session, 2)


def _mindwitness_scenario():
    """Reaches generic_runtime.c conditional_owner_discard (Mindwitness),
    reusing the already-committed scenario fixture from the CSession-level
    card test."""
    session = CSession.load(str(_MINDWITNESS_SCENARIO))
    num_players = session._state._ptr.contents.player_count
    return _wrap_as_pyspiel(session, num_players)


def _force_empty_deck_nonempty_discard(state, player_index: int, cards: list[str]):
    """Direct struct injection (mirrors f002b.py/f002_reroll.py's prep()):
    guarantees the next draw for this player MUST reshuffle."""
    from engine_c.bindings.engine_bindings import _lib

    s = raw(state)
    ps = s.players[player_index]
    ps.discard_pile_count = min(len(cards), 80)
    for j, cid in enumerate(cards[: ps.discard_pile_count]):
        ps.discard_pile[j] = _lib.intern(cid.encode())
    ps.deck_count = 0
    state._cached_indexed_moves = None


def _drive_until_shuffle_counter_changes(state, max_steps: int = 30):
    """Steps a fixed policy (first legal action each time) until
    shuffle_counter changes. Returns (was_chance_immediately_before, state)
    or (None, state) if the budget ran out without a change.
    """
    before = raw(state).shuffle_counter
    for _ in range(max_steps):
        if state.is_terminal() or state.current_player() < 0:
            return None, state
        was_chance = state.is_chance_node()
        legal = state.legal_actions()
        if not legal:
            return None, state
        state.apply_action(legal[0])
        if raw(state).shuffle_counter != before:
            return was_chance, state
    return None, state


# ---------------------------------------------------------------------------
# T-B1: a forced-discard event is a chance node
# ---------------------------------------------------------------------------


def test_forced_discard_is_chance_node():
    """T-B1: is_chance_node()==True immediately before a forced-discard
    event resolves, with chance_outcomes() length == the target's hand size.

    Pre-fix: FAIL -- is_chance_node() is False (F-003's own defect: the
    discard resolves silently, inline, within the same apply_action() that
    places Chuul's spy).
    """
    state = _chuul_scenario()
    assert _play_card(state, "chuul")
    assert raw(state).pending_generic, "expected Chuul's spy-placement choice to still be pending"

    p2_hand_before = raw(state).players[1].hand_count
    assert p2_hand_before >= 3, "P2 must have 3+ cards for local_discard's condition to fire"

    assert _resolve_action_id(state, "site_gauntlgrym"), "spy-placement target not found"

    assert state.is_chance_node(), (
        "expected a chance node exposing the forced-discard event immediately after "
        "Chuul's spy placement resolves; got is_chance_node()==False, meaning the "
        "discard already resolved silently inline (F-003)"
    )
    outcomes = state.chance_outcomes()
    p2_hand_now = raw(state).players[1].hand_count
    assert p2_hand_now == p2_hand_before, "hand should not shrink until the chance outcome is applied"
    assert len(outcomes) == p2_hand_now, "chance_outcomes() length must equal the target's current hand size"
    probs = [p for _, p in outcomes]
    assert probs and all(abs(p - probs[0]) < 1e-9 for p in probs), "outcomes must be uniformly weighted"
    assert abs(sum(probs) - 1.0) < 1e-9, "outcome probabilities must sum to 1"


# ---------------------------------------------------------------------------
# T-B2: a reshuffle exposes a sequence of chance nodes (D3)
# ---------------------------------------------------------------------------


def test_reshuffle_is_chance_node_sequence():
    """T-B2: driving a state to an empty-deck/nonempty-discard reshuffle
    exposes a chance node immediately before the reshuffle-triggered
    shuffle_counter advance, per D3's per-position decomposition.

    Pre-fix: FAIL -- is_chance_node() is False at every step, so
    was_chance is None (the driver never observes a True immediately
    preceding the shuffle_counter change).
    """
    game = _load_c_game(2)
    state = game.new_initial_state()
    state.apply_action(42)

    bot = _RandomBot(7)
    for _ in range(15):
        if state.is_terminal() or state.current_player() < 0:
            pytest.skip("game ended before reaching a reshuffle setup point")
        state.apply_action(bot.step(state))

    s = raw(state)
    cur = s.current_player_id
    target_idx = next((pi for pi in range(s.player_count) if s.players[pi].player_id != cur), None)
    if target_idx is None:
        pytest.skip("could not find a non-current player to seed the reshuffle for")

    p = s.players[target_idx]
    pool = [p.discard_pile[i] for i in range(p.discard_pile_count)] + [p.deck[i] for i in range(p.deck_count)]
    if len(pool) < 3:
        pytest.skip("not enough cards pooled to force a reshuffle")
    pool = pool[:8]
    for i, sym in enumerate(pool):
        p.discard_pile[i] = sym
    p.discard_pile_count = len(pool)
    p.deck_count = 0
    state._cached_indexed_moves = None

    was_chance, state = _drive_until_shuffle_counter_changes(state, max_steps=30)
    assert was_chance is not None, "shuffle_counter never advanced -- reshuffle was not reached"
    assert was_chance is True, (
        "expected is_chance_node()==True on the step immediately before the reshuffle-triggered "
        "shuffle_counter advance; got False, meaning the reshuffle resolved silently (F-003)"
    )


# ---------------------------------------------------------------------------
# T-B3: chance-outcome application matches the frozen legacy-path baseline
# ---------------------------------------------------------------------------


def test_chance_outcome_application_matches_legacy_rng_path():
    """T-B3 (GB3): applying each declared chance outcome must reproduce what
    the old inline-RNG path produced for the same (shuffle_seed,
    shuffle_counter), per the frozen legacy baseline captured in Phase 0
    (docs/validation/baseline/f003_legacy_path.pre.txt) before any Part B
    code exists to compare against.

    This is N/A pre-fix in the sense the fix plan's own Sec 14 states: there
    is no explicit-chance path yet to apply outcomes against. What this test
    can and does check today is the same is_chance_node() precondition
    T-B1/T-B2 check -- it FAILS at that assertion, for the same reason.

    The full baseline-vs-new-path comparison (walking each frozen row,
    finding the chance_outcomes() index matching its recorded result, and
    asserting the resulting deck/hand state matches byte-for-byte) depends
    on apply_resolve_chance's actual outcome-index semantics, which do not
    exist as code yet -- only as the proposed design in
    docs/validation/f002-f003-completion-plan.md Sec 2.3. That comparison
    is left for whoever lands the milestone that first makes a given site's
    chance node real (M1 for draw_cards_state/reshuffle rows, M3 for the
    apply_force_discard row, M4 for the four card-triggered rows) to
    complete against this same baseline file, not invented speculatively
    here against machinery that does not exist yet.
    """
    rows = _load_legacy_baseline()
    assert rows, f"legacy baseline is empty -- expected rows captured at {_BASELINE_PATH}"
    sites_in_baseline = {r["site"] for r in rows}
    assert "reshuffle_discard_into_deck" in sites_in_baseline
    assert "apply_force_discard" in sites_in_baseline

    # Same precondition T-B1/T-B2 check, exercised here on the Chuul scenario
    # (a card-triggered forced-discard row) since it is present in the
    # baseline and does not depend on RandomBot's stochastic setup.
    state = _chuul_scenario()
    assert _play_card(state, "chuul")
    assert _resolve_action_id(state, "site_gauntlgrym")
    assert state.is_chance_node(), (
        "expected a chance node before the discard resolves (same precondition as T-B1); "
        "got False -- GB3's outcome-replay comparison cannot run until this holds"
    )
    # Once the above holds post-GREEN, extend this test to walk `rows`,
    # re-derive the matching chance_outcomes() index for each recorded
    # event, apply it, and assert the resulting state matches the baseline
    # row's resulting_deck_order / hand-count fields exactly.


# ---------------------------------------------------------------------------
# T-B5: every §1(b) site is individually converted (GB6)
# ---------------------------------------------------------------------------


def test_site_draw_cards_state_is_chance_node():
    """T-B5 (site 1/7 effective): state.c:29-40 draw_cards_state's automatic
    per-turn draw exposes a chance node when it must reshuffle.

    Pre-fix: FAIL -- same reason as T-B2 (this is the same underlying
    struct-injection technique, targeting the OTHER of the two reshuffle
    implementations noted in the original fix plan Sec 1(d))."""
    game = _load_c_game(2)
    state = game.new_initial_state()
    state.apply_action(11)

    bot = _RandomBot(11 * 7)
    for _ in range(15):
        if state.is_terminal() or state.current_player() < 0:
            pytest.skip("game ended before reaching a draw-phase setup point")
        state.apply_action(bot.step(state))

    s = raw(state)
    cur = s.current_player_id
    target_idx = next((pi for pi in range(s.player_count) if s.players[pi].player_id != cur), None)
    if target_idx is None:
        pytest.skip("could not find a non-current player to seed the draw for")
    p = s.players[target_idx]
    pool = [p.discard_pile[i] for i in range(p.discard_pile_count)] + [p.deck[i] for i in range(p.deck_count)]
    if len(pool) < 3:
        pytest.skip("not enough cards pooled to force a reshuffle")
    pool = pool[:8]
    for i, sym in enumerate(pool):
        p.discard_pile[i] = sym
    p.discard_pile_count = len(pool)
    p.deck_count = 0
    state._cached_indexed_moves = None

    was_chance, state = _drive_until_shuffle_counter_changes(state, max_steps=30)
    assert was_chance is not None, "shuffle_counter never advanced -- draw_cards_state's reshuffle was not reached"
    assert was_chance is True


def test_site_apply_force_discard_is_chance_node():
    """T-B5 (site 2/7): actions.c:404-413 apply_force_discard's random
    branch, via cranium_rats."""
    state = _cranium_rats_scenario()
    assert _play_card(state, "cranium_rats")
    for _ in range(4):
        if not raw(state).pending_generic:
            break
        if not _find_and_apply(state, lambda m: m.move_type == "resolve_generic"):
            break
    assert state.is_chance_node(), "expected a chance node before apply_force_discard's random pick resolves"


def test_site_neogi_mass_discard_is_chance_node():
    """T-B5 (site 3/7): generic_runtime.c:519-548 end_of_turn_mass_discard
    (Neogi) -- also covers rules.c:530-538 (F-015: confirmed to be the SAME
    action firing a second time, not an independent site; see Sec 2.4)."""
    state = _neogi_scenario()
    assert _play_card(state, "neogi")
    for _ in range(6):
        if not raw(state).pending_generic:
            break
        if not _find_and_apply(state, lambda m: m.move_type == "resolve_generic"):
            break
    assert state.is_chance_node(), "expected a chance node before Neogi's end-of-turn mass discard resolves"


def test_site_chuul_local_discard_is_chance_node():
    """T-B5 (site 4/7): generic_runtime.c:593-633 local_discard (Chuul) --
    same scenario as T-B1, kept separate per §1(b)'s per-site enumeration."""
    state = _chuul_scenario()
    assert _play_card(state, "chuul")
    assert _resolve_action_id(state, "site_gauntlgrym")
    assert state.is_chance_node(), "expected a chance node before Chuul's local_discard resolves"


def test_site_nothic_mass_discard_is_chance_node():
    """T-B5 (site 5/7): generic_runtime.c:635-665 mass_discard (Nothic
    option_2)."""
    state = _nothic_scenario()
    assert _play_card(state, "nothic")
    assert _resolve_action_id(state, "option_2")
    assert _resolve_action_id(state, "site_gauntlgrym")
    assert state.is_chance_node(), "expected a chance node before Nothic's mass_discard resolves"


def test_site_mindwitness_conditional_owner_discard_is_chance_node():
    """T-B5 (site 6/7): generic_runtime.c:550-591 conditional_owner_discard
    (Mindwitness). Tries each assassinate target on a clone until one
    actually meets the 3+-card discard condition (mirrors the legacy
    baseline capture's own approach)."""
    state = _mindwitness_scenario()
    assert _play_card(state, "mindwitness")
    state.legal_actions()
    n_candidates = len(state._cached_indexed_moves)
    assert n_candidates > 0, "no assassinate targets available in the Mindwitness scenario"

    found_pending = False
    for idx in range(n_candidates):
        trial = state.clone()
        trial.apply_action(idx)
        if trial.is_chance_node():
            found_pending = True
            break

    assert found_pending, (
        "expected at least one assassinate target to expose a chance node before "
        "Mindwitness's conditional_owner_discard resolves; none did (F-003)"
    )


def test_site_reshuffle_discard_into_deck_is_chance_node():
    """T-B5 (site 7/7): state.c:219-231 reshuffle_discard_into_deck, reached
    via rules.c:629's cleanup-phase draw-up-to-5 (distinct from
    draw_cards_state's own inline reshuffle, per the original fix plan's
    §1(d) note that these are two separate implementations)."""
    game = _load_c_game(2)
    state = game.new_initial_state()
    state.apply_action(13)

    bot = _RandomBot(13 * 11)
    for _ in range(15):
        if state.is_terminal() or state.current_player() < 0:
            pytest.skip("game ended before reaching a cleanup setup point")
        state.apply_action(bot.step(state))

    s = raw(state)
    cur = s.current_player_id
    target_idx = next((pi for pi in range(s.player_count) if s.players[pi].player_id == cur), None)
    if target_idx is None:
        pytest.skip("could not find the current player to seed the cleanup reshuffle for")
    p = s.players[target_idx]
    pool = [p.discard_pile[i] for i in range(p.discard_pile_count)] + [p.deck[i] for i in range(p.deck_count)]
    if len(pool) < 3:
        pytest.skip("not enough cards pooled to force a reshuffle")
    pool = pool[:8]
    for i, sym in enumerate(pool):
        p.discard_pile[i] = sym
    p.discard_pile_count = len(pool)
    p.deck_count = 0
    state._cached_indexed_moves = None

    was_chance, state = _drive_until_shuffle_counter_changes(state, max_steps=30)
    assert was_chance is not None, "shuffle_counter never advanced -- reshuffle_discard_into_deck was not reached"
    assert was_chance is True
