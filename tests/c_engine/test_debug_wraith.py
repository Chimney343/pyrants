"""Debug: verify last_selection content after Wraith devour."""
from __future__ import annotations

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _sptr,
    make_card_test_session,
)

_SITE_A = "site_gauntlgrym"
_SITE_B = "site_menzoberranzan"
_P1 = "p1"
_P2 = "p2"
CARD_ID = "wraith"


def _build_session() -> CSession:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [CARD_ID]},
        troops={
            _P1: {_SITE_A: [_P2, None, None, None]},
            _P2: {_SITE_B: [_P1, _P2, None, None]},
        },
        current_player=_P1,
    )
    return session


def _dump_last_selection(session: CSession) -> dict[str, str]:
    s = _sptr(session).contents
    pg = s.pending_generic
    if not pg:
        return {}
    result = {}
    for i in range(pg.contents.last_selection_count):
        k = _lib.intern_str(pg.contents.last_selection_keys[i]).decode()
        v = _lib.intern_str(pg.contents.last_selection_values[i]).decode()
        result[k] = v
    return result


def _play_card(session: CSession) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == CARD_ID:
            session.submit_move(m)
            return
    raise AssertionError(f"{CARD_ID} not playable")


def _dump_legal_moves(session: CSession) -> list[dict]:
    result = []
    for m in session.legal_moves():
        if m.move_type == "resolve_generic":
            result.append({
                "move_type": m.move_type,
                "action_id": m.data.get("action_id"),
                "target_id": m.data.get("target_id"),
            })
    return result


def test_debug_wraith_last_selection() -> None:
    session = _build_session()
    _play_card(session)

    print("\n=== After playing Wraith, before spy placement ===")
    print("Legal moves:", _dump_legal_moves(session))
    print("Last selection:", _dump_last_selection(session))

    # Place spy at SITE_A
    spy_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == _SITE_A:
            spy_move = m
            break
    if spy_move is None:
        print("COULD NOT FIND SPY MOVE FOR", _SITE_A)
        print("Available moves:", _dump_legal_moves(session))
    assert spy_move is not None, "No spy move for SITE_A"
    session.submit_move(spy_move)

    print("\n=== After spy placement ===")
    print("Legal moves:", _dump_legal_moves(session))
    print("Last selection:", _dump_last_selection(session))

    # Devour Wraith
    devour_move = None
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == CARD_ID:
            devour_move = m
            break
    assert devour_move is not None, "No devour move"
    session.submit_move(devour_move)

    print("\n=== After devour ===")
    print("Legal moves:", _dump_legal_moves(session))
    print("Last selection:", _dump_last_selection(session))

    session.destroy()
