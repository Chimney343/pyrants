"""Tests for the resolve_generic context enrichment in scripts/run_ismcts.py.

The runner must capture, *at decision-write time* (before ``apply_action``
advances/clears the pending-generic state), which card a ``resolve_generic``
choice belongs to and what the choice actually does.  Two additive fields land
on ``resolve_generic`` decision lines only: ``chosen_label`` (human string via
``label_enrich.enrich_label``) and ``generic`` (structured card/action
context); ``chosen_move`` stays raw and every other move type is untouched.
"""

from __future__ import annotations

import json

import openspiel_pyrants  # noqa: F401
from scripts.run_ismcts import (
    _game_dir,
    _load_game_or_die,
    _resolve_policy,
    run_one_game,
)


def _quick_params(tmp_path, **overrides) -> dict:
    params = {
        "game": _load_game_or_die("python_pyrants_c", {"num_players": "2"}),
        "game_index": 0,
        "num_sims": 2,
        "uct_c": 1.4,
        "max_world_samples": 10,
        "final_policy_type": _resolve_policy("visited"),
        "final_policy_name": "visited",
        "seed": 42,
        "shuffle_seed": 42,
        "out_dir": tmp_path,
        "deck_a_id": "deck_a",
        "deck_b_id": "deck_b",
        "show_progress": False,
        "rollout_count": 1,
        "rollout_max_length": None,
        "max_rounds": 15,
        "num_players": 2,
    }
    params.update(overrides)
    return params


class _ScriptedBot:
    """Bot that plays the first legal play_card and never ends the main phase.

    Choosing ``play_card`` when none is legal falls back to the first legal
    move.  Resolve-generic/cleanup moves are taken as the bot is offered them.
    """

    def step_with_policy(self, state):
        legal_ids = state.legal_actions()
        chosen_id = None
        for aid in legal_ids:
            move = state.decode_action(aid)
            if move.move_type == "play_card":
                chosen_id = aid
                break
        if chosen_id is None:
            chosen_id = legal_ids[0]
        policy = [(aid, 1.0 / len(legal_ids)) for aid in legal_ids]
        return policy, chosen_id


def _install_scripted_bot(monkeypatch, bot):
    from open_spiel.python.algorithms.ismcts import ISMCTSBot

    def fake_step_with_policy(self, state):
        return bot.step_with_policy(state)

    monkeypatch.setattr(ISMCTSBot, "step_with_policy", fake_step_with_policy)


def _decision_lines(tmp_path) -> list[dict]:
    game_out = _game_dir(tmp_path, 0)
    path = game_out / "decisions.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def test_gauth_option_choice_label_and_generic(requires_c_engine, tmp_path, monkeypatch) -> None:
    """A resolve_generic option choice carries a card-context generic + label."""
    from scripts.run_ismcts import _enrich_resolve_generic
    from tests.c_engine.card_test_helpers import _make_engine, _sptr, make_card_test_session

    session = make_card_test_session(
        _make_engine(),
        ["p1", "p2"],
        hand={"p1": ["gauth"]},
        current_player="p1",
    )
    try:
        for m in session.legal_moves():
            if m.move_type == "play_card" and m.data.get("card_id") == "gauth":
                session.submit_move(m)
                break
        else:
            raise AssertionError("gauth not playable")

        from engine_c.bindings.pending_context import read_pending_generic_context

        assert read_pending_generic_context(_sptr(session)) is not None

        option_move = next(
            m for m in session.legal_moves()
            if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_1"
        )

        import types

        # The helper only touches adapter._state._ptr, so wrap the session's
        # state ptr in a lightweight adapter-shaped object.
        adapter_stub = types.SimpleNamespace(
            _state=types.SimpleNamespace(_ptr=_sptr(session))
        )
        extra = _enrich_resolve_generic(adapter_stub, option_move)

        assert extra["chosen_label"] == "Gauth: Gain 2 influence", extra
        generic = extra["generic"]
        assert generic["source_card_id"] == "gauth"
        assert generic["awaiting_option"] is True
        assert generic["op"] is None
        assert generic["card_action_id"] is None
        assert generic["move_action_id"] == "option_1"
        assert generic["move_target_id"] is None
        assert generic["selection_index"] == 0
    finally:
        session.destroy()


def test_run_writes_fields_only_on_resolve_generic_lines(
    requires_c_engine, tmp_path, monkeypatch
) -> None:
    """Smoke test: decisions.jsonl lines are shaped as the plan requires."""
    _install_scripted_bot(monkeypatch, _ScriptedBot())
    params = _quick_params(tmp_path, max_rounds=6)
    summary = run_one_game(**params)
    assert summary["decision_count"] > 0

    decisions = _decision_lines(tmp_path)
    assert decisions, "no decision lines written"

    generic_lines = [d for d in decisions if d["chosen_move"].startswith("resolve_generic(")]
    non_generic_lines = [d for d in decisions if not d["chosen_move"].startswith("resolve_generic(")]

    for d in generic_lines:
        assert "chosen_label" in d, f"resolve_generic line missing chosen_label: {d}"
        assert "generic" in d, f"resolve_generic line missing generic: {d}"
        generic = d["generic"]
        assert isinstance(generic.get("source_card_id"), str)
        assert isinstance(generic.get("move_action_id"), (str, type(None)))
        assert isinstance(generic.get("awaiting_option"), bool)

    for d in non_generic_lines:
        assert "chosen_label" not in d, f"non-generic line gained chosen_label: {d}"
        assert "generic" not in d, f"non-generic line gained generic: {d}"
