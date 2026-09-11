"""T3.3-T3.6 — live-engine coverage for the four trophy effect kinds.

Phase 3 of ``docs/nn-training-data-fix-plan-02.md``. ``tests/nn/test_actions.py``
covers the routing in isolation; these tests drive the *real* engine to the four
``custom_effect`` branches the 139-game census never reaches (R-2b), so a wrong
reading of the engine's payload shape fails here instead of hiding behind a
hand-built ``ActionContext``.

A trophy colour that is neither a current seat nor ``white`` is illegal for the
game (a 2-player game cannot hold a ``p3`` trophy); the live Lich test uses
``white`` plus a real seat colour, and ``tests/nn/test_actions.py`` pins the
raise for the illegal case.
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.c_adapter import CEngineAdapter
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.pending_context import read_pending_generic_context_full
from engine_c.bindings.session import CSession
from openspiel_pyrants.action_encoding_c import compute_c_action_map
from openspiel_pyrants.nn.actions import (
    ACTION_LAYOUT,
    RESOLVE_GENERIC_LAYOUT,
    action_context,
    move_to_global_action,
    owner_slot,
)
from openspiel_pyrants.nn.index import NODE_ID_TO_INDEX
from tests.c_engine.card_test_helpers import _make_engine, make_card_test_session
from tests.c_engine.test_card_gibbering_mouther import (
    SCENARIO_PATH as GIBBERING_SCENARIO,
)
from tests.c_engine.test_card_gibbering_mouther import (
    _add_player_to_site,
    _count_empty_slots,
)
from tests.c_engine.test_card_gibbering_mouther import (
    _play_card as _play_gibbering,
)
from tests.c_engine.test_card_lich import (
    _SITE_A,
    _SITE_B,
    _place_spy_at,
    _play_card,
    _resolve_generics_by_action,
    _set_trophy_hall,
)

ROOT = Path(__file__).resolve().parents[2]
ORCUS_SCENARIO = (
    ROOT / "data" / "scenarios" / "batch_card_generation" / "037_seed_4_orcus.json"
)


def _adapter(session: CSession) -> CEngineAdapter:
    # ``CSession.load`` leaves ``_player_ids`` empty; read the engine's own
    # order from the state so the adapter's rotation matches the engine.
    state = session._state._ptr.contents
    player_ids = [
        _lib.intern_str(state.player_ids[i]).decode() for i in range(state.player_count)
    ]
    return CEngineAdapter(session._state, session._engine, player_ids, session._seed)


def _pending_ctx(adapter: CEngineAdapter):
    cp = adapter.state.current_player_id
    pending = read_pending_generic_context_full(adapter._state._ptr)
    return pending, action_context(adapter, cp, pending)


def _moves(adapter: CEngineAdapter):
    return [move for _idx, move in compute_c_action_map(adapter)]


def _start(name: str) -> int:
    return ACTION_LAYOUT[name][0]


def _split_structured(target_id: str) -> tuple[str, int, str, int]:
    source, idx, node, slot = target_id.split(":")
    return source, int(idx), node, int(slot)


def _orcus_to_select_state() -> CSession:
    session = CSession.load(str(ORCUS_SCENARIO))
    for move in session.legal_moves():
        if move.move_type == "play_card" and move.data.get("card_id") == "orcus":
            session.submit_move(move)
            break
    else:
        session.destroy()
        raise AssertionError("orcus is not playable in the scenario")

    devour = [
        m
        for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("action_id") == "soldier"
    ]
    assert devour, "no devour target"
    session.submit_move(devour[0])
    session.submit_move(session.legal_moves()[0])  # assassinate 1
    session.submit_move(session.legal_moves()[0])  # assassinate 2
    return session


# ── self_purge_to_supply (Insane Outcast) ──────────────────────────────────


def test_self_purge_to_supply_on_live_engine(requires_c_engine) -> None:
    """Live coverage for ``self_purge_to_supply`` (Insane Outcast): each hand
    card offered maps into the ``card`` sub-block, and distinct cards stay
    apart. The 139-game census lost this branch when the unreleased
    non-recruitable rule change stranded the games that reached it."""
    session = make_card_test_session(
        _make_engine(),
        ["p1", "p2"],
        hand={"p1": ["insane_outcast", "noble", "gauth"]},
        current_player="p1",
    )
    _play_card(session, "insane_outcast")

    adapter = _adapter(session)
    try:
        pending, ctx = _pending_ctx(adapter)
        assert pending["op"] == "custom_effect"
        assert pending["effect_kind"] == "self_purge_to_supply"

        card_start, card_end = RESOLVE_GENERIC_LAYOUT["card"]
        seen: dict[int, str] = {}
        for move in _moves(adapter):
            payload = move.to_payload()
            gid = move_to_global_action(payload, ctx)
            assert card_start <= gid < card_end, (gid, payload)
            seen[gid] = payload["action_id"]
        assert set(seen.values()) == {"noble", "gauth"}
        assert len(seen) == 2
    finally:
        session.destroy()


# ── give_insane_outcast_* player selection ─────────────────────────────────


def _assert_player_block_routing(adapter, expected_effect_kind: str) -> set[str]:
    pending, ctx = _pending_ctx(adapter)
    assert pending["effect_kind"] == expected_effect_kind
    base = _start("resolve_generic")
    player_off = RESOLVE_GENERIC_LAYOUT["player"][0] - base
    seen: dict[int, str] = {}
    for move in _moves(adapter):
        payload = move.to_payload()
        candidate = payload["action_id"]
        if candidate is None and payload.get("target_id") is None:
            continue  # decline / skip
        gid = move_to_global_action(payload, ctx)
        assert gid == base + player_off + owner_slot(
            candidate, ctx.seat_order, allow_white=False
        ), (candidate, gid)
        seen[gid] = candidate
    assert len(seen) == len(set(seen.values()))
    return set(seen.values())


def test_give_insane_outcast_to_selected_player_on_live_engine(requires_c_engine) -> None:
    """``myconid_adult`` offers one ``player`` sub-block slot per opponent."""
    session = make_card_test_session(
        _make_engine(),
        ["p1", "p2", "p3"],
        hand={"p1": ["myconid_adult"]},
        current_player="p1",
    )
    _play_card(session, "myconid_adult")
    adapter = _adapter(session)
    try:
        candidates = _assert_player_block_routing(
            adapter, "give_insane_outcast_to_selected_player"
        )
        assert candidates == {"p2", "p3"}
    finally:
        session.destroy()


def test_give_insane_outcast_presence_on_last_selected_on_live_engine(
    requires_c_engine,
) -> None:
    """``gibbering_mouther`` offers one ``player`` slot per opponent with
    presence on the last selected node."""
    session = CSession.load(str(GIBBERING_SCENARIO))
    _play_gibbering(session)

    first = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert first, "no first deploy move"
    session.submit_move(first[0])

    second = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    chosen = next(
        (
            m
            for m in second
            if m.data.get("action_id")
            and _count_empty_slots(session, m.data["action_id"]) >= 2
        ),
        None,
    )
    assert chosen is not None, "no second deploy to a site with >=2 empty slots"
    _add_player_to_site(session, chosen.data["action_id"], "p1")
    session.submit_move(chosen)

    adapter = _adapter(session)
    try:
        candidates = _assert_player_block_routing(
            adapter,
            "give_insane_outcast_to_player_with_presence_on_last_selected_node",
        )
        assert "p1" in candidates
    finally:
        session.destroy()


# ── T3.3 deploy_from_trophy_hall (Lich) ────────────────────────────────────

def test_lich_deploy_from_trophy_hall_maps_each_trophy(requires_c_engine) -> None:
    """Every trophy index gets its own colour-keyed slot; no gid merges two
    different trophies. The gid count doubles from the collapsed v2 count."""
    session = make_card_test_session(
        _make_engine(),
        ["p1", "p2"],
        hand={"p1": ["lich"]},
        troops={
            "p2": {_SITE_A: ["p2", "p2", "p2", "p2"]},
            "empty": {_SITE_B: [None, None, None, None]},
        },
        current_player="p1",
    )
    # Legal 2-player hall: p2 holds a white trophy and a p1 trophy.
    _set_trophy_hall(session, "p2", ["white", "p1"])
    _play_card(session, "lich")
    _place_spy_at(session, _SITE_A)
    target_moves = _resolve_generics_by_action(session, "p2")
    assert target_moves, "expected lich_select_target_player moves"
    session.submit_move(target_moves[0])

    adapter = _adapter(session)
    try:
        pending, ctx = _pending_ctx(adapter)
        assert pending["effect_kind"] == "deploy_from_trophy_hall"

        moves = _moves(adapter)
        assert moves
        grouped: dict[int, set] = {}
        nodes = set()
        colours = set()
        for move in moves:
            payload = move.to_payload()
            gid = move_to_global_action(payload, ctx)
            source, idx, node, _slot = _split_structured(payload["target_id"])
            colour = ctx.trophy_halls[source][idx]
            grouped.setdefault(gid, set()).add(colour)
            nodes.add(node)
            colours.add(colour)
        # No gid group merges differently-coloured trophies.
        assert all(len(group) == 1 for group in grouped.values()), grouped
        assert colours == {"white", "p1"}
        # One slot per (deployable site, colour): the gid count is 2x the
        # collapsed v2 count (23 deployable sites -> 46).
        assert len(grouped) == 2 * len(nodes)
        assert len(nodes) == 23
        assert len(grouped) == 46
    finally:
        session.destroy()


# ── T3.6 lich_select_target_player (Lich) ──────────────────────────────────


def test_lich_select_target_player_on_live_engine(requires_c_engine) -> None:
    """Each candidate enemy maps to a distinct ``player`` slot."""
    session = make_card_test_session(
        _make_engine(),
        ["p1", "p2", "p3"],
        hand={"p1": ["lich"]},
        troops={
            "p2": {_SITE_A: ["p2", "p3", None, None]},
            "empty": {_SITE_B: [None, None, None, None]},
        },
        current_player="p1",
    )
    _set_trophy_hall(session, "p2", ["white"])
    _play_card(session, "lich")
    _place_spy_at(session, _SITE_A)

    adapter = _adapter(session)
    try:
        pending, ctx = _pending_ctx(adapter)
        assert pending["effect_kind"] == "lich_select_target_player"

        base = _start("resolve_generic")
        player_off = RESOLVE_GENERIC_LAYOUT["player"][0] - base
        seen: dict[int, str] = {}
        for move in _moves(adapter):
            payload = move.to_payload()
            gid = move_to_global_action(payload, ctx)
            candidate = payload["action_id"]
            expected = base + player_off + owner_slot(
                candidate, ctx.seat_order, allow_white=False
            )
            assert gid == expected, (candidate, gid, expected)
            seen[gid] = candidate
        assert set(seen.values()) == {"p2", "p3"}
        assert len(seen) == 2  # distinct slot per candidate
    finally:
        session.destroy()


# ── T3.4 select_trophy_hall / T3.5 steal_from_selected_trophy (Orcus) ──────


def test_select_trophy_hall_on_live_engine(requires_c_engine) -> None:
    """A live ``select_trophy_hall`` state maps every move; same-colour hall
    indices merge, different colours do not, and the ``index`` allow-list is the
    only block reached."""
    session = _orcus_to_select_state()
    adapter = _adapter(session)
    try:
        pending, ctx = _pending_ctx(adapter)
        assert pending["effect_kind"] == "select_trophy_hall"

        index_start, index_end = RESOLVE_GENERIC_LAYOUT["index"]
        choices: list[tuple[int, str, str]] = []  # (gid, source_player, colour)
        for move in _moves(adapter):
            payload = move.to_payload()
            gid = move_to_global_action(payload, ctx)
            if payload.get("action_id") is None and payload.get("target_id") is None:
                continue  # decline
            assert index_start <= gid < index_end, (gid, payload)
            source = payload["action_id"]
            colour = ctx.trophy_halls[source][int(payload["target_id"])]
            choices.append((gid, source, colour))

        assert choices, "expected at least one trophy to select"
        # For one source, gid is equal iff the colour is equal.
        for gid_a, source_a, colour_a in choices:
            for gid_b, source_b, colour_b in choices:
                if source_a != source_b:
                    continue
                assert (gid_a == gid_b) == (colour_a == colour_b), (
                    colour_a,
                    colour_b,
                    gid_a,
                    gid_b,
                )
    finally:
        session.destroy()


def test_steal_from_selected_trophy_on_live_engine(requires_c_engine) -> None:
    """After a select, every ``steal_from_selected_trophy`` move routes to
    ``assassinate[node x trophy_colour]``; slots at one node merge."""
    session = _orcus_to_select_state()
    non_skip = [
        m
        for m in session.legal_moves()
        if m.move_type == "resolve_generic" and m.data.get("action_id") is not None
    ]
    assert non_skip, "expected a trophy choice"
    session.submit_move(non_skip[0])

    adapter = _adapter(session)
    try:
        pending, ctx = _pending_ctx(adapter)
        assert pending["effect_kind"] == "steal_from_selected_trophy"

        grouped: dict[int, set] = {}
        for move in _moves(adapter):
            payload = move.to_payload()
            gid = move_to_global_action(payload, ctx)
            source, idx, node, _slot = _split_structured(payload["target_id"])
            colour = ctx.trophy_halls[source][idx]
            node_i = NODE_ID_TO_INDEX[node]
            expected = _start("assassinate") + node_i * 5 + owner_slot(
                colour, ctx.seat_order, allow_white=True
            )
            assert gid == expected, (colour, gid, expected)
            grouped.setdefault(gid, set()).add(payload["target_id"].rsplit(":", 1)[1])
        # Slots that differ only by destination slot at one node share a gid.
        assert all(len(slots) >= 1 for slots in grouped.values())
    finally:
        session.destroy()
