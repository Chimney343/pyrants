"""Chosen of Lolth: Return another player's troop or spy where you have presence.
At end of turn, promote another played card (cannot self-promote)."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.engine_bindings import PHASE_END_OF_TURN, _lib
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload
from tests.c_engine.card_test_helpers import _make_engine, make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _played_ids(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].played_cards[j]).decode() for j in range(s.players[i].played_cards_count)]
    return []


def _inner_circle_ids(session: CSession, pid: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].inner_circle[j]).decode() for j in range(s.players[i].inner_circle_count)]
    return []


def test_chosen_of_lolth_return_requires_presence_and_opponent():
    """return_unit must target only opponent units at sites where the current
    player has presence, never own units or units at non-presence sites."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["chosen_of_lolth"]},
        troops={
            "p2": {
                "site_gauntlgrym": ["p1", "p2", None],
                "site_the_wormwrithings": ["p2", None, None],
            },
        },
        spies={
            "site_gauntlgrym": ["p1", "p2"],
        },
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "chosen_of_lolth":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Chosen of Lolth not playable")

    targets = {
        (m.data.get("action_id"), m.data.get("target_id"))
        for m in session.legal_moves()
        if m._move_type == "resolve_generic"
    }

    assert ("site_gauntlgrym", "troop:1") in targets, (
        f"Opponent troop at presence site should be targetable: {targets}"
    )
    assert ("site_gauntlgrym", "spy:p2") in targets, (
        f"Opponent spy at presence site should be targetable: {targets}"
    )

    assert ("site_gauntlgrym", "troop:0") not in targets, (
        f"Own troop should not be targetable: {targets}"
    )
    assert ("site_gauntlgrym", "spy:p1") not in targets, (
        f"Own spy should not be targetable: {targets}"
    )

    assert not any(a == "site_the_wormwrithings" for a, _ in targets), (
        f"No target at a non-presence site should be offered: {targets}"
    )

    session.destroy()


def test_chosen_of_lolth_eot_promote_cannot_self_target():
    """Chosen of Lolth's end-of-turn promote must exclude itself from targets."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["chosen_of_lolth", "noble"]},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "chosen_of_lolth":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Chosen of Lolth not playable")

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "noble":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Noble not playable")

    for m in session.legal_moves():
        if m._move_type == "end_main_phase":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("No end_main_phase")

    s = session._state._ptr.contents
    assert s.phase == PHASE_END_OF_TURN, f"Expected END_OF_TURN phase, got {s.phase}"

    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}

    assert "promote_card" in move_types, f"Should have promote_card move, got: {move_types}"

    promote_moves = [m for m in moves if m._move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}

    assert "chosen_of_lolth" not in promote_targets, f"Chosen of Lolth should not target itself: {promote_targets}"
    assert "noble" in promote_targets, "Noble should be a promote target"

    noble_promote = [m for m in promote_moves if m.data.get("card_id") == "noble"]
    assert len(noble_promote) == 1
    session.submit_move(noble_promote[0])

    assert "noble" in _inner_circle_ids(session, "p1"), "Noble should be promoted to inner_circle"
    assert "noble" not in _played_ids(session, "p1"), "Noble should be removed from played_cards"

    session.destroy()


def test_chosen_of_lolth_eot_no_other_played_card_skip_allowed():
    """If Chosen of Lolth is the only played card, skip should be available."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["chosen_of_lolth"]},
        current_player="p1",
    )

    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == "chosen_of_lolth":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("Chosen of Lolth not playable")

    for m in session.legal_moves():
        if m._move_type == "end_main_phase":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("No end_main_phase")

    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}

    assert "promote_card" not in move_types, f"No other played card, should not have promote, got: {move_types}"
    assert "skip_promote" in move_types, f"Should have skip_promote when no targets, got: {move_types}"

    skip = [m for m in moves if m._move_type == "skip_promote"][0]
    session.submit_move(skip)

    moves2 = session.legal_moves()
    move_types2 = {m._move_type for m in moves2}
    assert "resolve_end_of_turn" in move_types2, f"After skip, should have resolve_end_of_turn, got: {move_types2}"

    session.destroy()


def test_chosen_of_lolth_catalog_encoding() -> None:
    """The catalog must encode opponent-only return with presence, and
    end-of-turn promote of *another* played card.

    Regression guard: ``return_unit`` must not use ``self_or_opponent_unit``
    (which lets the player return their own pieces) and must require presence;
    ``promote_card`` must carry ``requires_another_played_card`` so Chosen of
    Lolth cannot promote itself and the effect does nothing with no other
    played card.
    """
    catalog = assemble_catalog_payload(DATA_DIR / "cards")
    card = next(c for c in catalog["cards"] if c["card_id"] == "chosen_of_lolth")

    for action in (card["execution_model"]["actions"][0], card["actions"][0]):
        assert action["op"] == "return_unit", f"expected return_unit, got {action['op']}"
        assert action["target_scope"] == "opponent_unit", (
            f"return must target opponent_unit only, got {action['target_scope']}"
        )
        assert action["metadata"].get("requires_presence") is True, (
            f"return must require presence, got {action['metadata']}"
        )

    for action in (card["execution_model"]["actions"][1], card["actions"][1]):
        assert action["op"] == "promote_card", f"expected promote_card, got {action['op']}"
        assert action["timing"] == "end_of_turn", f"expected end_of_turn, got {action['timing']}"
        assert action["metadata"].get("requires_another_played_card") is True, (
            f"requires_another_played_card must be true, got {action['metadata']}"
        )
