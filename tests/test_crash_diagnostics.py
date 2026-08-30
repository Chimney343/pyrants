"""Structured crash-diagnosis tests for scripts/run_ismcts.py.

Phase 3 of the IS-MCTS observability work: when a move fails to apply, the
runner must build a structured crash record — the ``pending_card_id`` and
post-failure adapter state — so the documented crash classes can be identified
from ``failures.jsonl`` alone without ever reading a raw traceback.

``_diagnose_apply_failure`` and ``_build_crash_record`` are the two pure-ish
helpers under test here.  The first is exercised against the real C engine
(forcing a genuinely illegal move); the latter is exercised with test doubles
so it stays fast and focused on its field-merge logic.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.run_ismcts import _build_crash_record, _diagnose_apply_failure


def _make_adapter():
    """Build a real CEngineAdapter on a fresh minimal main-phase session."""
    from engine_c.bindings.c_adapter import CEngineAdapter
    from tests.c_engine.card_test_helpers import _make_engine, make_card_test_session

    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        current_player="p1",
    )
    return CEngineAdapter(session._state, eng, ["p1", "p2"], shuffle_seed=0)


def _make_adapter_with_pending_card():
    """Play ``mercenary_squad`` so a pending generic choice is active."""
    from engine_c.bindings.c_adapter import CEngineAdapter
    from tests.c_engine.card_test_helpers import _make_engine, make_card_test_session

    eng = _make_engine()
    session = make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["mercenary_squad"]},  # single-action card: deploy_troops
        current_player="p1",
    )
    adapter = CEngineAdapter(session._state, eng, ["p1", "p2"], shuffle_seed=0)
    play_move = next(
        m
        for m in adapter.legal_moves()
        if m.move_type == "play_card" and m.data.get("card_id") == "mercenary_squad"
    )
    adapter.apply(play_move)
    return adapter


def _illegal_assassinate_move():
    """A move that is illegal in every state: assassinate with a null target.

    ``apply_assassinate`` (``engine_c/rules.c``) bails out with NULL before ever
    touching the target because a fresh session has ``power < 3``, so this never
    dereferences the null node and is safe to use as an artificial failure.
    """
    from engine_c.bindings.ce_api import CMoveWrapper
    from engine_c.bindings.engine_bindings import MOVE_ASSASSINATE, Move, Sym

    c_move = Move()
    c_move.type = MOVE_ASSASSINATE
    c_move.data.assassinate.target_node_id = Sym(0)
    c_move.data.assassinate.troop_owner_id = Sym(0)
    c_move.data.assassinate.slot_index = 0
    c_move.player_index = 0
    return CMoveWrapper(c_move)


class TestDiagnoseApplyFailure:
    def test_extracts_structured_fields_after_failed_apply(self, requires_c_engine):
        adapter = _make_adapter()
        before_phase = adapter.phase()
        before_round = adapter.round_number()
        before_player = adapter.current_player_id()
        before_terminal = adapter.is_terminal()

        with pytest.raises(RuntimeError):
            adapter.apply(_illegal_assassinate_move())

        diag = _diagnose_apply_failure(adapter)

        assert diag["pending_card_id"] is None
        assert diag["phase_at_failure"] == before_phase
        assert diag["round_number_at_failure"] == before_round
        assert diag["current_player_at_failure"] == before_player
        assert diag["is_terminal_at_failure"] == before_terminal
        assert diag["legal_moves_count_at_failure"] > 0
        assert isinstance(diag["legal_moves_at_failure"], list)
        assert len(diag["legal_moves_at_failure"]) > 0
        assert all(isinstance(m, str) for m in diag["legal_moves_at_failure"])

    def test_pending_card_id_reflects_source_card(self, requires_c_engine):
        adapter = _make_adapter_with_pending_card()
        assert adapter.pending_generic_op() == "deploy_troops"

        with pytest.raises(RuntimeError):
            adapter.apply(_illegal_assassinate_move())

        diag = _diagnose_apply_failure(adapter)
        assert diag["pending_card_id"] == "mercenary_squad"


class TestDiagnoseApplyFailureIsDefensive:
    def test_diagnosis_failure_returns_diagnosis_failed(self):
        class BrokenAdapter:
            def legal_moves(self):
                raise ValueError("introspection exploded")

        diag = _diagnose_apply_failure(BrokenAdapter())
        assert diag == {"diagnosis_failed": "introspection exploded"}


class TestBuildCrashRecord:
    def test_merges_exception_diagnosis_and_attempted_move(self, monkeypatch):
        monkeypatch.setattr(
            "scripts.run_ismcts._diagnose_apply_failure",
            lambda adapter: {"pending_card_id": "elder_brain", "phase_at_failure": "main"},
        )
        state = SimpleNamespace(_adapter=object())
        exc = RuntimeError("boom")

        try:
            raise exc
        except RuntimeError:
            record = _build_crash_record(
                exc,
                state,
                step_index=5,
                attempted_move_type="resolve_generic",
                attempted_move_label="resolve_generic(...)",
                attempted_payload={"move_type": "resolve_generic_choice", "target_id": "site_chaulssin"},
            )

        assert record["exception_type"] == "RuntimeError"
        assert record["exception_message"] == "boom"
        assert "Traceback (most recent call last)" in record["traceback"]
        assert record["step_index"] == 5
        assert record["attempted_move_type"] == "resolve_generic"
        assert record["attempted_move_label"] == "resolve_generic(...)"
        assert record["attempted_payload"] == {
            "move_type": "resolve_generic_choice",
            "target_id": "site_chaulssin",
        }
        assert record["pending_card_id"] == "elder_brain"
        assert record["phase_at_failure"] == "main"

    def test_no_adapter_skips_diagnosis(self):
        state = SimpleNamespace()  # no _adapter attribute
        exc = RuntimeError("boom")

        try:
            raise exc
        except RuntimeError:
            record = _build_crash_record(
                exc,
                state,
                step_index=0,
                attempted_move_type=None,
                attempted_move_label="",
                attempted_payload={},
            )

        assert "pending_card_id" not in record
        assert "phase_at_failure" not in record
        assert record["exception_type"] == "RuntimeError"
        assert record["attempted_move_type"] is None
