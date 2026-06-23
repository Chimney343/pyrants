import json

data = json.load(open("data/cards/catalog.json"))
cards = data["cards"]

# Check which cards have execution_model or actions with these patterns
for c in cards:
    cid = c.get("card_id", "")
    actions = c.get("execution_model", {}).get("actions", []) or c.get("actions", [])
    for a in actions:
        meta = a.get("metadata", {})
        if meta.get("deferred_choice"):
            print(f"  DEFERRED: {cid} -> action {a['action_id']}, repeat_while={meta.get('repeat_while_targets')}")
        if meta.get("repeat_while_targets"):
            print(f"  REPEAT: {cid} -> action {a['action_id']}, deferred_choice={meta.get('deferred_choice')}")

print()
# Check scaled_vp_from_promoted_cards
for c in cards:
    cid = c.get("card_id", "")
    actions = c.get("execution_model", {}).get("actions", []) or c.get("actions", [])
    for a in actions:
        sf = a.get("source_fragment", "")
        if sf == "scaled_vp_from_promoted_cards":
            meta = a.get("metadata", {})
            has_as = "as" in meta
            print(f"  VP_SCALED: {cid}, has_as={has_as}, as_val={meta.get('as', 'MISSING')}, meta={json.dumps(meta)}")

print()
# Also check the effect_payload fragments path for deferred_choice
for c in cards:
    cid = c.get("card_id", "")
    ep = c.get("effect_payload", {})
    if isinstance(ep, dict):
        frags = ep.get("fragments", [])
        for f in frags:
            for step in f.get("steps", []):
                for a in step.get("actions", []):
                    meta = a.get("metadata", {})
                    if meta.get("deferred_choice"):
                        print(f"  EP_DEFERRED: {cid}, repeat_while={meta.get('repeat_while_targets')}")