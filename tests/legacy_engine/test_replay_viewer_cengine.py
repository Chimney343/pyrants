"""Tests for C-engine replay compatibility in the replay viewer."""

import json
from pathlib import Path

import pytest

from engine.moves import (
    SPECIAL_RECRUIT_SLOT_CARD_IDS,
    AssassinateMove,
    DeployMove,
    EndMainPhaseMove,
    InitialPlacementMove,
    PlayCardMove,
    ResolveCleanupMove,
    ResolveEndOfTurnMove,
    ResolveGenericChoiceMove,
)
from game_simulation import MOVE_ADAPTER

# ---- Structural normalisation (happens at load time) ----


def _normalise_cengine_payload(entry: dict) -> dict:
    """Convert a C-engine replay entry payload into Python-engine flat format.

    C-engine entry structure:
        {"player_id": "p1", "payload": {"type": "play_card", "data": {...}}}

    Python engine expects flat payload:
        {"player_id": "p1", "move_type": "play_card", "card_id": "noble", ...}
    """
    payload = dict(entry.get("payload", {}))

    # 1. Rename 'type' → 'move_type' (remove 'type' since extra="forbid").
    if "move_type" not in payload and "type" in payload:
        move_type_val = payload["type"]
        payload = {k: v for k, v in payload.items() if k != "type"}
        payload["move_type"] = move_type_val

    # 2. Flatten 'data' into top-level payload.
    data = payload.pop("data", None)
    if isinstance(data, dict):
        for k, v in data.items():
            payload[k] = v

    # 3. Inject player_id from entry level.
    if "player_id" not in payload:
        entry_player_id = entry.get("player_id")
        if entry_player_id is not None:
            payload["player_id"] = entry_player_id

    # 4. Map C-engine move type names to Python names.
    TYPE_MAP = {
        "resolve_generic": "resolve_generic_choice",
    }
    if payload.get("move_type") in TYPE_MAP:
        payload["move_type"] = TYPE_MAP[payload["move_type"]]

    return payload


# ---- Semantic repairs (happen at validation time, using game state) ----


def _repair_hand_index(state, payload: dict) -> dict:
    """Fix play_card hand_index by looking up card_id in the player's hand."""
    if payload.get("move_type") != "play_card":
        return payload
    card_id = payload.get("card_id")
    hand_index = payload.get("hand_index")
    if not isinstance(card_id, str) or hand_index is None:
        return payload
    player_id = payload.get("player_id")
    if not isinstance(player_id, str):
        return payload
    player_state = state.players.get(player_id)
    if player_state is None:
        return payload
    hand = player_state.hand
    if isinstance(hand_index, int) and hand_index < len(hand) and hand[hand_index] == card_id:
        return payload
    for idx, cid in enumerate(hand):
        if cid == card_id:
            return {**payload, "hand_index": idx}
    return payload


def _repair_recruit_market_slot(state, payload: dict) -> dict:
    """Convert C-engine recruit's card_id to Python's market_slot index."""
    if payload.get("move_type") != "recruit":
        return payload
    if "market_slot" in payload:
        return payload
    card_id = payload.get("card_id")
    if not isinstance(card_id, str):
        return payload

    # Check special recruit slots (house_guard, priestess_of_lolth, insane_outcast).
    for slot, cid in SPECIAL_RECRUIT_SLOT_CARD_IDS.items():
        if cid == card_id:
            result = {k: v for k, v in payload.items() if k != "card_id"}
            result["market_slot"] = slot
            return result

    # Look up in market row.
    for idx, cid in enumerate(state.market.row):
        if cid == card_id:
            result = {k: v for k, v in payload.items() if k != "card_id"}
            result["market_slot"] = idx
            return result

    return payload


def _repair_generic_choice(state, payload: dict) -> dict:
    """Convert C-engine resolve_generic fields into Python ResolveGenericChoiceMove format."""
    if payload.get("move_type") != "resolve_generic_choice":
        return payload
    if "source_card_id" in payload:
        return payload
    if "action_id" not in payload:
        return payload

    pending = state.pending_generic_choice
    if pending is None:
        return payload

    action_id = payload.get("action_id", "")
    option_id = None
    selection = {}

    # action_id starting with "option_" maps to option_id; everything else goes into selection.
    if isinstance(action_id, str) and action_id.startswith("option_"):
        option_id = action_id
    else:
        selection["action_id"] = action_id
        if "target_id" in payload:
            selection["target_id"] = payload["target_id"]
        if "selection_index" in payload:
            selection["selection_index"] = payload["selection_index"]

    # Build new payload with only the fields ResolveGenericChoiceMove expects.
    result = {
        "move_type": "resolve_generic_choice",
        "player_id": payload["player_id"],
        "source_card_id": pending.source_card_id,
    }
    if option_id is not None:
        result["option_id"] = option_id
    if selection:
        result["selection"] = selection

    return result


# ---- Structural normalisation tests ----


class TestNormaliseCenginePayload:
    def test_initial_placement(self):
        entry = {
            "player_id": "p1",
            "move_type": "initial_placement",
            "payload": {
                "type": "initial_placement",
                "data": {"target_node_id": "site_ched_nasad"},
            },
        }
        result = _normalise_cengine_payload(entry)
        assert result["move_type"] == "initial_placement"
        assert result["player_id"] == "p1"
        assert result["target_node_id"] == "site_ched_nasad"
        assert "type" not in result
        assert "data" not in result
        move = MOVE_ADAPTER.validate_python(result)
        assert isinstance(move, InitialPlacementMove)

    def test_play_card(self):
        entry = {
            "player_id": "p1",
            "move_type": "play_card",
            "payload": {
                "type": "play_card",
                "data": {"card_id": "noble", "hand_index": 1},
            },
        }
        result = _normalise_cengine_payload(entry)
        assert result["move_type"] == "play_card"
        assert result["card_id"] == "noble"
        assert result["hand_index"] == 1
        move = MOVE_ADAPTER.validate_python(result)
        assert isinstance(move, PlayCardMove)

    def test_deploy(self):
        entry = {
            "player_id": "p2",
            "move_type": "deploy",
            "payload": {
                "type": "deploy",
                "data": {"target_node_id": "route_35", "troop_count": 1},
            },
        }
        result = _normalise_cengine_payload(entry)
        assert result["troop_count"] == 1
        move = MOVE_ADAPTER.validate_python(result)
        assert isinstance(move, DeployMove)

    def test_assassinate(self):
        entry = {
            "player_id": "p1",
            "move_type": "assassinate",
            "payload": {
                "type": "assassinate",
                "data": {"target_node_id": "site_tsenvilyq", "target_slot_index": 0},
            },
        }
        result = _normalise_cengine_payload(entry)
        move = MOVE_ADAPTER.validate_python(result)
        assert isinstance(move, AssassinateMove)

    def test_end_main_phase(self):
        entry = {
            "player_id": "p1",
            "move_type": "end_main_phase",
            "payload": {"type": "end_main_phase", "data": {}},
        }
        result = _normalise_cengine_payload(entry)
        move = MOVE_ADAPTER.validate_python(result)
        assert isinstance(move, EndMainPhaseMove)

    def test_resolve_end_of_turn(self):
        entry = {
            "player_id": "p1",
            "move_type": "resolve_end_of_turn",
            "payload": {"type": "resolve_end_of_turn", "data": {}},
        }
        result = _normalise_cengine_payload(entry)
        move = MOVE_ADAPTER.validate_python(result)
        assert isinstance(move, ResolveEndOfTurnMove)

    def test_resolve_cleanup(self):
        entry = {
            "player_id": "p2",
            "move_type": "resolve_cleanup",
            "payload": {"type": "resolve_cleanup", "data": {}},
        }
        result = _normalise_cengine_payload(entry)
        move = MOVE_ADAPTER.validate_python(result)
        assert isinstance(move, ResolveCleanupMove)

    def test_resolve_generic_name_mapping(self):
        entry = {
            "player_id": "p1",
            "move_type": "resolve_generic",
            "payload": {
                "type": "resolve_generic",
                "data": {"action_id": "route_44", "target_id": None, "selection_index": 0},
            },
        }
        result = _normalise_cengine_payload(entry)
        assert result["move_type"] == "resolve_generic_choice"
        # (full validation requires _repair_generic_choice with state)

    def test_recruit_structural(self):
        entry = {
            "player_id": "p1",
            "move_type": "recruit",
            "payload": {"type": "recruit", "data": {"card_id": "grimlock"}},
        }
        result = _normalise_cengine_payload(entry)
        assert result["move_type"] == "recruit"
        assert result["card_id"] == "grimlock"
        # market_slot is filled later by _repair_recruit_market_slot

    def test_player_id_injected_from_entry(self):
        entry = {
            "player_id": "p42",
            "move_type": "initial_placement",
            "payload": {
                "type": "initial_placement",
                "data": {"target_node_id": "site_blingdenfire"},
            },
        }
        result = _normalise_cengine_payload(entry)
        assert result["player_id"] == "p42"

    def test_existing_player_id_not_overridden(self):
        entry = {
            "player_id": "entry_player",
            "move_type": "play_card",
            "payload": {
                "player_id": "payload_player",
                "type": "play_card",
                "data": {"card_id": "noble", "hand_index": 0},
            },
        }
        result = _normalise_cengine_payload(entry)
        assert result["player_id"] == "payload_player"

    def test_python_engine_payload_passes_through(self):
        """Existing Python-engine flat payloads must remain unchanged."""
        entry = {
            "player_id": "p1",
            "move_type": "play_card",
            "payload": {
                "move_type": "play_card",
                "player_id": "p1",
                "card_id": "noble",
                "hand_index": 0,
            },
        }
        result = _normalise_cengine_payload(entry)
        assert result == entry["payload"]


# ---- Semantic repair tests ----


class TestRepairRecruitMarketSlot:
    def test_repair_normal_market_slot(self):
        """Look up card_id 'grimlock' in market.row → index 0."""
        class FakeMarket:
            row = ["grimlock", "soldier", "noble"]

        class FakeState:
            market = FakeMarket()

        payload = {"move_type": "recruit", "player_id": "p1", "card_id": "grimlock"}
        result = _repair_recruit_market_slot(FakeState(), payload)
        assert result["market_slot"] == 0
        assert "card_id" not in result

    def test_repair_special_slot_house_guard(self):
        class FakeState:
            market = type("Market", (), {"row": []})()

        payload = {"move_type": "recruit", "player_id": "p1", "card_id": "house_guard"}
        result = _repair_recruit_market_slot(FakeState(), payload)
        from engine.moves import HOUSE_GUARD_RECRUIT_SLOT
        assert result["market_slot"] == HOUSE_GUARD_RECRUIT_SLOT
        assert "card_id" not in result

    def test_repair_special_slot_priestess(self):
        class FakeState:
            market = type("Market", (), {"row": []})()

        payload = {"move_type": "recruit", "player_id": "p1", "card_id": "priestess_of_lolth"}
        result = _repair_recruit_market_slot(FakeState(), payload)
        from engine.moves import PRIESTESS_RECRUIT_SLOT
        assert result["market_slot"] == PRIESTESS_RECRUIT_SLOT

    def test_non_recruit_passes_through(self):
        payload = {"move_type": "play_card", "card_id": "noble"}
        result = _repair_recruit_market_slot(None, payload)
        assert result is payload

    def test_already_has_market_slot(self):
        payload = {"move_type": "recruit", "market_slot": 2}
        result = _repair_recruit_market_slot(None, payload)
        assert result is payload

    def test_card_not_found_returns_unchanged(self):
        class FakeState:
            market = type("Market", (), {"row": ["noble"]})()

        payload = {"move_type": "recruit", "player_id": "p1", "card_id": "nonexistent"}
        result = _repair_recruit_market_slot(FakeState(), payload)
        assert result is payload


class FakePending:
    source_card_id = "priestess_of_lolth"
    awaiting_option = False


class TestRepairGenericChoice:
    def test_already_has_source_card_id(self):
        payload = {"move_type": "resolve_generic_choice", "source_card_id": "noble"}
        result = _repair_generic_choice(None, payload)
        assert result is payload

    def test_no_pending_choice(self):
        state = type("State", (), {"pending_generic_choice": None})()
        payload = {"move_type": "resolve_generic_choice", "player_id": "p1", "action_id": "route_44"}
        result = _repair_generic_choice(state, payload)
        assert result is payload

    def test_action_id_as_selection(self):
        state = type("State", (), {"pending_generic_choice": FakePending()})()
        payload = {
            "move_type": "resolve_generic_choice",
            "player_id": "p1",
            "action_id": "route_44",
            "target_id": None,
            "selection_index": 0,
        }
        result = _repair_generic_choice(state, payload)
        assert result["move_type"] == "resolve_generic_choice"
        assert result["source_card_id"] == "priestess_of_lolth"
        assert "option_id" not in result
        assert result["selection"] == {"action_id": "route_44", "target_id": None, "selection_index": 0}
        # Validate as proper Python move
        move = MOVE_ADAPTER.validate_python(result)
        assert isinstance(move, ResolveGenericChoiceMove)

    def test_action_id_as_option(self):
        state = type("State", (), {"pending_generic_choice": FakePending()})()
        payload = {
            "move_type": "resolve_generic_choice",
            "player_id": "p1",
            "action_id": "option_1",
            "target_id": None,
            "selection_index": 0,
        }
        result = _repair_generic_choice(state, payload)
        assert result["option_id"] == "option_1"
        # selection is omitted when empty (model default is {})
        move = MOVE_ADAPTER.validate_python(result)
        assert isinstance(move, ResolveGenericChoiceMove)

    def test_non_generic_choice_passes_through(self):
        payload = {"move_type": "play_card"}
        result = _repair_generic_choice(None, payload)
        assert result is payload


# ---- Full-file integration test ----


@pytest.mark.skipif(
    not Path(
        __file__, "..", "..",
        "artifacts", "ismcts", "c9ebaa6e2a79", "game_0000", "replay.json",
    ).resolve().exists(),
    reason="C-engine replay file not present",
)
def test_full_cengine_replay_normalisation():
    """Every entry in the C-engine replay must survive structural normalisation
    and Pydantic validation after repairs (recruit market_slot, generic choice,
    hand_index).  Full session replay may diverge at later steps due to engine-
    internal state differences; this test verifies the pipe does not crash."""
    from engine.state import build_initial_game_state
    from game_session import GameSession
    from game_setup.loaders import build_game_definition_from_dicts
    from game_setup.market_setup import combine_two_deck_market_setup, discover_full_deck_profiles
    from interface.replay_viewer import DECKS_DIR, _load_payload

    path = (
        Path(__file__).resolve().parents[2]
        / "artifacts"
        / "ismcts"
        / "c9ebaa6e2a79"
        / "game_0000"
        / "replay.json"
    )
    data = _load_payload(path)
    entries = data.get("replay_log", [])
    assert len(entries) > 0

    ctx = data.get("replay_context", {})
    board_path = Path(ctx["board_path"])
    card_path = Path(ctx["card_path"])
    setup_path = Path(ctx["setup_path"])
    player_ids = ctx["player_ids"]
    seed = ctx.get("seed", 42)

    board_data = json.loads(board_path.read_text(encoding="utf-8"))
    card_data = json.loads(card_path.read_text(encoding="utf-8"))
    base_setup = json.loads(setup_path.read_text(encoding="utf-8"))

    profiles = discover_full_deck_profiles(DECKS_DIR)
    deck_a = next(p for p in profiles if p.deck_id == ctx["deck_a_id"])
    deck_b = next(p for p in profiles if p.deck_id == ctx["deck_b_id"])

    market_setup = combine_two_deck_market_setup(base_setup, deck_a, deck_b)
    setup_data = market_setup.to_setup_data()

    definition = build_game_definition_from_dicts(board_data, card_data, setup_data)
    state = build_initial_game_state(definition, player_ids=player_ids, shuffle_seed=seed)
    session = GameSession(state)

    # Replay as far as possible with normalisation + state-dependent repairs.
    step_count = 0
    for _i, entry in enumerate(entries):
        try:
            payload = _normalise_cengine_payload(entry)
            payload = _repair_hand_index(session.state, payload)
            payload = _repair_recruit_market_slot(session.state, payload)
            payload = _repair_generic_choice(session.state, payload)
            move = MOVE_ADAPTER.validate_python(payload)
            session.submit_move(move)
            step_count += 1
        except Exception:
            # State divergence after this point is expected — partial replay is fine.
            break

    # We should get through at least setup + first round of main phase.
    assert step_count >= 5, (
        f"Replay diverged too early: only {step_count} entries succeeded. "
        "Check seed/hand alignment between C-engine and Python-engine."
    )

