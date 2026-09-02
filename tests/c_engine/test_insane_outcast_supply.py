"""Insane Outcast shared-supply cap and JSON-driven special-stack tests.

Locks the F-014 fix: ``give_insane_outcast`` never mints a 31st copy game-wide,
exhaustion allocates clockwise from the current player (rulebook :355), the
card's return paths replenish the board stack, stack totals are read from the
setup JSON, absent JSON stacks fall back to the legacy 15/15/30 table, and an
undefined insane stack (D6) makes outcast grants no-ops while the card's other
effects still resolve.
"""

from __future__ import annotations

import json

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import DATA_DIR, make_card_test_session

INSANE = "insane_outcast"


def _session_player(session: CSession, pid: str):
    s = session._state._ptr.contents
    for i in range(s.player_count):
        name = _lib.intern_str(s.player_ids[i])
        if name and name.decode() == pid:
            return s.players[i]
    raise AssertionError(f"player {pid} not found")


def _set_discard(session: CSession, pid: str, cards: list[str]) -> None:
    ps = _session_player(session, pid)
    ps.discard_pile_count = 0
    for cid in cards:
        if ps.discard_pile_count >= 80:
            break
        ps.discard_pile[ps.discard_pile_count] = _lib.intern(cid.encode())
        ps.discard_pile_count += 1


def _discard_count(session: CSession, pid: str, card_id: str) -> int:
    ps = _session_player(session, pid)
    sym = _lib.intern(card_id.encode())
    return sum(1 for i in range(ps.discard_pile_count) if ps.discard_pile[i] == sym)


def _total_owned_outcasts(session: CSession) -> int:
    sym = _lib.intern(INSANE.encode())
    s = session._state._ptr.contents
    total = 0
    for i in range(s.player_count):
        ps = s.players[i]
        total += sum(1 for j in range(ps.deck_count) if ps.deck[j] == sym)
        total += sum(1 for j in range(ps.hand_count) if ps.hand[j] == sym)
        total += sum(1 for j in range(ps.discard_pile_count) if ps.discard_pile[j] == sym)
        total += sum(1 for j in range(ps.played_cards_count) if ps.played_cards[j] == sym)
        total += sum(1 for j in range(ps.inner_circle_count) if ps.inner_circle[j] == sym)
        total += sum(1 for j in range(ps.trophy_hall_count) if ps.trophy_hall[j] == sym)
    return total


def _hand(session: CSession, pid: str) -> list[str]:
    ps = _session_player(session, pid)
    return [_lib.intern_str(ps.hand[i]).decode() for i in range(ps.hand_count)]


def _power(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.power


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _resolve_all_generic(session: CSession) -> None:
    """Submit every currently-offered resolve_generic move once (single pass)."""
    view = build_c_game_view(session)
    for m in view.legal_moves:
        if m.move_type == "resolve_generic":
            session.submit_move(m.move)


def _find_resolve(session: CSession, action_id: str):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == action_id:
            return m
    return None


def _find_recruit(session: CSession, card_id: str):
    for m in session.legal_moves():
        if m.move_type == "recruit" and m.data.get("card_id") == card_id:
            return m
    return None


def _remaining_outcasts(session: CSession) -> int:
    return build_c_game_view(session).insane_outcast_remaining


# ---------------------------------------------------------------------------
# T1 — the cap: 30 owned game-wide means a grant is a no-op, sibling effects run
# ---------------------------------------------------------------------------

def test_give_insane_outcast_respects_supply_cap() -> None:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["ghoul"]},
        current_player="p1",
    )
    _set_discard(session, "p1", [INSANE] * 30)
    assert _total_owned_outcasts(session) == 30
    power_before = _power(session)

    _play_card(session, "ghoul")
    _resolve_all_generic(session)

    # p2 (the only opponent) receives zero new copies; total stays at exactly 30.
    assert _discard_count(session, "p2", INSANE) == 0
    assert _total_owned_outcasts(session) == 30
    # ghoul's sibling effect (gain 2 power) still resolved.
    assert _power(session) == power_before + 2

    session.destroy()


# ---------------------------------------------------------------------------
# T2 — exhaustion allocates clockwise from the current player
# ---------------------------------------------------------------------------

def test_give_insane_outcast_partial_grant_clockwise() -> None:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2", "p3"],
        hand={"p1": ["ghoul"]},
        current_player="p1",
    )
    # 29 owned (all held by p3) leaves exactly 1 in the supply.
    _set_discard(session, "p3", [INSANE] * 29)

    _play_card(session, "ghoul")
    _resolve_all_generic(session)

    # Seat order p1,p2,p3; clockwise from p1 visits p2 before p3. The single
    # remaining outcast goes to p2; p3 (already holding 29) gets nothing more.
    assert _discard_count(session, "p2", INSANE) == 1
    assert _discard_count(session, "p3", INSANE) == 29
    assert _total_owned_outcasts(session) == 30

    session.destroy()


def test_give_insane_outcast_quantity_two_capped_per_copy() -> None:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["ghoul"]},
        current_player="p1",
    )
    # 29 owned leaves exactly 1 remaining even though ghoul grants 1/opponent.
    _set_discard(session, "p2", [INSANE] * 29)

    _play_card(session, "ghoul")
    _resolve_all_generic(session)

    assert _discard_count(session, "p2", INSANE) == 30
    assert _total_owned_outcasts(session) == 30

    session.destroy()


def test_demogorgon_two_per_opponent_capped_by_remaining() -> None:
    """demogorgon grants 2/opponent; with 1 remaining only 1 is ever minted."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2", "p3"],
        hand={"p1": ["demogorgon", "soldier", "noble", "house_guard", "priestess_of_lolth"]},
        troops={"p1": {"route_1": ["p1"], "route_4": ["p1"]}},
        current_player="p1",
    )
    # 29 owned (held by p2, the first clockwise opponent) → 1 remaining.
    _set_discard(session, "p2", [INSANE] * 29)
    nid = _lib.intern(b"site_gauntlgrym")
    nid2 = _lib.intern(b"site_neverwinter")
    nid3 = _lib.intern(b"route_8")
    s = session._state._ptr.contents
    for ni in range(s.node_count):
        node = s.nodes[ni]
        if node.node_id in (nid, nid2, nid3):
            if node.troop_slot_count < 1:
                node.troop_slot_count = 1
            node.troop_slots[0] = _lib.intern(b"white")

    _play_card(session, "demogorgon")

    devour = _find_resolve(session, "soldier")
    assert devour is not None
    session.submit_move(devour)

    anywhere = _find_resolve(session, "site_gauntlgrym")
    assert anywhere is not None
    session.submit_move(anywhere)

    for _ in range(2):
        ids = {m.data["action_id"] for m in session.legal_moves()
               if m.move_type == "resolve_generic" and m.data.get("action_id")}
        assert ids, "should offer presence-bound supplant targets"
        session.submit_move(_find_resolve(session, next(iter(ids))))

    assert session.legal_moves(), "effect should have auto-resolved to next moves"

    # p2 is first clockwise and holds the sole remaining outcast slot: it gets
    # exactly 1 more (not the full demogorgon quantity of 2). p3 gets 0.
    assert _discard_count(session, "p2", INSANE) == 30
    assert _discard_count(session, "p3", INSANE) == 0
    assert _total_owned_outcasts(session) == 30

    session.destroy()


# ---------------------------------------------------------------------------
# T3 — return paths replenish the board stack
# ---------------------------------------------------------------------------

def _assert_hand_outcast_replenishes(hand_p1: list[str]) -> None:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": hand_p1},
        current_player="p1",
    )
    # p1's held outcast is counted as owned → remaining is 29.
    assert _remaining_outcasts(session) == 29, _remaining_outcasts(session)
    _play_card(session, hand_p1[0])
    _resolve_all_generic(session)
    # The outcast left p1's hand via the discard/promote/devour replacement and
    # returned to supply → remaining is back to 30.
    assert _remaining_outcasts(session) == 30, _remaining_outcasts(session)
    session.destroy()


def test_self_purge_to_supply_replenishes_supply() -> None:
    _assert_hand_outcast_replenishes([INSANE, "noble"])


def test_promote_replenishes_supply() -> None:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["necromancer", INSANE]},
        current_player="p1",
    )
    assert _remaining_outcasts(session) == 29

    _play_card(session, "necromancer")
    option = _find_resolve(session, "option_2")
    assert option is not None, "necromancer modal should offer the promote branch"
    session.submit_move(option)

    # Choose the promote target by hand index (necromancer's zone pick).
    io_idx = _hand(session, "p1").index(INSANE)
    chosen = None
    for m in session.legal_moves():
        if (m.move_type == "resolve_generic" and m.data.get("target_id") == "hand"
                and m.data.get("action_id") == str(io_idx)):
            chosen = m
            break
    assert chosen is not None, "necromancer should allow promoting the outcast from hand"
    session.submit_move(chosen)

    assert _remaining_outcasts(session) == 30
    session.destroy()


def test_devour_replenishes_supply() -> None:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["balor", INSANE]},
        current_player="p1",
    )
    assert _remaining_outcasts(session) == 29

    _play_card(session, "balor")
    devour = _find_resolve(session, INSANE)
    assert devour is not None, "balor should be able to devour the outcast"
    session.submit_move(devour)

    assert _remaining_outcasts(session) == 30
    session.destroy()


# ---------------------------------------------------------------------------
# T4 — special-stack totals are read from the setup JSON
# ---------------------------------------------------------------------------

def _custom_setup(house_guard_total: int = 3) -> str:
    return json.dumps({
        "setup_id": "custom_supply",
        "starter_deck": {
            "deck_id": "starter_deck",
            "entries": [
                {"card_id": "noble", "count": 7},
                {"card_id": "soldier", "count": 3},
            ],
        },
        "market_deck": {
            "deck_id": "market_deck",
            "entries": [{"card_id": "priestess_of_lolth", "count": 10}],
        },
        "market_row_size": 6,
        "special_stacks": [
            {"market_slot": 100, "card_id": "house_guard", "stack_total": house_guard_total},
            {"market_slot": 101, "card_id": "priestess_of_lolth", "stack_total": 15},
            {"market_slot": 102, "card_id": "insane_outcast", "stack_total": 30},
        ],
    })


def test_special_stack_totals_read_from_setup_json() -> None:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
        setup_data_json=_custom_setup(house_guard_total=3),
    )
    session = make_card_test_session(eng, ["p1", "p2"], current_player="p1")
    s = session._state._ptr.contents
    s.resource_pool.influence = 100

    view = build_c_game_view(session)
    assert view.house_guard_remaining == 3, (
        f"house_guard total should come from JSON (3), got {view.house_guard_remaining}"
    )

    for expected in (2, 1, 0):
        recruit = _find_recruit(session, "house_guard")
        assert recruit is not None, f"house_guard recruit should be offered (remaining {expected + 1})"
        assert session.submit_move(recruit) is not None
        view = build_c_game_view(session)
        assert view.house_guard_remaining == expected, (
            f"expected {expected} remaining after recruit, got {view.house_guard_remaining}"
        )

    assert _find_recruit(session, "house_guard") is None, (
        "4th house_guard recruit must not be offered when the JSON total is 3"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# T5 — a setup JSON without special_stacks falls back to 15/15/30
# ---------------------------------------------------------------------------

def _legacy_setup() -> str:
    return json.dumps({
        "setup_id": "legacy_no_stacks",
        "starter_deck": {
            "deck_id": "starter_deck",
            "entries": [
                {"card_id": "noble", "count": 7},
                {"card_id": "soldier", "count": 3},
            ],
        },
        "market_deck": {
            "deck_id": "market_deck",
            "entries": [{"card_id": "noble", "count": 6}],
        },
        "market_row_size": 6,
    })


def test_legacy_setup_without_special_stacks_falls_back() -> None:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
        setup_data_json=_legacy_setup(),
    )
    session = make_card_test_session(eng, ["p1", "p2"], current_player="p1")
    view = build_c_game_view(session)
    assert view.house_guard_remaining == 15, view.house_guard_remaining
    assert view.priestess_remaining == 15, view.priestess_remaining
    assert view.insane_outcast_remaining == 30, view.insane_outcast_remaining
    session.destroy()


# ---------------------------------------------------------------------------
# T6 — insane stack is defined (demons market) ⇒ slot-102 recruit reachable;
#      undefined (non-demons market) ⇒ not offered and grants are no-ops
# ---------------------------------------------------------------------------

def _demons_setup(include_insane: bool) -> str:
    stacks = [
        {"market_slot": 100, "card_id": "house_guard", "stack_total": 15},
        {"market_slot": 101, "card_id": "priestess_of_lolth", "stack_total": 15},
    ]
    if include_insane:
        stacks.append({"market_slot": 102, "card_id": "insane_outcast", "stack_total": 30})
    return json.dumps({
        "setup_id": "demons_market",
        "starter_deck": {
            "deck_id": "starter_deck",
            "entries": [
                {"card_id": "noble", "count": 7},
                {"card_id": "soldier", "count": 3},
            ],
        },
        "market_deck": {
            "deck_id": "market_deck",
            "entries": [
                {"card_id": "demogorgon", "count": 1},
                {"card_id": "ettin", "count": 3},
                {"card_id": "ghoul", "count": 3},
            ],
        },
        "market_row_size": 6,
        "special_stacks": stacks,
    })


def _make_session(setup_data_json: str, hand: dict[str, list[str]] | None = None) -> CSession:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
        setup_data_json=setup_data_json,
    )
    return make_card_test_session(eng, ["p1", "p2"], hand=hand, current_player="p1")


def test_insane_stack_gated_on_demons_market() -> None:
    session = _make_session(_demons_setup(include_insane=True))
    s = session._state._ptr.contents
    s.resource_pool.influence = 100
    recruit = _find_recruit(session, INSANE)
    assert recruit is not None, "slot-102 insane_outcast recruit must be offered when the stack is defined"
    assert session.submit_move(recruit) is not None
    assert _discard_count(session, "p1", INSANE) == 1
    session.destroy()

    session = _make_session(_demons_setup(include_insane=False))
    s = session._state._ptr.contents
    s.resource_pool.influence = 100
    assert _find_recruit(session, INSANE) is None, (
        "insane_outcast recruit must NOT be offered when the stack is undefined"
    )
    session.destroy()


def test_undefined_insane_stack_makes_grant_a_noop() -> None:
    session = _make_session(_demons_setup(include_insane=False), hand={"p1": ["ghoul"]})
    hand = _hand(session, "p1")
    assert "ghoul" in hand
    power_before = _power(session)

    _play_card(session, "ghoul")
    _resolve_all_generic(session)

    # Undefined stack (D6): no outcast is minted for p2, sibling effect still runs.
    assert _discard_count(session, "p2", INSANE) == 0
    assert _total_owned_outcasts(session) == 0
    assert _power(session) == power_before + 2

    session.destroy()
