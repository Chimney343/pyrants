"""Handle/``CEngineAdapter`` parity (ADR-0011, brief F1).

F2 replaces the adapter's body with the handle, so this test is the guard that
makes that swap safe: for several seeds, both objects are driven through the
same random move sequence and must agree at every step on everything a caller
can observe — legal and display moves, phase, round, current player, every
player's view and information-state key, the scores, and a rollout drawn from
one seed.

It is a differential test, not a second implementation: if the two disagree,
the handle is wrong, because the adapter is what every caller uses today.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from engine_c.bindings import ce_api  # noqa: E402
from engine_c.bindings.c_adapter import CEngineAdapter  # noqa: E402
from engine_c.bindings.ce_api import CEngine  # noqa: E402
from engine_c.bindings.handle import GameHandle  # noqa: E402

PLAYERS = ["p1", "p2", "p3"]
SEEDS = [3, 42, 1234]

_requires_dll = pytest.mark.skipif(ce_api._lib is None, reason="engine_c DLL not available")


def _adapter_payloads(adapter: CEngineAdapter) -> list[dict]:
    return [move.to_payload() for move in adapter.legal_moves()]


def _adapter_display(adapter: CEngineAdapter) -> list[tuple[dict, bool]]:
    return [(move.to_payload(), applicable) for move, applicable in adapter.display_moves()]


def _handle_display(handle: GameHandle) -> list[tuple[dict, bool]]:
    return [(move.to_payload(), applicable) for move, applicable in handle.display_moves()]


def _compare(handle: GameHandle, adapter: CEngineAdapter, step: int, seed: int) -> None:
    where = f"seed={seed} step={step}"

    assert [m.to_payload() for m in handle.legal_moves()] == _adapter_payloads(adapter), where
    assert _handle_display(handle) == _adapter_display(adapter), where

    assert handle.phase() == adapter.phase(), where
    assert handle.round_number() == adapter.round_number(), where
    assert handle.current_player_id() == adapter.current_player_id(), where
    assert handle.is_terminal() == adapter.is_terminal(), where
    assert handle.player_ids == tuple(adapter.player_ids), where

    for player_id in PLAYERS:
        assert handle.player_view(player_id) == adapter.private_view_json(player_id), (
            f"{where} view of {player_id}"
        )
        assert handle.infostate_key(player_id) == adapter.infostate_hash(player_id), (
            f"{where} infostate of {player_id}"
        )

    assert handle.scores() == adapter.final_scores(), where
    assert handle.rollout(seed=step, max_length=12) == adapter.random_rollout(step, 12), where


@_requires_dll
@pytest.mark.parametrize("seed", SEEDS)
def test_handle_and_adapter_agree_at_every_step(seed: int):
    engine = CEngine()
    engine.initialize()
    adapter = CEngineAdapter(engine.create_game(PLAYERS, seed), engine, PLAYERS, seed)
    handle = GameHandle.new(PLAYERS, seed)
    try:
        _compare(handle, adapter, step=0, seed=seed)

        picks = random.Random(seed * 31 + 7)
        for step in range(1, 31):
            moves = handle.legal_moves()
            if not moves:
                break
            index = picks.randrange(len(moves))
            handle.apply(moves[index])
            adapter.apply(adapter.legal_moves()[index])
            _compare(handle, adapter, step=step, seed=seed)

        _compare(handle, adapter, step=step + 1, seed=seed)
    finally:
        handle.destroy()
        adapter.destroy()


@_requires_dll
@pytest.mark.parametrize("seed", SEEDS)
def test_a_determinized_handle_matches_a_determinized_adapter(seed: int):
    engine = CEngine()
    engine.initialize()
    adapter = CEngineAdapter(engine.create_game(PLAYERS, seed), engine, PLAYERS, seed)
    handle = GameHandle.new(PLAYERS, seed)
    try:
        for _step in range(1, 6):
            moves = handle.legal_moves()
            handle.apply(moves[0])
            adapter.apply(adapter.legal_moves()[0])

        world = handle.determinize("p1", seed + 500)
        world_adapter = adapter.determinize("p1", seed + 500)
        try:
            assert [m.to_payload() for m in world.legal_moves()] == _adapter_payloads(world_adapter)
            assert world.player_view("p1") == world_adapter.private_view_json("p1")
            assert world.player_view("p2") == world_adapter.private_view_json("p2")
            assert world.infostate_key("p1") == world_adapter.infostate_hash("p1")
            assert world.scores() == world_adapter.final_scores()
        finally:
            world.destroy()
            world_adapter.destroy()
    finally:
        handle.destroy()
        adapter.destroy()
