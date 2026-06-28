"""Marlos Urnrayle: gain 1 influence, recruit ambition card costing ≤4, promote ANOTHER played card."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import MAX_ZONE_SIZE, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _end_main_phase(session: CSession) -> None:
    for m in session.legal_moves():
        if m.move_type == "end_main_phase":
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError("No end_main_phase move")


def test_marlos_urnrayle_gains_one_influence() -> None:
    """Playing Marlos Urnrayle immediately grants 1 influence."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["marlos_urnrayle"]},
        current_player="p1",
    )
    s = session._state._ptr.contents
    s.resource_pool.influence = 0

    ms = s.market
    ms.row_count = 1
    ms.row[0] = _lib.intern(b"cult_fanatic")
    s.resource_pool.influence = 10

    _play_card(session, "marlos_urnrayle")

    s = session._state._ptr.contents
    assert s.resource_pool.influence == 11, f"Expected influence 11, got {s.resource_pool.influence}"

    session.destroy()


def test_marlos_urnrayle_recruit_filters_ambition_up_to_cost_4() -> None:
    """After playing Marlos, recruit moves only show ambition cards costing ≤4."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["marlos_urnrayle"]},
        current_player="p1",
    )
    s = session._state._ptr.contents

    market_cards = ["cult_fanatic", "balor", "noble"]
    ms = s.market
    ms.row_count = min(len(market_cards), MAX_ZONE_SIZE)
    for j, cid in enumerate(market_cards[:MAX_ZONE_SIZE]):
        ms.row[j] = _lib.intern(cid.encode())

    s.resource_pool.influence = 10

    _play_card(session, "marlos_urnrayle")

    recruit_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert recruit_moves, "Expected recruit moves after playing Marlos"

    target_ids = {m.data.get("action_id") for m in recruit_moves}
    assert "cult_fanatic" in target_ids, "cult_fanatic (ambition, cost 3) should be selectable"
    assert "balor" not in target_ids, "balor (conquest, cost 6) should NOT be selectable"
    assert "noble" not in target_ids, "noble (no ambition aspect) should NOT be selectable"

    session.destroy()


def test_marlos_urnrayle_promote_cannot_target_self() -> None:
    """End-of-turn promote should NOT let Marlos Urnrayle promote itself."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["marlos_urnrayle", "noble"]},
        current_player="p1",
    )
    s = session._state._ptr.contents

    ms = s.market
    ms.row_count = 1
    ms.row[0] = _lib.intern(b"cult_fanatic")
    s.resource_pool.influence = 10

    _play_card(session, "marlos_urnrayle")

    recruit_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert recruit_moves, "Expected recruit move after Marlos"
    session.submit_move(recruit_moves[0])

    _play_card(session, "noble")

    _end_main_phase(session)

    promote_moves = [m for m in session.legal_moves() if m.move_type == "promote_card"]
    assert promote_moves, "Expected end-of-turn promote moves"

    self_as_target = False
    other_targets = []
    for m in promote_moves:
        cid = m.data.get("card_id", "")
        if cid == "marlos_urnrayle":
            self_as_target = True
        else:
            other_targets.append(cid)

    assert not self_as_target, (
        f"Marlos Urnrayle should NOT be a promote target. Other targets: {other_targets}"
    )
    assert len(other_targets) > 0, "Should have at least one other promote target (noble)"

    session.destroy()


def test_marlos_urnrayle_promote_skippable_if_no_other_played_card() -> None:
    """When no other card is played, Marlos promote should be skippable or no target."""
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards" / "catalog.json"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["marlos_urnrayle"]},
        current_player="p1",
    )
    s = session._state._ptr.contents

    ms = s.market
    ms.row_count = 1
    ms.row[0] = _lib.intern(b"cult_fanatic")
    s.resource_pool.influence = 10

    _play_card(session, "marlos_urnrayle")

    recruit_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert recruit_moves
    session.submit_move(recruit_moves[0])

    _end_main_phase(session)

    promote_moves = [m for m in session.legal_moves() if m.move_type == "promote_card"]
    assert len(promote_moves) == 0, (
        f"Marlos played alone should have no promote targets, got {[m.data for m in promote_moves]}"
    )

    session.destroy()
