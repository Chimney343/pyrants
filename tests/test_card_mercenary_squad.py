"""Lock in Mercenary Squad card behavior: deploy 3 troops to board sites."""

from __future__ import annotations

import json
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "cards" / "catalog.json"


def test_mercenary_squad_execution_model_deploys_three_troops() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    ms = next(c for c in cards if c.get("card_id") == "mercenary_squad")

    actions = ms["execution_model"]["actions"]
    assert len(actions) == 1, "Mercenary Squad should have exactly 1 action"

    deploy = actions[0]
    assert deploy["op"] == "deploy_troops"
    assert deploy["quantity"] == {"kind": "fixed", "value": 3}
    assert deploy["target_scope"] == "board_site"
    assert deploy["timing"] == "immediate"
    assert deploy["optional"] is False
    assert deploy["filters"] == []

    assert ms["rules_text"] == "Deploy 3 troops."
    assert ms["cost"] == 3
    assert ms["aspect"] == "conquest"
    assert "drow" in ms["secondary_aspects"]


def test_mercenary_squad_deploys_three_troops_via_c_engine():
    from engine_c.bindings.ce_api import CEngine
    from engine_c.bindings.session import CSession

    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/batch_card_generation/076_seed_4_mercenary_squad.json", engine
    )

    s = session.state
    assert s.current_player_id == "p2", "Expected p2 to be current player"
    p_idx = s.player_index("p2")
    barracks_before = s.player_barracks(p_idx)

    def count_p2_troops():
        total = 0
        for ni in range(s._s.node_count):
            ns = s._s.nodes[ni]
            for si in range(ns.troop_slot_count):
                occupied = ns.troop_slots[si]
                if occupied != 0:
                    from engine_c.bindings.engine_bindings import _lib
                    pid = _lib.intern_str(occupied).decode()
                    if pid == "p2":
                        total += 1
        return total

    troops_before = count_p2_troops()

    moves = session.legal_moves()
    card_move = next(
        m for m in moves
        if m.move_type == "play_card" and m.data.get("card_id") == "mercenary_squad"
    )
    session.submit_move(card_move)

    selections = []
    while True:
        moves = session.legal_moves()
        gen = [m for m in moves if m.move_type == "resolve_generic"]
        if not gen:
            break
        selections.append(gen[0])
        result = session.submit_move(gen[0])
        assert result is not None, f"Generic choice #{len(selections)} failed for deploy_troops"

    assert len(selections) == 3, f"Expected 3 generic choices for deploy_troops, got {len(selections)}"

    s = session.state
    barracks_after = s.player_barracks(p_idx)
    troops_after = count_p2_troops()

    assert barracks_after == barracks_before - 3, \
        f"Barracks should decrease by 3 ({barracks_before} -> {barracks_before - 3}), got {barracks_after}"
    assert troops_after == troops_before + 3, \
        f"Troops on board should increase by 3 ({troops_before} -> {troops_before + 3}), got {troops_after}"

    selected_nodes = {sel.data.get("action_id") for sel in selections}
    node_ids = set()
    for ni in range(s._s.node_count):
        ns = s._s.nodes[ni]
        for si in range(ns.troop_slot_count):
            if ns.troop_slots[si] != 0:
                from engine_c.bindings.engine_bindings import _lib
                pid = _lib.intern_str(ns.troop_slots[si]).decode()
                if pid == "p2":
                    node_ids.add(_lib.intern_str(s._s.nodes[ni].node_id).decode())

    assert selected_nodes.issubset(node_ids), \
        f"Selected nodes {selected_nodes} should have p2 troops; nodes with p2: {node_ids}"

    session.destroy()
