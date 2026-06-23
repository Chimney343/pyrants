"""Test game terminality: end-of-round kill switches (barracks/market).

Verifies that kill switches (barracks==0, market deck empty) do NOT
immediately terminate the game. The game continues until the round
completes (last player's cleanup).
"""
from engine_c.bindings.session import CSession


def _load_session(scenario_path: str) -> CSession:
    return CSession.load(scenario_path)


def _play_card(session: CSession, card_id: str) -> None:
    for m in session.legal_moves():
        if m.move_type == "play_card" and m.data.get("card_id") == card_id:
            session.submit_move(m)
            return
    raise RuntimeError(f"Card {card_id} not found in legal moves")


def _resolve_all_generics(session: CSession) -> list[dict]:
    applied = []
    while True:
        moves = session.legal_moves()
        generics = [m for m in moves if m.move_type == "resolve_generic"]
        if not generics:
            break
        m = generics[0]
        session.submit_move(m)
        applied.append(m.data)
    return applied


def _end_turn(session: CSession) -> None:
    for m in session.legal_moves():
        if m.move_type == "end_main_phase":
            session.submit_move(m)
            break
    else:
        raise RuntimeError("No end_main_phase move available")

    for m in session.legal_moves():
        if m.move_type == "resolve_end_of_turn":
            session.submit_move(m)
            break
    else:
        raise RuntimeError("No resolve_end_of_turn move available")

    for m in session.legal_moves():
        if m.move_type == "resolve_cleanup":
            session.submit_move(m)
            break
    else:
        raise RuntimeError("No resolve_cleanup move available")


class TestRedDragonSupplantLastTroop:
    """Red Dragon: supplant_troop → return_spy → grant_vp (as vp_tokens).

    When the supplant reduces barracks to 0, the game must NOT terminate
    immediately — remaining card effects must resolve and grant vp_tokens.
    """

    SCENARIO = "data/scenarios/random_card_generation/red_dragon_seed_666.json"

    def test_game_continues_after_supplant_reduces_barracks_to_zero(self):
        """After supplant reduces barracks 1→0, game is NOT terminal."""
        session = _load_session(self.SCENARIO)
        st = session._state
        idx4 = st.player_index("p4")
        assert st.player_barracks(idx4) == 1

        _play_card(session, "red_dragon")
        generics = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
        assert len(generics) > 0, "Should have supplant targets"
        session.submit_move(generics[0])

        st = session._state
        idx4 = st.player_index("p4")
        assert st.player_barracks(idx4) == 0

        assert not session.is_terminal(), (
            "Game must NOT terminate mid-card when barracks hits 0"
        )
        assert len(session.legal_moves()) > 0, (
            "Remaining Red Dragon actions (return_spy, grant_vp) must be playable"
        )

    def test_all_actions_resolve_and_vp_tokens_awarded(self):
        """All three actions resolve; vp_tokens increase, score unchanged."""
        session = _load_session(self.SCENARIO)
        st = session._state
        idx4 = st.player_index("p4")

        vp_before = st._s.players[idx4].vp_tokens
        score_before = st.player_score(idx4)

        _play_card(session, "red_dragon")
        applied = _resolve_all_generics(session)

        st = session._state
        idx4 = st.player_index("p4")

        assert st.player_barracks(idx4) == 0
        assert len(applied) >= 2, (
            f"At least 2 generic actions should resolve (supplant + return_spy), "
            f"got {len(applied)}: {applied}"
        )
        assert st._s.players[idx4].vp_tokens > vp_before, (
            f"grant_vp should award vp_tokens (before={vp_before}, after={st._s.players[idx4].vp_tokens})"
        )
        assert st.player_score(idx4) == score_before, (
            f"Score should not change (VP goes to vp_tokens), "
            f"(before={score_before}, after={st.player_score(idx4)})"
        )


class TestRoundBoundaryTerminality:
    """Game ends at end of round, not immediately, when kill switch triggers."""

    def test_game_ends_at_round_boundary_when_barracks_zero(self):
        """After barracks hits 0, game continues through round, then terminates."""
        session = _load_session(TestRedDragonSupplantLastTroop.SCENARIO)

        _play_card(session, "red_dragon")
        generics = [m for m in session.legal_moves() if m.move_type == "resolve_generic"]
        session.submit_move(generics[0])
        assert not session.is_terminal(), "Game must not be terminal mid-round"

        _resolve_all_generics(session)
        _end_turn(session)

        assert session.is_terminal(), (
            "Game should be terminal after round completes "
            "when barracks == 0 kill switch is active"
        )
