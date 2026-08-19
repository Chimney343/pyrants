"""Matron Mother: Mill draw deck into discard pile, then promote a card from discard pile."""

from __future__ import annotations

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _sptr,
    make_card_test_session,
)


def _discard_pile_ids(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [
                _lib.intern_str(s.players[i].discard_pile[j]).decode()
                for j in range(s.players[i].discard_pile_count)
            ]
    return []


def _discard_pile_count(session: CSession, pid: str) -> int:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return s.players[i].discard_pile_count
    return 0


def _deck_count(session: CSession, pid: str) -> int:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return s.players[i].deck_count
    return 0


def _inner_circle_ids(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [
                _lib.intern_str(s.players[i].inner_circle[j]).decode()
                for j in range(s.players[i].inner_circle_count)
            ]
    return []


def _inner_circle_count(session: CSession, pid: str) -> int:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return s.players[i].inner_circle_count
    return 0


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def test_matron_mother_mills_deck_into_discard() -> None:
    """Playing Matron Mother moves all deck cards into the discard pile."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["matron_mother", "noble"]},
        current_player="p1",
    )
    s = _sptr(session).contents
    p1 = s.players[0]
    p1.deck_count = 4
    for j, cid in enumerate(["soldier", "house_guard", "priestess_of_lolth", "noble"]):
        p1.deck[j] = _lib.intern(cid.encode())

    deck_before = _deck_count(session, "p1")
    discard_before = _discard_pile_count(session, "p1")
    assert deck_before == 4
    assert discard_before == 0

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "matron_mother":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Matron Mother not playable")

    assert _deck_count(session, "p1") == 0, "Deck should be empty after mill"
    assert _discard_pile_count(session, "p1") == 4, "All 4 deck cards should be in discard pile"
    assert _has_pending_generic(session), "Should await promote selection"

    discard_ids = _discard_pile_ids(session, "p1")
    assert "soldier" in discard_ids
    assert "house_guard" in discard_ids
    assert "priestess_of_lolth" in discard_ids
    assert "noble" in discard_ids

    session.destroy()


def test_matron_mother_promote_from_discard_shows_discard_targets() -> None:
    """After mill, legal moves should show discard pile cards as promotion targets."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["matron_mother"]},
        current_player="p1",
    )
    s = _sptr(session).contents
    p1 = s.players[0]
    p1.deck_count = 2
    p1.deck[0] = _lib.intern(b"soldier")
    p1.deck[1] = _lib.intern(b"noble")

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "matron_mother":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Matron Mother not playable")

    generic_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    target_ids = {m.data.get("action_id") for m in generic_moves}

    assert "soldier" in target_ids, f"Discard pile cards should be promotion targets, got: {target_ids}"
    assert "noble" in target_ids, f"Discard pile cards should be promotion targets, got: {target_ids}"

    session.destroy()


def test_matron_mother_promotes_selected_card_from_discard_to_inner_circle() -> None:
    """Selecting a discard pile card promotes it to inner_circle."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["matron_mother"]},
        current_player="p1",
    )
    s = _sptr(session).contents
    p1 = s.players[0]
    p1.deck_count = 2
    p1.deck[0] = _lib.intern(b"soldier")
    p1.deck[1] = _lib.intern(b"noble")

    inner_before = _inner_circle_count(session, "p1")

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "matron_mother":
            session.submit_move(m)
            break

    generic_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    soldier_move = next(
        (m for m in generic_moves if m.data.get("action_id") == "soldier"), None
    )
    assert soldier_move is not None, "soldier should be selectable from discard"
    session.submit_move(soldier_move)

    assert not _has_pending_generic(session), "No pending generics after promotion"

    assert _inner_circle_count(session, "p1") == inner_before + 1, (
        f"Inner circle should increase by 1: was {inner_before}, now {_inner_circle_count(session, 'p1')}"
    )
    inner_ids = _inner_circle_ids(session, "p1")
    assert "soldier" in inner_ids, f"soldier should be in inner_circle: {inner_ids}"
    assert "noble" not in inner_ids, f"noble should still be in discard, not inner_circle: {inner_ids}"

    discard_ids = _discard_pile_ids(session, "p1")
    assert "soldier" not in discard_ids, f"soldier should be removed from discard: {discard_ids}"
    assert "noble" in discard_ids, f"noble should remain in discard: {discard_ids}"

    session.destroy()


def test_matron_mother_promote_from_empty_discard_is_no_op() -> None:
    """When deck and discard are both empty, mill does nothing and promote shows no targets."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["matron_mother"]},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "matron_mother":
            session.submit_move(m)
            break

    assert _deck_count(session, "p1") == 0
    assert _discard_pile_count(session, "p1") == 0

    generic_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(generic_moves) == 0, (
        f"Empty discard should yield no promotion targets, got: "
        f"{[(m.data.get('action_id'), m.data.get('target_id')) for m in generic_moves]}"
    )

    session.destroy()


def test_matron_mother_catalog_consistency() -> None:
    """Catalog execution_model and actions match rules_text."""
    from pathlib import Path

    catalog = assemble_catalog_payload(Path(__file__).resolve().parents[2] / "data" / "cards")
    cards = catalog if isinstance(catalog, list) else catalog.get("cards", catalog)
    mm = next(c for c in cards if c.get("card_id") == "matron_mother")

    actions = mm["execution_model"]["actions"]
    assert len(actions) == 2
    assert actions[0]["op"] == "custom_effect"
    assert actions[0]["metadata"]["effect_kind"] == "mill_deck_to_discard"
    assert actions[1]["op"] == "promote_card"
    assert actions[1]["source_fragment"] == "promote_from_discard"

    assert "Put your draw deck into your discard pile" in mm["rules_text"]
    assert "promote a card from your discard pile" in mm["rules_text"]

    assert mm["execution_model"]["actions"] == mm["actions"], (
        "execution_model and actions should be identical"
    )
