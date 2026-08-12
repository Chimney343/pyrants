"""Mind Flayer card behavior tests via the C engine bindings.

Execution model: modal_choice (exactly_one)
  - Option 1 (option_1): devour_cost from hand → gain 3 influence
  - Option 2 (option_2): devour_cost from hand → assassinate_troop from board_site

Rules text: "Devour a card from your hand, then choose exactly one mode:
either gain 3 influence, or assassinate a troop."

Verifies:
  - Modal choice is pending after play with source_card_id set
  - Exactly two options (option_1, option_2), no skip move
  - Option 1: devour a hand card, then gain 3 influence
  - Option 2: devour a hand card, then assassinate an enemy troop
  - Devour is mandatory (no skip for devour cost)
  - Hand count decreases correctly after devour
  - Card fully resolves (no remaining resolve_generic moves)
  - Card stays in played_cards (not devoured itself)
  - Influence gain adds to existing pool
  - Assassinate records trophy in trophy hall
  - Own troops are not valid assassinate targets
"""

from __future__ import annotations

from engine_c.bindings.engine_bindings import _lib
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

_P1 = "p1"
_P2 = "p2"
_CARD = "mind_flayer"
_SITE = "site_gauntlgrym"


def _hand_count(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].hand_count


def _has_pending_generic(session):
    return _sptr(session).contents.pending_generic is not None


def _pending_source_card_id(session):
    pg = _sptr(session).contents.pending_generic
    if not pg:
        return ""
    sym = _lib.intern_str(pg.contents.source_card_id)
    return sym.decode() if sym else ""


def _has_resolve_generic_moves(session):
    return any(m.move_type == "resolve_generic" for m in session.legal_moves())


def _play_card(session, card_id=_CARD):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    raise AssertionError(f"{card_id} not playable")


def _resolve_generic(session, action_id, target_id=None):
    for m in session.legal_moves():
        if m.move_type != "resolve_generic":
            continue
        d = m.data
        if d.get("action_id") == action_id and (
            target_id is None or str(d.get("target_id")) == target_id
        ):
            session.submit_move(m)
            return
    raise AssertionError(f"No resolve_generic for action_id={action_id} target_id={target_id}")


def _pick_modal_option(session, option_id):
    for m in session.legal_moves():
        if m.move_type == "resolve_generic" and m.data.get("action_id") == option_id:
            session.submit_move(m)
            return
    raise AssertionError(f"{option_id} not found in resolve_generic moves")


def _played_cards_ids(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.played_cards[j]).decode() for j in range(ps.played_cards_count)]


def _devour_pile(session):
    s = _sptr(session).contents
    return [_lib.intern_str(s.devour_pile[j]).decode() for j in range(s.devour_pile_count)]


def _influence(session):
    return _sptr(session).contents.resource_pool.influence


def _power(session):
    return _sptr(session).contents.resource_pool.power


def _trophy_hall(session, pid):
    pi = _session_player_index(session, pid)
    if pi < 0:
        return []
    ps = _sptr(session).contents.players[pi]
    return [_lib.intern_str(ps.trophy_hall[j]).decode() for j in range(ps.trophy_hall_count)]


def _set_troop_slots(session, node_id, slots):
    s = _sptr(session).contents
    nid = _lib.intern(node_id.encode())
    for ni in range(s.node_count):
        if s.nodes[ni].node_id == nid:
            s.nodes[ni].troop_slot_count = len(slots)
            for si, occ in enumerate(slots):
                s.nodes[ni].troop_slots[si] = _lib.intern(occ.encode()) if occ else 0
            break


# ---------------------------------------------------------------------------
# Modal choice structure tests
# ---------------------------------------------------------------------------


def test_mind_flayer_modal_choice_pending_after_play() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        current_player=_P1,
    )
    _play_card(session)
    assert _has_pending_generic(session)
    assert _pending_source_card_id(session) == _CARD
    session.destroy()


def test_mind_flayer_modal_has_exactly_two_options_no_skip() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        current_player=_P1,
    )
    _play_card(session)
    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    target_moves = [m for m in gen_moves if m.data.get("action_id") is not None]
    skip_moves = [m for m in gen_moves if m.data.get("action_id") is None]
    assert len(target_moves) == 2
    assert len(skip_moves) == 0
    option_ids = {m.data["action_id"] for m in target_moves}
    assert option_ids == {"option_1", "option_2"}
    session.destroy()


# ---------------------------------------------------------------------------
# Option 1: devour from hand → gain 3 influence
# ---------------------------------------------------------------------------


def test_mind_flayer_option_1_devour_then_gain_influence() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble", "soldier"]},
        current_player=_P1,
    )
    _sptr(session).contents.resource_pool.influence = 0
    _play_card(session)
    _pick_modal_option(session, "option_1")
    assert _has_pending_generic(session)
    _resolve_generic(session, "noble")
    assert not _has_resolve_generic_moves(session)
    assert _influence(session) == 3
    assert "noble" in _devour_pile(session)
    session.destroy()


def test_mind_flayer_option_1_hand_decreases_by_two() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble", "soldier", "priestess_of_lolth"]},
        current_player=_P1,
    )
    hand_before = _hand_count(session, _P1)
    _play_card(session)
    _pick_modal_option(session, "option_1")
    _resolve_generic(session, "noble")
    assert _hand_count(session, _P1) == hand_before - 2
    assert _influence(session) == 3
    session.destroy()


def test_mind_flayer_option_1_influence_adds_to_existing() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        current_player=_P1,
    )
    _sptr(session).contents.resource_pool.influence = 5
    _sptr(session).contents.resource_pool.power = 2
    _play_card(session)
    _pick_modal_option(session, "option_1")
    _resolve_generic(session, "noble")
    assert _influence(session) == 8
    assert _power(session) == 2
    session.destroy()


def test_mind_flayer_option_1_devour_is_mandatory() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble", "soldier", "house_guard"]},
        current_player=_P1,
    )
    _play_card(session)
    _pick_modal_option(session, "option_1")
    assert _has_pending_generic(session)
    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    skip_moves = [m for m in gen_moves if m.data.get("action_id") is None]
    assert len(skip_moves) == 0
    targets = {m.data["action_id"] for m in gen_moves}
    assert "noble" in targets
    assert "soldier" in targets
    assert "house_guard" in targets
    session.destroy()


# ---------------------------------------------------------------------------
# Option 2: devour from hand → assassinate_troop
# ---------------------------------------------------------------------------


def test_mind_flayer_option_2_devour_then_assassinate_enemy() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        troops={_P1: {_SITE: [_P1, _P2, None, None, None]}},
        current_player=_P1,
    )
    _play_card(session)
    _pick_modal_option(session, "option_2")
    assert _has_pending_generic(session)
    _resolve_generic(session, "noble")
    assert _has_resolve_generic_moves(session)
    _resolve_generic(session, _SITE, "1")
    assert not _has_resolve_generic_moves(session)
    assert "noble" in _devour_pile(session)
    assert _P2 in _trophy_hall(session, _P1)
    session.destroy()


def test_mind_flayer_option_2_unavailable_when_only_own_troops() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        troops={_P1: {_SITE: [_P1, _P1, None, None, None]}},
        current_player=_P1,
    )
    _play_card(session)
    option_2_moves = [m for m in session.legal_moves()
                      if m.move_type == "resolve_generic" and m.data.get("action_id") == "option_2"]
    assert len(option_2_moves) == 1
    assert option_2_moves[0].data.get("target_id") == "unavailable"
    session.destroy()


def test_mind_flayer_option_2_devour_is_mandatory() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble", "soldier"]},
        troops={_P1: {_SITE: [_P1, _P2, None, None, None]}},
        current_player=_P1,
    )
    _play_card(session)
    _pick_modal_option(session, "option_2")
    assert _has_pending_generic(session)
    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    skip_moves = [m for m in gen_moves if m.data.get("action_id") is None]
    assert len(skip_moves) == 0
    card_targets = {m.data["action_id"] for m in gen_moves}
    assert "noble" in card_targets
    assert "soldier" in card_targets
    session.destroy()


def test_mind_flayer_option_2_assassinate_is_mandatory_when_targets_exist() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        troops={_P1: {_SITE: [_P1, _P2, None, None, None]}},
        current_player=_P1,
    )
    _play_card(session)
    _pick_modal_option(session, "option_2")
    _resolve_generic(session, "noble")
    assert _has_resolve_generic_moves(session)
    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    skip_moves = [m for m in gen_moves if m.data.get("action_id") is None]
    assert len(skip_moves) == 0
    session.destroy()


def test_mind_flayer_option_2_assassinate_white_troop() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        troops={_P1: {_SITE: [_P1, None, None, None, None]}},
        current_player=_P1,
    )
    _set_troop_slots(session, _SITE, [_P1, "white", None, None, None])
    _play_card(session)
    _pick_modal_option(session, "option_2")
    _resolve_generic(session, "noble")
    _resolve_generic(session, _SITE, "1")
    assert not _has_resolve_generic_moves(session)
    assert "noble" in _devour_pile(session)
    assert "white" in _trophy_hall(session, _P1)
    session.destroy()


# ---------------------------------------------------------------------------
# Full resolution tests
# ---------------------------------------------------------------------------


def test_mind_flayer_resolves_completely_after_option_1() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        current_player=_P1,
    )
    _play_card(session)
    _pick_modal_option(session, "option_1")
    _resolve_generic(session, "noble")
    assert not _has_resolve_generic_moves(session)
    move_types = {m.move_type for m in session.legal_moves()}
    assert "end_main_phase" in move_types
    session.destroy()


def test_mind_flayer_resolves_completely_after_option_2() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        troops={_P1: {_SITE: [_P1, _P2, None, None, None]}},
        current_player=_P1,
    )
    _play_card(session)
    _pick_modal_option(session, "option_2")
    _resolve_generic(session, "noble")
    _resolve_generic(session, _SITE, "1")
    assert not _has_resolve_generic_moves(session)
    move_types = {m.move_type for m in session.legal_moves()}
    assert "end_main_phase" in move_types
    session.destroy()


def test_mind_flayer_stays_in_played_cards_option_1() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        current_player=_P1,
    )
    _play_card(session)
    _pick_modal_option(session, "option_1")
    _resolve_generic(session, "noble")
    played = _played_cards_ids(session, _P1)
    assert _CARD in played
    assert _CARD not in _devour_pile(session)
    session.destroy()


def test_mind_flayer_stays_in_played_cards_option_2() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        troops={_P1: {_SITE: [_P1, _P2, None, None, None]}},
        current_player=_P1,
    )
    _play_card(session)
    _pick_modal_option(session, "option_2")
    _resolve_generic(session, "noble")
    _resolve_generic(session, _SITE, "1")
    played = _played_cards_ids(session, _P1)
    assert _CARD in played
    assert _CARD not in _devour_pile(session)
    session.destroy()


def test_mind_flayer_devoured_card_goes_to_devour_pile() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        current_player=_P1,
    )
    _play_card(session)
    _pick_modal_option(session, "option_1")
    _resolve_generic(session, "noble")
    devoured = _devour_pile(session)
    assert "noble" in devoured
    assert _CARD not in devoured
    session.destroy()


def test_mind_flayer_power_unchanged() -> None:
    eng = _make_engine()
    session = make_card_test_session(
        eng,
        [_P1, _P2],
        hand={_P1: [_CARD, "noble"]},
        current_player=_P1,
    )
    _sptr(session).contents.resource_pool.power = 0
    _play_card(session)
    _pick_modal_option(session, "option_1")
    _resolve_generic(session, "noble")
    assert _power(session) == 0
    session.destroy()
