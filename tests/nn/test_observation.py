"""T3.7-T3.11 — observation encoding."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from openspiel_pyrants.nn.index import NODE_ADJACENT, NUM_CARD_IDS, card_index
from openspiel_pyrants.nn.observation import (
    ENCODER_VERSION,
    MAX_SEATS,
    OBS_LAYOUT,
    OBS_SIZE,
    PENDING_OP_SLOTS,
    PENDING_OPTION_SLOTS,
    effect_kind_index,
    encode_observation,
    node_features,
    op_index,
    seat_order,
)
from openspiel_pyrants.nn.public import public_multisets

ROOT = Path(__file__).resolve().parents[2]


def _counts_vector(cards) -> np.ndarray:
    vec = np.zeros(NUM_CARD_IDS, dtype=np.int16)
    for cid in cards:
        vec[card_index(cid)] += 1
    return vec


SEAT_FEATURE_KEYS = (
    "score",
    "vp_tokens",
    "barracks",
    "spies_available",
    "hand_size",
    "deck_size",
    "discard_size",
    "trophy_hall_size",
)


def _summary_tuple(summary: dict) -> tuple[int, ...]:
    return tuple(int(summary.get(key, 0)) for key in SEAT_FEATURE_KEYS)


def _summaries(adapter, pid: str) -> dict:
    view = json.loads(adapter.private_view_json(pid))
    return view["public"]["public_player_summaries"]


# ── T3.7 shape / dtype / range / tiling ────────────────────────────────────


def test_observation_shape_dtype_range(mid_game_adapter) -> None:
    adapter = mid_game_adapter()
    pid = adapter.current_player_id()
    obs = encode_observation(adapter, pid, None)

    assert obs.dtype == np.int16
    assert obs.shape == (OBS_SIZE,)
    assert (obs >= 0).all()
    assert (obs < 32767).all()
    assert np.array_equal(obs, encode_observation(adapter, pid, None))

    cursor = 0
    for start, end in sorted(OBS_LAYOUT.values()):
        assert start == cursor, (start, end)
        cursor = end
    assert cursor == OBS_SIZE


# ── T3.8 perspective-relative seats ────────────────────────────────────────


def test_observation_is_perspective_relative(mid_game_adapter) -> None:
    adapter = mid_game_adapter(2)
    for pid in ("p1", "p2"):
        obs = encode_observation(adapter, pid, None)
        start, end = OBS_LAYOUT["my_hand"]
        idx = adapter.player_index(pid)
        assert np.array_equal(obs[start:end], _counts_vector(adapter.state.player_hand(idx)))

    # The named contract test also owns the seat blocks: slot k is order[k],
    # so slot 0 is the acting player's own stats (not absolute seat 0).
    sf_start, sf_end = OBS_LAYOUT["seat_features"]
    for pid in ("p1", "p2"):
        obs = encode_observation(adapter, pid, None)
        order = seat_order(adapter, pid)
        summaries = _summaries(adapter, pid)
        block = obs[sf_start:sf_end].reshape(MAX_SEATS, 8)
        for slot, seat in enumerate(order):
            assert tuple(block[slot]) == _summary_tuple(summaries[seat]), (pid, slot)
    cur_start, cur_end = OBS_LAYOUT["seat_is_current"]
    cp = adapter.current_player_id()
    assert encode_observation(adapter, cp, None)[cur_start:cur_end].tolist() == [1, 0, 0, 0]

    start, end = OBS_LAYOUT["seat_present"]
    assert encode_observation(adapter, "p1", None)[start:end].tolist() == [1, 1, 0, 0]

    adapter4 = mid_game_adapter(4)
    assert (
        encode_observation(adapter4, "p1", None)[start:end].tolist() == [1, 1, 1, 1]
    )

    adapter3 = mid_game_adapter(3)
    assert seat_order(adapter3, "p2") == ["p2", "p3", "p1"]


def test_seat_features_are_perspective_relative(mid_game_adapter) -> None:
    """T2.1 (R-1): the own-stats block rotates with the acting player."""
    sf_start, sf_end = OBS_LAYOUT["seat_features"]
    for num_players in (3, 4):
        adapter = mid_game_adapter(num_players, seed=7, n_moves=60)
        blocks: dict[str, tuple] = {}
        summary_sets: dict[str, tuple] = {}
        for pid in adapter.player_ids:
            order = seat_order(adapter, pid)
            summaries = _summaries(adapter, pid)
            block = encode_observation(adapter, pid, None)[sf_start:sf_end].reshape(
                MAX_SEATS, 8
            )
            blocks[pid] = tuple(tuple(row) for row in block)
            summary_sets[pid] = tuple(_summary_tuple(summaries[seat]) for seat in order)
            for slot, seat in enumerate(order):
                assert tuple(block[slot]) == _summary_tuple(summaries[seat]), (
                    num_players,
                    pid,
                    slot,
                )
            for extra in range(num_players, MAX_SEATS):
                assert tuple(block[extra]) == (0,) * 8
        # Only assert the block *differs* between perspectives when the
        # underlying summaries differ, so the test is data-driven not flaky.
        if len(set(summary_sets.values())) > 1:
            assert len(set(blocks.values())) > 1


def test_seat_is_current_is_seat_zero(mid_game_adapter) -> None:
    """T2.2 (R-1): the encoder is called from the current seat, so this block
    is the constant ``[1, 0, 0, 0]`` for 2-, 3- and 4-player states."""
    cur_start, cur_end = OBS_LAYOUT["seat_is_current"]
    for num_players in (2, 3, 4):
        adapter = mid_game_adapter(num_players, seed=11, n_moves=50)
        pid = adapter.current_player_id()
        obs = encode_observation(adapter, pid, None)
        assert obs[cur_start:cur_end].tolist() == [1, 0, 0, 0], num_players


# ── T3.9 leak test: invariant under determinize ────────────────────────────


def test_observation_invariant_under_determinize(mid_game_adapter) -> None:
    control_diff = 0
    checked = 0
    for num_players in (2, 4):
        for k in range(10):
            adapter = mid_game_adapter(num_players, seed=100 + k, n_moves=30)
            pid = adapter.current_player_id()
            obs = encode_observation(adapter, pid, None)

            det = adapter.determinize(pid, 1000 + k)
            assert det is not None
            obs_det = encode_observation(det, pid, None)
            assert np.array_equal(obs, obs_det)

            opp_idx = next(
                i for i, p in enumerate(adapter.player_ids) if p != pid
            )
            if list(adapter.state.player_hand(opp_idx)) != list(det.state.player_hand(opp_idx)):
                control_diff += 1
            checked += 1
            det.destroy()

    assert checked == 20
    # If every determinization preserved the opponent hand, the leak test
    # would be vacuous; require at least one genuinely different world.
    assert control_diff > 0


# ── T3.10 public multisets match engine and final_decks ────────────────────


def _complete_game_dir() -> Path | None:
    root = ROOT / "artifacts" / "ismcts"
    if not root.exists():
        return None
    for replay_path in sorted(root.rglob("replay.json")):
        game_dir = replay_path.parent
        if (game_dir / "final_decks.json").exists() and (
            game_dir / "decisions.jsonl"
        ).exists():
            return game_dir
    return None


GAME_DIR = _complete_game_dir()


@pytest.mark.skipif(GAME_DIR is None, reason="no stored replay artifacts")
def test_public_multisets_match_engine_and_final_decks(requires_c_engine) -> None:
    from engine_c.bindings.c_adapter import CEngineAdapter
    from engine_c.bindings.ce_api import CEngine
    from interface.replay_loader import engine_seed, load_replay

    bundle = load_replay(GAME_DIR)
    engine = CEngine()
    engine.initialize(
        catalog_path=str(bundle.card_path),
        board_path=str(bundle.board_path),
        setup_path=str(bundle.setup_path),
        setup_data_json=bundle.setup_json,
    )
    player_ids = list(bundle.meta.player_ids)
    seed = engine_seed(bundle.meta.shuffle_seed)
    adapter = CEngineAdapter(engine.create_game(player_ids, seed), engine, player_ids, seed)

    try:
        log = [
            e
            for e in bundle.replay.get("replay_log", ())
            if e.get("payload", {}).get("move_type") != "__terminal__"
        ]
        stride = max(1, len(log) // 50)
        for idx, entry in enumerate(log):
            if idx % stride == 0:
                for pid in player_ids:
                    view = json.loads(adapter.private_view_json(pid))
                    pm = public_multisets(adapter, pid)
                    assert sum(pm.deck.values()) == view["deck_size"]
                    assert sum(pm.market_remaining.values()) == view["public"]["market_deck_size"]
                    for other_idx, _other in enumerate(player_ids):
                        engine_bag = Counter(
                            adapter.state.player_deck(other_idx)
                            + adapter.state.player_hand(other_idx)
                            + adapter.state.player_discard(other_idx)
                        )
                        assert pm.bags[other_idx] == engine_bag
            payload = entry["payload"]
            match = next(
                (m for m in adapter.legal_moves() if m.to_payload() == payload), None
            )
            assert match is not None
            adapter.apply(match)

        assert adapter.is_terminal()
        final_decks = json.loads((GAME_DIR / "final_decks.json").read_text(encoding="utf-8"))
        terminal_pm = public_multisets(adapter, player_ids[0])
        for i, _pid in enumerate(player_ids):
            owned = (
                terminal_pm.bags[i]
                + terminal_pm.played_by_seat[i]
                + terminal_pm.inner_circle_by_seat[i]
            )
            assert owned == Counter(final_decks["per_seat"][i])
    finally:
        adapter.destroy()


# ── T3.11 pending block ────────────────────────────────────────────────────


def test_pending_block_encodes_source_card_and_op(
    mid_game_adapter, pending_gauth_session, adapter_from_session
) -> None:
    from engine_c.bindings.pending_context import read_pending_generic_context

    session = pending_gauth_session
    adapter = adapter_from_session(session)
    ctx = read_pending_generic_context(adapter._state._ptr)
    assert ctx is not None
    assert ctx["awaiting_option"] is True
    assert ctx["source_card_id"] == "gauth"

    obs = encode_observation(adapter, "p1", ctx)
    src_start = OBS_LAYOUT["pending_source_card"][0]
    assert obs[src_start + card_index("gauth")] == 1
    flags_start = OBS_LAYOUT["pending_flags"][0]
    assert obs[flags_start + PENDING_OPTION_SLOTS] == 1  # awaiting_option

    # An op-pending context sets exactly one op one-hot.
    op_ctx = {
        "source_card_id": "gauth",
        "op": "deploy_troops",
        "card_action_id": None,
        "current_option_id": None,
        "awaiting_option": False,
        "optional": False,
    }
    obs_op = encode_observation(adapter, "p1", op_ctx)
    op_start = OBS_LAYOUT["pending_op"][0]
    op_block = obs_op[op_start:op_start + PENDING_OP_SLOTS]
    assert op_block.sum() == 1
    assert op_block[op_index("deploy_troops")] == 1

    # No pending choice -> every pending block is zero.
    fresh = mid_game_adapter(2)
    obs_none = encode_observation(fresh, fresh.current_player_id(), None)
    for name in ("pending_source_card", "pending_op", "pending_flags"):
        start, end = OBS_LAYOUT[name]
        assert obs_none[start:end].sum() == 0, name


# ── T2.5 effect-kind one-hot ────────────────────────────────────────────────


def test_encoder_version_bumped() -> None:
    assert ENCODER_VERSION == 3


def test_effect_kind_one_hot(mid_game_adapter) -> None:
    adapter = mid_game_adapter(2)
    pid = adapter.current_player_id()
    ctx = {
        "source_card_id": "myconid_adult",
        "op": "custom_effect",
        "card_action_id": "action_1",
        "current_option_id": None,
        "awaiting_option": False,
        "optional": False,
        "option_ids": [],
        "remaining_repeats": 0,
        "allow_repeat": False,
        "effect_kind": "give_insane_outcast_to_selected_player",
    }
    start, end = OBS_LAYOUT["pending_effect_kind"]
    obs = encode_observation(adapter, pid, ctx)
    block = obs[start:end]
    assert block.sum() == 1
    assert block[effect_kind_index("give_insane_outcast_to_selected_player")] == 1

    # A non-custom op leaves the block zero even if stale metadata is present.
    ctx_op = dict(ctx, op="deploy_troops", effect_kind="give_insane_outcast_to_selected_player")
    assert encode_observation(adapter, pid, ctx_op)[start:end].sum() == 0

    # An unknown custom effect falls into the unknown slot.
    ctx_unknown = dict(ctx, effect_kind=None)
    block_unknown = encode_observation(adapter, pid, ctx_unknown)[start:end]
    assert block_unknown.sum() == 1
    assert block_unknown[effect_kind_index(None)] == 1


def test_option_beyond_block_raises(mid_game_adapter) -> None:
    """T4.3 (m3): an option past the 8-slot block raises, not clamps."""
    from openspiel_pyrants.nn.actions import UnmappedMoveError

    adapter = mid_game_adapter(2)
    pid = adapter.current_player_id()
    ctx = {
        "source_card_id": "gauth",
        "op": None,
        "card_action_id": None,
        "current_option_id": "option_9",
        "awaiting_option": True,
        "optional": False,
        "option_ids": [f"option_{i}" for i in range(1, 10)],
        "remaining_repeats": 0,
        "allow_repeat": False,
        "effect_kind": None,
    }
    with pytest.raises(UnmappedMoveError, match="option position 8"):
        encode_observation(adapter, pid, ctx)


# ── T4.1 controller is a strict majority ───────────────────────────────────


def test_controller_is_strict_majority() -> None:
    order = ("me", "o1", "o2", "o3")

    def controller(slots):
        return node_features(slots, (), len(slots), order, ())["controller"]

    assert controller(("me", "me", "o1", "white")) == [1, 0, 0, 0, 0]
    assert controller(("me", "o1")) == [0, 0, 0, 0, 0]
    assert controller(("white", "white")) == [0, 0, 0, 0, 1]
    assert controller(("o1", "o1", "o1", "white", "white", "white")) == [0, 0, 0, 0, 0]


# ── T4.2 total control needs every space mine and no enemy spies ───────────


def test_total_control_requires_no_enemy_spies() -> None:
    order = ("me", "o1")
    assert node_features(("me", "me"), (), 2, order, ())["total_control"] == 1
    assert node_features(("me", "me"), ("o1",), 2, order, ())["total_control"] == 0
    assert node_features(("me", None), (), 2, order, ())["total_control"] == 0
    # My own spy does not block my total control.
    assert node_features(("me", "me"), ("me",), 2, order, ())["total_control"] == 1


# ── T4.3 presence follows the rulebook ─────────────────────────────────────


def test_presence_follows_rulebook() -> None:
    order = ("me", "o1")
    board = {
        "site_x": {"slots": (), "spies": (), "neighbors": ["route_a", "route_b"]},
        "route_a": {"slots": ("me",), "spies": (), "neighbors": ["site_x"]},
        "route_b": {"slots": (), "spies": (), "neighbors": ["site_x"]},
    }

    def presence(node_id):
        node = board[node_id]
        adjacent = [board[n]["slots"] for n in node["neighbors"]]
        return node_features(
            node["slots"], node["spies"], len(node["slots"]), order, adjacent
        )["presence"]

    assert presence("site_x") == 1  # my troop on an adjacent route
    assert presence("route_a") == 1  # my troop in this space
    assert presence("route_b") == 0  # nothing nearby

    # My spy at the site is presence, even with no troops anywhere.
    assert node_features((), ("me",), 0, order, ((), ()))["presence"] == 1
    assert node_features((), (), 0, order, ((), ()))["presence"] == 0


# ── T4.4 presence agrees with the engine's deploy targets ──────────────────


def _census_game_dirs(limit: int):
    root = ROOT / "artifacts" / "ismcts"
    if not root.exists():
        return []
    dirs = [
        p.parent
        for p in sorted(root.rglob("replay.json"))
        if (p.parent / "decisions.jsonl").exists()
    ]
    return dirs[:limit] if limit else dirs


@pytest.mark.skipif(not _census_game_dirs(1), reason="no stored replay artifacts")
def test_presence_agrees_with_engine_deploy_targets(requires_c_engine) -> None:
    from engine_c.bindings.c_adapter import CEngineAdapter
    from engine_c.bindings.ce_api import CEngine
    from interface.replay_loader import engine_seed, load_replay
    from openspiel_pyrants.state_c import _indexed_moves

    root = ROOT / "artifacts" / "ismcts"
    dirs = [
        p.parent
        for p in sorted(root.rglob("replay.json"))
        if (p.parent / "decisions.jsonl").exists()
    ][:3]
    assert dirs

    for game_dir in dirs:
        bundle = load_replay(game_dir)
        engine = CEngine()
        engine.initialize(
            catalog_path=str(bundle.card_path),
            board_path=str(bundle.board_path),
            setup_path=str(bundle.setup_path),
            setup_data_json=bundle.setup_json,
        )
        player_ids = list(bundle.meta.player_ids)
        seed = engine_seed(bundle.meta.shuffle_seed)
        adapter = CEngineAdapter(engine.create_game(player_ids, seed), engine, player_ids, seed)
        try:
            log = [
                e
                for e in bundle.replay.get("replay_log", ())
                if e.get("payload", {}).get("move_type") != "__terminal__"
            ]
            for entry in log:
                if adapter.pending_generic_op() is not None:
                    pass
                else:
                    cp = adapter.state.current_player_id
                    order = tuple(seat_order(adapter, cp))
                    nodes = json.loads(adapter.private_view_json(cp))["public"]["board_nodes"]
                    troops = {
                        n["node_id"]: tuple(n.get("troop_slots", ())) for n in nodes
                    }
                    spies = {n["node_id"]: tuple(n.get("spies", ())) for n in nodes}
                    for _idx, move in _indexed_moves(adapter):
                        payload = move.to_payload()
                        if payload.get("move_type") != "deploy":
                            continue
                        target = payload.get("target_node_id")
                        if not target:
                            continue
                        adjacent = [
                            troops[neighbor]
                            for neighbor in NODE_ADJACENT.get(target, ())
                            if neighbor in troops
                        ]
                        presence = node_features(
                            troops[target],
                            spies.get(target, ()),
                            len(troops[target]),
                            order,
                            adjacent,
                        )["presence"]
                        assert presence == 1, (game_dir, entry.get("step_index"), target)
                payload = entry["payload"]
                match = next((m for m in adapter.legal_moves() if m.to_payload() == payload), None)
                assert match is not None
                adapter.apply(match)
        finally:
            adapter.destroy()
