"""T2.1 / T2.4 — the additive full pending-context reader and pending flags.

Phase 2 of ``docs/nn-training-data-fix-plan.md``. The 6-key
``read_pending_generic_context`` stays unchanged; ``read_pending_generic_context_full``
adds ``option_ids``, ``remaining_repeats``, ``allow_repeat`` and ``effect_kind``.
"""

from __future__ import annotations

from engine_c.bindings.c_adapter import CEngineAdapter
from engine_c.bindings.pending_context import (
    read_pending_generic_context,
    read_pending_generic_context_full,
)
from openspiel_pyrants.nn.observation import (
    OBS_LAYOUT,
    PENDING_FLAG_ALLOW_REPEAT,
    PENDING_FLAG_AWAITING_OPTION,
    PENDING_FLAG_OPTIONAL,
    PENDING_FLAG_REMAINING_REPEATS,
    encode_observation,
)
from tests.c_engine.card_test_helpers import _make_engine, make_card_test_session

BASE_KEYS = {
    "source_card_id",
    "op",
    "card_action_id",
    "current_option_id",
    "awaiting_option",
    "optional",
}
FULL_KEYS = BASE_KEYS | {"option_ids", "remaining_repeats", "allow_repeat", "effect_kind"}


def _play(engine, card_id: str, **kwargs):
    session = make_card_test_session(
        engine, ["p1", "p2"], hand={"p1": [card_id]}, current_player="p1", **kwargs
    )
    for move in session.legal_moves():
        if move.move_type == "play_card" and move.data.get("card_id") == card_id:
            session.submit_move(move)
            return session
    raise AssertionError(f"could not play {card_id!r}")


def _adapter(session) -> CEngineAdapter:
    return CEngineAdapter(session._state, session._engine, session._player_ids, session._seed)


def test_read_pending_generic_context_full(requires_c_engine) -> None:
    gauth = _play(_make_engine(), "gauth")
    full = read_pending_generic_context_full(gauth._state._ptr)
    assert full is not None
    assert set(full) == FULL_KEYS
    assert full["source_card_id"] == "gauth"
    assert full["awaiting_option"] is True
    assert full["option_ids"] == ["option_1", "option_2"]
    assert full["remaining_repeats"] == 1
    assert full["allow_repeat"] is False
    assert full["effect_kind"] is None

    base = read_pending_generic_context(gauth._state._ptr)
    assert set(base) == BASE_KEYS
    assert {key: full[key] for key in base} == base

    mummy = _play(_make_engine(), "mummy_lord")
    full_m = read_pending_generic_context_full(mummy._state._ptr)
    assert full_m["remaining_repeats"] == 2
    assert full_m["allow_repeat"] is True

    myconid = _play(_make_engine(), "myconid_adult")
    full_c = read_pending_generic_context_full(myconid._state._ptr)
    assert full_c["op"] == "custom_effect"
    assert full_c["effect_kind"] == "give_insane_outcast_to_selected_player"

    quiet = make_card_test_session(
        _make_engine(), ["p1", "p2"], hand={"p1": ["noble"]}, current_player="p1"
    )
    assert read_pending_generic_context_full(quiet._state._ptr) is None


def test_full_reader_degrades_to_base_on_extended_failure(
    requires_c_engine, monkeypatch
) -> None:
    """T1.2 (R-3): an extended-read failure returns the 6-key base, not None.

    A monkeypatched ``sym_str`` raises only when asked to decode an option id
    (the extended read's first new call); the base read never decodes one.
    """
    import engine_c.bindings.pending_context as pc

    gauth = _play(_make_engine(), "gauth")
    ptr = gauth._state._ptr
    assert read_pending_generic_context(ptr) is not None

    real = pc.sym_str

    def flaky(sym):
        text = real(sym)
        if text and text.startswith("option"):
            raise RuntimeError("extended read failure")
        return text

    monkeypatch.setattr(pc, "sym_str", flaky)
    full = read_pending_generic_context_full(ptr)
    assert full is not None
    assert set(full) == BASE_KEYS
    assert {key: full[key] for key in BASE_KEYS} == read_pending_generic_context(ptr)


def test_pending_flags_encode_optional_and_repeats(requires_c_engine) -> None:
    fs = OBS_LAYOUT["pending_flags"][0]

    cult = _play(_make_engine(), "cult_fanatic")
    adapter = _adapter(cult)
    ctx = read_pending_generic_context_full(cult._state._ptr)
    assert ctx["op"] == "devour_cost"
    assert ctx["optional"] is True
    payloads = [move.to_payload() for move in adapter.legal_moves()]
    assert any(
        payload.get("action_id") is None and payload.get("target_id") is None
        for payload in payloads
    )
    obs = encode_observation(adapter, "p1", ctx)
    assert obs[fs + PENDING_FLAG_OPTIONAL] == 1
    assert obs[fs + PENDING_FLAG_AWAITING_OPTION] == 0
    assert obs[fs + PENDING_FLAG_ALLOW_REPEAT] == 0
    assert obs[fs + PENDING_FLAG_REMAINING_REPEATS] == 0

    mummy = _play(_make_engine(), "mummy_lord")
    madapter = _adapter(mummy)
    mctx = read_pending_generic_context_full(mummy._state._ptr)
    mobs = encode_observation(madapter, "p1", mctx)
    assert mobs[fs + PENDING_FLAG_AWAITING_OPTION] == 1
    assert mobs[fs + PENDING_FLAG_OPTIONAL] == 0
    assert mobs[fs + PENDING_FLAG_ALLOW_REPEAT] == 1
    assert mobs[fs + PENDING_FLAG_REMAINING_REPEATS] == 2

    fresh = _adapter(
        make_card_test_session(
            _make_engine(), ["p1", "p2"], hand={"p1": ["noble"]}, current_player="p1"
        )
    )
    start, end = OBS_LAYOUT["pending_flags"]
    assert encode_observation(fresh, "p1", None)[start:end].sum() == 0
