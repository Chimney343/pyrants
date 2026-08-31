import json, os, re

with open('data/cards/catalog.json') as f:
    catalog = json.load(f)
cards = [(c['name'], c.get('id','?')) for c in catalog['cards']]

test_dir = 'tests/c_engine'
test_files = os.listdir(test_dir)
test_card_keys = set()
for tf in test_files:
    m = re.match(r'test_card_(.+)\.py', tf)
    if m:
        test_card_keys.add(m.group(1))

def card_to_key(name):
    return name.lower().replace(' ','_').replace("'",'').replace(',','').replace('-','_')

# Build set of all card keys for cross-reference
all_card_keys = {card_to_key(name): name for name, _ in cards}

# Build reverse map: test_key -> matched card name (exact only)
test_to_card = {}
for name, _ in cards:
    key = card_to_key(name)
    if key in test_card_keys:
        test_to_card[key] = name

unmatched = []
fuzzy_matched = []
for name, cid in cards:
    key = card_to_key(name)
    if key in test_card_keys:
        continue  # exact match
    # Fuzzy: card key is prefix of some test key, AND that test key is NOT already claimed by another card
    candidates = [tk for tk in test_card_keys if tk.startswith(key + '_')]
    if candidates:
        # Filter out candidates already matched to other cards
        valid = [tk for tk in candidates if tk not in test_to_card]
        if valid:
            fuzzy_matched.append((name, valid))
        else:
            unmatched.append((name, cid, key))
    else:
        unmatched.append((name, cid, key))

print(f'Catalog cards: {len(cards)}')
print(f'Exact match: {len(cards) - len(unmatched) - len(fuzzy_matched)}')
print(f'Fuzzy match (no other card claims the test): {len(fuzzy_matched)}')
print(f'NO test: {len(unmatched)}')
print()

if fuzzy_matched:
    print('=== FUZZY MATCHED (card covered but test name extends card key) ===')
    for name, test_keys in fuzzy_matched:
        print(f'  {name} -> {test_keys}')
    print()

print('=== CARDS WITH NO TEST (tests/c_engine) ===')
for name, cid, key in unmatched:
    print(f'  {name}  ->  [{key}]')
