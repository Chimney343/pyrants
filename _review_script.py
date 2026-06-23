import json

data = json.load(open("data/cards/catalog.json"))

# Search A: cards with deferred_choice promotions
print("=== CARDS WITH deferred_choice ===")
for c in data:
    ep = c.get("effect_payload", {})
    if isinstance(ep, dict):
        if "deferred_choice" in str(ep):
            print(f"  {c['card_id']}: {c.get('name', '?')}")

# Search B: cards with promotions_remaining anywhere in payload
print("\n=== CARDS WITH promotions_remaining ===")
for c in data:
    ep = c.get("effect_payload", {})
    raw = json.dumps(ep)
    if "promotions_remaining" in raw:
        print(f"  {c['card_id']}: {c.get('name', '?')}")

# Search C: cards using scaled_vp_from_promoted_cards
print("\n=== CARDS USING scaled_vp_from_promoted_cards ===")
for c in data:
    ep = c.get("effect_payload", {})
    if isinstance(ep, dict):
        for frag in ep.get("fragments", []):
            for step in frag.get("steps", []):
                for action in step.get("actions", []):
                    params = action.get("params", {})
                    if params.get("source_fragment") == "scaled_vp_from_promoted_cards":
                        meta = params.get("metadata", {})
                        has_as = "as" in meta
                        print(f"  {c['card_id']}: has_as={has_as}, meta={json.dumps(meta)}")

# Search D: cards with "vp_tokens" references
print("\n=== ALL vp_tokens REFERENCES IN CATALOG ===")
import subprocess
result = subprocess.run(["rg", '-n', 'vp_tokens', 'data/cards/catalog.json'], capture_output=True, text=True)
print(result.stdout[:2000] if result.stdout else "  none found")