"""White Dragon card behavior tests: deploy 3 troops, gain VP tokens for controlled sites."""

from __future__ import annotations

from pathlib import Path

from engine_c.bindings.session import CSession
from engine_c.bindings.view import build_c_game_view
from tests.c_engine.card_test_helpers import (
    _make_engine,
    _player_vp_tokens,
    _session_player_index,
    _sptr,
    make_card_test_session,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_P1 = "p1"
_P2 = "p2"


def _player_score(session: CSession, pid: str) -> int:
    pi = _session_player_index(session, pid)
    if pi < 0:
        return 0
    return _sptr(session).contents.players[pi].score


def _has_pending_generic(session: CSession) -> bool:
    return bool(_sptr(session).contents.pending_generic)


def _build_white_dragon_session(controlled_site_count: int) -> CSession:
    extra_sites = [
        "site_gauntlgrym",
        "site_jhachalkhyn",
        "site_gracklstugh",
        "site_chasmleap_bridge",
        "site_blingdenfire",
    ]
    troops: dict[str, dict[str, list[str | None]]] = {_P1: {}}
    for i in range(controlled_site_count):
        sid = extra_sites[i]
        troops[_P1][sid] = [_P1, _P1, None, None, None, None]

    session = make_card_test_session(
        _make_engine(),
        [_P1, _P2],
        hand={_P1: ["white_dragon"]},
        troops=troops,
        current_player=_P1,
    )
    return session


def _play_card_and_deploy_all(session: CSession) -> None:
    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "white_dragon"]
    if not playable:
        msg = f"White Dragon not playable, legal types: {[getattr(m, 'move_type', '') for m in session.legal_moves()]}"
        raise AssertionError(msg)
    session.submit_move(playable[0])

    deployments = 0
    while deployments < 3:
        view = build_c_game_view(session)
        resolve_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
        if not resolve_moves:
            break
        session.submit_move(resolve_moves[0].move)
        deployments += 1


def test_white_dragon_vp_tokens_from_controlled_sites() -> None:
    """4 controlled sites with per=2 grants 2 VP tokens; score is unchanged."""
    session = _build_white_dragon_session(controlled_site_count=4)

    before_tokens = _player_vp_tokens(session, _P1)
    before_score = _player_score(session, _P1)

    _play_card_and_deploy_all(session)

    assert not _has_pending_generic(session), "Card must fully resolve"

    tokens_after = _player_vp_tokens(session, _P1)
    score_after = _player_score(session, _P1)

    expected_vp = 4 // 2
    assert tokens_after == before_tokens + expected_vp, (
        f"Expected {expected_vp} VP tokens (4 controlled sites // 2), "
        f"got vp_tokens={tokens_after} (was {before_tokens})"
    )
    assert score_after == before_score, (
        f"Score should not change (VP goes to tokens), was {before_score}, now {score_after}"
    )

    session.destroy()


def test_white_dragon_per_rounds_down() -> None:
    """3 controlled sites with per=2 grants 1 VP token (rounds down)."""
    session = _build_white_dragon_session(controlled_site_count=3)

    before_tokens = _player_vp_tokens(session, _P1)

    _play_card_and_deploy_all(session)

    assert not _has_pending_generic(session), "Card must fully resolve"

    tokens_after = _player_vp_tokens(session, _P1)
    expected_vp = 3 // 2
    assert tokens_after == before_tokens + expected_vp, (
        f"Expected {expected_vp} VP tokens (3 controlled sites // 2), "
        f"got vp_tokens={tokens_after} (was {before_tokens})"
    )

    session.destroy()


def test_white_dragon_no_sites_gives_zero_vp() -> None:
    """0 controlled sites grants 0 VP tokens."""
    session = _build_white_dragon_session(controlled_site_count=0)

    before_tokens = _player_vp_tokens(session, _P1)
    before_score = _player_score(session, _P1)

    _play_card_and_deploy_all(session)

    assert not _has_pending_generic(session), "Card must fully resolve"

    tokens_after = _player_vp_tokens(session, _P1)
    score_after = _player_score(session, _P1)

    assert tokens_after == before_tokens, (
        f"Expected 0 VP tokens (0 controlled sites), got {tokens_after}"
    )
    assert score_after == before_score, (
        f"Score should not change, was {before_score}, now {score_after}"
    )

    session.destroy()


def test_white_dragon_one_site_rounds_down_to_zero_vp() -> None:
    """1 controlled site with per=2 rounds down to 0 VP tokens (not a minimum of 1)."""
    session = _build_white_dragon_session(controlled_site_count=1)

    before_tokens = _player_vp_tokens(session, _P1)
    before_score = _player_score(session, _P1)

    _play_card_and_deploy_all(session)

    assert not _has_pending_generic(session), "Card must fully resolve"

    tokens_after = _player_vp_tokens(session, _P1)
    score_after = _player_score(session, _P1)

    assert tokens_after == before_tokens, (
        f"Expected 0 VP tokens (1 controlled site // 2 rounds down), got {tokens_after}"
    )
    assert score_after == before_score, (
        f"Score should not change, was {before_score}, now {score_after}"
    )

    session.destroy()


def test_white_dragon_deploys_three_troops() -> None:
    """Playing White Dragon deploys exactly 3 troops (barracks decrease by 3)."""
    session = _build_white_dragon_session(controlled_site_count=1)

    s = _sptr(session).contents
    pi = _session_player_index(session, _P1)
    before_barracks = s.players[pi].barracks

    _play_card_and_deploy_all(session)

    s = _sptr(session).contents
    after_barracks = s.players[pi].barracks
    assert after_barracks == before_barracks - 3, (
        f"Barracks should decrease by 3: {before_barracks} -> {after_barracks}"
    )

    session.destroy()


def test_white_dragon_short_barracks_grants_no_score() -> None:
    """A free card-effect deploy awards VP tokens (never score) for the deploys
    it cannot place.

    White Dragon says "Deploy 3 troops" for free. With only 1 troop in barracks
    the card deploys 1 troop and the 2 empty-barracks deploys award 2 VP tokens,
    plus the controlled-sites VP (4 // 2 = 2). Score never changes.
    """
    session = _build_white_dragon_session(controlled_site_count=4)

    s = _sptr(session).contents
    pi = _session_player_index(session, _P1)
    s.players[pi].barracks = 1

    before_barracks = s.players[pi].barracks
    before_score = _player_score(session, _P1)
    before_tokens = _player_vp_tokens(session, _P1)

    # Play and resolve every available deploy target until the card resolves.
    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "white_dragon"]
    assert playable, "White Dragon must be playable"
    session.submit_move(playable[0])

    while True:
        view = build_c_game_view(session)
        resolve_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
        if not resolve_moves:
            break
        session.submit_move(resolve_moves[0].move)

    assert not _has_pending_generic(session), "Card must fully resolve"

    s = _sptr(session).contents
    pi = _session_player_index(session, _P1)
    assert s.players[pi].barracks == before_barracks - 1, (
        f"Only 1 troop available; barracks should drop by 1: "
        f"{before_barracks} -> {s.players[pi].barracks}"
    )
    assert _player_vp_tokens(session, _P1) == before_tokens + 4, (
        f"Expected 4 VP tokens (2 empty-barracks deploys + 2 controlled sites), "
        f"got {_player_vp_tokens(session, _P1)}"
    )
    assert _player_score(session, _P1) == before_score, (
        f"Free deploy must not grant score; was {before_score}, "
        f"now {_player_score(session, _P1)}"
    )

    session.destroy()


def test_white_dragon_zero_barracks_grants_vp_tokens() -> None:
    """With 0 troops in barracks each deploy grants a VP token, then the VP
    clause still resolves.

    White Dragon is "Deploy 3 troops. Gain 1 VP for every 2 sites controlled."
    With an empty barracks the free deploy places nothing (no score, no stall)
    and awards 3 VP tokens (one per deploy), plus 1 VP for 2 controlled sites.
    """
    session = _build_white_dragon_session(controlled_site_count=2)

    s = _sptr(session).contents
    pi = _session_player_index(session, _P1)
    s.players[pi].barracks = 0

    before_tokens = _player_vp_tokens(session, _P1)
    before_score = _player_score(session, _P1)

    playable = [m for m in session.legal_moves()
                if getattr(m, "move_type", "") == "play_card"
                and m.data.get("card_id") == "white_dragon"]
    assert playable, "White Dragon must be playable"
    session.submit_move(playable[0])

    # Resolve every pending deploy (3 VP-token moves) until the card resolves.
    while True:
        view = build_c_game_view(session)
        resolve_moves = [m for m in view.legal_moves if m.move_type == "resolve_generic"]
        if not resolve_moves:
            break
        session.submit_move(resolve_moves[0].move)

    assert not _has_pending_generic(session), "Card must fully resolve"

    s = _sptr(session).contents
    pi = _session_player_index(session, _P1)
    assert s.players[pi].barracks == 0, (
        f"Barracks must stay 0 (nothing to deploy), got {s.players[pi].barracks}"
    )
    assert _player_vp_tokens(session, _P1) == before_tokens + 4, (
        f"Expected 4 VP tokens (3 deploys + 1 for 2 controlled sites), "
        f"got {_player_vp_tokens(session, _P1)}"
    )
    assert _player_score(session, _P1) == before_score, (
        f"Score should not change, was {before_score}, now {_player_score(session, _P1)}"
    )

    session.destroy()
