"""Find where 'Lich' (capital L) enters the game."""
import json
import glob

print("=== Searching deck files for Lich (any case) ===")
for f in glob.glob('data/decks/*.json'):
    d = json.load(open(f))
    entries = d.get('entries', [])
    for e in entries:
        cid = e.get('card_id', '')
        if 'Lich' in cid or 'lich' in cid:
            print(f'{f}: card_id={cid!r}')

print("\n=== Searching catalog for lich cards ===")
c = json.load(open('data/cards/catalog.json'))
for card in c['cards']:
    cid = card.get('card_id', '')
    if 'ich' in cid.lower():
        print(f'catalog: card_id={cid!r} name={card.get("name","")!r}')

print("\n=== C loader check ===")
# The C loader interns card_id from JSON. If the deck JSON has "Lich" (capital),
# but catalog has "lich" (lowercase), that's the mismatch.
# Let's check the undead deck specifically.
d = json.load(open('data/decks/undead.json'))
print(f"undead deck entries:")
for e in d['entries']:
    print(f"  card_id={e['card_id']!r} count={e['count']}")
