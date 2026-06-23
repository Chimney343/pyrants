import json

data = json.load(open("data/cards/catalog.json"))

print(f"Total top-level entries: {len(data)}")
print(f"Type of first entry: {type(data[0])}")

# Show structure of first entry
first = data[0]
if isinstance(first, dict):
    print(f"Keys: {list(first.keys())}")
    ep = first.get("effect_payload", {})
    print(f"effect_payload type: {type(ep)}")
    if isinstance(ep, dict):
        print(f"effect_payload keys: {list(ep.keys())}")
        frags = ep.get("fragments", [])
        print(f"fragments count: {len(frags)}")
        if frags:
            print(f"First fragment keys: {list(frags[0].keys()) if isinstance(frags[0], dict) else 'not dict'}")
    elif isinstance(ep, list):
        print("effect_payload is list")
    elif isinstance(ep, str):
        print(f"effect_payload is string: {ep[:100]}")
elif isinstance(first, str):
    print(f"First entry is a string: {first}")
    # find the first dict entry
    for i, c in enumerate(data):
        if isinstance(c, dict):
            print(f"First dict entry at index {i}: card_id={c.get('card_id', '?')}")
            break

# Find cards with specific patterns
for c in data:
    if isinstance(c, dict):
        cid = c.get("card_id", "")
        if "blue_dragon" in cid:
            print(f"\n=== Found {cid} ===")
            ep = c.get("effect_payload", {})
            if isinstance(ep, dict):
                print(json.dumps(ep, indent=2)[:2000])
            elif isinstance(ep, str):
                print(f"effect_payload is string: {ep[:500]}")
            break