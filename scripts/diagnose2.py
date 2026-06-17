"""Diagnostic v2: trace Sym values to find root cause of play_card failure."""
import ctypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine_c", "bindings"))

from engine_bindings import (
    _lib, Move as CMove, MOVE_PLAY_CARD, MOVE_END_MAIN_PHASE,
    MOVE_INITIAL_PLACEMENT, MOVE_RESOLVE_END_OF_TURN,
    MOVE_RESOLVE_CLEANUP, MOVE_RECRUIT,
    PHASE_SETUP, PHASE_MAIN,
)

_lib.intern_init(4096)
_lib.register_default_effects()

arena = _lib.arena_create(16 * 1024 * 1024)

catalog_path = os.path.join("data", "cards", "catalog.json")
board_path = os.path.join("data", "boards", "tyrants_of_the_underdark.json")
setup_path = os.path.join("data", "decks", "base_setup.json")

def_ptr = _lib.engine_load_definition(
    catalog_path.encode(), board_path.encode(), setup_path.encode(), arena
)
assert def_ptr, "Failed to load definition"

pids = (ctypes.c_char_p * 2)(b"p1", b"p2")
state = _lib.engine_create_game_definition(def_ptr, pids, 2, 42)
assert state, "Failed to create game state"

def dump_hand_raw(state, label=""):
    ps = state.contents.players[0]
    print(f"\n  === HAND DUMP {label} ===")
    print(f"  hand_count={ps.hand_count}")
    for i in range(min(ps.hand_count + 2, 20)):
        sym = ps.hand[i]
        name = _lib.intern_str(sym).decode() if sym else "NULL"
        in_hand = "(in hand)" if i < ps.hand_count else "(BEYOND hand_count — stale)"
        print(f"  hand[{i}] = Sym({sym:>5}) -> {name!r:30s} {in_hand}")

def dump_catalog_sample(state):
    cat = state.contents.definition.contents.catalog
    print(f"\n  Catalog has {cat.card_count} cards. First 10 card_ids:")
    for i in range(min(10, cat.card_count)):
        sym = cat.cards[i].card_id
        name = _lib.intern_str(sym).decode() if sym else "NULL"
        print(f"    [{i}] Sym({sym:>5}) -> {name!r}")

def dump_player_brief(state, pi):
    ps = state.contents.players[pi]
    pid = _lib.intern_str(ps.player_id).decode() if ps.player_id else "?"
    print(f"\n  Player[{pi}]: id={pid} hand_count={ps.hand_count} deck_count={ps.deck_count}")
    print(f"    hand (first 5): ", end="")
    for i in range(min(ps.hand_count, 5)):
        sym = ps.hand[i]
        name = _lib.intern_str(sym).decode() if sym else "NULL"
        print(f"Sym({sym})={name!r} ", end="")
    print()

dump_catalog_sample(state)
dump_player_brief(state, 0)
dump_player_brief(state, 1)

# Advance to main phase
print("\n=== Advancing to main phase ===")
for step in range(10):
    phase_id = state.contents.phase
    if phase_id == 2:  # MAIN
        break
    moves = (CMove * 64)()
    n = _lib.engine_legal_moves(state, moves, 64)
    if n == 0:
        print("No legal moves")
        break
    result = _lib.engine_apply(state, ctypes.byref(moves[0]))
    if result:
        state = result
    else:
        print(f"Apply failed at step {step}")
        break
    phase_names = {0: "setup", 1: "draw", 2: "main"}
    print(f"  Step {step}: {phase_names.get(phase_id, '?')}")

print(f"\n=== In main phase, before playing any card ===")
dump_hand_raw(state, "before play")
dump_player_brief(state, 0)

# Now play soldier from hand[0]
moves = (CMove * 128)()
n = _lib.engine_legal_moves(state, moves, 128)
print(f"\nLegal moves: {n}")

# Find play_card at index 0
played_move = None
for mi in range(n):
    if moves[mi].type == MOVE_PLAY_CARD:
        played_move = mi
        cid = _lib.intern_str(moves[mi].data.play_card.card_id).decode()
        hi = moves[mi].data.play_card.hand_index
        print(f"  move[{mi}]: play_card card={cid!r} hand_index={hi}")
        break

if played_move is not None:
    m = moves[played_move]
    m_cid = _lib.intern_str(m.data.play_card.card_id).decode()
    m_hi = m.data.play_card.hand_index
    print(f"\n=== Applying: play_card {m_cid!r} at hand_index={m_hi} ===")
    
    result = _lib.engine_apply(state, ctypes.byref(m))
    if result:
        print("Apply SUCCEEDED")
        state = result
    else:
        print("Apply FAILED — null returned")
    
    dump_hand_raw(state, "after play")
    dump_player_brief(state, 0)
    
    # Check: what card definitions exist for the Syms in the new hand?
    print("\n=== Checking hand cards against catalog ===")
    ps = state.contents.players[0]
    cat = state.contents.definition.contents.catalog
    for hi in range(ps.hand_count):
        sym = ps.hand[hi]
        name = _lib.intern_str(sym).decode() if sym else "NULL"
        found = False
        for ci in range(cat.card_count):
            if cat.cards[ci].card_id == sym:
                cname = _lib.intern_str(cat.cards[ci].name).decode()
                found = True
                print(f"  hand[{hi}] Sym({sym})={name!r} -> FOUND in catalog as {cname!r}")
                break
        if not found:
            print(f"  hand[{hi}] Sym({sym})={name!r} -> NOT FOUND in catalog!")

print("\nDone.")
