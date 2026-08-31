"""Play-legality gate for mandatory devour costs.

A card whose on-play effect contains a mandatory devour
(op "devour"/"devour_cost", optional false) is only legal to play when the
post-play state leaves at least one legal devour target in the source zone.
Cards whose source zone is empty (e.g. a singleton-hand Balor) must be
unplayable rather than silently waiving the cost.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

HAND_DEVOUR_CARDS = [
    "balor",
    "demogorgon",
    "glabrezu",
    "marilith",
    "mind_flayer",
    "orcus",
    "succubus",
]


def _init_engine() -> CEngine:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return eng


def _play_moves(session: CSession, card_id: str) -> list:
    return [
        m
        for m in session.legal_moves()
        if m._move_type == "play_card" and m.data.get("card_id") == card_id
    ]


def _generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if m._move_type == "resolve_generic"]


def _generic_target_ids(session: CSession) -> list[str]:
    return [m.data.get("action_id") for m in _generic_moves(session) if m.data.get("action_id")]


def _has_end_main_phase(session: CSession) -> bool:
    return any(m._move_type == "end_main_phase" for m in session.legal_moves())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("card_id", HAND_DEVOUR_CARDS)
def test_mandatory_hand_devour_singleton_hand_illegal(card_id: str) -> None:
    """A singleton-hand mandatory devour card has no play_card move."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [card_id]},
        current_player="p1",
    )

    assert _play_moves(session, card_id) == [], (
        f"{card_id} should have no play_card move with an empty post-play hand"
    )
    assert _has_end_main_phase(session), (
        f"{card_id} must not soft-lock: end_main_phase should remain legal"
    )
    session.destroy()


def test_hand_devour_extra_card_legal_and_charged() -> None:
    """With a second hand card, Balor is playable and the cost is charged."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["balor", "noble"]},
        current_player="p1",
    )

    plays = _play_moves(session, "balor")
    assert len(plays) == 1, f"Expected 1 play move for balor, got {len(plays)}"

    session.submit_move(plays[0])

    assert _generic_target_ids(session) == ["noble"], (
        f"Devour target should be exactly ['noble'], got {_generic_target_ids(session)}"
    )
    session.destroy()


def test_hand_devour_duplicates_playable() -> None:
    """Two copies of Balor: the other copy is a legal devour target."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["balor", "balor"]},
        current_player="p1",
    )

    assert len(_play_moves(session, "balor")) == 2, (
        f"Both copies of balor should be playable, got {len(_play_moves(session, 'balor'))}"
    )
    session.destroy()


def test_inner_circle_devour_zuggtmoy() -> None:
    """Zuggtmoy is unplayable with an empty inner circle, playable with one."""
    eng = _init_engine()

    empty = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["zuggtmoy"]},
        inner_circle={"p1": []},
        current_player="p1",
    )
    assert _play_moves(empty, "zuggtmoy") == [], (
        "zuggtmoy should be unplayable with an empty inner circle"
    )
    assert _has_end_main_phase(empty)
    empty.destroy()

    with_target = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["zuggtmoy"]},
        inner_circle={"p1": ["noble"]},
        current_player="p1",
    )
    plays = _play_moves(with_target, "zuggtmoy")
    assert len(plays) == 1
    with_target.submit_move(plays[0])
    assert _generic_target_ids(with_target) == ["noble"], (
        f"zuggtmoy devour target should be ['noble'], got {_generic_target_ids(with_target)}"
    )
    with_target.destroy()


def test_modal_partially_blocked_wight_still_playable() -> None:
    """Wight stays playable on a singleton hand; its devour option greys out."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["wight"]},
        current_player="p1",
    )

    plays = _play_moves(session, "wight")
    assert len(plays) == 1, "wight should be playable (option_1 has no devour)"

    session.submit_move(plays[0])

    opt_moves = {m.data.get("action_id"): m for m in _generic_moves(session)}
    assert "option_1" in opt_moves, "option_1 should be viable"
    assert opt_moves["option_2"].data.get("target_id") == "unavailable", (
        "option_2 (devour from empty hand) should be tagged unavailable"
    )
    session.destroy()


@pytest.mark.parametrize("card_id", ["skeletal_horde", "wraith"])
def test_self_devour_unaffected(card_id: str) -> None:
    """Self-devour (played_self) cards are always playable."""
    eng = _init_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": [card_id]},
        current_player="p1",
    )

    assert len(_play_moves(session, card_id)) == 1, (
        f"{card_id} should remain playable (played_self devour)"
    )
    session.destroy()


def test_apply_time_rejection_of_blocked_play() -> None:
    """A play_card move replayed into a singleton hand is rejected at apply."""
    eng = _init_engine()

    two_card = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["balor", "noble"]},
        current_player="p1",
    )
    play_move = _play_moves(two_card, "balor")[0]

    singleton = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["balor"]},
        current_player="p1",
    )
    assert singleton.submit_move(play_move) is None, (
        "Replaying an illegal balor play into a singleton hand must be rejected"
    )

    singleton.destroy()
    two_card.destroy()
