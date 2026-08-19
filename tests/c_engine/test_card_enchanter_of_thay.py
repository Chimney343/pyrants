"""Enchanter of Thay card behavior tests.

Modal choice: choose exactly one mode.
- Option 1: place a spy at a board site.
- Option 2: return one of your spies and gain 4 power.
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine, _sym_str
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_SITE = "site_gauntlgrym"
_CARD = "enchanter_of_thay"


def _power(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.power


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _pick_option(session: CSession, option_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == option_id:
            result = session.submit_move(m)
            if result is None:
                session.destroy()
                raise AssertionError(f"Option {option_id} was rejected")
            return
    session.destroy()
    movelist = [str(m) for m in session.legal_moves()]
    raise AssertionError(f"Option {option_id} not found; moves: {movelist}")


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    s = session._state._ptr.contents
    from engine_c.bindings.engine_bindings import _lib
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            result = []
            for si in range(s.nodes[ni].spy_count):
                spy_str = _lib.intern_str(s.nodes[ni].spies[si])
                if spy_str:
                    result.append(spy_str.decode())
            return result
    return []


def _spies_available(session: CSession, pid: str) -> int:
    s = session._state._ptr.contents
    for pi in range(s.player_count):
        pid_str = _sym_str(s.player_ids[pi])
        if pid_str == pid:
            return s.players[pi].spies_available
    return -1


def _has_pending_generic(session: CSession) -> bool:
    return any(m.move_type == "resolve_generic" for m in session.legal_moves())


# --- Tests ---


def test_enchanter_of_thay_modal_has_two_options():
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD]},
        spies={_SITE: ["p1"]},
        current_player="p1",
    )
    _play_card(session, _CARD)

    generic_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    option_ids = {m.data.get("action_id") for m in generic_moves}
    assert option_ids == {"option_1", "option_2"}, f"Expected both options; got {option_ids}"

    session.destroy()


def test_enchanter_of_thay_option_1_places_spy():
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD]},
        current_player="p1",
    )
    _play_card(session, _CARD)

    # With 5 spies available, option_1 should be available
    opt1 = [m for m in session.legal_moves() if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_1"]
    assert opt1, "option_1 should be available"
    assert opt1[0].data.get("target_id") != "unavailable", "option_1 should not be unavailable"

    session.destroy()


def test_enchanter_of_thay_option_2_available_with_spy_on_board():
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD]},
        spies={_SITE: ["p1"]},
        current_player="p1",
    )
    _play_card(session, _CARD)

    opt2 = [m for m in session.legal_moves() if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2"]
    assert opt2, "option_2 should be listed"
    assert opt2[0].data.get("target_id") != "unavailable", f"option_2 should be available; got {opt2[0].data}"

    session.destroy()


def test_enchanter_of_thay_option_2_unavailable_without_spy_on_board():
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD]},
        current_player="p1",
    )
    _play_card(session, _CARD)

    opt2 = [m for m in session.legal_moves() if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2"]
    assert opt2, "option_2 should still be listed"
    assert opt2[0].data.get("target_id") == "unavailable", (
        f"option_2 should be unavailable without a spy on board; got {opt2[0].data}"
    )

    session.destroy()


def test_enchanter_of_thay_option_2_returns_spy_and_grants_4_power():
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD]},
        spies={_SITE: ["p1"]},
        current_player="p1",
    )
    _play_card(session, _CARD)

    # Pick option_2
    _pick_option(session, "option_2")

    # Should now have return_spy target selection
    targets = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(targets) == 1, f"Expected 1 return_spy target, got {len(targets)}"
    assert targets[0].data.get("action_id") == _SITE, (
        f"Expected target site {_SITE}, got {targets[0].data.get('action_id')}"
    )

    # Execute the return
    spy_available_before = _spies_available(session, "p1")
    session.submit_move(targets[0])

    # Verify: power should be 4
    assert _power(session) == 4, f"Expected 4 power after option_2, got {_power(session)}"

    # Verify: spy should have been returned (spy count at site dropped by 1)
    spy_available_after = _spies_available(session, "p1")
    assert _spies_at_node(session, _SITE) == [], "Site should have no p1 spies after return"
    assert spy_available_after == spy_available_before + 1, (
        f"Expected spies_available to increase by 1, got {spy_available_before} -> {spy_available_after}"
    )

    # Verify: card fully resolved, no pending generic moves
    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert not gen, f"Expected no pending generic moves, got {len(gen)}"

    session.destroy()
