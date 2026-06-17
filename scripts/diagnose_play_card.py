"""Diagnostic: trace why engine_apply returns NULL for play_card moves."""
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

pid = _lib.intern(b"p1")

# Helper: get player info
def dump_hand(state, label=""):
    ps = state.contents.players[0]
    cards = []
    for i in range(ps.hand_count):
        name = _lib.intern_str(ps.hand[i]).decode()
        cards.append(f"{name}[{i}]")
    print(f"  Hand {label}: {cards} (count={ps.hand_count})")

def dump_catalog_cards(state, label=""):
    cat = state.contents.definition.contents.catalog
    print(f"  Catalog {label}: {cat.card_count} cards")
    for i in range(min(cat.card_count, 3)):
        c = cat.cards[i]
        cid = _lib.intern_str(c.card_id).decode() if c.card_id else "NULL"
        cname = _lib.intern_str(c.name).decode() if c.name else "NULL"
        print(f"    [{i}] card_id={cid!r} name={cname!r}")

print("=== Phase 1: Setup ===")
print(f"Phase: {state.contents.phase}")
dump_catalog_cards(state, "initial")

# Step 1: Apply initial placements
moves = (CMove * 64)()
n = _lib.engine_legal_moves(state, moves, 64)
print(f"Legal moves in setup: {n}")
# Apply placement for p1
for i in range(2):
    moves = (CMove * 64)()
    n = _lib.engine_legal_moves(state, moves, 64)
    if n == 0:
        print("No legal moves!")
        break
    m = moves[0]
    print(f"  Applying move: type={m.type} node_id={_lib.intern_str(m.data.initial_placement.node_id).decode()}")
    result = _lib.engine_apply(state, ctypes.byref(m))
    if result:
        state = result
    else:
        print("  APPLY FAILED!")
        break

print(f"Phase after placements: {state.contents.phase}")
pid2 = _lib.intern(b"p2")

# Step 2: End main phase for p1 repeatedly to advance
print("\n=== Phase 2: Advance to Main ===")
for step in range(20):
    phase_id = state.contents.phase
    phase_map = {0: "setup", 1: "draw", 2: "main", 3: "end_of_turn", 4: "cleanup", 5: "game_over"}
    current = phase_map.get(phase_id, f"unknown({phase_id})")

    cp_sym = state.contents.current_player_id
    cp = _lib.intern_str(cp_sym).decode() if cp_sym else "?"

    moves = (CMove * 128)()
    n = _lib.engine_legal_moves(state, moves, 128)

    if current == "main":
        dump_hand(state, f"phase={current} cp={cp}")

    print(f"Step {step}: phase={current} cp={cp} legal_moves={n}")

    if n == 0:
        print("  No legal moves — terminal?")
        break

    # Find a play_card move if in main phase
    applied = False
    for mi in range(n):
        mt = moves[mi].type
        if mt == MOVE_PLAY_CARD:
            cid = _lib.intern_str(moves[mi].data.play_card.card_id).decode()
            hi = moves[mi].data.play_card.hand_index
            print(f"  Found play_card move[{mi}]: card_id={cid!r} hand_index={hi}")

            # Also print hand contents
            ps = state.contents.players[0]
            hand_card = _lib.intern_str(ps.hand[hi]).decode()
            match = "MATCH" if ps.hand[hi] == moves[mi].data.play_card.card_id else "MISMATCH"
            print(f"    Hand[{hi}]={hand_card!r} — {match}")
            if ps.hand[hi] != moves[mi].data.play_card.card_id:
                print(f"    Sym values: hand={ps.hand[hi]} move={moves[mi].data.play_card.card_id}")

        if mt == MOVE_PLAY_CARD and not applied:
            m = moves[mi]
            result = _lib.engine_apply(state, ctypes.byref(m))
            if result:
                state = result
                applied = True
                print(f"    Played successfully!")
            else:
                # Investigate WHY it failed
                cid = _lib.intern_str(m.data.play_card.card_id).decode()
                hi = m.data.play_card.hand_index
                print(f"    APPLY FAILED for play_card {cid!r} at hand[{hi}]")
                # Check what's in hand
                ps = state.contents.players[0]
                print(f"    Hand has {ps.hand_count} cards:")
                for j in range(ps.hand_count):
                    hcid = _lib.intern_str(ps.hand[j]).decode()
                    print(f"      hand[{j}] = {hcid!r} (Sym={ps.hand[j]})")
                # Check if card is in catalog
                cat = state.contents.definition.contents.catalog
                found_in_catalog = False
                for j in range(cat.card_count):
                    if cat.cards[j].card_id == m.data.play_card.card_id:
                        found_in_catalog = True
                        cname = _lib.intern_str(cat.cards[j].name).decode()
                        print(f"    Found in catalog: {cname!r}")
                        break
                if not found_in_catalog:
                    print(f"    Card {cid!r} NOT FOUND in catalog!")
                    # Search catalog for similar names
                    for j in range(min(cat.card_count, 5)):
                        cid2 = _lib.intern_str(cat.cards[j].card_id).decode()
                        print(f"    Catalog[{j}]: {cid2!r}")

    if not applied:
        # Apply first legal move
        m = moves[0]
        result = _lib.engine_apply(state, ctypes.byref(m))
        if result:
            state = result
        else:
            print(f"  APPLY FAILED for move type {m.type}")
            break

print("\nDone.")
