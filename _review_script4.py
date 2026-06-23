import json

data = json.load(open("data/cards/catalog.json"))

print(f"Top-level keys: {list(data.keys())}")

cards = data.get("cards", [])
print(f"Cards count: {len(cards)}")

# Find Blue Dragon
for c in cards:
    cid = c.get("card_id", "")
    if "blue_dragon" in cid:
        print(f"\n=== {cid} ===")
        ep = c.get("effect_payload", "")
        print(f"effect_payload type: {type(ep)}")
        if isinstance(ep, str):
            # may be a string reference, look it up
            print(f"effect_payload string: {ep[:200]}")
        elif isinstance(ep, dict):
            print(json.dumps(ep, indent=2)[:3000])
        break

# Search A: cards with deferred_choice
print("\n=== CARDS WITH deferred_choice ===")
for c in cards:
    cid = c.get("card_id", "")
    ep = c.get("effect_payload", "")
    if isinstance(ep, str):
        continue
    raw = json.dumps(ep)
    if "deferred_choice" in raw:
        print(f"  {cid}")

# Search B: cards with repeat_while_targets
print("\n=== CARDS WITH repeat_while_targets ===")
for c in cards:
    cid = c.get("card_id", "")
    ep = c.get("effect_payload", "")
    if isinstance(ep, str):
        continue
    raw = json.dumps(ep)
    if "repeat_while_targets" in raw:
        print(f"  {cid}")

# Search C: cards with scaled_vp_from_promoted_cards
print("\n=== CARDS USING scaled_vp_from_promoted_cards ===")
for c in cards:
    cid = c.get("card_id", "")
    ep = c.get("effect_payload", "")
    if isinstance(ep, str):
        continue
    raw = json.dumps(ep)
    if "scaled_vp_from_promoted_cards" in raw:
        meta_start = raw.find('"metadata"')
        snippet = raw[max(0,meta_start-50):meta_start+200] if meta_start >= 0 else raw
        print(f"  {cid}")
        # also show the full ep
        if "blue_dragon" in cid:
            print(f"  EP: {json.dumps(ep, indent=2)[:1000]}")