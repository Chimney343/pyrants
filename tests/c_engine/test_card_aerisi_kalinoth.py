"""Aerisi Kalinoth card behavior tests via the C engine bindings.

Verifies:
- Gain 1 power immediately on play
- Place 1 spy on a chosen board site
- Recruit a Guile card costing ≤4 (paying its influence cost)
- Recruit filtering: only Guile-cost≤4 market cards shown
- Card leaves hand after play
- Sequence resolves cleanly with no pending choices
- Recruited card lands in discard pile
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import (
    MAX_ZONE_SIZE,
    PHASE_MAIN,
    _lib,
)
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SCENARIO_PATH = DATA_DIR / "scenarios" / "batch_card_generation" / "081_seed_4_aerisi_kalinoth.json"

_P1 = "p1"
_P2 = "p2"
_SITE_A = "site_gauntlgrym"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sptr(session: CSession):
    return session._state._ptr


def _player_index(session: CSession, pid: str) -> int:
    s = _sptr(session).contents
    for i in range(s.player_count):
        pname = _lib.intern_str(s.player_ids[i])
        if pname and pname.decode() == pid:
            return i
    return -1


def _hand_ids(session: CSession, pid: str) -> list[str]:
    pi = _player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.hand[j]).decode() for j in range(ps.hand_count)]


def _discard_ids(session: CSession, pid: str) -> list[str]:
    pi = _player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.discard_pile[j]).decode() for j in range(ps.discard_pile_count)]


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            return [_lib.intern_str(s.nodes[ni].spies[i]).decode() for i in range(s.nodes[ni].spy_count)]
    return []


def _spies_available(session: CSession, pid: str) -> int:
    pi = _player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].spies_available


def _resource_power(session: CSession) -> int:
    return _sptr(session).contents.resource_pool.power


def _resource_influence(session: CSession) -> int:
    return _sptr(session).contents.resource_pool.influence


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _init_engine() -> CEngine:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return eng


def _set_market_row(session: CSession, card_ids: list[str]) -> None:
    s = _sptr(session).contents
    ms = s.market
    ms.row_count = min(len(card_ids), MAX_ZONE_SIZE)
    for j, cid in enumerate(card_ids[:MAX_ZONE_SIZE]):
        ms.row[j] = _lib.intern(cid.encode())


def _market_row_ids(session: CSession) -> list[str]:
    s = _sptr(session).contents
    return [_lib.intern_str(s.market.row[j]).decode() for j in range(s.market.row_count)]


def _build_session(**kwargs) -> CSession:
    """Create a minimal Main-phase session with aerisi_kalinoth in P1's hand."""
    defaults: dict = {
        "player_ids": [_P1, _P2],
        "hand": {_P1: ["aerisi_kalinoth"]},
        "current_player": _P1,
    }
    defaults.update(kwargs)
    eng = _init_engine()
    from tests.c_engine.card_test_helpers import make_card_test_session

    session = make_card_test_session(eng, defaults.pop("player_ids"), **defaults)
    s = _sptr(session).contents
    s.phase = PHASE_MAIN
    return session


def _play_card(session: CSession, card_id: str = "aerisi_kalinoth") -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


def _resolve_generic_by_action_id(session: CSession, action_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == action_id:
            session.submit_move(m)
            return
    available = [m.data for m in session.legal_moves() if m.move_type == "resolve_generic"]
    session.destroy()
    raise AssertionError(
        f"resolve_generic move for {action_id} not found, available: {available}"
    )


# ---------------------------------------------------------------------------
# scenario-based tests (uses 081_seed_4_aerisi_kalinoth.json)
# ---------------------------------------------------------------------------


def test_aerisi_kalinoth_full_sequence_scenario() -> None:
    """End-to-end via scenario: play → place spy → recruit → verify all effects."""
    session = CSession.load(str(SCENARIO_PATH))

    s = session.state
    assert s.current_player_id == "p1"
    power_before = _resource_power(session)
    influence_before = _resource_influence(session)
    spies_before = _spies_available(session, "p1")
    hand_before = _hand_ids(session, "p1")

    assert "aerisi_kalinoth" in hand_before, "Aerisi Kalinoth must be in hand"

    _play_card(session)

    s = session.state
    power_after_play = _resource_power(session)
    assert power_after_play == power_before + 1, (
        f"Expected +1 power, got {power_after_play} (was {power_before})"
    )

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_moves) > 0, "Expected generic choices for place_spy"
    spy_nodes = {m.data.get("action_id") for m in gen_moves}
    spy_target = next(iter(spy_nodes))

    _resolve_generic_by_action_id(session, spy_target)

    assert _P1 in _spies_at_node(session, spy_target), (
        f"Spy must be placed on {spy_target}"
    )
    assert _spies_available(session, "p1") == spies_before - 1, (
        f"spies_available should decrease by 1: {spies_before} → {_spies_available(session, 'p1')}"
    )

    # The scenario starts with 0 influence, so the mandatory paid recruit has no
    # affordable Guile card ≤4 and auto-skips.
    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_moves) == 0, (
        f"With 0 influence, no affordable Guile card ≤4 should be offered; got "
        f"{[m.data for m in gen_moves]}"
    )

    assert not _has_pending_generic(session), "No pending choices after full resolution"

    power_after = _resource_power(session)
    influence_after = _resource_influence(session)
    hand_after = _hand_ids(session, "p1")

    assert power_after == power_before + 1
    assert influence_after == influence_before, (
        f"Unaffordable recruit must not change influence: {influence_before} → {influence_after}"
    )
    assert "aerisi_kalinoth" not in hand_after, "Card must leave hand"

    session.destroy()


def test_aerisi_kalinoth_recruit_filtered_to_guile_max_cost_four_scenario() -> None:
    """All legal recruit targets must have aspect=guile and cost≤4."""

    session = CSession.load(str(SCENARIO_PATH))

    _play_card(session)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    spy_move = gen_moves[0]
    session.submit_move(spy_move)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    recruit_cards = [m.data.get("action_id") for m in gen_moves]

    cat = assemble_catalog_payload(DATA_DIR / "cards")["cards"]

    for cid in recruit_cards:
        card = next((c for c in cat if c["card_id"] == cid), None)
        assert card is not None, f"Recruit target {cid} not in catalog"
        assert card["aspect"] == "guile", (
            f"Recruit target {card['name']} has aspect {card['aspect']}, expected guile"
        )
        assert card["cost"] <= 4, (
            f"Recruit target {card['name']} costs {card['cost']}, expected ≤4"
        )

    session.destroy()


# ---------------------------------------------------------------------------
# programmatic tests (minimal session, controlled market)
# ---------------------------------------------------------------------------


def test_aerisi_kalinoth_gains_one_power() -> None:
    """Playing aerisi_kalinoth grants exactly 1 power immediately."""
    session = _build_session()
    power_before = _resource_power(session)

    _play_card(session)

    power_after = _resource_power(session)
    assert power_after == power_before + 1, (
        f"Expected +1 power, got {power_after} (was {power_before})"
    )

    session.destroy()


def test_aerisi_kalinoth_places_spy_on_selected_node() -> None:
    """After selecting a node, that node has P1's spy."""
    session = _build_session()
    spies_avail = _spies_available(session, _P1)

    _play_card(session)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assert len(gen_moves) > 0, "Expected spy placement move"
    spy_node = gen_moves[0].data.get("action_id")

    _resolve_generic_by_action_id(session, spy_node)

    assert _P1 in _spies_at_node(session, spy_node), (
        f"Spy should be placed at {spy_node}"
    )
    assert _spies_available(session, _P1) == spies_avail - 1, (
        "spies_available should decrease by 1"
    )

    session.destroy()


def test_aerisi_kalinoth_recruit_filtered_to_guile_max_cost_four() -> None:
    """Only guile cards costing ≤4 appear as recruit choices."""
    session = _build_session()

    _set_market_row(session, [
        "air_elemental",   # guile, 3  → should appear
        "soldier",         # obedience, 0 → should NOT appear
        "noble",           # obedience, 0 → should NOT appear
    ])
    sptr = _sptr(session).contents
    sptr.resource_pool.influence = 10

    _play_card(session)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    spy_move = gen_moves[0]
    session.submit_move(spy_move)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    recruit_ids = {m.data.get("action_id") for m in gen_moves}

    assert "air_elemental" in recruit_ids, "air_elemental (guile, cost 3) must be offered"
    assert "soldier" not in recruit_ids, "soldier (obedience) must NOT be offered"
    assert "noble" not in recruit_ids, "noble (obedience) must NOT be offered"

    session.destroy()


def test_aerisi_kalinoth_recruit_deducts_influence() -> None:
    """Recruiting with aerisi_kalinoth spends influence equal to the card's cost.

    Aerisi says "recruit a Guile card that costs 4 or less" (not "without paying
    its cost"), so the recruit is paid.
    """
    session = _build_session()

    _set_market_row(session, ["air_elemental"])  # guile, cost 3
    sptr = _sptr(session).contents

    sptr.resource_pool.influence = 10
    influence_before = sptr.resource_pool.influence

    _play_card(session)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    spy_move = gen_moves[0]
    session.submit_move(spy_move)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    recruit_move = gen_moves[0]
    session.submit_move(recruit_move)

    influence_after = _resource_influence(session)
    assert influence_after == influence_before - 3, (
        f"Recruit should cost 3 influence: {influence_before} → {influence_after}"
    )

    session.destroy()


def test_aerisi_kalinoth_card_leaves_hand() -> None:
    """After playing, aerisi_kalinoth is no longer in hand."""
    session = _build_session()
    hand_before = _hand_ids(session, _P1)
    assert "aerisi_kalinoth" in hand_before

    _play_card(session)
    hand_after_play = _hand_ids(session, _P1)
    assert "aerisi_kalinoth" not in hand_after_play, (
        f"aerisi_kalinoth must leave hand after play; got {hand_after_play}"
    )

    session.destroy()


def test_aerisi_kalinoth_resolves_cleanly_no_pending() -> None:
    """After resolve_generic for both spy and recruit, no pending state remains."""
    session = _build_session()

    _set_market_row(session, ["air_elemental"])
    sptr = _sptr(session).contents
    sptr.resource_pool.influence = 10

    _play_card(session)
    assert _has_pending_generic(session), "Should be pending for spy placement"

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    spy_move = gen_moves[0]
    session.submit_move(spy_move)
    assert _has_pending_generic(session), "Should be pending for recruit"

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    recruit_move = gen_moves[0]
    session.submit_move(recruit_move)

    assert not _has_pending_generic(session), (
        "No pending choices after full resolution"
    )

    session.destroy()


def test_aerisi_kalinoth_recruit_card_goes_to_discard() -> None:
    """Recruited card appears in discard pile."""
    session = _build_session()

    _set_market_row(session, ["air_elemental"])
    sptr = _sptr(session).contents
    sptr.resource_pool.influence = 10
    discard_before = _discard_ids(session, _P1)

    _play_card(session)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    spy_move = gen_moves[0]
    session.submit_move(spy_move)

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    recruit_move = gen_moves[0]
    session.submit_move(recruit_move)

    discard_after = _discard_ids(session, _P1)
    assert len(discard_after) == len(discard_before) + 1, (
        f"Expected +1 card in discard, got {len(discard_before)} → {len(discard_after)}"
    )
    assert "air_elemental" in discard_after, (
        f"air_elemental must be in discard; got {discard_after}"
    )

    session.destroy()
