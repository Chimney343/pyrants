"""Insane Outcast: discard another card from hand, then return Insane Outcast to supply.

Also: if Insane Outcast would be devoured or promoted, return it to supply instead.
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _player_hand(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == pid:
            ps = s.players[i]
            return [_lib.intern_str(ps.hand[j]).decode() for j in range(ps.hand_count)]
    return []


def _player_discard(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == pid:
            ps = s.players[i]
            return [_lib.intern_str(ps.discard_pile[j]).decode() for j in range(ps.discard_pile_count)]
    return []


def _player_played(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == pid:
            ps = s.players[i]
            return [_lib.intern_str(ps.played_cards[j]).decode() for j in range(ps.played_cards_count)]
    return []


def _player_inner_circle(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == pid:
            ps = s.players[i]
            return [_lib.intern_str(ps.inner_circle[j]).decode() for j in range(ps.inner_circle_count)]
    return []


def _devour_pile(session: CSession) -> list[str]:
    s = session._state._ptr.contents
    return [_lib.intern_str(s.devour_pile[j]).decode() for j in range(s.devour_pile_count)]


def _set_played_cards(session: CSession, pid: str, card_ids: list[str]) -> None:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == pid:
            ps = s.players[i]
            ps.played_cards_count = min(len(card_ids), 80)
            for j, cid in enumerate(card_ids[:80]):
                ps.played_cards[j] = _lib.intern(cid.encode())
            return


def _resolve_generic(session: CSession, action_id: str) -> bool:
    """Submit the first resolve_generic move whose action_id matches. Return True if found."""
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == action_id:
            session.submit_move(m)
            return True
    return False


def test_insane_outcast_discard_another_card_and_return_to_supply():
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["insane_outcast", "noble"]},
        current_player="p1",
    )

    hand_before = _player_hand(session, "p1")
    discard_before = _player_discard(session, "p1")
    assert "noble" in hand_before
    assert len(discard_before) == 0

    _play_card(session, "insane_outcast")

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert gen_moves, "Expected a resolve_generic move to choose a card to discard"

    for m in gen_moves:
        if m.data.get("action_id") == "noble":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError(f"No resolve_generic move for noble; got: {gen_moves}")

    hand_after = _player_hand(session, "p1")
    discard_after = _player_discard(session, "p1")
    played_after = _player_played(session, "p1")

    assert "noble" not in hand_after, f"noble should be removed from hand, got {hand_after}"
    assert "noble" in discard_after, f"noble should be in discard, got {discard_after}"
    assert "insane_outcast" not in played_after, (
        f"insane_outcast should NOT be in played cards (returned to supply), got {played_after}"
    )
    assert "insane_outcast" not in hand_after, (
        f"insane_outcast should NOT be in hand after play, got {hand_after}"
    )

    session.destroy()


def test_insane_outcast_promote_returns_to_supply():
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["necromancer"]},
        current_player="p1",
    )
    _set_played_cards(session, "p1", ["insane_outcast"])

    _play_card(session, "necromancer")
    _resolve_generic(session, "option_2")

    promoted = _resolve_generic(session, "insane_outcast")

    played_after = _player_played(session, "p1")
    inner_after = _player_inner_circle(session, "p1")

    assert promoted, "Should have been able to select insane_outcast for promotion"
    assert "insane_outcast" not in inner_after, (
        f"insane_outcast should NOT be in inner circle (returned to supply), got {inner_after}"
    )
    assert "insane_outcast" not in played_after, (
        f"insane_outcast should be removed from played cards, got {played_after}"
    )

    session.destroy()


def test_insane_outcast_devour_returns_to_supply():
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["balor", "insane_outcast"]},
        current_player="p1",
    )

    hand_before = _player_hand(session, "p1")
    assert "insane_outcast" in hand_before

    _play_card(session, "balor")

    devoured = _resolve_generic(session, "insane_outcast")

    hand_after = _player_hand(session, "p1")
    devour_after = _devour_pile(session)

    assert devoured, "Should have been able to select insane_outcast for devour"
    assert "insane_outcast" not in devour_after, (
        f"insane_outcast should NOT be in devour pile (returned to supply), got {devour_after}"
    )
    assert "insane_outcast" not in hand_after, (
        f"insane_outcast should be removed from hand, got {hand_after}"
    )

    session.destroy()
