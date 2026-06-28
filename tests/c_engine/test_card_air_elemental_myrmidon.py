"""Air Elemental Myrmidon: Place a spy, then at EOT promote an Obedience card."""

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


def _spies_at_node(session: CSession, node_id: str) -> list[str]:
    s = _sptr(session).contents
    nid_sym = _lib.intern(node_id.encode())
    for i in range(s.node_count):
        if s.nodes[i].node_id == nid_sym:
            return [_lib.intern_str(s.nodes[i].spies[j]).decode()
                    for j in range(s.nodes[i].spy_count)]
    return []


def _inner_circle_count(session: CSession, pid: str) -> int:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return s.players[i].inner_circle_count
    return 0


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


_SPY_SITE = "site_gauntlgrym"


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


def test_air_elemental_myrmidon_places_spy_and_promotes_obedience_at_eot():
    """Play Air Elemental Myrmidon: place spy immediately, then promote Noble at EOT."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["noble", "air_elemental_myrmidon"]},
        current_player="p1",
    )

    # Play Noble first so it's in played_cards and can be promoted at EOT.
    _play_card(session, "noble")
    assert "noble" in _played_ids(session, "p1")

    # Play Air Elemental Myrmidon.
    _play_card(session, "air_elemental_myrmidon")
    assert _has_pending_generic(session), "Should await spy placement selection"

    # Spy placement: select a site.
    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    site_moves = [m for m in gen_moves if m.data.get("action_id") == _SPY_SITE]
    assert len(site_moves) >= 1, f"Should have spy placement move for {_SPY_SITE}, got: {[m.data for m in gen_moves]}"
    session.submit_move(site_moves[0])

    # Spy should now be at the site.
    assert "p1" in _spies_at_node(session, _SPY_SITE), "Spy should be placed at selected site"

    # Card fully resolved — no more generic pending choices.
    assert not _has_pending_generic(session), "Should be no pending generic after spy placement"

    # End main phase → END_OF_TURN.
    _submit_move_of_type(session, "end_main_phase")
    s = _sptr(session).contents
    assert s.phase == PHASE_END_OF_TURN, f"Expected END_OF_TURN phase, got {s.phase}"

    # EOT: should have promote_card for Noble (Obedience).
    moves = session.legal_moves()
    move_types = {m._move_type for m in moves}
    assert "promote_card" in move_types, f"Should have promote_card, got: {move_types}"

    promote_moves = [m for m in moves if m._move_type == "promote_card"]
    promote_targets = {m.data.get("card_id") for m in promote_moves}
    assert "noble" in promote_targets, f"Noble should be a promote target, got: {promote_targets}"
    assert "air_elemental_myrmidon" not in promote_targets, (
        "Air Elemental Myrmidon is Guile, should not be a promote target "
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
    assert "promote_card" not in move_types2, f"Only one promotion allowed, got: {move_types2}"
    assert "resolve_end_of_turn" in move_types2, (
        f"Should resolve EOT after promotion, got: {move_types2}"
    )

    _submit_move_of_type(session, "resolve_end_of_turn")
    _submit_move_of_type(session, "resolve_cleanup")
    session.destroy()


def test_air_elemental_myrmidon_promotion_label_includes_aspect():
    """The promotion label at EOT should show the required aspect (Obedience)."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["noble", "air_elemental_myrmidon"]},
        current_player="p1",
    )

    _play_card(session, "noble")
    _play_card(session, "air_elemental_myrmidon")

    # Resolve spy placement.
    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    site_moves = [m for m in gen_moves if m.data.get("action_id") == _SPY_SITE]
    session.submit_move(site_moves[0])

    # End main phase → EOT.
    _submit_move_of_type(session, "end_main_phase")

    # Check the promotion move label via the enriched view.
    view = build_c_game_view(session)
    promote_moves = [m for m in view.legal_moves if m.move_type == "promote_card"]
    assert len(promote_moves) >= 1, "Should have at least one promote_card move"

    noble_move = [m for m in promote_moves if m.move.data.get("card_id") == "noble"][0]
    label = noble_move.label
    assert "Obedience" in label, (
        f"Promotion label should include aspect (Obedience). Got: {label}"
    )

    session.destroy()


def test_air_elemental_myrmidon_no_obedience_card_skip_available():
    """If no Obedience card is in played_cards, skip_promote should be available."""
    eng = _make_engine()
    session = make_card_test_session(
        eng, ["p1", "p2"],
        hand={"p1": ["air_elemental_myrmidon"]},
        current_player="p1",
    )

    _play_card(session, "air_elemental_myrmidon")

    # Resolve spy placement.
    gen_moves = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
    site_moves = [m for m in gen_moves if m.data.get("action_id") == _SPY_SITE]
    session.submit_move(site_moves[0])

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
    assert "resolve_end_of_turn" in move_types2, (
        f"After skip, should have resolve_end_of_turn, got: {move_types2}"
    )

    session.destroy()
