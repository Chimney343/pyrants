"""Scoring mechanic tests: trophies, vp_tokens, controlled sites, final scores.

Locks in the behaviours fixed during the Red Dragon card review:
  1. White troops give trophies (not excluded).
  2. Trophies don't change ps->score; viewer sums them separately.
  3. grant_vp with as:vp_tokens changes vp_tokens only, not score.
  4. grant_vp without as:vp_tokens changes score only.
  5. count_controlled_sites = exclusive (total) control, not majority.
  6. compute_final_scores includes trophies + vp_tokens.
"""
from __future__ import annotations

import ctypes

from engine_c.bindings.engine_bindings import _lib
from engine_c.bindings.session import CSession
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

P1 = "p1"
P2 = "p2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _player_score(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].score


def _trophy_count(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].trophy_hall_count


def _add_trophies(session: CSession, pid: str, count: int, label: str = b"p2") -> None:
    s = _sptr(session).contents
    pi = _session_player_index(session, pid)
    ps = s.players[pi]
    for _ in range(count):
        if ps.trophy_hall_count < 50:
            ps.trophy_hall[ps.trophy_hall_count] = _lib.intern(label)
            ps.trophy_hall_count += 1


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    raise RuntimeError(f"{card_id} not in legal moves")


def _resolve_all_generics(session: CSession) -> int:
    count = 0
    while True:
        gens = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
        if not gens:
            break
        session.submit_move(gens[0])
        count += 1
    return count


def _count_controlled_sites(session: CSession, pid: str) -> int:
    """Direct call to C engine's count_controlled_sites."""
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    player_sym = _sptr(session).contents.players[pi].player_id
    _lib.count_controlled_sites.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    _lib.count_controlled_sites.restype = ctypes.c_int
    return _lib.count_controlled_sites(_sptr(session), player_sym)


def _compute_final_score(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    scores = (ctypes.c_int * 4)()
    _lib.compute_final_scores(_sptr(session), scores)
    return scores[pi]


def _player_vp_tokens_raw(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].vp_tokens


# ---------------------------------------------------------------------------
# Trophy mechanics
# ---------------------------------------------------------------------------

class TestTrophyScoring:
    """Taking a trophy increases trophy_hall_count but NOT ps->score."""

    def test_white_troop_supplant_adds_to_trophy_hall(self):
        """Supplanting a white troop puts 'white' in the trophy hall."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={P1: ["red_dragon"]},
            troops={P1: {"site_gauntlgrym": [P1, "white", None, None]}},
            spies={},
            current_player=P1,
        )
        tc_before = _trophy_count(session, P1)

        _play_card(session, "red_dragon")
        supplant = [m for m in session.legal_moves()
                    if m.move_type == "resolve_generic"
                    and m.data.get("action_id") == "site_gauntlgrym"
                    and m.data.get("target_id") == "1"]
        assert supplant, "White troop at slot 1 should be supplantable"
        session.submit_move(supplant[0])

        tc_after = _trophy_count(session, P1)
        assert tc_after == tc_before + 1, (
            f"White trophy should be added: {tc_before} → {tc_after}"
        )
        session.destroy()

    def test_player_troop_supplant_adds_to_trophy_hall(self):
        """Supplanting an enemy player's troop puts their ID in trophy hall."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={P1: ["red_dragon"]},
            troops={P1: {"site_gauntlgrym": [P1, P2, None, None]}},
            spies={},
            current_player=P1,
        )
        tc_before = _trophy_count(session, P1)

        _play_card(session, "red_dragon")
        supplant = [m for m in session.legal_moves()
                    if m.move_type == "resolve_generic"
                    and m.data.get("action_id") == "site_gauntlgrym"
                    and m.data.get("target_id") == "1"]
        assert supplant, "P2 troop at slot 1 should be supplantable"
        session.submit_move(supplant[0])

        tc_after = _trophy_count(session, P1)
        assert tc_after == tc_before + 1, (
            f"Player trophy should be added: {tc_before} → {tc_after}"
        )
        session.destroy()

    def test_trophy_does_not_change_score(self):
        """Adding a trophy must not increase ps->score (viewer sums separately)."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={P1: ["red_dragon"]},
            troops={P1: {"site_gauntlgrym": [P1, "white", None, None]}},
            spies={},
            current_player=P1,
        )
        score_before = _player_score(session, P1)
        tc_before = _trophy_count(session, P1)

        _play_card(session, "red_dragon")
        supplant = [m for m in session.legal_moves()
                    if m.move_type == "resolve_generic"
                    and m.data.get("action_id") == "site_gauntlgrym"
                    and m.data.get("target_id") == "1"]
        session.submit_move(supplant[0])

        assert _trophy_count(session, P1) == tc_before + 1, "Trophy must be added"
        assert _player_score(session, P1) == score_before, (
            f"Score must NOT change on trophy: was {score_before}, now {_player_score(session, P1)}"
        )
        session.destroy()

    def test_white_troop_assassinate_adds_to_trophy_hall(self):
        """Assassinating a white troop adds trophy (Quaggoth card)."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={P1: ["quaggoth"]},
            troops={P1: {"site_gauntlgrym": [P1, "white", None, None]}},
            spies={},
            current_player=P1,
        )
        tc_before = _trophy_count(session, P1)

        _play_card(session, "quaggoth")
        gens = [m for m in session.legal_moves()
                if m.move_type == "resolve_generic"]
        assert gens, "Quaggoth should have assassinate targets"
        session.submit_move(gens[0])

        tc_after = _trophy_count(session, P1)
        assert tc_after == tc_before + 1, (
            f"Assassinating white troop must add trophy: {tc_before} → {tc_after}"
        )
        session.destroy()


# ---------------------------------------------------------------------------
# VP token scoring
# ---------------------------------------------------------------------------

class TestVPTokenScoring:
    """grant_vp with as:vp_tokens updates vp_tokens, not score."""

    def test_grant_vp_as_tokens_updates_vp_tokens_not_score(self):
        """Red Dragon's grant_vp (as:vp_tokens) -> vp_tokens up, score unchanged."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={P1: ["red_dragon"]},
            troops={
                P1: {
                    "site_gauntlgrym": [P1, P2],
                },
            },
            spies={"site_gauntlgrym": [P2]},
            current_player=P1,
        )
        score_before = _player_score(session, P1)
        vp_before = _player_vp_tokens_raw(session, P1)

        _play_card(session, "red_dragon")
        _resolve_all_generics(session)

        assert _player_vp_tokens_raw(session, P1) > vp_before, (
            "vp_tokens should increase from grant_vp"
        )
        assert _player_score(session, P1) == score_before, (
            f"Score must NOT change from as:vp_tokens grant_vp: "
            f"was {score_before}, now {_player_score(session, P1)}"
        )
        session.destroy()

    def test_grant_vp_without_as_tokens_updates_score(self):
        """Death Knight grant_vp: 1 VP per 5 non-white trophies, rounded down."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={P1: ["death_knight"]},
            troops={P1: {"site_gauntlgrym": [P1, P2, None, None]}},
            spies={},
            current_player=P1,
        )
        _add_trophies(session, P1, 10, b"p2")

        score_before = _player_score(session, P1)
        vp_before = _player_vp_tokens_raw(session, P1)

        _play_card(session, "death_knight")
        _resolve_all_generics(session)

        expected_score = score_before + 2
        assert _player_score(session, P1) == expected_score, (
            f"Death Knight should grant floor(11/5)=2 VP. "
            f"10 initial trophies + 1 from supplant = 11, /5 = 2. "
            f"Got score {_player_score(session, P1)}, expected {expected_score}"
        )
        assert _player_vp_tokens_raw(session, P1) == vp_before, (
            "vp_tokens must NOT change from non-token grant_vp"
        )
        session.destroy()

    def test_death_knight_white_trophies_excluded(self):
        """Death Knight ignores white trophies; only player trophies count."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={P1: ["death_knight"]},
            troops={P1: {"site_gauntlgrym": [P1, P2, None, None]}},
            spies={},
            current_player=P1,
        )
        _add_trophies(session, P1, 4, b"p2")
        _add_trophies(session, P1, 5, b"white")

        score_before = _player_score(session, P1)

        _play_card(session, "death_knight")
        _resolve_all_generics(session)

        expected_score = score_before + 1
        assert _player_score(session, P1) == expected_score, (
            f"Death Knight must ignore white trophies. "
            f"4 player + 1 from supplant = 5 player trophies, /5 = 1 VP. "
            f"Got score {_player_score(session, P1)}, expected {expected_score}"
        )
        session.destroy()

    def test_death_knight_rounds_down(self):
        """Death Knight rounds down: 14 player trophies → floor(14/5)=2 VP,
        and the supplant adds one more, so 15/5=3 VP from trophy scaling."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={P1: ["death_knight"]},
            troops={P1: {"site_gauntlgrym": [P1, P2, None, None]}},
            spies={},
            current_player=P1,
        )
        _add_trophies(session, P1, 14, b"p2")

        score_before = _player_score(session, P1)

        _play_card(session, "death_knight")
        _resolve_all_generics(session)

        expected_score = score_before + 3
        assert _player_score(session, P1) == expected_score, (
            f"Death Knight must round down. "
            f"14 initial + 1 from supplant = 15 player trophies, /5 = 3 VP. "
            f"Got score {_player_score(session, P1)}, expected {expected_score}"
        )
        session.destroy()

    def test_death_knight_zero_player_trophies(self):
        """Death Knight with no player trophies: supplant adds 1 trophy,
        floor(1/5)=0 VP from scaling, no score change."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={P1: ["death_knight"]},
            troops={P1: {"site_gauntlgrym": [P1, P2, None, None]}},
            spies={},
            current_player=P1,
        )

        score_before = _player_score(session, P1)

        _play_card(session, "death_knight")
        _resolve_all_generics(session)

        assert _player_score(session, P1) == score_before, (
            f"Death Knight with 0 initial trophies should grant 0 VP. "
            f"1 from supplant, /5 = 0. "
            f"Got score {_player_score(session, P1)}, expected {score_before}"
        )
        session.destroy()


# ---------------------------------------------------------------------------
# Controlled sites = exclusive (total) control
#   Tested indirectly via Red Dragon's grant_vp: vp_tokens awarded
#   must match exclusive controlled sites, not majority.
# ---------------------------------------------------------------------------

class TestControlledSites:
    """count_controlled_sites = exclusive (total) control, not majority.
    Tested directly via the exported C function."""

    def test_exclusive_site_counts_two(self):
        """Two exclusive sites, one shared → count_controlled_sites == 2."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={},
            troops={
                P1: {
                    "site_gauntlgrym": [P1, P2, None, None],   # shared
                    "site_jhachalkhyn": [P1, P1, None, None],  # exclusive
                    "site_gracklstugh": [P1, None, None, None],# exclusive
                },
            },
            spies={},
            current_player=P1,
        )
        cs = _count_controlled_sites(session, P1)
        assert cs == 2, (
            f"2 exclusive sites should count, shared should not. Got {cs}"
        )
        session.destroy()

    def test_site_with_white_troop_counts(self):
        """Site with p1 majority over white troops counts (white is not a player)."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={},
            troops={
                P1: {
                    "site_gauntlgrym": [P1, P1, "white", None],
                },
            },
            spies={},
            current_player=P1,
        )
        cs = _count_controlled_sites(session, P1)
        assert cs == 1, (
            f"Site with p1 majority over white should count as controlled, got {cs}"
        )
        session.destroy()

    def test_site_with_enemy_troop_does_not_count(self):
        """Site with p1 + p2 does NOT count as controlled."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={},
            troops={
                P1: {
                    "site_gauntlgrym": [P1, P2, None, None],
                },
            },
            spies={},
            current_player=P1,
        )
        cs = _count_controlled_sites(session, P1)
        assert cs == 0, (
            f"Site with p1+p2 should NOT count, got {cs}"
        )
        session.destroy()

    def test_multiple_exclusive_sites(self):
        """Three exclusive sites → count_controlled_sites == 3."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2],
            hand={},
            troops={
                P1: {
                    "site_gauntlgrym": [P1, None, None, None],
                    "site_jhachalkhyn": [P1, P1, None, None],
                    "site_gracklstugh": [P1, P1, P1, None],
                },
            },
            spies={},
            current_player=P1,
        )
        cs = _count_controlled_sites(session, P1)
        assert cs == 3, (
            f"All 3 exclusive sites should count, got {cs}"
        )
        session.destroy()


# ---------------------------------------------------------------------------
# compute_final_scores
# ---------------------------------------------------------------------------

class TestFinalScores:
    """compute_final_scores sums score + trophies + vp_tokens + ..."""

    def test_trophies_included_in_final_score(self):
        """Final score increases by trophy count when trophies are added."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2], hand={}, troops={}, spies={}, current_player=P1,
        )
        score1 = _compute_final_score(session, P1)
        _add_trophies(session, P1, 5, b"white")
        score2 = _compute_final_score(session, P1)
        assert score2 == score1 + 5, (
            f"Final score should increase by trophy count: {score1} → {score2}"
        )
        session.destroy()

    def test_vp_tokens_included_in_final_score(self):
        """Final score increases by vp_tokens count."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2], hand={}, troops={}, spies={}, current_player=P1,
        )
        score1 = _compute_final_score(session, P1)
        s = _sptr(session).contents
        pi = _session_player_index(session, P1)
        s.players[pi].vp_tokens = 7
        score2 = _compute_final_score(session, P1)
        assert score2 == score1 + 7, (
            f"Final score should increase by vp_tokens: {score1} → {score2}"
        )
        session.destroy()

    def test_final_score_includes_both_trophies_and_tokens(self):
        """Both components contribute to the final total."""
        eng = _make_engine()
        session = make_card_test_session(
            eng, [P1, P2], hand={}, troops={}, spies={}, current_player=P1,
        )
        score_before = _compute_final_score(session, P1)

        _add_trophies(session, P1, 3, b"white")
        s = _sptr(session).contents
        pi = _session_player_index(session, P1)
        s.players[pi].vp_tokens = 4

        score_after = _compute_final_score(session, P1)
        assert score_after == score_before + 3 + 4, (
            f"Final score should include trophies (3) + vp_tokens (4): "
            f"{score_before} → {score_after}"
        )
        session.destroy()


# ---------------------------------------------------------------------------
# Total control end-game bonus (+2 VP per total-control site at final tally)
#   `award_end_of_turn_site_vp` (per-turn, uses total_control_vp_per_turn)
#   is an unrelated in-game scoring feature and stays unchanged.
# ---------------------------------------------------------------------------

# Site used for these tests:
#   site_jhachalkhyn: troop_capacity=4, control_vp=4, total_control_vp_per_turn=0
#   site_gracklstugh: troop_capacity=4, control_vp=3, total_control_vp_per_turn=0
# Both have total_control_vp_per_turn=0 so the per-turn mechanism contributes
# nothing; the only levers are control_vp (majority) and the new +2 bonus.
_TOTAL_CONTROL_SITE_1 = "site_jhachalkhyn"
_TOTAL_CONTROL_SITE_2 = "site_gracklstugh"


class TestTotalControlFinalBonus:
    """compute_final_scores awards +2 VP per site under total control at end of
    game, on top of normal control_vp. Distinct from the per-turn award."""

    def test_total_control_grants_plus_2_over_majority_baseline(self):
        """Same site, same control_vp, only difference is total control.

        Setup A: [P1,P1,P1,None]  -> majority, NOT total control.
        Setup B: [P1,P1,P1,P1]    -> total control (all slots P1, no enemy spies).

        The only thing that should change between A and B is the +2 bonus.
        """
        eng = _make_engine()
        session_a = make_card_test_session(
            eng, [P1, P2], hand={},
            troops={P1: {_TOTAL_CONTROL_SITE_1: [P1, P1, P1, None]}},
            spies={}, current_player=P1,
        )
        score_a = _compute_final_score(session_a, P1)
        session_a.destroy()

        session_b = make_card_test_session(
            eng, [P1, P2], hand={},
            troops={P1: {_TOTAL_CONTROL_SITE_1: [P1, P1, P1, P1]}},
            spies={}, current_player=P1,
        )
        score_b = _compute_final_score(session_b, P1)
        session_b.destroy()

        assert score_b - score_a == 2, (
            f"Total control should grant +2 VP on top of control_vp. "
            f"Score A (majority, no total control) = {score_a}, "
            f"Score B (total control) = {score_b}, "
            f"delta = {score_b - score_a}, expected 2."
        )

    def test_multiple_total_control_sites_scale(self):
        """Two total-control sites -> +4 over the same majority-only baseline."""
        eng = _make_engine()
        session_majority = make_card_test_session(
            eng, [P1, P2], hand={},
            troops={P1: {
                _TOTAL_CONTROL_SITE_1: [P1, P1, P1, None],
                _TOTAL_CONTROL_SITE_2: [P1, P1, P1, None],
            }},
            spies={}, current_player=P1,
        )
        score_majority = _compute_final_score(session_majority, P1)
        session_majority.destroy()

        session_total = make_card_test_session(
            eng, [P1, P2], hand={},
            troops={P1: {
                _TOTAL_CONTROL_SITE_1: [P1, P1, P1, P1],
                _TOTAL_CONTROL_SITE_2: [P1, P1, P1, P1],
            }},
            spies={}, current_player=P1,
        )
        score_total = _compute_final_score(session_total, P1)
        session_total.destroy()

        assert score_total - score_majority == 4, (
            f"Two total-control sites should grant +4 VP (2 each). "
            f"Majority baseline = {score_majority}, total = {score_total}, "
            f"delta = {score_total - score_majority}, expected 4."
        )

    def test_enemy_spy_on_total_control_site_cancels_bonus(self):
        """An enemy spy at the site breaks total control -> no +2 bonus,
        even if every troop slot is the player's."""
        eng = _make_engine()
        session_spy = make_card_test_session(
            eng, [P1, P2], hand={},
            troops={P1: {_TOTAL_CONTROL_SITE_1: [P1, P1, P1, P1]}},
            spies={_TOTAL_CONTROL_SITE_1: [P2]},
            current_player=P1,
        )
        score_spy = _compute_final_score(session_spy, P1)
        session_spy.destroy()

        session_total = make_card_test_session(
            eng, [P1, P2], hand={},
            troops={P1: {_TOTAL_CONTROL_SITE_1: [P1, P1, P1, P1]}},
            spies={}, current_player=P1,
        )
        score_total = _compute_final_score(session_total, P1)
        session_total.destroy()

        session_majority = make_card_test_session(
            eng, [P1, P2], hand={},
            troops={P1: {_TOTAL_CONTROL_SITE_1: [P1, P1, P1, None]}},
            spies={}, current_player=P1,
        )
        score_majority = _compute_final_score(session_majority, P1)
        session_majority.destroy()

        # Spy cancels the +2 bonus: spy setup scores the same as majority.
        assert score_spy == score_majority, (
            f"Enemy spy should cancel total-control bonus. "
            f"Spy score = {score_spy}, majority score = {score_majority}"
        )
        # And the bonus would otherwise apply:
        assert score_total - score_spy == 2, (
            f"Without the spy the bonus should reappear. "
            f"Total = {score_total}, spy = {score_spy}, "
            f"delta = {score_total - score_spy}, expected 2."
        )
