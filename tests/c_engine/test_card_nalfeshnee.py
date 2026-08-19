"""Nalfeshnee card behavior tests: gain 3 influence + promote top of deck.

Nalfeshnee: "Gain 3 influence. Promote the top card of your draw deck directly
into your promoted area. If your draw deck is empty, apply normal
shuffle-to-refill rules first."

The card is a sequence of two immediate, self-scoped, non-optional actions, so
playing it should resolve fully with no pending generic choice.
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_CARD_ID = "nalfeshnee"


def _init_engine() -> CEngine:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return eng


def _sptr(session: CSession):
    return session._state._ptr.contents


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _influence(session: CSession) -> int:
    return _sptr(session).resource_pool.influence


def _player_deck(session: CSession, player_id: str) -> list[str]:
    s = _sptr(session)
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [_lib.intern_str(ps.deck[j]).decode() for j in range(ps.deck_count)]
    return []


def _player_inner_circle(session: CSession, player_id: str) -> list[str]:
    s = _sptr(session)
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [_lib.intern_str(ps.inner_circle[j]).decode() for j in range(ps.inner_circle_count)]
    return []


def _set_discard(session: CSession, player_index: int, card_ids: list[str]) -> None:
    ps = _sptr(session).players[player_index]
    ps.discard_pile_count = len(card_ids)
    for j, cid in enumerate(card_ids):
        ps.discard_pile[j] = _lib.intern(cid.encode())


def test_nalfeshnee_gains_three_influence() -> None:
    """Playing Nalfeshnee grants exactly 3 influence."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        deck={"p1": ["soldier"]},
        current_player="p1",
    )
    _sptr(session).resource_pool.influence = 0

    _play_card(session, _CARD_ID)

    assert _influence(session) == 3, f"Expected 3 influence, got {_influence(session)}"
    session.destroy()


def test_nalfeshnee_promotes_top_of_deck() -> None:
    """Nalfeshnee promotes the top card (highest index) of the draw deck."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        deck={"p1": ["soldier", "noble"]},
        current_player="p1",
    )
    ic_before = _player_inner_circle(session, "p1")

    _play_card(session, _CARD_ID)

    deck_after = _player_deck(session, "p1")
    ic_after = _player_inner_circle(session, "p1")

    assert len(ic_after) == len(ic_before) + 1, f"Expected 1 more inner circle card, got {ic_after}"
    assert "noble" in ic_after, f"Expected 'noble' in inner circle: {ic_after}"
    assert "noble" not in deck_after, f"Expected 'noble' removed from deck: {deck_after}"
    assert "soldier" in deck_after, f"Expected 'soldier' still in deck: {deck_after}"
    session.destroy()


def test_nalfeshnee_resolves_without_pending_generic() -> None:
    """Both actions are immediate and self-scoped, so no pending choice remains."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        deck={"p1": ["soldier"]},
        current_player="p1",
    )

    _play_card(session, _CARD_ID)

    assert not _sptr(session).pending_generic, "Nalfeshnee should fully resolve without a pending choice"
    session.destroy()


def test_nalfeshnee_shuffles_discard_into_deck_when_empty() -> None:
    """With an empty draw deck, Nalfeshnee refills from discard then promotes."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _set_discard(session, 0, ["bounty_hunter", "noble"])

    _play_card(session, _CARD_ID)

    ic_after = _player_inner_circle(session, "p1")
    assert len(ic_after) == 1, f"Expected 1 card in inner circle, got {ic_after}"
    session.destroy()


def test_nalfeshnee_empty_deck_and_discard_gains_influence_only() -> None:
    """With nothing to promote, Nalfeshnee still gains influence and does not crash."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )
    _sptr(session).resource_pool.influence = 0

    _play_card(session, _CARD_ID)

    assert _influence(session) == 3, f"Expected 3 influence, got {_influence(session)}"
    assert _player_inner_circle(session, "p1") == []
    session.destroy()
