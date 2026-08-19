"""Derro card behavior tests: supplant white troop, then recruit Insane Outcast."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from game_setup.loaders import assemble_catalog_payload
from tests.c_engine.card_test_helpers import make_card_test_session

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "batch_card_generation" / "023_seed_4_derro.json"
)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _player_discard(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [_lib.intern_str(ps.discard_pile[j]).decode() for j in range(ps.discard_pile_count)]
    return []


def _player_all_zones(session: CSession, player_id: str) -> dict[str, list[str]]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return {
                "hand": [_lib.intern_str(ps.hand[j]).decode() for j in range(ps.hand_count)],
                "deck": [_lib.intern_str(ps.deck[j]).decode() for j in range(ps.deck_count)],
                "discard": [_lib.intern_str(ps.discard_pile[j]).decode() for j in range(ps.discard_pile_count)],
                "played": [_lib.intern_str(ps.played_cards[j]).decode() for j in range(ps.played_cards_count)],
                "inner_circle": [_lib.intern_str(ps.inner_circle[j]).decode() for j in range(ps.inner_circle_count)],
            }
    return {}


def test_derro_supplant_then_recruit_insane_outcast() -> None:
    """Playing Derro should supplant a white troop then auto-recruit an Insane Outcast into discard."""
    session = CSession.load(str(SCENARIO_PATH))

    before_discard = _player_discard(session, "p4")
    before_io_count = before_discard.count("insane_outcast")

    # Play Derro
    played = False
    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "derro":
            session.submit_move(m)
            played = True
            break
    assert played, "Derro must be playable"

    # Resolve the supplant_troop selection
    view = build_c_game_view(session)
    resolve_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert len(resolve_moves) > 0, "Derro must prompt for supplant target"
    session.submit_move(resolve_moves[0].move)

    # After both actions (supplant + auto-recruit), there should be no more pending choices
    view = build_c_game_view(session)
    resolve_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert len(resolve_moves) == 0, "Derro must fully resolve with no remaining generic choices"

    # Verify Insane Outcast was added to discard
    after_discard = _player_discard(session, "p4")
    after_io_count = after_discard.count("insane_outcast")
    assert after_io_count == before_io_count + 1, (
        f"Expected {before_io_count + 1} Insane Outcasts in discard, found {after_io_count}"
    )

    session.destroy()


def test_derro_does_not_affect_other_players() -> None:
    """Only the current player (p4) should receive the Insane Outcast."""
    session = CSession.load(str(SCENARIO_PATH))

    before = {
        pid: _player_discard(session, pid).count("insane_outcast")
        for pid in ["p1", "p2", "p3", "p4"]
    }

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "derro":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    rm = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    session.submit_move(rm[0].move)

    after = {
        pid: _player_discard(session, pid).count("insane_outcast")
        for pid in ["p1", "p2", "p3", "p4"]
    }

    assert after["p4"] == before["p4"] + 1, f"p4 should gain 1 IO: {before['p4']} → {after['p4']}"
    assert after["p1"] == before["p1"], f"p1 should be unchanged: {before['p1']} → {after['p1']}"
    assert after["p2"] == before["p2"], f"p2 should be unchanged: {before['p2']} → {after['p2']}"
    assert after["p3"] == before["p3"], f"p3 should be unchanged: {before['p3']} → {after['p3']}"

    session.destroy()


def test_derro_programmatic_session() -> None:
    """Test Derro with a programmatically constructed session using make_card_test_session."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["derro"]},
        current_player="p1",
    )

    # Pre-populate discard so we can observe the delta
    s = session._state._ptr.contents
    p1 = s.players[0]
    p1.discard_pile[0] = _lib.intern(b"soldier")
    p1.discard_pile_count = 1

    before_discard = _player_discard(session, "p1")
    assert before_discard.count("insane_outcast") == 0

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "derro":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    rm = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    assert len(rm) > 0, "Must have supplant target even on near-empty board"
    session.submit_move(rm[0].move)

    after_discard = _player_discard(session, "p1")
    assert after_discard.count("insane_outcast") == 1, (
        f"Expected 1 Insane Outcast, found {after_discard.count('insane_outcast')}"
    )
    assert len(after_discard) == before_discard.__len__() + 1, (
        f"Discard should grow by 1: {len(before_discard)} → {len(after_discard)}"
    )

    session.destroy()


def test_cstate_player_deck_and_played_methods() -> None:
    """player_deck() and player_played() on CState return correct lists."""
    session = CSession.load(str(SCENARIO_PATH))
    cstate = session.state

    for pid in ["p1", "p2", "p3", "p4"]:
        idx = cstate.player_index(pid)
        deck = cstate.player_deck(idx)
        played = cstate.player_played(idx)
        assert isinstance(deck, list), f"player_deck({pid}) must return list"
        assert isinstance(played, list), f"player_played({pid}) must return list"
        assert all(isinstance(c, str) for c in deck)
        assert all(isinstance(c, str) for c in played)

    session.destroy()


def test_derro_only_adds_insane_outcast_to_discard_not_other_zones() -> None:
    """The auto-recruited Insane Outcast goes only to discard, not hand/deck/played/inner."""
    session = CSession.load(str(SCENARIO_PATH))

    before_zones = _player_all_zones(session, "p4")

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "derro":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    rm = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    session.submit_move(rm[0].move)

    after_zones = _player_all_zones(session, "p4")

    # Discard gains exactly 1 Insane Outcast
    disc_before = before_zones["discard"].count("insane_outcast")
    disc_after = after_zones["discard"].count("insane_outcast")
    assert disc_after == disc_before + 1, f"discard IO: {disc_before} → {disc_after}"

    # Other zones should not have gained any Insane Outcast
    for zone in ["hand", "deck", "played", "inner_circle"]:
        b = before_zones[zone].count("insane_outcast")
        a = after_zones[zone].count("insane_outcast")
        assert a == b, f"{zone} IO should not change: {b} → {a}"

    session.destroy()


def test_derro_view_reflects_discard() -> None:
    """build_c_game_view must show the updated discard after Derro resolves."""
    session = CSession.load(str(SCENARIO_PATH))

    view_before = build_c_game_view(session)
    io_before = [cv.card_id for cv in view_before.current_player_discard].count("insane_outcast")

    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == "derro":
            session.submit_move(m)
            break

    view = build_c_game_view(session)
    rm = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    session.submit_move(rm[0].move)

    view_after = build_c_game_view(session)
    io_after = [cv.card_id for cv in view_after.current_player_discard].count("insane_outcast")

    assert io_after == io_before + 1, (
        f"View should show +1 Insane Outcast: {io_before} → {io_after}"
    )

    session.destroy()


def test_derro_catalog_encoding_auto_recruits_insane_outcast() -> None:
    """Derro's second action must be ``custom_effect``/``give_insane_outcast_to_self``.

    Regression guard: a catalog refactor changed this to ``recruit_card`` with
    ``target_scope: market``, which asks the player to buy a market-row card and
    can never deliver the Insane Outcast (it lives in a special stack, not the
    market row).
    """
    catalog = assemble_catalog_payload(DATA_DIR / "cards")
    derro = next(c for c in catalog["cards"] if c["card_id"] == "derro")

    for action in (derro["execution_model"]["actions"][1], derro["actions"][1]):
        assert action["op"] == "custom_effect", f"expected custom_effect, got {action['op']}"
        assert action["target_scope"] == "self", f"expected target_scope self, got {action['target_scope']}"
        assert action["metadata"] == {"effect_kind": "give_insane_outcast_to_self"}, (
            f"expected give_insane_outcast_to_self, got {action['metadata']}"
        )
