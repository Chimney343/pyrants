"""Vanifer card behavior tests:
- Free assassinate player OR white troop
- Free recruit Malice card from market costing <= 4
"""

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_SITE_GAUNTLGRYM = "site_gauntlgrym"
_P1 = "p1"
_P2 = "p2"


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _trophy_hall_size(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].trophy_hall_count


def _discard_size(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].discard_pile_count


def _discard_contains(session: CSession, pid: str, card_id: str) -> bool:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return False
    target = _lib.intern(card_id.encode())
    ps = _sptr(session).contents.players[pi]
    return any(ps.discard_pile[i] == target for i in range(ps.discard_pile_count))


def test_vanifer_assassinate_includes_white_troops():
    """Vanifer's assassinate should offer both white and opponent troops as targets."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P2: ["vanifer"]},
        troops={
            _P2: {_SITE_GAUNTLGRYM: [_P2, _P1, "white"]},
        },
        current_player=_P2,
    )

    # Play Vanifer
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "vanifer":
            session.submit_move(m)
            break

    assert _has_pending_generic(session), "Expected pending generic after playing Vanifer"

    moves = session.legal_moves()
    resolve_moves = [m for m in moves if m.move_type == "resolve_generic"]

    # Should have 2 targets: p1 (slot 1) and white (slot 2)
    # p2's own troop at slot 0 should not be offered
    action_ids = set()
    target_ids = set()
    for m in resolve_moves:
        action_ids.add(m.data.get("action_id"))
        target_ids.add(m.data.get("target_id"))

    assert len(resolve_moves) == 2, f"Expected 2 assassinate targets, got {len(resolve_moves)}"
    assert "1" in target_ids, "Slot 1 (p1 troop) should be a target"
    assert "2" in target_ids, "Slot 2 (white troop) should be a target"
    assert "0" not in target_ids, "Slot 0 (own troop) should NOT be a target"


def test_vanifer_assassinate_works():
    """Assassinating a troop with Vanifer should move it to trophy hall."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P2: ["vanifer"]},
        troops={
            _P2: {_SITE_GAUNTLGRYM: [_P2, _P1]},
        },
        current_player=_P2,
    )

    trophy_before = _trophy_hall_size(session, _P2)

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "vanifer":
            session.submit_move(m)
            break

    assert _has_pending_generic(session)
    moves = session.legal_moves()
    resolve = [m for m in moves if m.move_type == "resolve_generic"]
    assert len(resolve) >= 1

    session.submit_move(resolve[0])

    trophy_after = _trophy_hall_size(session, _P2)
    assert trophy_after == trophy_before + 1, "Trophy hall should increase by 1 after assassinate"


def test_vanifer_recruit_filters_malice_and_cost():
    """Vanifer's recruit should only offer Malice cards costing <= 4 (free recruit)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P2: ["vanifer"]},
        troops={
            _P2: {_SITE_GAUNTLGRYM: [_P2, _P1]},
        },
        current_player=_P2,
    )

    # Set market to include malice cards at various costs and non-malice cards
    s = _sptr(session).contents
    market = ["fire_elemental_myrmidon", "death_tyrant", "neogi", "ghoul", "aboleth"]
    # fire_elemental_myrmidon: malice cost 4
    # death_tyrant: malice cost 7 (too expensive)
    # neogi: conquest (wrong aspect)
    # ghoul: malice cost 4
    # aboleth: guile (wrong aspect)
    s.market.row_count = len(market)
    for j, c in enumerate(market):
        s.market.row[j] = _lib.intern(c.encode())

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "vanifer":
            session.submit_move(m)
            break

    assert _has_pending_generic(session)

    # Resolve assassinate
    moves = session.legal_moves()
    resolve = [m for m in moves if m.move_type == "resolve_generic"]
    session.submit_move(resolve[0])

    # Now should be on the recruit action
    moves2 = session.legal_moves()
    recruit_moves = [m for m in moves2 if m.move_type == "resolve_generic"]

    card_ids = [m.data.get("action_id") for m in recruit_moves]
    # Should include fire_elemental_myrmidon (malice cost 4) and ghoul (malice cost 4)
    # Should NOT include death_tyrant (malice cost 7), neogi (conquest), aboleth (guile)
    assert "fire_elemental_myrmidon" in card_ids, "fire_elemental_myrmidon (malice cost 4) should be offered"
    assert "ghoul" in card_ids, "ghoul (malice cost 4) should be offered"
    assert "death_tyrant" not in card_ids, "death_tyrant (malice cost 7) should NOT be offered"
    assert "neogi" not in card_ids, "neogi (conquest) should NOT be offered"
    assert "aboleth" not in card_ids, "aboleth (guile) should NOT be offered"


def test_vanifer_recruit_is_free():
    """Recruiting a Malice card via Vanifer should NOT deduct influence (free recruit)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P2: ["vanifer"]},
        troops={
            _P2: {_SITE_GAUNTLGRYM: [_P2, _P1]},
        },
        current_player=_P2,
    )

    s = _sptr(session).contents
    # Set influence to 0 to prove it's free
    s.resource_pool.influence = 0
    s.market.row_count = 1
    s.market.row[0] = _lib.intern(b"fire_elemental_myrmidon")

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "vanifer":
            session.submit_move(m)
            break

    assert _has_pending_generic(session)

    # Resolve assassinate
    moves = session.legal_moves()
    session.submit_move([m for m in moves if m.move_type == "resolve_generic"][0])

    # Resolve recruit (skip move is index 0 for optional actions; pick the target)
    moves2 = session.legal_moves()
    recruit_moves = [m for m in moves2 if m.move_type == "resolve_generic"]
    assert len(recruit_moves) >= 1, "Should have at least one recruit target"
    recruit_move = next(
        m for m in recruit_moves if m.data.get("action_id") == "fire_elemental_myrmidon"
    )
    session.submit_move(recruit_move)

    # Card should be in discard pile (recruited for free)
    assert _discard_contains(session, _P2, "fire_elemental_myrmidon"), \
        "fire_elemental_myrmidon should be in discard pile after free recruit"


def test_vanifer_recruit_is_optional():
    """Vanifer's recruit should be skippable — the player may decline the free recruit."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P2: ["vanifer"]},
        troops={
            _P2: {_SITE_GAUNTLGRYM: [_P2, _P1]},
        },
        current_player=_P2,
    )

    s = _sptr(session).contents
    s.resource_pool.influence = 0
    s.market.row_count = 1
    s.market.row[0] = _lib.intern(b"fire_elemental_myrmidon")

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "vanifer":
            session.submit_move(m)
            break

    assert _has_pending_generic(session)

    # Resolve assassinate
    moves = session.legal_moves()
    session.submit_move([m for m in moves if m.move_type == "resolve_generic"][0])

    # On the recruit action: a skip move must be offered alongside the recruit target
    moves2 = session.legal_moves()
    recruit_moves = [m for m in moves2 if m.move_type == "resolve_generic"]
    skip_count = sum(1 for m in recruit_moves if m.data.get("action_id") is None)
    target_count = sum(1 for m in recruit_moves if m.data.get("action_id") is not None)
    assert skip_count == 1, f"Expected 1 skip move for optional recruit, got {skip_count}"
    assert target_count >= 1, "Expected at least one recruit target"

    # Skip the recruit — no card should be added to the discard pile
    skip = next(m for m in recruit_moves if m.data.get("action_id") is None)
    session.submit_move(skip)

    assert not _discard_contains(session, _P2, "fire_elemental_myrmidon"), \
        "fire_elemental_myrmidon should not be recruited when the recruit is skipped"


def test_vanifer_recruit_visible_decline_when_no_valid_cards():
    """When no Malice card costing <=4 is in the market, the optional recruit
    must still surface a visible decline move instead of silently auto-skipping."""
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P2: ["vanifer"]},
        troops={
            _P2: {_SITE_GAUNTLGRYM: [_P2, _P1]},
        },
        current_player=_P2,
    )

    s = _sptr(session).contents
    # Market holds only a conquest card — no qualifying Malice card.
    s.market.row_count = 1
    s.market.row[0] = _lib.intern(b"neogi")

    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "vanifer":
            session.submit_move(m)
            break

    assert _has_pending_generic(session)

    # Resolve assassinate
    moves = session.legal_moves()
    session.submit_move([m for m in moves if m.move_type == "resolve_generic"][0])

    # On the recruit action with no valid targets, a decline move must still be offered.
    moves2 = session.legal_moves()
    recruit_moves = [m for m in moves2 if m.move_type == "resolve_generic"]
    skip_count = sum(1 for m in recruit_moves if m.data.get("action_id") is None)
    target_count = sum(1 for m in recruit_moves if m.data.get("action_id") is not None)
    assert skip_count == 1, f"Expected a visible decline move, got {skip_count}"
    assert target_count == 0, (
        f"Expected no recruit targets (no Malice card <=4), got {[m.data for m in recruit_moves]}"
    )

    # Declining the recruit must not recruit anything.
    skip = next(m for m in recruit_moves if m.data.get("action_id") is None)
    session.submit_move(skip)

    assert not _discard_contains(session, _P2, "neogi"), \
        "neogi should not be recruited when there is no qualifying Malice card"

    session.destroy()
