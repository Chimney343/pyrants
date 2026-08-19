"""Deathblade card tests — 2 sequential assassinations, both mandatory."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "batch_card_generation" / "067_seed_4_deathblade.json"
)


def _trophy_hall(session: CSession, player_id: str) -> list[str]:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        pid = _lib.intern_str(s.player_ids[i]).decode()
        if pid == player_id:
            ps = s.players[i]
            return [
                _lib.intern_str(ps.trophy_hall[j]).decode()
                for j in range(ps.trophy_hall_count)
            ]
    return []


def test_deathblade_two_mandatory_assassinations() -> None:
    """Deathblade: 2 sequential assassinate_troop actions, both optional=false.
    Player must resolve both when targets exist; no skip offered for either."""
    session = CSession.load(str(SCENARIO_PATH))

    trophy_before = len(_trophy_hall(session, "p3"))

    # 1. Play Deathblade
    play_move = None
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "deathblade":
            play_move = m
            break
    assert play_move is not None, "Deathblade not found in legal moves"
    session.submit_move(play_move)

    # 2. First assassinate — verify no skip option (optional=false)
    action1_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(action1_moves) > 0, "Expected at least one legal target for action_1"

    # A skip move would have action_id=None / SYM_NULL.
    skip_moves = [m for m in action1_moves if m.data.get("action_id") is None]
    assert len(skip_moves) == 0, "action_1 should have no skip move (optional=false)"

    # Record first target's node for later verification
    first_target = action1_moves[0]

    result = session.submit_move(first_target)
    assert result is not None, "First assassinate failed"

    # 3. Second assassinate — verify still no skip option
    action2_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(action2_moves) > 0, "Expected at least one legal target for action_2"

    skip_moves2 = [m for m in action2_moves if m.data.get("action_id") is None]
    assert len(skip_moves2) == 0, "action_2 should have no skip move (optional=false)"

    result2 = session.submit_move(action2_moves[0])
    assert result2 is not None, "Second assassinate failed"

    # 4. Card should be done — no more resolve_generic moves
    final_moves = session.legal_moves()
    final_gen = [m for m in final_moves if m.move_type == "resolve_generic"]
    assert len(final_gen) == 0, (
        f"Expected no more resolve_generic after 2 assassinations, got {len(final_gen)}"
    )

    # 5. Trophy hall should have 2 more entries (the assassinated troops)
    trophy_after = len(_trophy_hall(session, "p3"))
    assert trophy_after == trophy_before + 2, (
        f"Expected +2 trophies (2 assassinations), got {trophy_after} (was {trophy_before})"
    )

    session.destroy()


def test_deathblade_catalog_actions_are_mandatory() -> None:
    """Verify both execution_model actions have optional=false."""

    catalog = assemble_catalog_payload(Path(__file__).resolve().parents[2] / "data" / "cards")

    deathblade = None
    for card in catalog["cards"]:
        if card["card_id"] == "deathblade":
            deathblade = card
            break
    assert deathblade is not None, "Deathblade not found in catalog"

    em = deathblade["execution_model"]
    assert em["kind"] == "sequence", "Expected sequence execution model"
    actions = em["actions"]
    assert len(actions) == 2, f"Expected 2 actions, got {len(actions)}"

    a1 = actions[0]
    assert a1["op"] == "assassinate_troop"
    assert a1["optional"] is False, f"action_1 optional should be false, got {a1['optional']}"

    a2 = actions[1]
    assert a2["op"] == "assassinate_troop"
    assert a2["optional"] is False, f"action_2 optional should be false, got {a2['optional']}"

    # Also check the top-level actions array
    top_actions = deathblade.get("actions", [])
    assert len(top_actions) == 2
    assert top_actions[0]["optional"] is False
    assert top_actions[1]["optional"] is False


def test_deathblade_no_valid_targets_auto_skips() -> None:
    """When no legal assassination targets exist, both actions auto-skip.
    Card resolves immediately with no effect and no stuck pending state."""
    session = CSession.load(str(SCENARIO_PATH))

    # Remove all p3 presence from every board node
    s = session._state._ptr.contents
    for i in range(s.node_count):
        ns = s.nodes[i]
        for t in range(ns.troop_slot_count):
            if ns.troop_slots[t]:
                val = _lib.intern_str(ns.troop_slots[t]).decode() if ns.troop_slots[t] else None
                if val == "p3":
                    ns.troop_slots[t] = 0
        for sp in range(ns.spy_count):
            if ns.spies[sp]:
                val = _lib.intern_str(ns.spies[sp]).decode() if ns.spies[sp] else None
                if val == "p3":
                    ns.spies[sp] = 0

    trophy_before = len(_trophy_hall(session, "p3"))

    play_move = None
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == "deathblade":
            play_move = m
            break
    assert play_move is not None, "Deathblade not found in legal moves"

    result = session.submit_move(play_move)
    assert result is not None, "Playing Deathblade should succeed even with no targets"

    # No resolve_generic moves — both actions auto-skipped
    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_moves) == 0, (
        f"Expected 0 resolve_generic moves when no targets, got {len(gen_moves)}"
    )

    # Pending generic should be cleared
    s = session._state._ptr.contents
    assert not s.pending_generic, "Expected no pending_generic after auto-skip"

    # Trophy hall unchanged — no assassinations happened
    trophy_after = len(_trophy_hall(session, "p3"))
    assert trophy_after == trophy_before, (
        f"Trophy hall should be unchanged, was {trophy_before} now {trophy_after}"
    )

    # Regular turn continues — play_card and end_main_phase moves available
    move_types = {m.move_type for m in session.legal_moves()}
    assert "play_card" in move_types, "Should still be able to play other cards"
    assert "end_main_phase" in move_types, "Should be able to end main phase"

    session.destroy()
