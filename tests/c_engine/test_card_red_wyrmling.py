"""Red Wyrmling card behavior tests: gain 2 power and 2 influence.

Red Wyrmling is a simple fixed-resource card with no timing or targeting
questions. Its execution model is a sequence of two ``gain_resource`` actions
targeting ``self``, so the card fully auto-resolves on play with no pending
generic choice.
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _power(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.power


def _influence(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.influence


def _played_cards(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [
                _lib.intern_str(ps.played_cards[j]).decode()
                for j in range(ps.played_cards_count)
            ]
    return []


def _resolve_generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if getattr(m, "move_type", "") == "resolve_generic"]


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _build_session() -> CSession:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["red_wyrmling"]},
        current_player="p1",
    )


def test_red_wyrmling_gains_two_power_and_two_influence() -> None:
    """Playing Red Wyrmling grants exactly 2 power and 2 influence."""
    session = _build_session()

    power_before = _power(session)
    influence_before = _influence(session)

    _play_card(session, "red_wyrmling")

    assert _power(session) == power_before + 2, (
        f"Expected +2 power, got {_power(session) - power_before}"
    )
    assert _influence(session) == influence_before + 2, (
        f"Expected +2 influence, got {_influence(session) - influence_before}"
    )

    session.destroy()


def test_red_wyrmling_auto_resolves_without_pending_choice() -> None:
    """The card has no targets, so it resolves fully with no pending generic moves."""
    session = _build_session()

    _play_card(session, "red_wyrmling")

    assert not _resolve_generic_moves(session), (
        "Expected no pending generic choice for a self-targeted resource card"
    )

    session.destroy()


def test_red_wyrmling_moves_to_played_cards() -> None:
    """Playing the card removes it from hand and places it in played_cards."""
    session = _build_session()

    _play_card(session, "red_wyrmling")

    played = _played_cards(session, "p1")
    assert "red_wyrmling" in played, f"Expected red_wyrmling in played_cards, got {played}"

    session.destroy()


def test_red_wyrmling_catalog_structure() -> None:
    """Verify the catalog execution_model encodes rules_text faithfully."""
    catalog = assemble_catalog_payload(DATA_DIR / "cards")

    card = None
    for c in catalog["cards"]:
        if c["card_id"] == "red_wyrmling":
            card = c
            break
    assert card is not None, "Red Wyrmling not found in catalog"

    assert card["name"] == "Red Wyrmling"
    assert card["cost"] == 5
    assert card["aspect"] == "malice"
    assert card["deck_vp"] == 3
    assert card["inner_circle_vp"] == 5
    assert card["rules_text"] == "Gain 2 power and 2 influence."

    em = card["execution_model"]
    assert em["kind"] == "sequence", f"Expected sequence, got {em['kind']}"
    actions = em["actions"]
    assert len(actions) == 2, f"Expected 2 actions, got {len(actions)}"

    a1 = actions[0]
    assert a1["op"] == "gain_resource", f"action_1 should be gain_resource, got {a1['op']}"
    assert a1["target_scope"] == "self"
    assert a1["optional"] is False
    assert a1["quantity"] == {"kind": "fixed", "value": 2}
    assert a1["metadata"]["resource"] == "power"

    a2 = actions[1]
    assert a2["op"] == "gain_resource", f"action_2 should be gain_resource, got {a2['op']}"
    assert a2["target_scope"] == "self"
    assert a2["optional"] is False
    assert a2["quantity"] == {"kind": "fixed", "value": 2}
    assert a2["metadata"]["resource"] == "influence"
