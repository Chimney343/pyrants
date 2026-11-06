"""T3.1-T3.6 — global action encoding (v2).

Phase 3 of ``docs/nn-training-data-fix-plan.md``. The v1 encoder keyed several
``resolve_generic`` shapes on a positional fallback, so rulebook-distinct moves
shared one slot (F-026). v2 routes troop/spy targets into the existing
``assassinate`` / ``return_spy`` blocks and rebuilds ``resolve_generic`` on the
rulebook's nouns.
"""

from __future__ import annotations

import os

import pytest

from openspiel_pyrants.nn.actions import (
    ACTION_LAYOUT,
    ACTION_SPACE_USED,
    ACTION_SPACE_VERSION,
    NUM_GLOBAL_ACTIONS,
    RESOLVE_GENERIC_LAYOUT,
    ActionContext,
    UnmappedMoveError,
    action_context,
    legal_mask,
    move_to_global_action,
)
from openspiel_pyrants.nn.index import CARD_ID_TO_INDEX, NODE_ID_TO_INDEX, OP_IDS

NODE = "site_gauntlgrym"
NODE_I = NODE_ID_TO_INDEX[NODE]
ROUTE = "route_1"
ROUTE_I = NODE_ID_TO_INDEX[ROUTE]

CTX = ActionContext(
    acting_player_id="p1",
    seat_order=("p1", "p2", "p3", "p4"),
    troop_slots_by_node={NODE: ("p2", "p2", "white"), ROUTE: ("p1",)},
)


def _start(name: str) -> int:
    return ACTION_LAYOUT[name][0]


def _rg(offset: int) -> int:
    return _start("resolve_generic") + offset


def _card(name: str) -> int:
    return CARD_ID_TO_INDEX[name]


# ── T3.1 layout partitions the space ───────────────────────────────────────


def test_action_layout_partitions_the_space() -> None:
    expected_sizes = {
        "play_card": 126,
        "recruit": 126,
        "promote": 127,
        "initial_placement": 81,
        "deploy": 82,
        "assassinate": 405,
        "return_spy": 324,
        "fixed": 5,
        "resolve_generic": 240,
    }
    starts = sorted(start for start, _ in ACTION_LAYOUT.values())
    assert starts[0] == 0
    for (start, end), nxt in zip(
        sorted(ACTION_LAYOUT.values()), starts[1:] + [ACTION_SPACE_USED], strict=False
    ):
        assert start < end
        assert end == nxt
    assert ACTION_SPACE_USED == 1516
    assert ACTION_SPACE_USED <= NUM_GLOBAL_ACTIONS
    for name, size in expected_sizes.items():
        start, end = ACTION_LAYOUT[name]
        assert end - start == size

    assert ACTION_SPACE_VERSION == 3
    sub_sizes = {name: end - start for name, (start, end) in RESOLVE_GENERIC_LAYOUT.items()}
    assert sub_sizes == {
        "option": 8,
        "decline": 1,
        "node": 81,
        "card": 126,
        "player": 4,
        "index": 20,
    }
    # Sub-blocks tile the resolve_generic block exactly.
    cursor = _start("resolve_generic")
    for name in ("option", "decline", "node", "card", "player", "index"):
        start, end = RESOLVE_GENERIC_LAYOUT[name]
        assert start == cursor
        cursor = end
    assert cursor == _start("resolve_generic") + 240


# ── T3.2 move -> global id table ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "payload", "ctx", "expected"),
    [
        (
            "play_card",
            {"move_type": "play_card", "card_id": "noble", "hand_index": 0},
            CTX,
            _start("play_card") + _card("noble"),
        ),
        (
            "recruit",
            {"move_type": "recruit", "card_id": "noble"},
            CTX,
            _start("recruit") + _card("noble"),
        ),
        (
            "promote_card",
            {"move_type": "promote_card", "card_id": "noble"},
            CTX,
            _start("promote") + _card("noble"),
        ),
        (
            "skip_promote",
            {"move_type": "skip_promote", "source_card_id": "noble"},
            CTX,
            _start("promote") + 126,
        ),
        (
            "initial_placement",
            {"move_type": "initial_placement", "target_node_id": NODE},
            CTX,
            _start("initial_placement") + NODE_I,
        ),
        (
            "deploy_null",
            {"move_type": "deploy", "target_node_id": None, "troop_count": 1},
            CTX,
            _start("deploy") + 81,
        ),
        (
            "deploy_node",
            {"move_type": "deploy", "target_node_id": NODE, "troop_count": 1},
            CTX,
            _start("deploy") + NODE_I,
        ),
        (
            "assassinate_opp1",
            {"move_type": "assassinate", "target_node_id": NODE, "target_slot_index": 1},
            CTX,
            _start("assassinate") + NODE_I * 5 + 1,
        ),
        (
            "assassinate_white",
            {"move_type": "assassinate", "target_node_id": NODE, "target_slot_index": 2},
            CTX,
            _start("assassinate") + NODE_I * 5 + 4,
        ),
        (
            "return_spy_opp1",
            {"move_type": "return_spy", "node_id": ROUTE, "spy_owner_id": "p2"},
            CTX,
            _start("return_spy") + ROUTE_I * 4 + 1,
        ),
        ("fixed_end_main", {"move_type": "end_main_phase"}, CTX, _start("fixed") + 0),
        ("fixed_eot", {"move_type": "resolve_end_of_turn"}, CTX, _start("fixed") + 1),
        ("fixed_cleanup", {"move_type": "resolve_cleanup"}, CTX, _start("fixed") + 2),
        (
            "fixed_activate",
            {"move_type": "activate_card_ability"},
            CTX,
            _start("fixed") + 3,
        ),
        # ── resolve_generic v2 ─────────────────────────────────────────────
        (
            "rg_option_2_by_position",
            {"move_type": "resolve_generic_choice", "action_id": "option_2", "target_id": None},
            ActionContext("p1", ("p1", "p2"), {}, None, option_ids=("option_1", "option_2")),
            _rg(1),
        ),
        (
            "rg_option_named_by_position",
            {
                "move_type": "resolve_generic_choice",
                "action_id": "promote_end_of_turn",
                "target_id": None,
            },
            ActionContext(
                "p1", ("p1", "p2"), {}, None,
                option_ids=("gain_influence", "promote_end_of_turn"),
            ),
            _rg(1),
        ),
        (
            "rg_decline",
            {"move_type": "resolve_generic_choice", "action_id": None, "target_id": None},
            ActionContext("p1", ("p1", "p2"), {}, "devour_cost"),
            _rg(8),
        ),
        (
            "rg_node_deploy",
            {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": None},
            ActionContext("p1", ("p1", "p2"), {}, "deploy_troops"),
            _rg(9 + NODE_I),
        ),
        (
            "rg_node_place_spy_single",
            {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": None},
            ActionContext("p1", ("p1", "p2"), {}, "place_spy"),
            _rg(9 + NODE_I),
        ),
        (
            "rg_node_place_spy_pair",
            {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": ROUTE},
            ActionContext("p1", ("p1", "p2"), {}, "place_spy"),
            _rg(9 + NODE_I),
        ),
        (
            "rg_node_move_troop_destination",
            {
                "move_type": "resolve_generic_choice",
                "action_id": ROUTE,
                "target_id": f"0:{NODE}:1",
            },
            ActionContext("p1", ("p1", "p2"), {}, "move_troop"),
            _rg(9 + NODE_I),
        ),
        (
            "rg_node_return_spy",
            {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": None},
            ActionContext("p1", ("p1", "p2"), {}, "return_spy"),
            _rg(9 + NODE_I),
        ),
        (
            "rg_troop_assassinate",
            {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": "1"},
            ActionContext("p1", ("p1", "p2"), {NODE: ("p2", "p2", "white")}, "assassinate_troop"),
            _start("assassinate") + NODE_I * 5 + 1,
        ),
        (
            "rg_troop_supplant",
            {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": "0"},
            ActionContext(
                "p1", ("p1", "p2", "p3", "p4"), {NODE: ("p2", "p2", "white")}, "supplant_troop"
            ),
            _start("assassinate") + NODE_I * 5 + 1,
        ),
        (
            "rg_return_unit_troop",
            {"move_type": "resolve_generic_choice", "action_id": ROUTE, "target_id": "troop:0"},
            ActionContext("p1", ("p1", "p2"), {ROUTE: ("p2",)}, "return_unit"),
            _start("assassinate") + ROUTE_I * 5 + 1,
        ),
        (
            "rg_return_unit_spy",
            {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": "spy:p2"},
            ActionContext("p1", ("p1", "p2"), {}, "return_unit"),
            _start("return_spy") + NODE_I * 4 + 1,
        ),
        (
            "rg_card_recruit",
            {"move_type": "resolve_generic_choice", "action_id": "noble", "target_id": None},
            ActionContext("p1", ("p1", "p2"), {}, "recruit_card"),
            _rg(90 + _card("noble")),
        ),
        (
            "rg_card_devour_cost",
            {"move_type": "resolve_generic_choice", "action_id": "noble", "target_id": None},
            ActionContext("p1", ("p1", "p2"), {}, "devour_cost"),
            _rg(90 + _card("noble")),
        ),
        (
            "rg_custom_effect_card_pile_index",
            {"move_type": "resolve_generic_choice", "action_id": "noble", "target_id": "0"},
            ActionContext("p1", ("p1", "p2"), {}, "custom_effect"),
            _rg(90 + _card("noble")),
        ),
        (
            "rg_custom_effect_player",
            {"move_type": "resolve_generic_choice", "action_id": "p2", "target_id": None},
            ActionContext("p1", ("p1", "p2"), {}, "custom_effect"),
            _rg(216 + 1),
        ),
        (
            "rg_custom_effect_select_trophy_hall",
            {"move_type": "resolve_generic_choice", "action_id": "p1", "target_id": "0"},
            ActionContext(
                "p1",
                ("p1", "p2"),
                {},
                "custom_effect",
                effect_kind="select_trophy_hall",
                trophy_halls={"p1": ("p2",), "p2": ("white",)},
            ),
            _rg(220 + (0 * 5 + 1)),
        ),
        (
            "rg_custom_effect_node",
            {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": None},
            ActionContext("p1", ("p1", "p2"), {}, "custom_effect"),
            _rg(9 + NODE_I),
        ),
        (
            "rg_custom_effect_structured_white_trophy",
            {
                "move_type": "resolve_generic_choice",
                "action_id": NODE,
                "target_id": "p1:0:site_gauntlgrym:2",
                "selection_index": 0,
            },
            ActionContext(
                "p1", ("p1", "p2"), {}, "custom_effect",
                effect_kind="steal_white_trophy_to_board",
                trophy_halls={"p1": ("white",)},
            ),
            _start("assassinate") + NODE_I * 5 + 4,
        ),
        (
            "rg_custom_effect_structured_placement",
            {
                "move_type": "resolve_generic_choice",
                "action_id": NODE,
                "target_id": "p1:0:site_gauntlgrym:2",
                "selection_index": 0,
            },
            ActionContext(
                "p1", ("p1", "p2"), {}, "custom_effect",
                effect_kind="deploy_from_trophy_hall",
                trophy_halls={"p1": ("p2",)},
            ),
            _start("assassinate") + NODE_I * 5 + 1,
        ),
        (
            "rg_custom_effect_structured_steal_selected",
            {
                "move_type": "resolve_generic_choice",
                "action_id": NODE,
                "target_id": "p1:0:site_gauntlgrym:2",
                "selection_index": 0,
            },
            ActionContext(
                "p1", ("p1", "p2"), {}, "custom_effect",
                effect_kind="steal_from_selected_trophy",
                trophy_halls={"p1": ("white",)},
            ),
            _start("assassinate") + NODE_I * 5 + 4,
        ),
        (
            "rg_force_discard_player",
            {"move_type": "resolve_generic_choice", "action_id": "p2", "target_id": None},
            ActionContext("p1", ("p1", "p2", "p3", "p4"), {}, "force_discard"),
            _rg(216 + 1),
        ),
        (
            "rg_force_discard_card",
            {"move_type": "resolve_generic_choice", "action_id": "noble", "target_id": None},
            ActionContext("p1", ("p1", "p2"), {}, "force_discard"),
            _rg(90 + _card("noble")),
        ),
        (
            "rg_promote_hand_index",
            {"move_type": "resolve_generic_choice", "action_id": "0", "target_id": "hand"},
            ActionContext("p1", ("p1", "p2"), {}, "promote_card", my_hand=("noble", "gauth")),
            _rg(90 + _card("noble")),
        ),
        (
            "rg_promote_discard_index",
            {"move_type": "resolve_generic_choice", "action_id": "1", "target_id": "discard"},
            ActionContext("p1", ("p1", "p2"), {}, "promote_card", my_discard=("gauth", "noble")),
            _rg(90 + _card("noble")),
        ),
        (
            "rg_promote_played_card",
            {"move_type": "resolve_generic_choice", "action_id": "noble", "target_id": "played"},
            ActionContext("p1", ("p1", "p2"), {}, "promote_card"),
            _rg(90 + _card("noble")),
        ),
    ],
)
def test_move_to_global_action_table(label, payload, ctx, expected) -> None:
    assert move_to_global_action(payload, ctx) == expected, label


# ── T3.3 duplicate-equivalent moves merge ──────────────────────────────────


def test_duplicate_equivalent_moves_merge() -> None:
    a = {"move_type": "play_card", "card_id": "noble", "hand_index": 0}
    b = {"move_type": "play_card", "card_id": "noble", "hand_index": 3}
    assert move_to_global_action(a, CTX) == move_to_global_action(b, CTX)

    s0 = {"move_type": "assassinate", "target_node_id": NODE, "target_slot_index": 0}
    s1 = {"move_type": "assassinate", "target_node_id": NODE, "target_slot_index": 1}
    s2 = {"move_type": "assassinate", "target_node_id": NODE, "target_slot_index": 2}
    assert move_to_global_action(s0, CTX) == move_to_global_action(s1, CTX)
    assert move_to_global_action(s0, CTX) != move_to_global_action(s2, CTX)

    # Two troop slot indices with the same owner merge; different owners do not.
    troop_ctx = ActionContext("p1", ("p1", "p2"), {NODE: ("p2", "p2", "white")}, "assassinate_troop")
    troop0 = {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": "0"}
    troop1 = {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": "1"}
    troop2 = {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": "2"}
    assert move_to_global_action(troop0, troop_ctx) == move_to_global_action(troop1, troop_ctx)
    assert move_to_global_action(troop0, troop_ctx) != move_to_global_action(troop2, troop_ctx)

    # troop vs spy at one site and owner differ.
    unit_troop = {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": "troop:0"}
    unit_spy = {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": "spy:p2"}
    gctx = ActionContext("p1", ("p1", "p2"), {NODE: ("p2",)}, "return_unit")
    assert move_to_global_action(unit_troop, gctx) != move_to_global_action(unit_spy, gctx)

    # Two copies of one card merge; two sources to one move destination merge.
    c0 = {"move_type": "resolve_generic_choice", "action_id": "noble", "target_id": None}
    assert move_to_global_action(c0, ActionContext("p1", ("p1", "p2"), {}, "recruit_card")) == (
        move_to_global_action(c0, ActionContext("p1", ("p1", "p2"), {}, "recruit_card"))
    )
    mv_a = {"move_type": "resolve_generic_choice", "action_id": ROUTE, "target_id": f"0:{NODE}:1"}
    mv_b = {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": f"0:{NODE}:1"}
    mctx = ActionContext("p1", ("p1", "p2"), {}, "move_troop")
    assert move_to_global_action(mv_a, mctx) == move_to_global_action(mv_b, mctx)


def test_select_trophy_hall_keys_on_colour() -> None:
    """Distinct trophy colours stay apart; same-colour hall indices merge."""
    ctx = ActionContext(
        "p1",
        ("p1", "p2", "p3"),
        {},
        "custom_effect",
        effect_kind="select_trophy_hall",
        trophy_halls={"p1": ("p2", "white", "p2")},
    )

    def gid(index: int) -> int:
        return move_to_global_action(
            {"move_type": "resolve_generic_choice", "action_id": "p1", "target_id": str(index)},
            ctx,
        )

    assert gid(0) == gid(2)  # both a p2 trophy
    assert gid(0) != gid(1)  # white trophy is a distinct choice


# ── T3.1/T3.2 structured trophy placement (R-2) ────────────────────────────


def test_structured_placement_keys_on_trophy_colour() -> None:
    """T3.1 (R-2): a structured target keys on the trophy's colour, not its
    physical hall slot; same-colour indices and same-node slots merge."""
    ctx = ActionContext(
        "p1",
        ("p1", "p2", "p3", "p4"),
        {},
        "custom_effect",
        effect_kind="deploy_from_trophy_hall",
        trophy_halls={"p2": ("white", "p3", "p3")},
    )

    def gid(target: str) -> int:
        return move_to_global_action(
            {"move_type": "resolve_generic_choice", "action_id": NODE, "target_id": target},
            ctx,
        )

    white = gid(f"p2:0:{NODE}:0")
    p3_a = gid(f"p2:1:{NODE}:0")
    p3_b = gid(f"p2:1:{NODE}:3")  # same trophy, another empty slot -> merge
    p3_other = gid(f"p2:2:{NODE}:0")  # same colour, different trophy idx -> merge

    assert white == _start("assassinate") + NODE_I * 5 + 4
    assert p3_a == _start("assassinate") + NODE_I * 5 + 2
    assert white != p3_a
    assert p3_b == p3_a
    assert p3_other == p3_a


def test_structured_placement_unmapped_raises() -> None:
    """T3.2 (R-2): malformed, out-of-range and out-of-game trophy references
    raise ``UnmappedMoveError`` naming the op and shape."""
    ctx = ActionContext(
        "p1",
        ("p1", "p2"),
        {},
        "custom_effect",
        effect_kind="deploy_from_trophy_hall",
        trophy_halls={"p1": ("white",), "p2": ("p1",)},
    )
    for target in (
        f"p1:5:{NODE}:0",  # trophy index past the hall
        f"p9:0:{NODE}:0",  # source is not a player with a hall
        f"p1:x:{NODE}:0",  # non-numeric trophy index
        "p1:0:site_gauntlgrym",  # malformed (3 parts)
    ):
        with pytest.raises(UnmappedMoveError) as excinfo:
            move_to_global_action(
                {
                    "move_type": "resolve_generic_choice",
                    "action_id": NODE,
                    "target_id": target,
                },
                ctx,
            )
        assert "custom_effect" in str(excinfo.value)
        assert "structured" in str(excinfo.value)

    # A colour that is neither a seat nor white (p3 in a 2-player game) is
    # illegal: "a 2-player game simply cannot allow a p3 slot".
    illegal = ActionContext(
        "p1",
        ("p1", "p2"),
        {},
        "custom_effect",
        effect_kind="deploy_from_trophy_hall",
        trophy_halls={"p2": ("p3",)},
    )
    with pytest.raises(UnmappedMoveError, match="structured"):
        move_to_global_action(
            {
                "move_type": "resolve_generic_choice",
                "action_id": NODE,
                "target_id": f"p2:0:{NODE}:0",
            },
            illegal,
        )


def test_option_beyond_block_raises() -> None:
    """T4.3 (m3): an option past the 8-slot block raises, not clamps."""
    option_ids = tuple(f"option_{i}" for i in range(1, 10))
    ctx = ActionContext("p1", ("p1", "p2"), {}, None, option_ids=option_ids)
    assert move_to_global_action(
        {"move_type": "resolve_generic_choice", "action_id": "option_8", "target_id": None},
        ctx,
    ) == _rg(7)
    with pytest.raises(UnmappedMoveError, match="option position 8"):
        move_to_global_action(
            {"move_type": "resolve_generic_choice", "action_id": "option_9", "target_id": None},
            ctx,
        )


# ── T3.4 unmapped moves raise ──────────────────────────────────────────────


def test_unmapped_move_raises() -> None:
    with pytest.raises(UnmappedMoveError):
        move_to_global_action({"move_type": "play_card", "card_id": "not_a_card"}, CTX)
    with pytest.raises(UnmappedMoveError):
        move_to_global_action({"move_type": "deploy", "target_node_id": "not_a_node"}, CTX)
    with pytest.raises(UnmappedMoveError):
        move_to_global_action(
            {
                "move_type": "resolve_generic_choice",
                "action_id": "not_a_node",
                "target_id": None,
            },
            ActionContext("p1", ("p1", "p2"), {}, "deploy_troops"),
        )
    with pytest.raises(UnmappedMoveError) as excinfo:
        move_to_global_action(
            {
                "move_type": "resolve_generic_choice",
                "action_id": "not_a_card",
                "target_id": None,
            },
            ActionContext("p1", ("p1", "p2"), {}, "custom_effect"),
        )
    assert "custom_effect" in str(excinfo.value)
    assert "unknown" in str(excinfo.value)

    with pytest.raises(UnmappedMoveError):
        move_to_global_action(
            {"move_type": "resolve_generic_choice", "action_id": "option_2", "target_id": None},
            ActionContext("p1", ("p1", "p2"), {}, None, option_ids=("option_1",)),
        )


# ── T3.5 census over stored replays ────────────────────────────────────────


def _census_game_dirs(limit: int):
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "artifacts" / "ismcts"
    if not root.exists():
        return []
    dirs = []
    for replay_path in sorted(root.rglob("replay.json")):
        game_dir = replay_path.parent
        if (game_dir / "decisions.jsonl").exists():
            dirs.append(game_dir)
    return dirs[:limit] if limit else dirs


def _troop_owner(node_id, slot_index, ctx):
    slots = ctx.troop_slots_by_node.get(node_id or "", ())
    idx = int(slot_index)
    return slots[idx] if 0 <= idx < len(slots) else None


def _pair_info(payload, ctx):
    """(kind, destination, source) for a factored pair move, else ``None``."""
    op = ctx.pending_op
    if op == "move_troop":
        target = payload.get("target_id") or ""
        if target.count(":") < 2:
            return None
        src_slot, dst, _dst_slot = target.split(":", 2)
        return ("move_troop", dst, f"{payload.get('action_id')}:{src_slot}")
    if op == "place_spy" and payload.get("target_id"):
        return ("place_spy", payload.get("action_id"), payload.get("target_id"))
    return None


def _structured_trophy_colour(target_id, ctx):
    """Colour of the trophy a structured ``<sp>:<idx>:<node>:<slot>`` names.

    Derived from the live context's trophy halls, *not* from the encoder's
    routing, so the census can disagree with the encoder and fail (R-2b).
    """
    if not isinstance(target_id, str):
        return None
    parts = target_id.split(":")
    if len(parts) != 4:
        return None
    source, idx_str = parts[0], parts[1]
    if not idx_str.isdigit():
        return None
    hall = ctx.trophy_halls.get(source, ())
    idx = int(idx_str)
    return hall[idx] if 0 <= idx < len(hall) else None


def _semantic_key(payload, ctx):
    """The test's own notion of the move's rulebook identity."""
    move_type = payload.get("move_type")
    if move_type != "resolve_generic_choice":
        if move_type == "play_card":
            return ("play_card", payload.get("card_id"))
        if move_type == "recruit":
            return ("recruit", payload.get("card_id"))
        if move_type == "promote_card":
            return ("promote", payload.get("card_id"))
        if move_type == "skip_promote":
            return ("skip_promote",)
        if move_type == "initial_placement":
            return ("initial_placement", payload.get("target_node_id"))
        if move_type == "deploy":
            return ("deploy", payload.get("target_node_id"))
        if move_type == "assassinate":
            owner = _troop_owner(
                payload.get("target_node_id"), payload.get("target_slot_index"), ctx
            )
            return ("troop", payload.get("target_node_id"), owner)
        if move_type == "return_spy":
            return ("return_spy", payload.get("node_id"), payload.get("spy_owner_id"))
        if move_type in ("end_main_phase", "resolve_end_of_turn", "resolve_cleanup",
                         "activate_card_ability", "activate_ability",
                         "decline_card_ability", "decline_ability"):
            return (move_type,)
        return (move_type,)

    op = ctx.pending_op
    action_id = payload.get("action_id")
    target_id = payload.get("target_id")
    if action_id is None and target_id is None:
        return ("decline",)
    if op is None:
        return ("option", ctx.option_ids.index(action_id))
    if op in ("assassinate_troop", "supplant_troop"):
        return ("troop", action_id, _troop_owner(action_id, target_id, ctx))
    if op == "return_unit":
        if isinstance(target_id, str) and target_id.startswith("troop:"):
            return ("troop", action_id, _troop_owner(action_id, target_id.split(":", 1)[1], ctx))
        return ("spy", action_id, target_id.split(":", 1)[1])
    if op in ("deploy_troops", "return_spy"):
        return (op, action_id)
    if op == "place_spy":
        return ("place_spy", action_id, target_id)
    if op == "move_troop":
        return ("move_troop", action_id, target_id)
    if op in ("recruit_card", "devour", "devour_cost", "play_card"):
        return ("card", action_id)
    if op == "force_discard":
        if action_id in ctx.seat_order:
            return ("player", action_id)
        return ("card", action_id)
    if op == "promote_card":
        if target_id in ("played", "hand", "discard"):
            if target_id == "played":
                return ("card", action_id)
            source = ctx.my_hand if target_id == "hand" else ctx.my_discard
            return ("card", source[int(action_id)])
        return ("card", action_id)
    if op == "custom_effect":
        if isinstance(action_id, str) and action_id in CARD_ID_TO_INDEX:
            return ("card", action_id)
        if action_id in ctx.seat_order:
            if ctx.effect_kind in ("select_trophy_hall", "steal_white_trophy_to_board"):
                hall = ctx.trophy_halls.get(action_id, ())
                colour = (
                    hall[int(target_id)]
                    if isinstance(target_id, str)
                    and target_id.isdigit()
                    and int(target_id) < len(hall)
                    else None
                )
                return ("trophy", action_id, colour)
            return ("player", action_id, target_id)
        if isinstance(action_id, str) and action_id in NODE_ID_TO_INDEX:
            if isinstance(target_id, str) and ":" in target_id:
                # Structured trophy placement: the rulebook noun is the troop
                # colour deployed, derived independently of the encoder (R-2b).
                return ("troop", action_id, _structured_trophy_colour(target_id, ctx))
            return ("node", action_id)
    return ("other", op, action_id, target_id, payload.get("selection_index"))


_INDEX_ALLOW_LIST = frozenset({("custom_effect", "select_trophy_hall")})

# Choice-producing (op, effect_kind) branches enumerated by
# ``engine_c/selection.c`` that the census must account for (R-2b). A branch the
# stored games never reach is named in ``_UNCOVERED_BY_CENSUS`` with the
# live-engine test that covers it; a branch in neither place fails the full
# census.
_CHOICE_BRANCHES = frozenset({
    ("custom_effect", "self_purge_to_supply"),
    ("custom_effect", "steal_white_trophy_to_board"),
    ("custom_effect", "deploy_from_trophy_hall"),
    ("custom_effect", "select_trophy_hall"),
    ("custom_effect", "steal_from_selected_trophy"),
    ("custom_effect", "lich_select_target_player"),
    # selection.c:177-194 also enumerates one move per opponent for these two
    # (the review of Fix Plan 02 closed this gate gap).
    ("custom_effect", "give_insane_outcast_to_selected_player"),
    ("custom_effect", "give_insane_outcast_to_player_with_presence_on_last_selected_node"),
})

_UNCOVERED_BY_CENSUS = {
    ("custom_effect", "steal_white_trophy_to_board"): (
        "tests/nn/test_actions_live_custom_effects.py::"
        "test_steal_white_trophy_to_board_on_live_engine"
    ),
    ("custom_effect", "deploy_from_trophy_hall"): (
        "tests/nn/test_actions_live_custom_effects.py::"
        "test_lich_deploy_from_trophy_hall_maps_each_trophy"
    ),
    ("custom_effect", "select_trophy_hall"): (
        "tests/nn/test_actions_live_custom_effects.py::"
        "test_select_trophy_hall_on_live_engine"
    ),
    ("custom_effect", "steal_from_selected_trophy"): (
        "tests/nn/test_actions_live_custom_effects.py::"
        "test_steal_from_selected_trophy_on_live_engine"
    ),
    ("custom_effect", "lich_select_target_player"): (
        "tests/nn/test_actions_live_custom_effects.py::"
        "test_lich_select_target_player_on_live_engine"
    ),
}

# Checked-in expected coverage of the full (PYRANTS_NN_CENSUS=1) walk. The
# corpus is every replayable game dir under `artifacts/ismcts/`, so it grows when
# a new run is written and the counts must be re-baked deliberately. Baked
# 2026-09-11 on the post-wipe corpus: 34 dirs = the 32-game 200-sim run
# `runs/20260911T193759Z_58e54c44a5f5` + the 2-game `just ismcts-quick` run,
# all under the insane_outcast non-recruitable rule, 0 desync. Every choice
# branch the corpus never reaches is named in _UNCOVERED_BY_CENSUS; the three
# insane_outcast branches are reached again through demon-deck give effects.
_EXPECTED_BRANCH_COVERAGE: dict = {
    ("assassinate_troop", None): 650,
    ("custom_effect", "give_insane_outcast_to_player_with_presence_on_last_selected_node"): 14,
    ("custom_effect", "give_insane_outcast_to_selected_player"): 47,
    ("custom_effect", "self_purge_to_supply"): 70,
    ("deploy_troops", None): 740,
    ("devour_cost", None): 214,
    ("force_discard", None): 97,
    ("move_troop", None): 21,
    ("place_spy", None): 347,
    ("play_card", None): 1,
    ("recruit_card", None): 9,
    ("return_spy", None): 141,
    ("return_unit", None): 104,
    ("supplant_troop", None): 128,
}
_EXPECTED_SUB_BLOCK_COVERAGE: dict = {
    "assassinate": 1661,
    "deploy": 7568,
    "fixed": 35074,
    "initial_placement": 136,
    "play_card": 23231,
    "promote": 244,
    "recruit": 4921,
    "resolve_generic.card": 293,
    "resolve_generic.decline": 291,
    "resolve_generic.node": 1216,
    "resolve_generic.option": 780,
    "resolve_generic.player": 158,
    "return_spy": 421,
}


def _routing_block(gid: int) -> str:
    for name, (start, end) in ACTION_LAYOUT.items():
        if start <= gid < end:
            if name == "resolve_generic":
                for sub, (sub_start, sub_end) in RESOLVE_GENERIC_LAYOUT.items():
                    if sub_start <= gid < sub_end:
                        return f"resolve_generic.{sub}"
            return name
    return "unknown"


def _index_shape(payload, ctx):
    op = ctx.pending_op
    action_id = payload.get("action_id")
    target_id = payload.get("target_id")
    if op == "custom_effect" and ctx.effect_kind == "select_trophy_hall":
        return (op, "select_trophy_hall")
    structured = isinstance(target_id, str) and ":" in target_id
    if op == "custom_effect" and action_id in NODE_ID_TO_INDEX and structured:
        return (op, "node", "structured")
    return (op, type(action_id).__name__, type(target_id).__name__)


@pytest.mark.skipif(not _census_game_dirs(1), reason="no stored replay artifacts")
def test_every_legal_move_in_stored_replays_maps(requires_c_engine) -> None:
    from pathlib import Path

    from engine_c.bindings.c_adapter import CEngineAdapter
    from engine_c.bindings.ce_api import CEngine
    from engine_c.bindings.pending_context import read_pending_generic_context_full
    from interface.replay_loader import engine_seed, load_replay
    from openspiel_pyrants.state_c import _indexed_moves

    full = os.environ.get("PYRANTS_NN_CENSUS") == "1"
    limit = 0 if full else 3
    max_steps = 1_000_000 if full else 800

    root = Path(__file__).resolve().parents[2] / "artifacts" / "ismcts"
    dirs = [
        p.parent
        for p in sorted(root.rglob("replay.json"))
        if (p.parent / "decisions.jsonl").exists()
    ]
    if not full:
        dirs = dirs[:limit]
    assert dirs

    collisions: list = []
    bad_index: list = []
    mixed_states = 0
    pending_ops: set = set()
    non_forced_states = 0
    pair_merge_states = 0
    branch_counts: dict = {}
    sub_block_counts: dict = {}
    skipped_desync: list = []

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
        adapter = CEngineAdapter(
            engine.create_game(player_ids, seed), engine, player_ids, seed
        )
        # Per-game accumulators: a replay that desyncs mid-walk is skipped
        # whole, so its partial states never reach the coverage table. This is
        # F-022-style artifact drift (e.g. an unreleased rule change that makes a
        # recorded move illegal); the dataset builder rejects such games too.
        game_collisions: list = []
        game_bad_index: list = []
        game_mixed = 0
        game_ops: set = set()
        game_non_forced = 0
        game_pair_merge = 0
        game_branch: dict = {}
        game_sub: dict = {}
        desync = None
        try:
            log = [
                e
                for e in bundle.replay.get("replay_log", ())
                if e.get("payload", {}).get("move_type") != "__terminal__"
            ]
            for entry in log[:max_steps]:
                cp = adapter.state.current_player_id
                pending = read_pending_generic_context_full(adapter._state._ptr)
                ctx = action_context(adapter, cp, pending)
                moves = [move for _idx, move in _indexed_moves(adapter)]
                if pending and pending.get("op"):
                    game_ops.add(pending["op"])
                    # (g) coverage: states seen per (op, effect_kind).
                    branch_key = (pending["op"], pending.get("effect_kind"))
                    game_branch[branch_key] = game_branch.get(branch_key, 0) + 1
                if pending and pending.get("awaiting_option"):
                    game_ops.add("__option__")
                generic = [
                    m
                    for m in moves
                    if m.move_type in ("resolve_generic_choice", "resolve_generic")
                ]
                if generic and len(generic) != len(moves):
                    game_mixed += 1

                mapped: dict[int, list] = {}
                for move in moves:
                    payload = move.to_payload()
                    # (a) every move maps.
                    gid = move_to_global_action(payload, ctx)
                    mapped.setdefault(gid, []).append(payload)
                    # (d) index slots only on the allow-list.
                    index_start, index_end = RESOLVE_GENERIC_LAYOUT["index"]
                    if index_start <= gid < index_end:
                        shape = _index_shape(payload, ctx)
                        if shape not in _INDEX_ALLOW_LIST:
                            game_bad_index.append(
                                (game_dir, entry.get("step_index"), shape, payload)
                            )

                # (g) coverage: routing sub-blocks visited by this state.
                for block in {_routing_block(gid) for gid in mapped}:
                    game_sub[block] = game_sub.get(block, 0) + 1

                if len(moves) > 1:
                    game_non_forced += 1
                    state_pair_merge = False
                    for group in mapped.values():
                        if len(group) < 2:
                            continue
                        pairs = [_pair_info(p, ctx) for p in group]
                        if all(p is not None for p in pairs) and len(
                            {(p[0], p[1]) for p in pairs}
                        ) == 1:
                            state_pair_merge = True
                            continue
                        keys = {_semantic_key(p, ctx) for p in group}
                        if len(keys) > 1:
                            game_collisions.append(
                                (game_dir, entry.get("step_index"), group)
                            )
                    if state_pair_merge:
                        game_pair_merge += 1

                payload = entry["payload"]
                match = next(
                    (m for m in adapter.legal_moves() if m.to_payload() == payload),
                    None,
                )
                if match is None:
                    # The replay records a move the current engine refuses
                    # (artifact drift). Skip the game; do not assert alignment.
                    desync = (
                        entry.get("step_index"),
                        payload.get("move_type"),
                        payload.get("card_id"),
                    )
                    break
                adapter.apply(match)
        finally:
            adapter.destroy()

        if desync is not None:
            skipped_desync.append((game_dir, desync))
            continue

        collisions.extend(game_collisions)
        bad_index.extend(game_bad_index)
        mixed_states += game_mixed
        pending_ops |= game_ops
        non_forced_states += game_non_forced
        pair_merge_states += game_pair_merge
        for key, count in game_branch.items():
            branch_counts[key] = branch_counts.get(key, 0) + count
        for block, count in game_sub.items():
            sub_block_counts[block] = sub_block_counts.get(block, 0) + count

    print("CENSUS_CORPUS", f"dirs={len(dirs)} walked={len(dirs) - len(skipped_desync)} skipped={len(skipped_desync)}")
    print("CENSUS_SKIPPED_DESYNC", len(skipped_desync), repr(skipped_desync[:3]))
    print("CENSUS_BRANCH_COVERAGE", repr(dict(sorted(branch_counts.items()))))
    print("CENSUS_SUB_BLOCK_COVERAGE", repr(dict(sorted(sub_block_counts.items()))))
    if collisions:
        print("CENSUS_COLLISIONS", repr(collisions[:5]))
    # (b) no rulebook-distinct moves share a global id.
    assert collisions == [], f"{len(collisions)} semantic collisions; first={collisions[:2]}"
    # (d) the index sub-block is only reached through the allow-list.
    assert bad_index == [], f"non-allow-listed index shapes: {bad_index[:3]}"
    # (e) generic and non-generic moves never coexist in one state.
    assert mixed_states == 0
    # (f) every pending op is in the catalog-derived vocabulary.
    assert pending_ops - set(OP_IDS) <= {"__option__"}
    # (c) pair-move merges (destination-keyed, sources merged) stay bounded.
    # The plan's 0.2 % came from a 23-game sample (16/18,265 = 0.09 %); the full
    # 137-game census measures 227/112,339 = 0.202 %, so the heuristic bound here
    # is 0.25 %.
    if non_forced_states:
        frac = pair_merge_states / non_forced_states
        assert frac <= 0.0025, (pair_merge_states, non_forced_states, frac)

    # (g) coverage is reported always, and asserted against the checked-in
    # table on the full walk. A branch neither visited nor named in
    # _UNCOVERED_BY_CENSUS fails: a gate that cannot say which branches it saw
    # is not a gate (R-2b).
    if full:
        covered = {key for key in _CHOICE_BRANCHES if key in branch_counts}
        listed = set(_UNCOVERED_BY_CENSUS)
        assert covered & listed == set(), covered & listed
        assert covered | listed == _CHOICE_BRANCHES, _CHOICE_BRANCHES - (covered | listed)
        assert branch_counts == _EXPECTED_BRANCH_COVERAGE, "branch coverage drifted"
        assert sub_block_counts == _EXPECTED_SUB_BLOCK_COVERAGE, "sub-block coverage drifted"


# ── legal_mask ─────────────────────────────────────────────────────────────


def test_legal_mask_true_exactly_on_mapped_ids() -> None:
    payloads = [
        {"move_type": "play_card", "card_id": "noble", "hand_index": 0},
        {"move_type": "end_main_phase"},
    ]
    mask = legal_mask(payloads, CTX)
    assert mask.shape == (NUM_GLOBAL_ACTIONS,)
    assert set(mask.nonzero()[0].tolist()) == {
        move_to_global_action(p, CTX) for p in payloads
    }
