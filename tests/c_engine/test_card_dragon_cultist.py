"""Dragon Cultist card behavior tests.

Execution model: modal_choice (exactly_one)
  - Option 1 (option_1): gain 2 power
  - Option 2 (option_2): gain 2 influence

Verifies:
  - Modal choice is pending after play with source_card_id set
  - Exactly two options are offered, no skip move (exactly_one)
  - Option 1 grants 2 power, influence unchanged
  - Option 2 grants 2 influence, power unchanged
  - Card fully resolves after modal choice
  - Card stays in played_cards
  - Option 1 grants 2 power regardless of trophy hall (no conditional doubling)
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import MAX_ZONE_SIZE, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _session_player_index,
    _sptr,
    make_card_test_session,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_CARD_ID = "dragon_cultist"


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _power(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.power


def _influence(session: CSession) -> int:
    return session._state._ptr.contents.resource_pool.influence


def _has_pending_generic(session: CSession) -> bool:
    return bool(session._state._ptr.contents.pending_generic)


def _pending_source_card_id(session: CSession) -> str:
    pg = session._state._ptr.contents.pending_generic
    if not pg:
        return ""
    sym = _lib.intern_str(pg.contents.source_card_id)
    return sym.decode() if sym else ""


def _played_cards_ids(session: CSession, player_index: int = 0) -> list[str]:
    s = session._state._ptr.contents
    ps = s.players[player_index]
    return [_lib.intern_str(ps.played_cards[j]).decode() for j in range(ps.played_cards_count)]


def _set_trophy_hall(session: CSession, pid: str, trophies: list[str]) -> None:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return
    s = _sptr(session).contents
    ps = s.players[pi]
    ps.trophy_hall_count = min(len(trophies), MAX_ZONE_SIZE)
    for i, t in enumerate(trophies[:MAX_ZONE_SIZE]):
        ps.trophy_hall[i] = _lib.intern(t.encode())


def _init_engine() -> CEngine:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return eng


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_dragon_cultist_modal_choice_pending_after_play() -> None:
    """After playing Dragon Cultist, a pending generic choice exists for the modal."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )

    _play_card(session, _CARD_ID)

    assert _has_pending_generic(session), (
        "Dragon Cultist must enter pending generic choice for modal selection"
    )
    assert _pending_source_card_id(session) == _CARD_ID, (
        f"Pending source_card_id should be {_CARD_ID}, "
        f"got {_pending_source_card_id(session)}"
    )
    session.destroy()


def test_dragon_cultist_modal_has_exactly_two_options_no_skip() -> None:
    """Modal offers exactly two options (option_1, option_2) with no skip move."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )

    _play_card(session, _CARD_ID)

    gen_moves = [m for m in session.legal_moves() if m._move_type == "resolve_generic"]
    target_moves = [m for m in gen_moves if m.data.get("action_id") is not None]
    skip_moves = [m for m in gen_moves if m.data.get("action_id") is None]

    assert len(target_moves) == 2, (
        f"Expected exactly 2 modal options, got {len(target_moves)}: "
        f"{[m.data for m in target_moves]}"
    )
    assert len(skip_moves) == 0, (
        f"Expected no skip move for exactly_one modal, got {len(skip_moves)}"
    )

    option_ids = {m.data["action_id"] for m in target_moves}
    assert option_ids == {"option_1", "option_2"}, (
        f"Expected options option_1 and option_2, got {option_ids}"
    )
    session.destroy()


def test_dragon_cultist_option_1_grants_two_power() -> None:
    """Choosing option_1 grants 2 power and 0 influence."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )

    s = session._state._ptr.contents
    s.resource_pool.power = 0
    s.resource_pool.influence = 0

    _play_card(session, _CARD_ID)

    option_1_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "option_1"
    ]
    assert option_1_moves, (
        f"No resolve_generic move for option_1; moves: "
        f"{[m.data for m in session.legal_moves()]}"
    )
    session.submit_move(option_1_moves[0])

    assert _power(session) == 2, f"Expected 2 power after option_1, got {_power(session)}"
    assert _influence(session) == 0, (
        f"Expected 0 influence after option_1, got {_influence(session)}"
    )
    session.destroy()


def test_dragon_cultist_option_2_grants_two_influence() -> None:
    """Choosing option_2 grants 2 influence and 0 power."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )

    s = session._state._ptr.contents
    s.resource_pool.power = 0
    s.resource_pool.influence = 0

    _play_card(session, _CARD_ID)

    option_2_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "option_2"
    ]
    assert option_2_moves, (
        f"No resolve_generic move for option_2; moves: "
        f"{[m.data for m in session.legal_moves()]}"
    )
    session.submit_move(option_2_moves[0])

    assert _influence(session) == 2, f"Expected 2 influence after option_2, got {_influence(session)}"
    assert _power(session) == 0, f"Expected 0 power after option_2, got {_power(session)}"
    session.destroy()


def test_dragon_cultist_resolves_after_modal_choice() -> None:
    """After choosing a modal option, Dragon Cultist fully resolves with no pending state."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )

    _play_card(session, _CARD_ID)

    option_1_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "option_1"
    ]
    assert option_1_moves
    session.submit_move(option_1_moves[0])

    assert not _has_pending_generic(session), (
        "Dragon Cultist should fully resolve after modal choice"
    )

    move_types = {m.move_type for m in session.legal_moves()}
    assert "end_main_phase" in move_types, "Should be able to end main phase after resolution"

    session.destroy()


def test_dragon_cultist_stays_in_played_cards() -> None:
    """Dragon Cultist stays in played_cards after resolving."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )

    _play_card(session, _CARD_ID)

    option_2_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "option_2"
    ]
    assert option_2_moves
    session.submit_move(option_2_moves[0])

    played = _played_cards_ids(session)
    assert _CARD_ID in played, (
        f"Dragon Cultist should stay in played_cards, got: {played}"
    )

    session.destroy()


def test_dragon_cultist_power_gain_with_nonzero_start() -> None:
    """Power gain adds to existing power, influence is unchanged."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )

    s = session._state._ptr.contents
    s.resource_pool.power = 3
    s.resource_pool.influence = 5

    _play_card(session, _CARD_ID)

    option_1_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "option_1"
    ]
    assert option_1_moves
    session.submit_move(option_1_moves[0])

    assert _power(session) == 5, f"Expected 5 power (3 + 2), got {_power(session)}"
    assert _influence(session) == 5, f"Expected 5 influence unchanged, got {_influence(session)}"

    session.destroy()


# ---------------------------------------------------------------------------
# Trophy-hall independence regression test
# ---------------------------------------------------------------------------


def test_option_1_grants_two_power_even_with_player_trophies() -> None:
    """Option 1 grants 2 power (not 4) even when player has >=5 player trophies.

    Dragon Cultist is a simple modal resource card. The trophy-hall conditional
    power bonus belongs to Dragonclaw, not Dragon Cultist; this test locks in
    that Dragon Cultist never doubles its power.
    """
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [_CARD_ID]},
        current_player="p1",
    )

    s = session._state._ptr.contents
    s.resource_pool.power = 0
    s.resource_pool.influence = 0
    _set_trophy_hall(session, "p1", ["p2"] * 5)

    _play_card(session, _CARD_ID)

    option_1_moves = [
        m for m in session.legal_moves()
        if m._move_type == "resolve_generic" and m.data.get("action_id") == "option_1"
    ]
    assert option_1_moves
    session.submit_move(option_1_moves[0])

    assert _power(session) == 2, (
        f"Expected 2 power regardless of trophy hall, got {_power(session)}"
    )
    assert _influence(session) == 0, (
        f"Expected 0 influence after option_1, got {_influence(session)}"
    )
    session.destroy()
