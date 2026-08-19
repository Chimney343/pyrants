"""Find Sym=512 in the catalog and check intern table."""
import ctypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine_c", "bindings"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_setup.loaders import assemble_catalog_text
from pathlib import Path

from engine_bindings import _lib

_lib.intern_init(4096)
_lib.register_default_effects()

arena = _lib.arena_create(16 * 1024 * 1024)
catalog_json = assemble_catalog_text(Path("data/cards"))
board_path = os.path.join("data", "boards", "tyrants_of_the_underdark.json")
setup_path = os.path.join("data", "decks", "base_setup.json")

def_ptr = _lib.engine_load_definition_json(
    catalog_json.encode(), board_path.encode(), setup_path.encode(), arena
)
assert def_ptr, "Failed"

cat = def_ptr.contents.catalog
print(f"Catalog: {cat.card_count} cards")

# Find all cards with name containing "ich"
for i in range(cat.card_count):
    c = cat.cards[i]
    cid_str = _lib.intern_str(c.card_id).decode() if c.card_id else "NULL"
    name_str = _lib.intern_str(c.name).decode() if c.name else "NULL"
    if 'ich' in cid_str.lower() or 'ich' in name_str.lower():
        print(f"  [{i}] card_id=Sym({c.card_id})={cid_str!r} name=Sym({c.name})={name_str!r}")

# Check what Sym values are used for "lich" vs "Lich" vs "noble" vs "Noble"
print(f"\nDirect intern check:")
for s in ["lich", "Lich", "noble", "Noble", "soldier", "Soldier"]:
    sym = _lib.intern(s.encode())
    back = _lib.intern_str(sym).decode()
    print(f"  {s!r:10s} -> Sym({sym}) -> {back!r}")

# What is Sym(512)?
print(f"\nSym(512) -> {_lib.intern_str(512).decode()!r}")

# What card has card_id Sym(512)?
for i in range(cat.card_count):
    if cat.cards[i].card_id == 512:
        name = _lib.intern_str(cat.cards[i].name).decode()
        print(f"Card with card_id=512: name={name!r}")
        break
else:
    print("No card with card_id=512")

# What card has name Sym(512)?
for i in range(cat.card_count):
    if cat.cards[i].name == 512:
        cid = _lib.intern_str(cat.cards[i].card_id).decode()
        print(f"Card with name=512: card_id={cid!r}")
        break
else:
    print("No card with name=512")

# Check deck entries
setup = def_ptr.contents.setup
print(f"\nSetup: starter_deck entries={setup.starter_deck.entry_count}")
for i in range(setup.starter_deck.entry_count):
    e = setup.starter_deck.entries[i]
    cid = _lib.intern_str(e.card_id).decode() if e.card_id else "NULL"
    print(f"  [{i}] card_id=Sym({e.card_id})={cid!r} count={e.count}")
