"""Interface tests for the game handle (ADR-0011, brief F1).

Everything here goes through ``GameHandle``'s public surface: no ``CState``, no
ctypes struct and no raw pointer. The two exceptions are deliberate and small:
a rejected move is built from a ctypes ``Move`` because that is the only way to
express "not in the legal list", and the capacity/clone/determinize failures
replace the library with a fake, as ``test_move_capacity_binding.py`` does.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from engine_c.bindings import ce_api, engine_bindings  # noqa: E402
from engine_c.bindings import errors as handle_errors  # noqa: E402
from engine_c.bindings.ce_api import CMoveWrapper  # noqa: E402
from engine_c.bindings.engine_bindings import MOVE_END_MAIN_PHASE  # noqa: E402
from engine_c.bindings.engine_bindings import Move as CMove  # noqa: E402
from engine_c.bindings.handle import Definition, GameHandle, Move  # noqa: E402

_DATA = _REPO_ROOT / "data"
BOARD = _DATA / "boards" / "tyrants_of_the_underdark.json"
CARDS = _DATA / "cards"
SETUP = _DATA / "decks" / "base_setup.json"

_requires_dll = pytest.mark.skipif(ce_api._lib is None, reason="engine_c DLL not available")


def _payloads(handle: GameHandle) -> list[dict]:
    return [move.to_payload() for move in handle.legal_moves()]


def _five_card_setup() -> str:
    return json.dumps({
        "setup_id": "five_card_setup",
        "starter_deck": {
            "deck_id": "starter_deck",
            "entries": [{"card_id": "noble", "count": 3}, {"card_id": "soldier", "count": 2}],
        },
        "market_deck": {
            "deck_id": "market_deck",
            "entries": [{"card_id": "priestess_of_lolth", "count": 10}],
        },
        "market_row_size": 6,
    })


class _ProxyLib:
    """Delegates every attribute to the real library, overriding the named ones."""

    def __init__(self, lib, **overrides):
        self._lib = lib
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._lib, name)


class _OverflowingLib:
    """A stand-in library whose move query reports more than the buffer holds."""

    def __init__(self, needed: int):
        self.needed = needed
        self.asked: list[int] = []

    def engine_move_capacity(self):
        return 1024

    def engine_legal_moves(self, ptr, buf, cap):
        self.asked.append(cap)
        return self.needed

    def engine_display_moves(self, ptr, buf, applicable, cap):
        self.asked.append(cap)
        return self.needed


def _new_handle(player_ids: list[str], seed: int = 42) -> GameHandle:
    return GameHandle.new(player_ids, seed)


def _enter_main_phase(handle: GameHandle) -> None:
    """Play the setup placements; the engine leaves setup after one per player."""
    for _ in range(len(handle.player_ids)):
        assert handle.phase() == "setup"
        handle.apply(handle.legal_moves()[0])
    assert handle.phase() == "main"


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


@_requires_dll
def test_new_starts_a_game_in_the_setup_phase():
    handle = _new_handle(["p1", "p2"])
    try:
        assert handle.player_ids == ("p1", "p2")
        assert handle.seed == 42
        assert handle.phase() == "setup"
        assert handle.round_number() == 1
        assert handle.current_player_id() == "p1"
        assert handle.is_terminal() is False
        assert handle.legal_moves(), "a fresh game must offer initial placement"
    finally:
        handle.destroy()


@_requires_dll
def test_new_is_deterministic_for_a_seed():
    first = _new_handle(["p1", "p2"], seed=7)
    second = _new_handle(["p1", "p2"], seed=7)
    try:
        assert first.player_view("p1") == second.player_view("p1")
        assert _payloads(first) == _payloads(second)
    finally:
        first.destroy()
        second.destroy()


@_requires_dll
def test_from_files_honours_setup_data_json():
    default = GameHandle.from_files(
        board_path=BOARD, card_path=CARDS, setup_path=SETUP,
        player_ids=["p1", "p2"], seed=42,
    )
    custom = GameHandle.from_files(
        board_path=BOARD, card_path=CARDS, setup_path=SETUP,
        setup_data_json=_five_card_setup(), player_ids=["p1", "p2"], seed=42,
    )
    try:
        assert json.loads(default.player_view("p1"))["deck_size"] == 10
        assert json.loads(custom.player_view("p1"))["deck_size"] == 5
    finally:
        default.destroy()
        custom.destroy()


@_requires_dll
def test_new_accepts_a_shared_definition():
    definition = Definition.load(board_path=BOARD, card_path=CARDS, setup_path=SETUP)
    first = GameHandle.new(["p1", "p2"], 3, definition=definition)
    second = GameHandle.new(["p1", "p2"], 3, definition=definition)
    try:
        assert first.player_view("p1") == second.player_view("p1")
    finally:
        first.destroy()
        second.destroy()


@_requires_dll
def test_a_bad_definition_raises_engine_setup_failed(tmp_path):
    with pytest.raises(handle_errors.EngineSetupFailed):
        Definition.load(
            board_path=BOARD,
            card_path=tmp_path / "no_such_catalog",
            setup_path=SETUP,
        )


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


@_requires_dll
def test_apply_mutates_the_handle():
    handle = _new_handle(["p1", "p2"])
    try:
        before_view = handle.player_view("p1")
        before_player = handle.current_player_id()
        handle.apply(handle.legal_moves()[0])
        assert handle.player_view("p1") != before_view
        assert handle.current_player_id() != before_player
    finally:
        handle.destroy()


@_requires_dll
def test_a_rejected_apply_raises_and_leaves_the_state_alone():
    handle = _new_handle(["p1", "p2"])
    try:
        before = _payloads(handle)
        rejected = CMove()
        rejected.type = MOVE_END_MAIN_PHASE
        with pytest.raises(handle_errors.EngineApplyRejected):
            handle.apply(CMoveWrapper(rejected))
        assert _payloads(handle) == before
        assert handle.phase() == "setup"
        handle.apply(handle.legal_moves()[0])
    finally:
        handle.destroy()


# ---------------------------------------------------------------------------
# Clone and determinize
# ---------------------------------------------------------------------------


@_requires_dll
def test_clone_is_independent_of_its_original():
    handle = _new_handle(["p1", "p2"])
    clone = handle.clone()
    try:
        view_before = handle.player_view("p1")
        key_before = handle.infostate_key("p1")
        moves_before = _payloads(handle)
        player_before = handle.current_player_id()

        clone.apply(clone.legal_moves()[0])

        assert _payloads(handle) == moves_before
        assert handle.player_view("p1") == view_before
        assert handle.infostate_key("p1") == key_before
        assert handle.current_player_id() == player_before
        assert clone.player_view("p1") != view_before
        assert clone.current_player_id() != player_before
    finally:
        clone.destroy()
        handle.destroy()


@_requires_dll
def test_determinize_keeps_the_observers_view():
    handle = _new_handle(["p1", "p2"], seed=5)
    world = handle.determinize("p1", 99)
    try:
        assert world.player_view("p1") == handle.player_view("p1")
        assert world.infostate_key("p1") == handle.infostate_key("p1")
        assert _payloads(world) == _payloads(handle)
    finally:
        world.destroy()
        handle.destroy()


# ---------------------------------------------------------------------------
# Views, key, phase and scores
# ---------------------------------------------------------------------------


@_requires_dll
def test_views_are_json_and_keys_follow_the_views():
    handle = _new_handle(["p1", "p2"])
    try:
        first = json.loads(handle.player_view("p1"))
        assert isinstance(first, dict)
        assert "public" in first and "deck_size" in first

        assert handle.infostate_key("p1") == handle.infostate_key("p1")

        # In setup nothing is private yet, so both keys agree; once the main
        # phase hands each player their own hand, the views and keys must not.
        _enter_main_phase(handle)
        assert handle.player_view("p1") != handle.player_view("p2")
        assert handle.infostate_key("p1") != handle.infostate_key("p2")

        with pytest.raises(KeyError):
            handle.player_view("nobody")
        with pytest.raises(KeyError):
            handle.infostate_key("nobody")
    finally:
        handle.destroy()


@_requires_dll
def test_scores_cover_every_player():
    handle = _new_handle(["p1", "p2", "p3"])
    try:
        scores = handle.scores()
        assert set(scores) == {"p1", "p2", "p3"}
        assert all(isinstance(value, int) for value in scores.values())
    finally:
        handle.destroy()


@_requires_dll
def test_winner_is_none_until_the_game_ends():
    handle = _new_handle(["p1", "p2"])
    try:
        assert handle.winner() is None
    finally:
        handle.destroy()


# ---------------------------------------------------------------------------
# Rollout
# ---------------------------------------------------------------------------


@_requires_dll
def test_rollout_is_deterministic_and_does_not_mutate():
    handle = _new_handle(["p1", "p2"])
    try:
        view_before = handle.player_view("p1")
        first = handle.rollout(seed=11, max_length=4)
        second = handle.rollout(seed=11, max_length=4)
        assert first == second
        terminal, scores = first
        assert isinstance(terminal, bool)
        assert set(scores) == {"p1", "p2"}
        assert handle.player_view("p1") == view_before
    finally:
        handle.destroy()


# ---------------------------------------------------------------------------
# Scenario documents
# ---------------------------------------------------------------------------


@_requires_dll
def test_scenario_round_trip(tmp_path):
    handle = _new_handle(["p1", "p2"], seed=9)
    try:
        handle.apply(handle.legal_moves()[0])
        path = tmp_path / "scenario.json"
        handle.save_scenario(path)
        assert path.exists()

        loaded = GameHandle.load_scenario(path)
        try:
            assert loaded.player_ids == handle.player_ids
            assert loaded.phase() == handle.phase()
            assert loaded.round_number() == handle.round_number()
            assert loaded.current_player_id() == handle.current_player_id()
            assert _payloads(loaded) == _payloads(handle)
            assert loaded.player_view("p1") == handle.player_view("p1")
        finally:
            loaded.destroy()
    finally:
        handle.destroy()


@_requires_dll
def test_loading_a_broken_scenario_raises_engine_setup_failed(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(handle_errors.EngineSetupFailed):
        GameHandle.load_scenario(path)


# ---------------------------------------------------------------------------
# Lifetime
# ---------------------------------------------------------------------------


@_requires_dll
def test_the_context_manager_destroys_the_state():
    with GameHandle.new(["p1", "p2"], 42) as handle:
        assert handle.player_view("p1")
        assert handle.destroyed is False
    assert handle.destroyed is True
    with pytest.raises(handle_errors.EngineDestroyedError):
        handle.legal_moves()


@_requires_dll
def test_destroy_is_safe_twice():
    handle = _new_handle(["p1", "p2"])
    handle.destroy()
    handle.destroy()
    assert handle.destroyed is True


@_requires_dll
@pytest.mark.parametrize("operation", ["legal_moves", "display_moves", "clone", "player_view", "scores"])
def test_every_operation_reports_a_destroyed_handle(operation):
    handle = _new_handle(["p1", "p2"])
    handle.destroy()
    with pytest.raises(handle_errors.EngineDestroyedError):
        if operation == "player_view":
            handle.player_view("p1")
        else:
            getattr(handle, operation)()


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------


def test_the_failure_family_is_one_runtime_error_family():
    for name in (
        "EngineError",
        "EngineApplyRejected",
        "EngineCloneFailed",
        "EngineDeterminizeFailed",
        "EngineSetupFailed",
        "EngineDestroyedError",
        "MoveCapacityError",
    ):
        assert issubclass(getattr(handle_errors, name), RuntimeError), name
    for name in (
        "EngineApplyRejected",
        "EngineCloneFailed",
        "EngineDeterminizeFailed",
        "EngineSetupFailed",
        "EngineDestroyedError",
        "MoveCapacityError",
    ):
        assert issubclass(getattr(handle_errors, name), handle_errors.EngineError), name


def test_move_capacity_error_is_the_same_object_everywhere():
    from engine_c.bindings import handle

    assert ce_api.MoveCapacityError is handle_errors.MoveCapacityError
    assert handle.MoveCapacityError is handle_errors.MoveCapacityError


def test_move_capacity_error_survives_the_rehome():
    error = handle_errors.MoveCapacityError("legal", 2048, 1024)
    assert error.query == "legal"
    assert error.needed == 2048
    assert error.capacity == 1024
    assert "2048" in str(error)


@_requires_dll
def test_legal_moves_raise_move_capacity_error(monkeypatch):
    handle = _new_handle(["p1", "p2"])
    fake = _OverflowingLib(needed=1025)
    try:
        monkeypatch.setattr(ce_api, "_lib", fake)
        with pytest.raises(handle_errors.MoveCapacityError) as excinfo:
            handle.legal_moves()
        assert excinfo.value.needed == 1025
        assert excinfo.value.capacity == 1024
    finally:
        monkeypatch.undo()
        handle.destroy()


@_requires_dll
def test_display_moves_raise_move_capacity_error(monkeypatch):
    handle = _new_handle(["p1", "p2"])
    fake = _OverflowingLib(needed=4096)
    try:
        monkeypatch.setattr(ce_api, "_lib", fake)
        with pytest.raises(handle_errors.MoveCapacityError) as excinfo:
            handle.display_moves()
        assert excinfo.value.query == "display"
    finally:
        monkeypatch.undo()
        handle.destroy()


@_requires_dll
def test_a_failed_clone_raises_engine_clone_failed(monkeypatch):
    handle = _new_handle(["p1", "p2"])
    proxy = _ProxyLib(engine_bindings._lib, engine_clone=lambda ptr: None)
    try:
        monkeypatch.setattr(engine_bindings, "_lib", proxy)
        with pytest.raises(handle_errors.EngineCloneFailed):
            handle.clone()
    finally:
        monkeypatch.undo()
        handle.destroy()


@_requires_dll
def test_a_failed_determinize_raises_engine_determinize_failed(monkeypatch):
    handle = _new_handle(["p1", "p2"])
    proxy = _ProxyLib(ce_api._lib, engine_determinize=lambda *args: None)
    try:
        monkeypatch.setattr(ce_api, "_lib", proxy)
        with pytest.raises(handle_errors.EngineDeterminizeFailed):
            handle.determinize("p1", 3)
    finally:
        monkeypatch.undo()
        handle.destroy()


@_requires_dll
def test_the_move_value_is_todays_wrapper_not_a_second_object():
    """``legal_moves`` is on the search's hot path (ADR-0011, F1's Move decision)."""
    assert Move is CMoveWrapper
    handle = _new_handle(["p1", "p2"])
    try:
        for move in handle.legal_moves():
            assert type(move) is CMoveWrapper
            assert isinstance(move, Move)
            assert isinstance(move.move_type, str)
            assert isinstance(move.data, dict)
            assert isinstance(move.to_payload(), dict)
    finally:
        handle.destroy()
