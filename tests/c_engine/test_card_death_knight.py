"""Death Knight card tests — supplant a troop, then gain 1 VP per 5 non-white trophies."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _player_vp_tokens,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SCENARIO_PATH = (
    DATA_DIR / "scenarios" / "batch_card_generation" / "110_seed_4_death_knight.json"
)

P1 = "p1"
P2 = "p2"


def _player_score(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].score


def _trophy_hall(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == pid:
            ps = s.players[i]
            return [
                _lib.intern_str(ps.trophy_hall[j]).decode()
                for j in range(ps.trophy_hall_count)
            ]
    return []


def _add_trophies(session: CSession, pid: str, count: int, label: str) -> None:
    s = _sptr(session).contents
    pi = _session_player_index(session, pid)
    ps = s.players[pi]
    for _ in range(count):
        if ps.trophy_hall_count < 50:
            ps.trophy_hall[ps.trophy_hall_count] = _lib.intern(label.encode())
            ps.trophy_hall_count += 1


# ---------------------------------------------------------------------------
# Catalog structure
# ---------------------------------------------------------------------------


def test_death_knight_execution_model_structure():
    """Verify the catalog execution model: sequence with supplant + grant_vp."""
    catalog = assemble_catalog_payload(DATA_DIR / "cards")

    dk = None
    for card in catalog["cards"]:
        if card["card_id"] == "death_knight":
            dk = card
            break
    assert dk is not None, "Death Knight not found in catalog"
    assert dk["name"] == "Death Knight"
    assert dk["cost"] == 6
    assert dk["aspect"] == "malice"
    assert "undead" in dk["secondary_aspects"]

    em = dk["execution_model"]
    assert em["kind"] == "sequence"
    actions = em["actions"]
    assert len(actions) == 2, f"Expected 2 actions, got {len(actions)}"

    a1 = actions[0]
    assert a1["op"] == "supplant_troop"
    assert a1["target_scope"] == "board_site"
    assert a1["timing"] == "immediate"
    assert a1["optional"] is False

    a2 = actions[1]
    assert a2["op"] == "grant_vp"
    assert a2["target_scope"] == "self"
    assert a2["timing"] == "immediate"
    assert a2["optional"] is False
    assert a2["metadata"]["count_from"] == "trophy_hall_non_white"
    assert a2["metadata"]["per"] == 5

    # Top-level actions array
    top_actions = dk.get("actions", [])
    assert len(top_actions) == 2
    top_a2 = top_actions[1]
    assert top_a2["op"] == "grant_vp"
    assert top_a2["metadata"]["count_from"] == "trophy_hall_non_white"
    assert top_a2["metadata"]["per"] == 5


# ---------------------------------------------------------------------------
# Supplant behaviour
# ---------------------------------------------------------------------------


def test_death_knight_supplant_adds_to_trophy_hall():
    """Supplanting a troop adds it to current player's trophy hall."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, [P1, P2],
        hand={P1: ["death_knight"]},
        troops={P1: {"site_gauntlgrym": [P1, P2, None, None]}},
        current_player=P1,
    )
    trophy_before = len(_trophy_hall(session, P1))

    playable = [m for m in session.legal_moves()
                if m.move_type == "play_card"
                and m.data.get("card_id") == "death_knight"]
    assert playable, "Death Knight not playable"
    session.submit_move(playable[0])

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_moves) > 0, "Expected supplant resolve_generic moves"
    session.submit_move(gen_moves[0])

    # After supplant, no more generic moves (grant_vp is immediate, auto-resolved)
    gen_after = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_after) == 0, f"Expected 0 pending generics after grant_vp, got {len(gen_after)}"

    trophy_after = len(_trophy_hall(session, P1))
    assert trophy_after == trophy_before + 1, (
        f"Expected +1 trophy from supplant, got {trophy_after} (was {trophy_before})"
    )

    session.destroy()


def test_death_knight_supplant_is_mandatory():
    """When a supplant target exists, no skip option is offered."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, [P1, P2],
        hand={P1: ["death_knight"]},
        troops={P1: {"site_gauntlgrym": [P1, P2, None, None]}},
        current_player=P1,
    )
    playable = [m for m in session.legal_moves()
                if m.move_type == "play_card"
                and m.data.get("card_id") == "death_knight"]
    session.submit_move(playable[0])

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_moves) > 0, "Expected at least one supplant target"

    skip_moves = [m for m in gen_moves if m.data.get("action_id") is None]
    assert len(skip_moves) == 0, "Supplant is mandatory, no skip should be offered"

    session.destroy()


# ---------------------------------------------------------------------------
# VP award — grant_vp without as:vp_tokens (= score change)
# ---------------------------------------------------------------------------


def test_death_knight_vp_per_five_player_trophies():
    """1 VP per 5 non-white trophies: 10 trophies + 1 supplant = 11 → 2 VP."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, [P1, P2],
        hand={P1: ["death_knight"]},
        troops={P1: {"site_gauntlgrym": [P1, P2, None, None]}},
        current_player=P1,
    )
    _add_trophies(session, P1, 10, "p2")

    score_before = _player_score(session, P1)
    vp_tokens_before = _player_vp_tokens(session, P1)

    playable = [m for m in session.legal_moves()
                if m.move_type == "play_card"
                and m.data.get("card_id") == "death_knight"]
    session.submit_move(playable[0])

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert gen, "Expected supplant resolve_generic"
    session.submit_move(gen[0])

    expected_vp = 2
    assert _player_score(session, P1) == score_before + expected_vp, (
        f"10 trophies + 1 supplant = 11, /5 = {expected_vp} VP. "
        f"Got score {_player_score(session, P1)}"
    )
    assert _player_vp_tokens(session, P1) == vp_tokens_before, (
        "vp_tokens must not change (non-token grant_vp)"
    )

    session.destroy()


def test_death_knight_white_trophies_excluded():
    """White trophies do not count toward the VP award."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, [P1, P2],
        hand={P1: ["death_knight"]},
        troops={P1: {"site_gauntlgrym": [P1, P2, None, None]}},
        current_player=P1,
    )
    _add_trophies(session, P1, 4, "p2")
    _add_trophies(session, P1, 5, "white")

    score_before = _player_score(session, P1)

    playable = [m for m in session.legal_moves()
                if m.move_type == "play_card"
                and m.data.get("card_id") == "death_knight"]
    session.submit_move(playable[0])

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.submit_move(gen[0])

    assert _player_score(session, P1) == score_before + 1, (
        f"4 player + 1 supplant = 5 player trophies → 1 VP. "
        f"White trophies must be excluded. Got {_player_score(session, P1)}"
    )

    session.destroy()


def test_death_knight_rounds_down():
    """VP is floor-divided: 14 + 1 (supplant) = 15 → 3 VP, not 2."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, [P1, P2],
        hand={P1: ["death_knight"]},
        troops={P1: {"site_gauntlgrym": [P1, P2, None, None]}},
        current_player=P1,
    )
    _add_trophies(session, P1, 14, "p2")

    score_before = _player_score(session, P1)

    playable = [m for m in session.legal_moves()
                if m.move_type == "play_card"
                and m.data.get("card_id") == "death_knight"]
    session.submit_move(playable[0])

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.submit_move(gen[0])

    assert _player_score(session, P1) == score_before + 3, (
        f"14 + 1 supplant = 15 player trophies → 3 VP. Got {_player_score(session, P1)}"
    )

    session.destroy()


def test_death_knight_zero_player_trophies():
    """With zero non-white trophies, supplant adds 1, /5 = 0 VP."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, [P1, P2],
        hand={P1: ["death_knight"]},
        troops={P1: {"site_gauntlgrym": [P1, P2, None, None]}},
        current_player=P1,
    )
    score_before = _player_score(session, P1)

    playable = [m for m in session.legal_moves()
                if m.move_type == "play_card"
                and m.data.get("card_id") == "death_knight"]
    session.submit_move(playable[0])

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.submit_move(gen[0])

    assert _player_score(session, P1) == score_before, (
        f"0 trophies + 1 supplant = 1, /5 = 0 VP. Got {_player_score(session, P1)}"
    )

    session.destroy()


# ---------------------------------------------------------------------------
# Scenario-based end-to-end
# ---------------------------------------------------------------------------


def test_death_knight_scenario_plays_without_stuck():
    """Scenario: play death_knight, resolve supplant, verify no stuck state."""
    session = CSession.load(str(SCENARIO_PATH))

    playable = [m for m in session.legal_moves()
                if m.move_type == "play_card"
                and m.data.get("card_id") == "death_knight"]
    if not playable:
        session.destroy()
        return

    session.submit_move(playable[0])

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    if gen:
        session.submit_move(gen[0])

    # After grant_vp resolves, no pending generics should remain
    gen_after = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_after) == 0, (
        f"Expected no pending generics after Death Knight resolves, got {len(gen_after)}"
    )

    s = _sptr(session).contents
    assert not s.pending_generic, "pending_generic should be cleared after card resolves"

    session.destroy()


def test_death_knight_no_supplant_target_auto_skips():
    """When no enemy troops exist to supplant, action auto-skips.
    Card resolves with no effect, no stuck state."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, [P1, P2],
        hand={P1: ["death_knight"]},
        # No enemy troops — P1 has troops at sites but no opponent troops
        troops={P1: {"site_gauntlgrym": [P1, None, None, None]}},
        current_player=P1,
    )
    trophy_before = len(_trophy_hall(session, P1))
    score_before = _player_score(session, P1)

    playable = [m for m in session.legal_moves()
                if m.move_type == "play_card"
                and m.data.get("card_id") == "death_knight"]
    if not playable:
        session.destroy()
        return

    session.submit_move(playable[0])

    gen = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen) == 0, (
        f"Expected no resolve_generic when no supplant target, got {len(gen)}"
    )

    s = _sptr(session).contents
    assert not s.pending_generic, "pending_generic should be cleared after auto-skip"

    # Trophy hall and score unchanged
    assert len(_trophy_hall(session, P1)) == trophy_before, "Trophy hall unchanged"
    assert _player_score(session, P1) == score_before, "Score unchanged"

    session.destroy()
