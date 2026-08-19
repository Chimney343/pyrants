"""Myconid Sovereign card behavior tests: promote another (not self)."""

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

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _legal_move_types(session: CSession):
    """Return list of (move_type, card_id|None) for each legal move."""
    result = []
    for m in session.legal_moves():
        mt = m._move_type
        cid = m.data.get("card_id") if mt == "promote_card" else None
        result.append((mt, cid))
    return result


def _play_card(session: CSession, card_id: str):
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    raise AssertionError(f"Could not play {card_id}")


def _player_inner_circle(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [_lib.intern_str(ps.inner_circle[j]).decode() for j in range(ps.inner_circle_count)]
    return []


def _player_played_cards(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [_lib.intern_str(ps.played_cards[j]).decode() for j in range(ps.played_cards_count)]
    return []


def _end_main_phase(session: CSession):
    for m in session.legal_moves():
        if m._move_type == "end_main_phase":
            session.submit_move(m)
            return
    raise AssertionError("No end_main_phase move")


def _resolve_first_generic(session: CSession):
    view = build_c_game_view(session)
    rg_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
    if rg_moves:
        session.submit_move(rg_moves[0].move)
    else:
        # Custom effect may not require selection (implicit target)
        pass


def test_myconid_sovereign_cannot_promote_self():
    """Myconid Sovereign's end-of-turn promote must exclude itself."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["myconid_sovereign", "noble"]},
        troops={
            "p1": {
                "site_gauntlgrym": ["p1", None, None],
            }
        },
        current_player="p1",
    )

    _play_card(session, "myconid_sovereign")
    _resolve_first_generic(session)
    _play_card(session, "noble")
    _end_main_phase(session)

    moves = _legal_move_types(session)
    promote_targets = [cid for mt, cid in moves if mt == "promote_card"]

    assert "noble" in promote_targets, f"noble should be a promotion target, got: {promote_targets}"
    assert "myconid_sovereign" not in promote_targets, (
        f"myconid_sovereign should NOT be a promotion target, got: {promote_targets}"
    )

    session.destroy()


def test_myconid_sovereign_skip_with_no_other_cards():
    """When only Myconid Sovereign is played, skip_promote should be available."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["myconid_sovereign"]},
        troops={
            "p1": {
                "site_gauntlgrym": ["p1", None, None],
            }
        },
        current_player="p1",
    )

    _play_card(session, "myconid_sovereign")
    _resolve_first_generic(session)
    _end_main_phase(session)

    moves = _legal_move_types(session)
    move_types = [mt for mt, _cid in moves]

    assert "skip_promote" in move_types, f"Expected skip_promote when no other cards to promote, got: {move_types}"
    assert "promote_card" not in move_types, f"Expected no promote_card when no other cards, got: {move_types}"

    session.destroy()


def test_myconid_sovereign_promotes_correct_card():
    """Promoting noble via Myconid Sovereign should move noble to inner circle."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["myconid_sovereign", "noble"]},
        troops={
            "p1": {
                "site_gauntlgrym": ["p1", None, None],
            }
        },
        current_player="p1",
    )

    _play_card(session, "myconid_sovereign")
    _resolve_first_generic(session)
    _play_card(session, "noble")
    _end_main_phase(session)

    ic_before = _player_inner_circle(session, "p1")

    for m in session.legal_moves():
        if m._move_type == "promote_card" and m.data.get("card_id") == "noble":
            session.submit_move(m)
            break
    else:
        session.destroy()
        raise AssertionError("No promote_card move for noble")

    ic_after = _player_inner_circle(session, "p1")
    played_after = _player_played_cards(session, "p1")

    assert len(ic_after) == len(ic_before) + 1, f"Expected noble in inner circle, got: {ic_after}"
    assert "noble" in ic_after, f"noble should be in inner circle: {ic_after}"
    assert "noble" not in played_after, f"noble should no longer be played: {played_after}"
    assert "myconid_sovereign" in played_after, f"myconid_sovereign should still be played: {played_after}"

    session.destroy()


def test_myconid_sovereign_catalog_encoding_requires_another_played_card():
    """The promote action must carry ``requires_another_played_card`` in its metadata.

    Regression guard: the deferred end-of-turn promotion targets "another played
    card" and must exclude Myconid Sovereign itself. If the metadata flag is lost,
    the engine offers self as a promote target and never falls back to
    ``skip_promote`` when no other card was played this turn.
    """
    catalog = assemble_catalog_payload(DATA_DIR / "cards")
    card = next(c for c in catalog["cards"] if c["card_id"] == "myconid_sovereign")

    for action in (card["execution_model"]["actions"][1], card["actions"][1]):
        assert action["op"] == "promote_card", f"expected promote_card, got {action['op']}"
        assert action["timing"] == "end_of_turn", f"expected end_of_turn, got {action['timing']}"
        assert action["metadata"].get("requires_another_played_card") is True, (
            f"requires_another_played_card must be true, got {action['metadata']}"
        )
