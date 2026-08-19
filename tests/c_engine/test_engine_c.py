"""Pure-C engine behavior tests (no Python engine dependency)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine_c.bindings.ce_api import CEngine  # noqa: E402
from engine_c.bindings.session import CSession  # noqa: E402
from game_setup.loaders import assemble_catalog_payload


def test_quaggoth_assassinate_count_snapshotted():
    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/test_card_generation/017_seed_4_quaggoth.json", engine
    )

    moves = session.legal_moves()
    qmove = next(
        m for m in moves
        if m.move_type == "play_card" and m.data.get("card_id") == "quaggoth"
    )
    session.submit_move(qmove)

    total = 0
    while True:
        moves = session.legal_moves()
        gen = [m for m in moves if m.move_type == "resolve_generic"]
        if not gen:
            break
        result = session.submit_move(gen[0])
        assert result is not None, f"Assassinate #{total + 1} failed"
        total += 1

    assert total == 3, f"Expected 3 assassinations (majority controlled sites), got {total}"


def test_marilith_devours_hand_card_and_gains_five_power():
    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/batch_card_generation/031_seed_4_marilith.json", engine
    )

    s = session.state
    assert s.current_player_id == "p1", "Expected p1 to be current player"
    p_idx = s.player_index("p1")
    power_before = s.resource_power
    hand_before = s.player_hand(p_idx)
    devour_before = list(s.devour_pile)
    assert "marilith" in hand_before, "marilith must be in p1's hand"

    moves = session.legal_moves()
    card_move = next(
        m for m in moves
        if m.move_type == "play_card" and m.data.get("card_id") == "marilith"
    )
    session.submit_move(card_move)

    moves = session.legal_moves()
    gen = [m for m in moves if m.move_type == "resolve_generic"]
    assert len(gen) > 0, "Expected devour_cost selection moves"
    devour_move = gen[0]
    devoured_card_id = devour_move.data.get("target_id") or devour_move.data.get("action_id")
    session.submit_move(devour_move)

    while True:
        moves = session.legal_moves()
        gen = [m for m in moves if m.move_type == "resolve_generic"]
        if not gen:
            break
        session.submit_move(gen[0])

    s = session.state
    hand_after = s.player_hand(p_idx)
    devour_after = list(s.devour_pile)
    power_after = s.resource_power

    assert power_after == power_before + 5, \
        f"Expected +5 power, got {power_after} (was {power_before})"
    assert len(hand_after) == len(hand_before) - 2, \
        f"Expected hand -2 (play + devour), got {len(hand_before)} → {len(hand_after)}"
    assert devoured_card_id not in hand_after, \
        f"Devoured card {devoured_card_id} still in hand"
    assert len(devour_after) == len(devour_before) + 1, \
        f"Expected devour pile +1, got {len(devour_before)} → {len(devour_after)}"
    assert devoured_card_id in devour_after, \
        f"Devoured card {devoured_card_id} not found in devour pile"
    assert "marilith" not in hand_after, \
        "marilith should be in played cards, not hand"

    session.destroy()


def test_aerisi_kalinoth_recruit_requires_influence():
    """Aerisi Kalinoth: gain 1 power, place 1 spy; the recruit is paid and skips with 0 influence."""
    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/batch_card_generation/081_seed_4_aerisi_kalinoth.json", engine
    )

    s = session.state
    assert s.current_player_id == "p1", "Expected p1 to be current player"
    p_idx = s.player_index("p1")
    influence_before = s.resource_influence
    power_before = s.resource_power
    spies_before = s._s.players[p_idx].spies_available
    discard_before = s.player_discard(p_idx)

    moves = session.legal_moves()
    aerisi_move = next(
        m for m in moves
        if m.move_type == "play_card" and m.data.get("card_id") == "aerisi_kalinoth"
    )
    session.submit_move(aerisi_move)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_moves) > 0, "Expected generic choices for place_spy"

    spy_move = gen_moves[0]
    session.submit_move(spy_move)

    # The scenario starts with 0 influence, so the mandatory paid recruit has no
    # affordable Guile card ≤4 and auto-skips.
    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_moves) == 0, (
        f"With 0 influence, no recruit target should be offered; got {[m.data for m in gen_moves]}"
    )

    s = session.state
    influence_after = s.resource_influence
    power_after = s.resource_power
    spies_after = s._s.players[p_idx].spies_available
    discard_after = s.player_discard(p_idx)

    assert power_after == power_before + 1, \
        f"Expected +1 power, got {power_after} (was {power_before})"
    assert spies_after == spies_before - 1, \
        f"Expected 1 spy placed, spies {spies_before} → {spies_after}"
    assert influence_after == influence_before, \
        f"Unaffordable recruit must not change influence: {influence_before} → {influence_after}"
    assert len(discard_after) == len(discard_before), \
        f"No recruit should occur with 0 influence, discard {len(discard_before)} → {len(discard_after)}"

    session.destroy()


def test_air_elemental_focus_draw_with_duplicate_cards():
    """Air Elemental focus draw must work when hand has two copies of the same
    Guile card.  The second copy is a different physical card and satisfies
    focus — the Sym comparison must not exclude it."""
    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/random_card_generation/air_elemental_seed_666.json", engine
    )

    cp = session.state.current_player_id
    p_idx = session.state.player_index(cp)
    deck_before = len(session.state.player_deck(p_idx))

    assert deck_before >= 1, "Deck must have at least 1 card to draw"

    moves = session.legal_moves()
    ae = next(m for m in moves if m.move_type == "play_card" and m.data.get("card_id") == "air_elemental")
    session.submit_move(ae)

    # Choose Option 2 (return spy + deploy 3 troops + focus draw)
    moves = session.legal_moves()
    gen = [m for m in moves if m.move_type == "resolve_generic"]
    opt2 = next(m for m in gen if m.data.get("action_id") == "option_2")
    session.submit_move(opt2)

    # Resolve all remaining generic moves
    while True:
        moves = session.legal_moves()
        gen = [m for m in moves if m.move_type == "resolve_generic"]
        if not gen:
            break
        session.submit_move(gen[0])

    deck_after = len(session.state.player_deck(p_idx))
    assert deck_after == deck_before - 1, \
        f"Expected 1 card drawn (deck {deck_before} -> {deck_before-1}), got {deck_after}"

    session.destroy()


def test_air_elemental_option_1_focus_draw():
    """Option 1 (place spy) must also draw a card when Guile focus is met
    (catalog fix: option_1 was missing the draw_cards action)."""
    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/random_card_generation/air_elemental_seed_666.json", engine
    )

    raw = CSession.save_to_string(session.state, move_count=0, is_terminal=False)
    session.destroy()
    payload = json.loads(raw)
    gs = payload["state"]
    cp = gs["current_player_id"]
    cp_data = next(p for p in gs["players"] if p["player_id"] == cp)
    cp_data["spies_available"] = max(cp_data["spies_available"], 1)
    has_guile = any(c != "air_elemental" and _is_aspect(c, "guile") for c in cp_data["hand"])
    if not has_guile:
        _ensure_guile_focus(cp_data, gs)

    tmp_path = "data/scenarios/test_card_generation/_ae_opt1_test.json"
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    engine2 = CEngine()
    engine2.initialize()
    session2 = CSession.load(tmp_path, engine2)

    p_idx = session2.state.player_index(cp)
    deck_before = len(session2.state.player_deck(p_idx))

    moves = session2.legal_moves()
    ae = next(m for m in moves if m.move_type == "play_card" and m.data.get("card_id") == "air_elemental")
    session2.submit_move(ae)

    moves = session2.legal_moves()
    gen = [m for m in moves if m.move_type == "resolve_generic"]
    opt1 = next(m for m in gen if m.data.get("action_id") == "option_1")
    result = session2.submit_move(opt1)
    assert result is not None, "Option 1 submit failed"

    moves = session2.legal_moves()
    gen = [m for m in moves if m.move_type == "resolve_generic"]
    if gen:
        session2.submit_move(gen[0])

    deck_after = len(session2.state.player_deck(p_idx))
    assert deck_after == deck_before - 1, \
        f"Expected 1 card drawn via Option 1 (deck {deck_before} -> {deck_before-1}), got {deck_after}"

    session2.destroy()


def test_water_elemental_focus_draw():
    """Water Elemental must draw a card when Conquest focus is met
    (catalog fix: draw_cards action was missing from execution model)."""
    engine = CEngine()
    engine.initialize()
    session = CSession.load(
        "data/scenarios/test_card_generation/we_focus_test.json", engine
    )

    raw = CSession.save_to_string(session.state, move_count=0, is_terminal=False)
    session.destroy()
    payload = json.loads(raw)
    gs = payload["state"]
    cp = gs["current_player_id"]
    cp_data = next(p for p in gs["players"] if p["player_id"] == cp)

    has_conquest = any(c != "water_elemental" and _is_aspect(c, "conquest") for c in cp_data["hand"])
    if not has_conquest:
        _ensure_aspect_focus(cp_data, gs, "conquest", "black_wyrmling")

    site_found = False
    for node in gs["nodes"]:
        if "troop_slots" in node and len(node["troop_slots"]) >= 2:
            site_found = True
            break
    if not site_found:
        gs["nodes"][0]["troop_slots"] = [None, None, None]

    tmp_path = "data/scenarios/test_card_generation/_we_focus_test.json"
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    engine2 = CEngine()
    engine2.initialize()
    session2 = CSession.load(tmp_path, engine2)

    p_idx = session2.state.player_index(cp)
    deck_before = len(session2.state.player_deck(p_idx))

    moves = session2.legal_moves()
    we = next(m for m in moves if m.move_type == "play_card" and m.data.get("card_id") == "water_elemental")
    session2.submit_move(we)

    while True:
        moves = session2.legal_moves()
        gen = [m for m in moves if m.move_type == "resolve_generic"]
        if not gen:
            break
        session2.submit_move(gen[0])

    deck_after = len(session2.state.player_deck(p_idx))
    assert deck_after == deck_before - 1, \
        f"Expected 1 card drawn via Water Elemental (deck {deck_before} -> {deck_before-1}), got {deck_after}"

    session2.destroy()


def _is_aspect(card_id: str, aspect: str) -> bool:
    cat = assemble_catalog_payload(Path("data/cards"))["cards"]
    for c in cat:
        if c["card_id"] == card_id:
            return c["aspect"] == aspect
    return False


def _ensure_guile_focus(player_data: dict, game_state: dict) -> None:
    _ensure_aspect_focus(player_data, game_state, "guile", "banshee")


def _ensure_aspect_focus(player_data: dict, game_state: dict, aspect: str, fallback: str) -> None:
    for i, c in enumerate(player_data["hand"]):
        if not _is_aspect(c, aspect):
            player_data["hand"][i] = fallback
            return
