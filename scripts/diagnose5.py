"""Diagnostic v5: Compare raw bytes between src and clone."""
import ctypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine_c", "bindings"))

from engine_bindings import (
    _lib, Move as CMove, GameStateStruct, PlayerState, MAX_PLAYERS, MAX_NODES,
)

_lib.intern_init(4096)
_lib.register_default_effects()

arena = _lib.arena_create(16 * 1024 * 1024)
catalog_path = os.path.join("data", "cards", "catalog.json")
board_path = os.path.join("data", "boards", "tyrants_of_the_underdark.json")
setup_path = os.path.join("data", "decks", "base_setup.json")
def_ptr = _lib.engine_load_definition(catalog_path.encode(), board_path.encode(), setup_path.encode(), arena)
assert def_ptr

pids = (ctypes.c_char_p * 2)(b"p1", b"p2")
state = _lib.engine_create_game_definition(def_ptr, pids, 2, 42)
assert state

# Advance to main
for step in range(20):
    if state.contents.phase == 2:
        break
    moves = (CMove * 64)()
    n = _lib.engine_legal_moves(state, moves, 64)
    if n == 0: break
    result = _lib.engine_apply(state, ctypes.byref(moves[0]))
    if result:
        state = result
    else: break

# Now state is in main phase, has hand with 5 cards
# Compute the offset of players[0].hand in GameStateStruct
ps_offset = GameStateStruct.players.offset
ps0_offset = ps_offset + 0 * ctypes.sizeof(PlayerState)
hand_offset_in_ps = PlayerState.hand.offset
hand0_offset = ps0_offset + hand_offset_in_ps

print(f"players offset in GameState: {ps_offset}")
print(f"PlayerState size: {ctypes.sizeof(PlayerState)}")
print(f"hand offset in PlayerState: {hand_offset_in_ps}")
print(f"hand[0] byte offset in GameState: {hand0_offset}")
print(f"Total GameState size: {ctypes.sizeof(GameStateStruct)}")

# Read hand from Python ctypes
def read_hand(buf, count):
    syms = []
    for i in range(count):
        val = ctypes.c_uint32.from_buffer(buf, hand0_offset + i * 4).value
        name = _lib.intern_str(val).decode() if val else "NULL"
        syms.append(f"{val}({name})")
    return syms

# Get raw byte buffer of the src state
src_buf = (ctypes.c_ubyte * ctypes.sizeof(GameStateStruct)).from_address(
    ctypes.addressof(state.contents))
src_count = state.contents.players[0].hand_count
print(f"\nSource hand (count={src_count}): {read_hand(src_buf, src_count + 2)}")

# Now clone manually via C engine's clone
clone = _lib.engine_clone(state)
if clone:
    # Need to handle the clone pointer properly
    # The clone returns void* / int if restype not set
    print(f"Clone ptr type: {type(clone)} value: {clone}")
    # Try casting
    clone_ptr = ctypes.cast(clone, ctypes.POINTER(GameStateStruct))
    clone_count = clone_ptr.contents.players[0].hand_count
    clone_buf = (ctypes.c_ubyte * ctypes.sizeof(GameStateStruct)).from_address(
        ctypes.addressof(clone_ptr.contents))
    print(f"Clone hand (count={clone_count}): {read_hand(clone_buf, clone_count + 2)}")
    
    # Compare raw bytes at hand position
    print(f"\nRaw bytes at hand[0] (src vs clone):")
    for i in range(6):
        offset = hand0_offset + i * 4
        src_val = int.from_bytes(src_buf[offset:offset+4], 'little')
        clone_val = int.from_bytes(clone_buf[offset:offset+4], 'little')
        status = "MATCH" if src_val == clone_val else "DIFF"
        print(f"  hand[{i}] offset={offset}: src={src_val} clone={clone_val} {status}")

print("\nDone.")
