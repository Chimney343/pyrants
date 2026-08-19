"""Black Wyrmling card behavior tests: gain 1 influence + assassinate a white troop."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _trophy_hall(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [
                _lib.intern_str(ps.trophy_hall[j]).decode()
                for j in range(ps.trophy_hall_count)
            ]
    return []


def _node_troop_slots(session: CSession, node_id: str) -> list[str | None]:
    s = session._state._ptr.contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            ns = s.nodes[ni]
            result = []
            for t in range(ns.troop_slot_count):
                occ = ns.troop_slots[t]
                result.append(_lib.intern_str(occ).decode() if occ != 0 else None)
            return result
    return []


def _influence(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.influence


def _resolve_generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if getattr(m, "move_type", "") == "resolve_generic"]


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _has_pending_generic(session: CSession) -> bool:
    return any(getattr(m, "move_type", "") == "resolve_generic" for m in session.legal_moves())


def test_black_wyrmling_gains_influence_and_assassinates_white_troop() -> None:
    """Play at site with presence + white troop: gain 1 influence, assassinate the white troop."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["black_wyrmling"]},
        troops={"white": {"site_gauntlgrym": ["white", None, None]}},
        spies={"site_gauntlgrym": ["p1"]},
        current_player="p1",
    )

    influence_before = _influence(session)
    trophies_before = len(_trophy_hall(session, "p1"))
    gaunt_before = _node_troop_slots(session, "site_gauntlgrym")
    assert "white" in gaunt_before, f"White troop should be at site_gauntlgrym: {gaunt_before}"

    _play_card(session, "black_wyrmling")

    rg_moves = _resolve_generic_moves(session)
    assert len(rg_moves) >= 1, f"Expected at least 1 resolve_generic for assassinate, got {len(rg_moves)}"
    assert rg_moves[0].data.get("target_id") == "0", (
        f"Assassinate should target slot 0 (white troop), got {rg_moves[0].data}"
    )

    session.submit_move(rg_moves[0])

    assert _influence(session) == influence_before + 1, "Should gain 1 influence"
    gaunt_after = _node_troop_slots(session, "site_gauntlgrym")
    assert "white" not in gaunt_after, f"White troop should be assassinated: {gaunt_after}"

    trophy_after = len(_trophy_hall(session, "p1"))
    assert trophy_after == trophies_before + 1, (
        f"Trophy hall should have +1 assassinated troop, got {trophy_after} (was {trophies_before})"
    )

    final_gen = _resolve_generic_moves(session)
    assert len(final_gen) == 0, (
        f"Expected 0 resolve_generic after assassinate, got {len(final_gen)}"
    )

    session.destroy()


def test_black_wyrmling_no_valid_target_auto_resolves() -> None:
    """When no white troop exists on board, gain influence and auto-resolve with no pending state."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["black_wyrmling", "noble"]},
        current_player="p1",
    )

    influence_before = _influence(session)
    trophies_before = len(_trophy_hall(session, "p1"))

    _play_card(session, "black_wyrmling")

    assert _influence(session) == influence_before + 1, "Should gain 1 influence"
    assert not _has_pending_generic(session), "No pending generic when no white troops"

    s = session._state._ptr.contents
    assert not s.pending_generic, "pending_generic should be NULL"

    assert len(_trophy_hall(session, "p1")) == trophies_before, "Trophy hall unchanged"

    move_types = {getattr(m, "move_type", "") for m in session.legal_moves()}
    assert "play_card" in move_types, "Should still be able to play other cards"
    assert "end_main_phase" in move_types, "Should be able to end main phase"

    session.destroy()


def test_black_wyrmling_only_targets_white_troops() -> None:
    """At a site with non-white enemy troops, no resolve_generic moves should be generated."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["black_wyrmling"]},
        troops={"p2": {"site_gauntlgrym": ["p2", None, None]}},
        spies={"site_gauntlgrym": ["p1"]},
        current_player="p1",
    )

    influence_before = _influence(session)

    _play_card(session, "black_wyrmling")

    assert _influence(session) == influence_before + 1, "Should gain 1 influence"
    assert not _has_pending_generic(session), (
        "No resolve_generic when only non-white troops exist"
    )

    gaunt_after = _node_troop_slots(session, "site_gauntlgrym")
    assert "p2" in gaunt_after, "p2's troop should still be there"

    session.destroy()


def test_black_wyrmling_requires_presence_for_target_site() -> None:
    """White troop at a site without presence should not be targetable."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["black_wyrmling"]},
        troops={"white": {"site_gauntlgrym": ["white", None, None]}},
        current_player="p1",
    )

    influence_before = _influence(session)

    _play_card(session, "black_wyrmling")

    assert _influence(session) == influence_before + 1, "Should gain 1 influence"

    rg_moves = _resolve_generic_moves(session)
    assert len(rg_moves) == 0, (
        f"Expected 0 resolve_generic (no presence at site with white), got {len(rg_moves)}"
    )

    gaunt_after = _node_troop_slots(session, "site_gauntlgrym")
    assert "white" in gaunt_after, "White troop should still be there (no presence)"

    session.destroy()


def test_black_wyrmling_trophy_hall_contains_assassinated_white() -> None:
    """Assassinated white troop should appear in the trophy hall as 'white'."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["black_wyrmling"]},
        troops={"white": {"site_gauntlgrym": ["white", None, None]}},
        spies={"site_gauntlgrym": ["p1"]},
        current_player="p1",
    )

    _play_card(session, "black_wyrmling")

    rg_moves = _resolve_generic_moves(session)
    assert len(rg_moves) >= 1, f"Expected at least 1 resolve_generic, got {len(rg_moves)}"
    session.submit_move(rg_moves[0])

    trophies = _trophy_hall(session, "p1")
    assert "white" in trophies, f"Trophy hall should contain 'white', got {trophies}"

    session.destroy()


def test_black_wyrmling_influence_gained_even_without_white_target() -> None:
    """Influence is gained regardless of whether an assassinate target exists."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["black_wyrmling"]},
        current_player="p1",
    )

    _play_card(session, "black_wyrmling")

    assert _influence(session) == 1, "Should have gained 1 influence"
    assert not _has_pending_generic(session), "Card should be fully resolved"

    session.destroy()


def test_black_wyrmling_catalog_structure() -> None:
    """Verify execution_model: sequence with gain_resource + assassinate_troop."""
    catalog = assemble_catalog_payload(DATA_DIR / "cards")

    card = None
    for c in catalog["cards"]:
        if c["card_id"] == "black_wyrmling":
            card = c
            break
    assert card is not None, "Black Wyrmling not found in catalog"

    assert card["cost"] == 3
    assert card["aspect"] == "conquest"
    assert card["deck_vp"] == 1
    assert card["inner_circle_vp"] == 4
    assert "Assassinate a white troop" in card["rules_text"]
    assert "Gain 1 influence" in card["rules_text"]

    em = card["execution_model"]
    assert em["kind"] == "sequence", f"Expected sequence, got {em['kind']}"
    actions = em["actions"]
    assert len(actions) == 2, f"Expected 2 actions, got {len(actions)}"

    a1 = actions[0]
    assert a1["op"] == "gain_resource", f"action_1 should be gain_resource, got {a1['op']}"
    assert a1["optional"] is False, "action_1 must be mandatory"
    assert a1["quantity"] == {"kind": "fixed", "value": 1}
    assert a1["metadata"]["resource"] == "influence"

    a2 = actions[1]
    assert a2["op"] == "assassinate_troop", f"action_2 should be assassinate_troop, got {a2['op']}"
    assert a2["optional"] is False, "action_2 must be mandatory"
    assert "white_troop_only" in a2["filters"]
