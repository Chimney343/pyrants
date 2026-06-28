"""Water Elemental Myrmidon: Assassinate white troop, then at EOT promote an Obedience card."""

from __future__ import annotations

from engine_c.bindings.engine_bindings import PHASE_END_OF_TURN, _lib
from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import _make_engine, _sptr, make_card_test_session


def _inner_circle_ids(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].inner_circle[j]).decode()
                    for j in range(s.players[i].inner_circle_count)]
    return []


def _played_ids(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].played_cards[j]).decode()
                    for j in range(s.players[i].played_cards_count)]
    return []


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _troop_slots(session: CSession, node_id: str) -> list[str | None]:
    s = _sptr(session).contents
    nid_sym = _lib.intern(node_id.encode())
    for i in range(s.node_count):
        if s.nodes[i].node_id == nid_sym:
            slots = []
            for j in range(s.nodes[i].troop_slot_count):
                occ = s.nodes[i].troop_slots[j]
                slots.append(_lib.intern_str(occ).decode() if occ else None)
            return slots
    return []


_ASSN_SITE = "site_gauntlgrym"


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m._move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not in hand")


def _submit_move_of_type(session: CSession, move_type: str):
    for m in session.legal_moves():
        if m._move_type == move_type:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"No move of type {move_type}")


def test_water_elemental_myrmidon_assassinates_white_and_promotes_obedience_at_eot():
    """Play Water Elemental Myrmidon: assassinate white troop, then promote Noble at EOT."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["noble", "water_elemental_myrmidon"]},
        troops={"p1": {_ASSN_SITE: ["p1", "white", None]}},
        current_player="p1",
    )

    # Play Noble first so it's in played_cards and can be promoted at EOT.
    _play_card(session, "noble")
    assert "noble" in _played_ids(session, "p1")

    # Play Water Elemental Myrmidon.
    _play_card(session, "water_elemental_myrmidon")
    assert _has_pending_generic(session), "Should await assassination selection"

    # Assassinate: select a white troop at a site.
    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assn_moves = [m for m in gen_moves if m.data.get("action_id") == _ASSN_SITE]
    assert len(assn_moves) >= 1, f"Should have assassination move for {_ASSN_SITE}"
    session.submit_move(assn_moves[0])

    # White troop should be gone from the site.
    slots = _troop_slots(session, _ASSN_SITE)
    assert "white" not in slots, f"White troop should be assassinated, got: {slots}"

    # Card fully resolved.
    assert not _has_pending_generic(session)

    # End main phase → END_OF_TURN.
    _submit_move_of_type(session, "end_main_phase")
    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    # EOT: should have promote_card for Noble (Obedience).
    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}
    assert "promote_card" in move_types, f"Should have promote_card, got: {move_types}"

    promote_moves = [m for m in moves if m._move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert "noble" in promote_targets, f"Noble should be a promote target, got: {promote_targets}"
    assert "water_elemental_myrmidon" not in promote_targets, (
        "Water Elemental Myrmidon is Conquest, should not be a promote target "
        "(required_aspect=obedience)"
    )

    # Promote Noble.
    noble_move = [m for m in promote_moves if m.data.get("card_id") == "noble"][0]
    session.submit_move(noble_move)

    assert "noble" in _inner_circle_ids(session, "p1"), "Noble should be promoted to inner_circle"
    assert "noble" not in _played_ids(session, "p1"), "Noble should be removed from played_cards"

    # Only one promotion — resolve EOT.
    moves2 = session.legal_moves()
    move_types2 = {m._move_type for m in moves2}
    assert "promote_card" not in move_types2
    assert "resolve_end_of_turn" in move_types2

    _submit_move_of_type(session, "resolve_end_of_turn")
    _submit_move_of_type(session, "resolve_cleanup")
    session.destroy()




def test_water_elemental_myrmidon_promotion_label_includes_aspect():
    """The promotion label at EOT should show the required aspect (Obedience)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["noble", "water_elemental_myrmidon"]},
        troops={"p1": {_ASSN_SITE: ["p1", "white", None]}},
        current_player="p1",
    )

    _play_card(session, "noble")
    _play_card(session, "water_elemental_myrmidon")

    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assn_moves = [m for m in gen_moves if m.data.get("action_id") == _ASSN_SITE]
    session.submit_move(assn_moves[0])

    _submit_move_of_type(session, "end_main_phase")

    view = build_c_game_view(session)
    promote_moves = [m for m in view.legal_moves if m.move_type == "promote_card"]
    assert len(promote_moves) >= 1, "Should have at least one promote_card move"

    noble_move = [m for m in promote_moves if m.move.data.get("card_id") == "noble"][0]
    label = noble_move.label
    assert "Obedience" in label, (
        f"Promotion label should include aspect (Obedience). Got: {label}"
    )

    session.destroy()


def test_water_elemental_myrmidon_skip_when_no_obedience_card_played():
    """If only Water Elemental Myrmidon is played (no Obedience card), skip_promote is the only option."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["water_elemental_myrmidon"]},
        troops={"p1": {_ASSN_SITE: ["p1", "white", None]}},
        current_player="p1",
    )

    # Play Water Elemental Myrmidon (Conquest, not Obedience).
    _play_card(session, "water_elemental_myrmidon")

    # Resolve assassination.
    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    assn_moves = [m for m in gen_moves if m.data.get("action_id") == _ASSN_SITE]
    session.submit_move(assn_moves[0])

    assert not _has_pending_generic(session)

    # End main phase → EOT.
    _submit_move_of_type(session, "end_main_phase")
    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN

    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}
    assert "promote_card" not in move_types, (
        f"No Obedience card played, should not have promote_card, got: {move_types}"
    )
    assert "skip_promote" in move_types, (
        f"Should have skip_promote when no valid targets, got: {move_types}"
    )

    skip = [m for m in moves if m._move_type == "skip_promote"][0]
    session.submit_move(skip)

    moves2 = session.legal_moves()
    move_types2 = {m._move_type for m in moves2}
    assert "resolve_end_of_turn" in move_types2

    _submit_move_of_type(session, "resolve_end_of_turn")
    _submit_move_of_type(session, "resolve_cleanup")
    session.destroy()
