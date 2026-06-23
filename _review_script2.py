import json

data = json.load(open("data/cards/catalog.json"))

# Search A: which cards have deferred_choice in promotion?
print("=== CARDS WITH deferred_choice promotions ===")
for c in data:
    if isinstance(c, dict):
        ep = c.get("effect_payload", {})
        if isinstance(ep, dict):
            frags = ep.get("fragments", [])
            for frag in frags:
                steps = frag.get("steps", [])
                for step in steps:
                    actions = step.get("actions", [])
                    for action in actions:
                        meta = action.get("metadata", {})
                        if meta.get("deferred_choice"):
                            print(f"  {c['card_id']}: deferred_choice=true, repeat_while_targets={meta.get('repeat_while_targets', 'not set')}")
                            print(f"    fragment={action.get('source_fragment','?')}, qty={action.get('quantity',{})}")

# Search B: cards with repeat_while_targets
print("\n=== CARDS WITH repeat_while_targets ===")
for c in data:
    if isinstance(c, dict):
        ep = c.get("effect_payload", {})
        if isinstance(ep, dict):
            frags = ep.get("fragments", [])
            for frag in frags:
                steps = frag.get("steps", [])
                for step in steps:
                    actions = step.get("actions", [])
                    for action in actions:
                        meta = action.get("metadata", {})
                        if meta.get("repeat_while_targets"):
                            dc = meta.get("deferred_choice", False)
                            print(f"  {c['card_id']}: repeat_while_targets=true, deferred_choice={dc}")

# Search C: cards using scaled_vp_from_promoted_cards
print("\n=== CARDS USING scaled_vp_from_promoted_cards ===")
for c in data:
    if isinstance(c, dict):
        ep = c.get("effect_payload", {})
        if isinstance(ep, dict):
            frags = ep.get("fragments", [])
            for frag in frags:
                steps = frag.get("steps", [])
                for step in steps:
                    for action in step.get("actions", []):
                        params = action.get("params", {})
                        if params.get("source_fragment") == "scaled_vp_from_promoted_cards":
                            meta = params.get("metadata", {})
                            has_as = "as" in meta
                            print(f"  {c['card_id']}: name={c.get('name','?')}, has_as={has_as}, as_val={meta.get('as','N/A')}, meta={json.dumps(meta)}")