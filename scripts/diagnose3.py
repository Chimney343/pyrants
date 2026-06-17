"""Diagnostic v3: Test if engine_clone_cow preserves hand correctly."""
import ctypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine_c", "bindings"))

from engine_bindings import (
    _lib, Move as CMove,
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

# Advance to main phase
for step in range(10):
    if state.contents.phase == 2:  # MAIN
        break
    moves = (CMove * 64)()
    n = _lib.engine_legal_moves(state, moves, 64)
    if n == 0:
        break
    result = _lib.engine_apply(state, ctypes.byref(moves[0]))
    if result:
        state = result
    else:
        break

# Now clone WITHOUT applying any move
clone = _lib.engine_clone_cow(state)
print(f"Original state ptr: {state}")
print(f"Clone state ptr: {clone}")

# Check original hand
ps_orig = state.contents.players[0]
print(f"\nOriginal hand (count={ps_orig.hand_count}):")
for i in range(ps_orig.hand_count):
    sym = ps_orig.hand[i]
    name = _lib.intern_str(sym).decode()
    print(f"  hand[{i}] = Sym({sym}) -> {name!r}")

# Check clone hand
ps_clone = clone.contents.players[0]
print(f"\nClone hand (count={ps_clone.hand_count}):")
for i in range(ps_clone.hand_count):
    sym = ps_clone.hand[i]
    name = _lib.intern_str(sym).decode()
    print(f"  hand[{i}] = Sym({sym}) -> {name!r}")

# Are they the same?
match = True
for i in range(min(ps_orig.hand_count, ps_clone.hand_count)):
    if ps_orig.hand[i] != ps_clone.hand[i]:
        match = False
        print(f"MISMATCH at index {i}: orig={ps_orig.hand[i]} clone={ps_clone.hand[i]}")
print(f"\nHands match: {match}")

# Now modifiy the original's hand and see if clone is affected
print("\n=== Modifying original hand[0] ===")
ps_orig.hand[0] = ctypes.c_uint32(999)
print(f"After modify: orig hand[0] = {ps_orig.hand[0]}, clone hand[0] = {ps_clone.hand[0]}")

# Are they independent?
if ps_orig.hand[0] == ps_clone.hand[0]:
    print("WARNING: Clone shares memory with original! memcpy didn't deep-copy!")
else:
    print("OK: Clone is independent")

_lib.engine_destroy(state)
_lib.engine_destroy(clone)
print("\nDone.")
