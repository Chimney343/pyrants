"""Diagnostic v4: Test corruption with different cards."""
import ctypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine_c", "bindings"))

from engine_bindings import (
    _lib, Move as CMove, MOVE_PLAY_CARD,
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
assert def_ptr

def create_game(seed):
    pids = (ctypes.c_char_p * 2)(b"p1", b"p2")
    return _lib.engine_create_game_definition(def_ptr, pids, 2, seed)

def advance_to_main(state):
    for step in range(20):
        if state.contents.phase == 2:
            return state
        moves = (CMove * 64)()
        n = _lib.engine_legal_moves(state, moves, 64)
        if n == 0:
            break
        result = _lib.engine_apply(state, ctypes.byref(moves[0]))
        if result:
            state = result
        else:
            break
    return state

def show_hand(state, label):
    ps = state.contents.players[0]
    cards = []
    for i in range(ps.hand_count):
        sym = ps.hand[i]
        name = _lib.intern_str(sym).decode() if sym else "NULL"
        cards.append(f"Sym({sym})={name!r}")
    print(f"  {label}: [{', '.join(cards)}]")

# Test 1: Play first card (soldier)
state = advance_to_main(create_game(42))
show_hand(state, "Before play")

moves = (CMove * 128)()
n = _lib.engine_legal_moves(state, moves, 128)
print(f"  Legal: {n} moves")

# Find all play_card moves and show their card_id and hand_index
play_moves = []
for i in range(n):
    if moves[i].type == MOVE_PLAY_CARD:
        cid = _lib.intern_str(moves[i].data.play_card.card_id).decode()
        hi = moves[i].data.play_card.hand_index
        play_moves.append((i, cid, hi))
        print(f"  move[{i}]: play_card {cid!r} hand_index={hi}")

# Apply all play_card moves possible, NOT skipping any
for mi, cid, hi in play_moves:
    print(f"\n--- Applying play_card {cid!r} at hand_index={hi} ---")
    result = _lib.engine_apply(state, ctypes.byref(moves[mi]))
    if result:
        state = result
        show_hand(state, "After")
        
        # Check if hand has wrong cards
        ps = state.contents.players[0]
        all_ok = True
        for i in range(ps.hand_count):
            sym = ps.hand[i]
            # Check if this Sym is in the catalog
            cat = state.contents.definition.contents.catalog
            found = False
            for ci in range(cat.card_count):
                if cat.cards[ci].card_id == sym:
                    found = True
                    break
            if not found:
                name = _lib.intern_str(sym).decode()
                print(f"  *** CORRUPTION: hand[{i}] = Sym({sym}) = {name!r} NOT IN CATALOG!")
                all_ok = False
        if all_ok:
            print(f"  Hand OK: all cards in catalog")
    else:
        print(f"  Apply FAILED!")
        break

print("\nDone.")
