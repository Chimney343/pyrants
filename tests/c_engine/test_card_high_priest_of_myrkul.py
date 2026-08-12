"""High Priest of Myrkul card behavior tests.

Two-action sequence:
- action_1 (immediate): return_unit [opponent_unit] — returns another player's troop or spy.
- action_2 (end_of_turn, optional, repeat_while_targets): promote_card [self]
  with required_secondary_aspect "undead" — at end of turn, promote any number
  of Undead cards played this turn (zero, one, some, or all).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine_c.bindings.engine_bindings import PHASE_END_OF_TURN, _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import _make_engine, _sptr, make_card_test_session

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_P1 = "p1"
_P2 = "p2"
_CARD = "high_priest_of_myrkul"
_SITE = "site_gauntlgrym"


# ── helpers ──────────────────────────────────────────────────────────────────

def _resolve_move_for_target(legal_moves, action_id, target_id):
    for m in legal_moves:
        d = m.data
        if m._move_type == "resolve_generic" and d.get("action_id") == action_id and d.get("target_id") == target_id:
            return m
    return None


def _played_ids(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].played_cards[j]).decode()
                    for j in range(s.players[i].played_cards_count)]
    return []


def _inner_circle_ids(session: CSession, pid: str) -> list[str]:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return [_lib.intern_str(s.players[i].inner_circle[j]).decode()
                    for j in range(s.players[i].inner_circle_count)]
    return []


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _player_barracks(session: CSession, pid: str) -> int:
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            return s.players[i].barracks
    return -1


def _set_played_cards(session: CSession, pid: str, card_ids: list[str]) -> None:
    """Inject cards directly into played_cards, bypassing play_card resolution."""
    s = _sptr(session).contents
    for i in range(s.player_count):
        if _lib.intern_str(s.players[i].player_id).decode() == pid:
            s.players[i].played_cards_count = min(len(card_ids), 80)
            for j, cid in enumerate(card_ids[:80]):
                s.players[i].played_cards[j] = _lib.intern(cid.encode())
            return


def _build_session(**kwargs):
    defaults = {
        "player_ids": [_P1, _P2],
        "hand": {_P2: [_CARD]},
        "troops": {
            _P1: {_SITE: [_P1, None]},
        },
        "current_player": _P2,
    }
    defaults.update(kwargs)
    eng = _make_engine()
    session = make_card_test_session(eng, defaults.pop("player_ids"), **defaults)
    return session


def _play_card(session: CSession, card_id: str = _CARD):
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError(f"{card_id} not playable")


def _end_main_phase(session: CSession):
    for m in session.legal_moves():
        if m.move_type == "end_main_phase":
            session.submit_move(m)
            return
    session.destroy()
    raise AssertionError("No end_main_phase move")


# ── tests ────────────────────────────────────────────────────────────────────

def _play_hp_and_return_unit(session: CSession) -> None:
    """Play High Priest and resolve the return_unit targeting p1's troop."""
    _play_card(session)
    assert _has_pending_generic(session), "Should await return_unit target selection"

    move = _resolve_move_for_target(session.legal_moves(), _SITE, "troop:0")
    assert move is not None, f"p1 troop at {_SITE} should be targetable"
    session.submit_move(move)

    assert not _has_pending_generic(session), "No pending generic after return + EOT promote intercept"


class TestHighPriestOfMyrkul:
    """C-engine behavior tests for High Priest of Myrkul."""

    def test_full_flow_returns_unit_and_promotes_undead(self) -> None:
        """Play HP, return opponent troop,
        have an undead + non-undead in played_cards,
        at EOT only undead appears as promote target."""
        session = _build_session()
        _play_hp_and_return_unit(session)

        _set_played_cards(session, _P2, ["ogre_zombie", "noble"])
        _end_main_phase(session)

        s = _sptr(session).contents
        assert s.phase == PHASE_END_OF_TURN, f"Expected END_OF_TURN, got {s.phase}"

        moves = session.legal_moves()
        move_types = {m.move_type for m in moves}
        assert "promote_card" in move_types, f"Should have promote_card, got: {move_types}"
        assert "skip_promote" in move_types, f"Should have skip_promote, got: {move_types}"

        promote_moves = [m for m in moves if m.move_type == "promote_card"]
        promote_targets = {m.data.get("card_id") for m in promote_moves}
        assert "ogre_zombie" in promote_targets, f"Undead ogre_zombie should be a promote target, got: {promote_targets}"
        assert "noble" not in promote_targets, f"Non-undead noble should NOT be a promote target: {promote_targets}"

        ogre_promote = [m for m in promote_moves if m.data.get("card_id") == "ogre_zombie"][0]
        session.submit_move(ogre_promote)

        assert "ogre_zombie" in _inner_circle_ids(session, _P2), "Ogre Zombie should be promoted"
        assert "ogre_zombie" not in _played_ids(session, _P2), "Ogre Zombie removed from played_cards"
        assert "noble" in _played_ids(session, _P2), "Noble should still be in played_cards"

        moves2 = session.legal_moves()
        move_types2 = {m.move_type for m in moves2}
        assert "resolve_end_of_turn" in move_types2, (
            f"After promoting the only undead card, should resolve EOT. Got: {move_types2}"
        )

        session.destroy()

    def test_skip_all_promotions(self) -> None:
        """Play HP, return opponent troop, have undead card, skip EOT promote."""
        session = _build_session()
        _play_hp_and_return_unit(session)

        _set_played_cards(session, _P2, ["ogre_zombie"])
        _end_main_phase(session)

        s = _sptr(session).contents
        assert s.phase == PHASE_END_OF_TURN

        moves = session.legal_moves()
        skip_moves = [m for m in moves if m.move_type == "skip_promote"]
        assert len(skip_moves) == 1, "Should have skip_promote"
        session.submit_move(skip_moves[0])

        moves2 = session.legal_moves()
        move_types2 = {m.move_type for m in moves2}
        assert "resolve_end_of_turn" in move_types2, f"Should resolve EOT after skip. Got: {move_types2}"
        assert "ogre_zombie" not in _inner_circle_ids(session, _P2), "Ogre Zombie should NOT be promoted after skip"
        assert "ogre_zombie" in _played_ids(session, _P2), "Ogre Zombie should remain in played_cards"

        session.destroy()

    def test_promote_zero_when_no_undead_played(self) -> None:
        """Only non-undead cards in played_cards, EOT should resolve cleanly."""
        session = _build_session()
        _play_hp_and_return_unit(session)

        _set_played_cards(session, _P2, ["noble"])
        _end_main_phase(session)

        s = _sptr(session).contents
        assert s.phase == PHASE_END_OF_TURN

        moves = session.legal_moves()
        move_types = {m.move_type for m in moves}

        if "resolve_end_of_turn" in move_types:
            session.submit_move([m for m in moves if m.move_type == "resolve_end_of_turn"][0])
        elif "skip_promote" in move_types:
            session.submit_move([m for m in moves if m.move_type == "skip_promote"][0])
        else:
            session.destroy()
            raise AssertionError(f"EOT should be resolvable, got: {move_types}")

        session.destroy()

    def test_promote_multiple_undead_step_by_step(self) -> None:
        """Two undead + one non-undead in played_cards.
        At EOT, both undead appear. Promote one, second still available.
        Promote second, then resolve EOT. Verify both promoted, non-undead stays."""
        session = _build_session()
        _play_hp_and_return_unit(session)

        _set_played_cards(session, _P2, ["ogre_zombie", "ravenous_zombies", "noble"])
        _end_main_phase(session)

        s = _sptr(session).contents
        assert s.phase == PHASE_END_OF_TURN

        moves = session.legal_moves()
        move_types = {m.move_type for m in moves}
        assert "promote_card" in move_types
        assert "skip_promote" in move_types

        promote_targets = {m.data.get("card_id") for m in moves if m.move_type == "promote_card"}
        assert "ogre_zombie" in promote_targets
        assert "ravenous_zombies" in promote_targets
        assert "noble" not in promote_targets

        ogre_moves = [m for m in moves if m.move_type == "promote_card" and m.data.get("card_id") == "ogre_zombie"]
        session.submit_move(ogre_moves[0])
        assert "ogre_zombie" in _inner_circle_ids(session, _P2)
        assert "ogre_zombie" not in _played_ids(session, _P2)

        moves2 = session.legal_moves()
        move_types2 = {m.move_type for m in moves2}
        assert "promote_card" in move_types2, f"Second promotion round: should still offer promote_card. Got: {move_types2}"
        promote_targets2 = {m.data.get("card_id") for m in moves2 if m.move_type == "promote_card"}
        assert "ogre_zombie" not in promote_targets2, "Already promoted, should not appear again"
        assert "ravenous_zombies" in promote_targets2, "Still an undead target"

        raven = [m for m in moves2 if m.move_type == "promote_card" and m.data.get("card_id") == "ravenous_zombies"][0]
        session.submit_move(raven)
        assert "ravenous_zombies" in _inner_circle_ids(session, _P2)
        assert "ravenous_zombies" not in _played_ids(session, _P2)

        moves3 = session.legal_moves()
        move_types3 = {m.move_type for m in moves3}
        assert "resolve_end_of_turn" in move_types3, (
            f"After all undead promoted, should resolve EOT. Got: {move_types3}"
        )
        assert "noble" in _played_ids(session, _P2), "Non-undead noble should remain in played_cards"

        session.destroy()

    def test_returns_opponent_troop_increments_barracks(self) -> None:
        """Verify that returning an opponent's troop increments their barracks."""
        session = _build_session()

        p1_barracks_before = _player_barracks(session, _P1)
        _play_hp_and_return_unit(session)

        assert _player_barracks(session, _P1) == p1_barracks_before + 1, (
            f"Opponent barracks should increase after troop return: "
            f"{p1_barracks_before} -> {_player_barracks(session, _P1)}"
        )

        session.destroy()

    def test_skip_both_promotions_with_two_undead(self) -> None:
        """Two undead in played_cards: skip promotion, verify none promoted and EOT resolves."""
        session = _build_session()
        _play_hp_and_return_unit(session)

        _set_played_cards(session, _P2, ["ogre_zombie", "ravenous_zombies"])
        _end_main_phase(session)

        s = _sptr(session).contents
        assert s.phase == PHASE_END_OF_TURN

        moves = session.legal_moves()
        skip_moves = [m for m in moves if m.move_type == "skip_promote"]
        assert len(skip_moves) == 1
        session.submit_move(skip_moves[0])

        assert "ogre_zombie" not in _inner_circle_ids(session, _P2)
        assert "ravenous_zombies" not in _inner_circle_ids(session, _P2)
        assert "ogre_zombie" in _played_ids(session, _P2)
        assert "ravenous_zombies" in _played_ids(session, _P2)

        moves2 = session.legal_moves()
        move_types2 = {m.move_type for m in moves2}
        assert "resolve_end_of_turn" in move_types2, (
            f"After skipping, should resolve EOT. Got: {move_types2}"
        )

        session.destroy()
