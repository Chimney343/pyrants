"""Air Elemental card tests.

Option 2 must be: return a spy, then deploy 3 troops, then (if Guile focus is
met) draw a card.  There must be no assassinate step in the second modal.
"""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from game_setup.loaders import assemble_catalog_payload
from tests.c_engine.card_test_helpers import make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_SPY_SITE = "site_gauntlgrym"


def _player_index(session: CSession, pid: str) -> int:
    s = session._state._ptr.contents
    for i in range(s.player_count):
        if _lib.intern_str(s.player_ids[i]).decode() == pid:
            return i
    return -1


def _barracks(session: CSession, pid: str) -> int:
    return session._state._ptr.contents.players[_player_index(session, pid)].barracks


def _spies_available(session: CSession, pid: str) -> int:
    return session._state._ptr.contents.players[_player_index(session, pid)].spies_available


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    s = session._state._ptr.contents
    nid = _lib.intern(node_id.encode())
    for i in range(s.node_count):
        if s.nodes[i].node_id == nid:
            return [_lib.intern_str(s.nodes[i].spies[j]).decode() for j in range(s.nodes[i].spy_count)]
    return []


def _resolve_generic_moves(session: CSession) -> list:
    return [m for m in session.legal_moves() if getattr(m, "move_type", "") == "resolve_generic"]


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if getattr(m, "move_type", "") == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _build_session() -> CSession:
    eng = CEngine()
    eng.initialize(
        catalog_path=str(DATA_DIR / "cards"),
        board_path=str(DATA_DIR / "boards" / "tyrants_of_the_underdark.json"),
        setup_path=str(DATA_DIR / "decks" / "base_setup.json"),
    )
    return make_card_test_session(
        eng,
        ["p1", "p2"],
        hand={"p1": ["air_elemental"]},
        spies={_SPY_SITE: ["p1"]},
        troops={"p1": {_SPY_SITE: [None, None, None], "site_menzoberranzan": [None, None, None]}},
        current_player="p1",
    )


def test_air_elemental_catalog_option_2_sequence() -> None:
    """Option 2 must be return_spy -> deploy_troops x3 -> focus draw (no assassinate)."""
    catalog = assemble_catalog_payload(DATA_DIR / "cards")

    card = None
    for c in catalog["cards"]:
        if c["card_id"] == "air_elemental":
            card = c
            break
    assert card is not None, "air_elemental not found in catalog"

    em = card["execution_model"]
    assert em["kind"] == "modal_choice"
    options = {o["option_id"]: o for o in em["options"]}
    assert set(options) == {"option_1", "option_2"}

    ops = [a["op"] for a in options["option_2"]["actions"]]
    assert ops == ["return_spy", "deploy_troops", "deploy_troops", "deploy_troops", "draw_cards"], (
        f"option_2 op sequence wrong: {ops}"
    )

    actions = options["option_2"]["actions"]
    assert actions[0]["metadata"] == {"spy_owner": "self"}
    for i in (1, 2, 3):
        assert actions[i]["optional"] is False
        assert actions[i]["quantity"] == {"kind": "fixed", "value": 1}
        assert actions[i]["source_fragment"] == f"deploy_troops_step_{i}"
    assert actions[4]["metadata"] == {"requires_focus": True, "focus_aspect": "guile"}


def test_air_elemental_option_2_returns_spy_and_deploys_three_troops() -> None:
    """Option 2 returns one spy then deploys exactly 3 troops, no assassinate."""
    session = _build_session()

    barracks_before = _barracks(session, "p1")
    spies_before = _spies_available(session, "p1")

    _play_card(session, "air_elemental")

    # Modal choice: pick option_2.
    gen = _resolve_generic_moves(session)
    opt2 = next(m for m in gen if m.data.get("action_id") == "option_2")
    session.submit_move(opt2)

    # First pending action is return_spy (own spy at the site).
    gen = _resolve_generic_moves(session)
    return_moves = [m for m in gen if m.data.get("action_id") == _SPY_SITE]
    assert len(return_moves) == 1, f"Expected return_spy move for {_SPY_SITE}, got {[m.data for m in gen]}"
    session.submit_move(return_moves[0])

    assert _SPY_SITE not in _spies_at_node(session, _SPY_SITE), "Spy should be returned"
    assert _spies_available(session, "p1") == spies_before + 1, "Returned spy should be back in supply"

    # Exactly 3 deploy steps follow.
    deploys = 0
    while True:
        gen = _resolve_generic_moves(session)
        deploy_moves = [m for m in gen if m.data.get("action_id") not in ("option_1", "option_2")]
        if not deploy_moves:
            break
        session.submit_move(deploy_moves[0])
        deploys += 1
        assert deploys <= 3, "Option 2 deployed more than 3 troops"

    assert deploys == 3, f"Expected 3 deploy steps, got {deploys}"
    assert _barracks(session, "p1") == barracks_before - 3, (
        f"Expected 3 troops deployed (barracks {barracks_before} -> {barracks_before - 3}), "
        f"got {_barracks(session, 'p1')}"
    )

    session.destroy()
