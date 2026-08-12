"""Cross-validation tests: C engine vs Python engine.

Loads the same game definition in both engines, creates initial states
with the same seed, and verifies that:

1. legal_moves() produces the same set of moves
2. apply() produces equivalent states
3. Terminal detection matches
4. Winner determination matches
5. Phase transitions match
"""

import sys
import os
import ctypes

# Add engine_c bindings to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "engine_c", "bindings"))

import pytest

from engine.state import (
    GameState,
    TurnPhase,
    build_initial_game_state,
)
from engine.rules import (
    legal_moves as py_legal_moves,
    apply as py_apply,
    is_terminal as py_is_terminal,
    winner as py_winner,
)
from engine.moves import (
    AssassinateMove,
    DeployMove,
    EndMainPhaseMove,
    InitialPlacementMove,
    Move,
    PlayCardMove,
    PromoteCardMove,
    ResolveCleanupMove,
    ResolveEndOfTurnMove,
    SkipPromoteMove,
)
from game_setup.loaders import build_game_definition_from_files

from engine_bindings import (
    _lib, Move as CMove, GameStateStruct, Sym,
    MOVE_PLAY_CARD, MOVE_END_MAIN_PHASE, MOVE_RESOLVE_END_OF_TURN,
    MOVE_RESOLVE_CLEANUP, MOVE_ASSASSINATE, MOVE_DEPLOY,
    MOVE_RECRUIT, MOVE_RETURN_SPY, MOVE_ACTIVATE_ABILITY,
    MOVE_DECLINE_ABILITY, MOVE_PROMOTE_CARD, MOVE_SKIP_PROMOTE,
    MOVE_RESOLVE_GENERIC, MOVE_INITIAL_PLACEMENT,
    PHASE_SETUP, PHASE_DRAW, PHASE_MAIN, PHASE_END_OF_TURN,
    PHASE_CLEANUP, PHASE_GAME_OVER,
)

from ctypes import c_int


# ── helpers ───────────────────────────────────────────────────────────────

def _sym_str(sym):
    """Decode interned Sym to Python str."""
    if sym == 0:
        return None
    return _lib.intern_str(sym).decode()


def _setup_c_engine():
    """Initialize the C engine and return a callable that creates states."""
    _lib.intern_init(4096)
    _lib.register_default_effects()

    arena = _lib.arena_create(8 * 1024 * 1024)

    catalog_path = os.path.join("data", "cards", "catalog.json")
    board_path = os.path.join("data", "boards", "tyrants_of_the_underdark.json")
    setup_path = os.path.join("data", "decks", "base_setup.json")

    def_ptr = _lib.engine_load_definition(
        catalog_path.encode(), board_path.encode(), setup_path.encode(), arena
    )
    assert def_ptr, "Failed to load game definition in C engine"

    def create(seed):
        pids = (ctypes.c_char_p * 2)(b"p1", b"p2")
        gs = _lib.engine_create_game_definition(def_ptr, pids, 2, seed)
        assert gs, "Failed to create game state in C engine"
        return gs

    return create


def _move_type_to_python(move_type):
    """Map C MoveType to Python move class."""
    if move_type == MOVE_INITIAL_PLACEMENT:
        return "initial_placement"
    if move_type == MOVE_PLAY_CARD:
        return "play_card"
    if move_type == MOVE_END_MAIN_PHASE:
        return "end_main_phase"
    if move_type == MOVE_RESOLVE_END_OF_TURN:
        return "resolve_end_of_turn"
    if move_type == MOVE_RESOLVE_CLEANUP:
        return "resolve_cleanup"
    if move_type == MOVE_ASSASSINATE:
        return "assassinate"
    if move_type == MOVE_DEPLOY:
        return "deploy"
    if move_type == MOVE_RECRUIT:
        return "recruit"
    if move_type == MOVE_RETURN_SPY:
        return "return_spy"
    if move_type == MOVE_ACTIVATE_ABILITY:
        return "activate_ability"
    if move_type == MOVE_DECLINE_ABILITY:
        return "decline_ability"
    if move_type == MOVE_PROMOTE_CARD:
        return "promote_card"
    if move_type == MOVE_SKIP_PROMOTE:
        return "skip_promote"
    if move_type == MOVE_RESOLVE_GENERIC:
        return "resolve_generic"
    return "unknown"


_move_name_to_py = {
    "initial_placement": InitialPlacementMove,
    "play_card": PlayCardMove,
    "end_main_phase": EndMainPhaseMove,
    "resolve_end_of_turn": ResolveEndOfTurnMove,
    "resolve_cleanup": ResolveCleanupMove,
    "assassinate": AssassinateMove,
    "deploy": DeployMove,
    "promote_card": PromoteCardMove,
    "skip_promote": SkipPromoteMove,
}


def _c_move_to_dict(c_move, player_id):
    """Convert a C Move to a Python dict representing the move."""
    mt = _move_type_to_python(c_move.type)
    result = {"type": mt, "player_id": _sym_str(player_id)}
    if mt == "initial_placement":
        result["target_node_id"] = _sym_str(c_move.data.initial_placement.node_id)
    elif mt == "play_card":
        result["card_id"] = _sym_str(c_move.data.play_card.card_id)
        result["hand_index"] = c_move.data.play_card.hand_index
    elif mt == "assassinate":
        result["target_node_id"] = _sym_str(c_move.data.assassinate.target_node_id)
        result["target_slot_index"] = c_move.data.assassinate.slot_index
    elif mt == "deploy":
        result["target_node_id"] = _sym_str(c_move.data.deploy.node_id)
    elif mt == "recruit":
        result["card_id"] = _sym_str(c_move.data.recruit.card_id)
    elif mt == "return_spy":
        result["node_id"] = _sym_str(c_move.data.return_spy.node_id)
        result["spy_owner_id"] = _sym_str(c_move.data.return_spy.spy_owner_id)
    elif mt == "activate_ability":
        result["card_id"] = _sym_str(c_move.data.activate_ability.card_id)
        result["ability_key"] = _sym_str(c_move.data.activate_ability.ability_key)
    elif mt == "decline_ability":
        result["card_id"] = _sym_str(c_move.data.decline_ability.card_id)
        result["ability_key"] = _sym_str(c_move.data.decline_ability.ability_key)
    elif mt == "promote_card":
        result["card_id"] = _sym_str(c_move.data.promote_card.card_id)
    return result


def _py_move_to_dict(move):
    """Convert a Python Move to a dict."""
    if isinstance(move, InitialPlacementMove):
        return {"type": "initial_placement", "player_id": move.player_id,
                "target_node_id": move.target_node_id}
    if isinstance(move, PlayCardMove):
        return {"type": "play_card", "player_id": move.player_id,
                "card_id": move.card_id, "hand_index": move.hand_index}
    if isinstance(move, EndMainPhaseMove):
        return {"type": "end_main_phase", "player_id": move.player_id}
    if isinstance(move, ResolveEndOfTurnMove):
        return {"type": "resolve_end_of_turn", "player_id": move.player_id}
    if isinstance(move, ResolveCleanupMove):
        return {"type": "resolve_cleanup", "player_id": move.player_id}
    if isinstance(move, AssassinateMove):
        return {"type": "assassinate", "player_id": move.player_id,
                "target_node_id": move.target_node_id,
                "target_slot_index": move.target_slot_index}
    if isinstance(move, DeployMove):
        return {"type": "deploy", "player_id": move.player_id,
                "target_node_id": move.target_node_id}
    if isinstance(move, PromoteCardMove):
        return {"type": "promote_card", "player_id": move.player_id,
                "card_id": move.card_id}
    return {"type": str(type(move).__name__), "player_id": move.player_id}


def _move_dict_sort_key(m):
    """Sort key for move dicts — by type, then player, then args."""
    return (m.get("type", ""), m.get("player_id", ""),
            str(sorted(m.items())))


def _compare_move_sets(py_moves, c_moves, c_state):
    """Compare Python moves list to C moves list. Returns list of discrepancies."""
    py_dicts = [_py_move_to_dict(m) for m in py_moves]
    c_dicts = [_c_move_to_dict(m, c_state.contents.current_player_id)
               for m in c_moves]

    py_sorted = sorted(py_dicts, key=_move_dict_sort_key)
    c_sorted = sorted(c_dicts, key=_move_dict_sort_key)

    py_keys = set(tuple(sorted(d.items())) for d in py_dicts)
    c_keys = set(tuple(sorted(d.items())) for d in c_dicts)

    only_py = py_keys - c_keys
    only_c = c_keys - py_keys

    return only_py, only_c, len(py_sorted), len(c_sorted)


# ── tests ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def py_def():
    """Load the Python game definition once."""
    from pathlib import Path
    return build_game_definition_from_files(
        Path("data/boards/tyrants_of_the_underdark.json"),
        Path("data/cards/catalog.json"),
        Path("data/decks/base_setup.json"),
    )


@pytest.fixture(scope="session")
def c_create():
    """Return a callable that creates C engine states."""
    return _setup_c_engine()


def test_both_engines_load(py_def, c_create):
    """Verify both engines can load the game definition."""
    assert py_def is not None
    c_state = c_create(42)
    assert c_state is not None
    _lib.engine_destroy(c_state)


def test_initial_state_phase(py_def, c_create):
    """Both engines start in SETUP phase."""
    py_state = build_initial_game_state(py_def, ["p1", "p2"], shuffle_seed=42)
    c_state = c_create(42)

    assert py_state.phase == TurnPhase.SETUP
    assert c_state.contents.phase == PHASE_SETUP

    _lib.engine_destroy(c_state)


def test_setup_legal_moves(py_def, c_create):
    """Both engines produce the same initial placement moves."""
    py_state = build_initial_game_state(py_def, ["p1", "p2"], shuffle_seed=42)
    c_state = c_create(42)

    py_moves = py_legal_moves(py_state)
    c_moves = (CMove * 64)()
    c_count = _lib.engine_legal_moves(c_state, c_moves, 64)
    c_moves_list = [c_moves[i] for i in range(c_count)]

    only_py, only_c, py_n, c_n = _compare_move_sets(py_moves, c_moves_list, c_state)

    assert py_n == c_n, f"Move counts differ: Python={py_n}, C={c_n}"
    assert not only_py, f"Moves only in Python: {only_py}"
    assert not only_c, f"Moves only in C: {only_c}"

    _lib.engine_destroy(c_state)


def test_apply_initial_placement(py_def, c_create):
    """Both engines transition from SETUP correctly after initial placement."""
    py_state = build_initial_game_state(py_def, ["p1", "p2"], shuffle_seed=42)
    c_state = c_create(42)

    py_moves = py_legal_moves(py_state)
    py_move = py_moves[0]

    c_moves = (CMove * 64)()
    c_count = _lib.engine_legal_moves(c_state, c_moves, 64)
    assert c_count > 0

    # Find matching C move
    py_node = py_move.target_node_id
    c_move = None
    for i in range(c_count):
        if _sym_str(c_moves[i].data.initial_placement.node_id) == py_node:
            c_move = c_moves[i]
            break
    assert c_move is not None, f"No C move for node {py_node}"

    py_result = py_apply(py_state, py_move)
    c_result = _lib.engine_apply(c_state, ctypes.byref(c_move))

    assert c_result is not None
    assert py_result.phase.value == {0: "setup", 1: "draw", 2: "main",
                                     3: "end_of_turn", 4: "cleanup",
                                     5: "game_over"}[c_result.contents.phase]

    assert _sym_str(c_result.contents.current_player_id) == py_result.current_player_id

    _lib.engine_destroy(c_state)
    _lib.engine_destroy(c_result)


def test_complete_setup_phase(py_def, c_create):
    """Both engines complete setup and transition to MAIN."""
    py_state = build_initial_game_state(py_def, ["p1", "p2"], shuffle_seed=42)
    c_state = c_create(42)

    # Apply initial placements for both players
    for i in range(2):
        py_moves = py_legal_moves(py_state)
        py_state = py_apply(py_state, py_moves[0])

        c_moves = (CMove * 64)()
        c_count = _lib.engine_legal_moves(c_state, c_moves, 64)
        c_result = _lib.engine_apply(c_state, ctypes.byref(c_moves[0]))
        _lib.engine_destroy(c_state)
        c_state = c_result

    assert py_state.phase == TurnPhase.MAIN
    assert c_state.contents.phase == PHASE_MAIN

    _lib.engine_destroy(c_state)


def test_draw_to_main_phase(py_def, c_create):
    """Both engines reach MAIN phase after initial placements."""
    py_state = build_initial_game_state(py_def, ["p1", "p2"], shuffle_seed=42)
    c_state = c_create(42)

    for _ in range(2):
        py_moves = py_legal_moves(py_state)
        py_state = py_apply(py_state, py_moves[0])

        c_moves = (CMove * 64)()
        c_count = _lib.engine_legal_moves(c_state, c_moves, 64)
        c_result = _lib.engine_apply(c_state, ctypes.byref(c_moves[0]))
        _lib.engine_destroy(c_state)
        c_state = c_result

    assert py_state.phase == TurnPhase.MAIN
    assert c_state.contents.phase == PHASE_MAIN

    py_hand_size = len(py_state.players["p1"].hand)
    c_hand_size = c_state.contents.players[0].hand_count
    assert py_hand_size == c_hand_size, \
        f"Hand sizes differ: Python={py_hand_size}, C={c_hand_size}"

    _lib.engine_destroy(c_state)


def test_main_phase_has_play_card(py_def, c_create):
    """Both engines offer play_card moves in MAIN phase."""
    py_state = build_initial_game_state(py_def, ["p1", "p2"], shuffle_seed=42)
    c_state = c_create(42)

    for _ in range(2):
        py_moves = py_legal_moves(py_state)
        py_state = py_apply(py_state, py_moves[0])

        c_moves = (CMove * 64)()
        c_count = _lib.engine_legal_moves(c_state, c_moves, 64)
        c_result = _lib.engine_apply(c_state, ctypes.byref(c_moves[0]))
        _lib.engine_destroy(c_state)
        c_state = c_result

    py_moves = py_legal_moves(py_state)
    c_moves = (CMove * 64)()
    c_count = _lib.engine_legal_moves(c_state, c_moves, 64)

    py_play_count = sum(1 for m in py_moves if isinstance(m, PlayCardMove))
    c_play_count = sum(1 for i in range(c_count) if c_moves[i].type == MOVE_PLAY_CARD)

    assert py_play_count > 0, "Python engine has no play_card moves"
    assert c_play_count > 0, "C engine has no play_card moves"

    end_main_py = sum(1 for m in py_moves if isinstance(m, EndMainPhaseMove))
    end_main_c = sum(1 for i in range(c_count) if c_moves[i].type == MOVE_END_MAIN_PHASE)
    assert end_main_py == end_main_c, \
        f"End main count mismatch: Python={end_main_py}, C={end_main_c}"

    _lib.engine_destroy(c_state)


def test_terminal_detection(py_def, c_create):
    """Both engines agree on terminal conditions."""
    py_state = build_initial_game_state(py_def, ["p1", "p2"], shuffle_seed=42)
    c_state = c_create(42)

    assert not py_is_terminal(py_state)
    assert not _lib.engine_is_terminal(c_state)

    # Force game over
    py_state = build_initial_game_state(py_def, ["p1", "p2"], shuffle_seed=42)
    from engine.phases import set_game_over as py_set_game_over
    py_state = py_set_game_over(py_state, {})

    _lib.set_game_over(c_state)

    assert py_is_terminal(py_state)
    assert _lib.engine_is_terminal(c_state)

    py_w = py_winner(py_state)
    c_score = c_int()
    c_w = _lib.engine_winner(c_state, ctypes.byref(c_score))
    assert (py_w is None) == (c_w == 0)

    _lib.engine_destroy(c_state)


def test_resource_after_card_play(py_def, c_create):
    """Playing a card gives resources in both engines."""
    py_state = build_initial_game_state(py_def, ["p1", "p2"], shuffle_seed=42)
    c_state = c_create(42)

    for _ in range(2):
        py_moves = py_legal_moves(py_state)
        py_state = py_apply(py_state, py_moves[0])

        c_moves = (CMove * 64)()
        c_count = _lib.engine_legal_moves(c_state, c_moves, 64)
        c_result = _lib.engine_apply(c_state, ctypes.byref(c_moves[0]))
        _lib.engine_destroy(c_state)
        c_state = c_result

    py_before = (py_state.resource_pool.power, py_state.resource_pool.influence)
    c_before = (c_state.contents.resource_pool.power, c_state.contents.resource_pool.influence)

    py_moves = py_legal_moves(py_state)
    c_moves = (CMove * 64)()
    c_count = _lib.engine_legal_moves(c_state, c_moves, 64)

    py_move = None
    for m in py_moves:
        if isinstance(m, PlayCardMove):
            py_move = m
            break

    c_move_idx = -1
    for i in range(c_count):
        if c_moves[i].type == MOVE_PLAY_CARD:
            c_move_idx = i
            break

    if py_move is None and c_move_idx < 0:
        return

    py_result = py_apply(py_state, py_move) if py_move else py_state
    if c_move_idx >= 0:
        c_result = _lib.engine_apply(c_state, ctypes.byref(c_moves[c_move_idx]))
    else:
        c_result = c_state

    py_after = (py_result.resource_pool.power, py_result.resource_pool.influence)
    c_after = (c_result.contents.resource_pool.power, c_result.contents.resource_pool.influence)

    py_delta = (py_after[0] - py_before[0], py_after[1] - py_before[1])
    c_delta = (c_after[0] - c_before[0], c_after[1] - c_before[1])

    assert py_delta == c_delta, \
        f"Resource delta mismatch: Python={py_delta}, C={c_delta}"

    _lib.engine_destroy(c_state)
    if c_result != c_state:
        _lib.engine_destroy(c_result)


def test_quaggoth_assassinate_count_snapshotted():
    from engine_c.bindings.session import CSession
    from engine_c.bindings.ce_api import CEngine

    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/test_card_generation/017_seed_4_quaggoth.json", engine
    )

    moves = session.legal_moves()
    qmove = next(
        m for m in moves
        if m.move_type == "play_card" and m.data.get("card_id") == "quaggoth"
    )
    session.submit_move(qmove)

    total = 0
    while True:
        moves = session.legal_moves()
        gen = [m for m in moves if m.move_type == "resolve_generic"]
        if not gen:
            break
        result = session.submit_move(gen[0])
        assert result is not None, f"Assassinate #{total + 1} failed"
        total += 1

    assert total == 3, f"Expected 3 assassinations (majority controlled sites), got {total}"


def test_marilith_devours_hand_card_and_gains_five_power():
    from engine_c.bindings.session import CSession
    from engine_c.bindings.ce_api import CEngine

    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/batch_card_generation/031_seed_4_marilith.json", engine
    )

    s = session.state
    assert s.current_player_id == "p1", "Expected p1 to be current player"
    p_idx = s.player_index("p1")
    power_before = s.resource_power
    hand_before = s.player_hand(p_idx)
    devour_before = list(s.devour_pile)
    assert "marilith" in hand_before, "marilith must be in p1's hand"

    moves = session.legal_moves()
    card_move = next(
        m for m in moves
        if m.move_type == "play_card" and m.data.get("card_id") == "marilith"
    )
    session.submit_move(card_move)

    moves = session.legal_moves()
    gen = [m for m in moves if m.move_type == "resolve_generic"]
    assert len(gen) > 0, "Expected devour_cost selection moves"
    devour_move = gen[0]
    devoured_card_id = devour_move.data.get("target_id") or devour_move.data.get("action_id")
    session.submit_move(devour_move)

    while True:
        moves = session.legal_moves()
        gen = [m for m in moves if m.move_type == "resolve_generic"]
        if not gen:
            break
        session.submit_move(gen[0])

    s = session.state
    hand_after = s.player_hand(p_idx)
    devour_after = list(s.devour_pile)
    power_after = s.resource_power

    assert power_after == power_before + 5, \
        f"Expected +5 power, got {power_after} (was {power_before})"
    assert len(hand_after) == len(hand_before) - 2, \
        f"Expected hand -2 (play + devour), got {len(hand_before)} → {len(hand_after)}"
    assert devoured_card_id not in hand_after, \
        f"Devoured card {devoured_card_id} still in hand"
    assert len(devour_after) == len(devour_before) + 1, \
        f"Expected devour pile +1, got {len(devour_before)} → {len(devour_after)}"
    assert devoured_card_id in devour_after, \
        f"Devoured card {devoured_card_id} not found in devour pile"
    assert "marilith" not in hand_after, \
        "marilith should be in played cards, not hand"

    session.destroy()


def test_aerisi_kalinoth_free_recruit():
    """Aerisi Kalinoth: gain 1 power, place 1 spy, recruit free guile card costing ≤4."""
    from engine_c.bindings.session import CSession
    from engine_c.bindings.ce_api import CEngine

    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/batch_card_generation/081_seed_4_aerisi_kalinoth.json", engine
    )

    s = session.state
    assert s.current_player_id == "p1", "Expected p1 to be current player"
    p_idx = s.player_index("p1")
    influence_before = s.resource_influence
    power_before = s.resource_power
    spies_before = s._s.players[p_idx].spies_available
    discard_before = s.player_discard(p_idx)

    moves = session.legal_moves()
    aerisi_move = next(
        m for m in moves
        if m.move_type == "play_card" and m.data.get("card_id") == "aerisi_kalinoth"
    )
    session.submit_move(aerisi_move)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_moves) > 0, "Expected generic choices for place_spy"

    spy_move = gen_moves[0]
    session.submit_move(spy_move)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_moves) > 0, "Expected generic choices for recruit_card"

    recruit_cards = [m.data.get("action_id") for m in gen_moves]
    import json
    with open("data/cards/catalog.json", encoding="utf-8-sig") as f:
        cat = json.load(f)["cards"]
    for cid in recruit_cards:
        card = next((c for c in cat if c["card_id"] == cid), None)
        assert card is not None, f"Recruit target {cid} not in catalog"
        assert card["aspect"] == "guile", \
            f"Recruit target {card['name']} has aspect {card['aspect']}, expected guile"
        assert card["cost"] <= 4, \
            f"Recruit target {card['name']} costs {card['cost']}, expected ≤4"

    recruit_move = gen_moves[0]
    session.submit_move(recruit_move)

    s = session.state
    influence_after = s.resource_influence
    power_after = s.resource_power
    spies_after = s._s.players[p_idx].spies_available
    discard_after = s.player_discard(p_idx)

    assert power_after == power_before + 1, \
        f"Expected +1 power, got {power_after} (was {power_before})"
    assert spies_after == spies_before - 1, \
        f"Expected 1 spy placed, spies {spies_before} → {spies_after}"
    assert influence_after == influence_before, \
        f"Free recruit must not deduct influence: {influence_before} → {influence_after}"
    assert len(discard_after) == len(discard_before) + 1, \
        f"Expected +1 card in discard from recruit, got {len(discard_before)} → {len(discard_after)}"

    session.destroy()


def test_air_elemental_focus_draw_with_duplicate_cards():
    """Air Elemental focus draw must work when hand has two copies of the same
    Guile card.  The second copy is a different physical card and satisfies
    focus — the Sym comparison must not exclude it."""
    import json as _json

    from engine_c.bindings.session import CSession
    from engine_c.bindings.ce_api import CEngine

    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/random_card_generation/air_elemental_seed_666.json", engine
    )

    cp = session.state.current_player_id
    p_idx = session.state.player_index(cp)
    deck_before = len(session.state.player_deck(p_idx))

    assert deck_before >= 1, "Deck must have at least 1 card to draw"

    moves = session.legal_moves()
    ae = next(m for m in moves if m.move_type == "play_card" and m.data.get("card_id") == "air_elemental")
    session.submit_move(ae)

    # Choose Option 2 (return spy + deploy 3 troops + focus draw)
    moves = session.legal_moves()
    gen = [m for m in moves if m.move_type == "resolve_generic"]
    opt2 = next(m for m in gen if m.data.get("action_id") == "option_2")
    session.submit_move(opt2)

    # Resolve all remaining generic moves
    while True:
        moves = session.legal_moves()
        gen = [m for m in moves if m.move_type == "resolve_generic"]
        if not gen:
            break
        session.submit_move(gen[0])

    deck_after = len(session.state.player_deck(p_idx))
    assert deck_after == deck_before - 1, \
        f"Expected 1 card drawn (deck {deck_before} -> {deck_before-1}), got {deck_after}"

    session.destroy()


def test_air_elemental_option_1_focus_draw():
    """Option 1 (place spy) must also draw a card when Guile focus is met
    (catalog fix: option_1 was missing the draw_cards action)."""
    import json as _json, os as _os

    from engine_c.bindings.session import CSession
    from engine_c.bindings.ce_api import CEngine

    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/random_card_generation/air_elemental_seed_666.json", engine
    )

    raw = CSession.save_to_string(session.state, move_count=0, is_terminal=False)
    session.destroy()
    payload = _json.loads(raw)
    gs = payload["state"]
    cp = gs["current_player_id"]
    cp_data = next(p for p in gs["players"] if p["player_id"] == cp)
    cp_data["spies_available"] = max(cp_data["spies_available"], 1)
    has_guile = any(c != "air_elemental" and _is_aspect(c, "guile") for c in cp_data["hand"])
    if not has_guile:
        _ensure_guile_focus(cp_data, gs)

    tmp_path = "data/scenarios/test_card_generation/_ae_opt1_test.json"
    _os.makedirs(_os.path.dirname(tmp_path), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        _json.dump(payload, f)

    engine2 = CEngine()
    engine2.initialize()
    session2 = CSession.load(tmp_path, engine2)

    p_idx = session2.state.player_index(cp)
    deck_before = len(session2.state.player_deck(p_idx))

    moves = session2.legal_moves()
    ae = next(m for m in moves if m.move_type == "play_card" and m.data.get("card_id") == "air_elemental")
    session2.submit_move(ae)

    moves = session2.legal_moves()
    gen = [m for m in moves if m.move_type == "resolve_generic"]
    opt1 = next(m for m in gen if m.data.get("action_id") == "option_1")
    result = session2.submit_move(opt1)
    assert result is not None, "Option 1 submit failed"

    moves = session2.legal_moves()
    gen = [m for m in moves if m.move_type == "resolve_generic"]
    if gen:
        session2.submit_move(gen[0])

    deck_after = len(session2.state.player_deck(p_idx))
    assert deck_after == deck_before - 1, \
        f"Expected 1 card drawn via Option 1 (deck {deck_before} -> {deck_before-1}), got {deck_after}"

    session2.destroy()


def test_water_elemental_focus_draw():
    """Water Elemental must draw a card when Conquest focus is met
    (catalog fix: draw_cards action was missing from execution model)."""
    import json as _json, os as _os

    from engine_c.bindings.session import CSession
    from engine_c.bindings.ce_api import CEngine

    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/test_card_generation/we_focus_test.json", engine
    )

    raw = CSession.save_to_string(session.state, move_count=0, is_terminal=False)
    session.destroy()
    payload = _json.loads(raw)
    gs = payload["state"]
    cp = gs["current_player_id"]
    cp_data = next(p for p in gs["players"] if p["player_id"] == cp)

    has_conquest = any(c != "water_elemental" and _is_aspect(c, "conquest") for c in cp_data["hand"])
    if not has_conquest:
        _ensure_aspect_focus(cp_data, gs, "conquest", "black_wyrmling")

    site_found = False
    for node in gs["nodes"]:
        if "troop_slots" in node and len(node["troop_slots"]) >= 2:
            site_found = True
            break
    if not site_found:
        gs["nodes"][0]["troop_slots"] = [None, None, None]

    tmp_path = "data/scenarios/test_card_generation/_we_focus_test.json"
    _os.makedirs(_os.path.dirname(tmp_path), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        _json.dump(payload, f)

    engine2 = CEngine()
    engine2.initialize()
    session2 = CSession.load(tmp_path, engine2)

    p_idx = session2.state.player_index(cp)
    deck_before = len(session2.state.player_deck(p_idx))

    moves = session2.legal_moves()
    we = next(m for m in moves if m.move_type == "play_card" and m.data.get("card_id") == "water_elemental")
    session2.submit_move(we)

    while True:
        moves = session2.legal_moves()
        gen = [m for m in moves if m.move_type == "resolve_generic"]
        if not gen:
            break
        session2.submit_move(gen[0])

    deck_after = len(session2.state.player_deck(p_idx))
    assert deck_after == deck_before - 1, \
        f"Expected 1 card drawn via Water Elemental (deck {deck_before} -> {deck_before-1}), got {deck_after}"

    session2.destroy()


def _is_aspect(card_id: str, aspect: str) -> bool:
    import json as _json
    with open("data/cards/catalog.json", encoding="utf-8") as f:
        cat = _json.load(f)["cards"]
    for c in cat:
        if c["card_id"] == card_id:
            return c["aspect"] == aspect
    return False


def _ensure_guile_focus(player_data: dict, game_state: dict) -> None:
    _ensure_aspect_focus(player_data, game_state, "guile", "banshee")


def _ensure_aspect_focus(player_data: dict, game_state: dict, aspect: str, fallback: str) -> None:
    for i, c in enumerate(player_data["hand"]):
        if not _is_aspect(c, aspect):
            player_data["hand"][i] = fallback
            return
