"""A1 tests — the IS-MCTS tree key must fingerprint the observation, not
serialise it.

`ISMCTSBot.get_state_key` returns ``information_state_string()`` (~13 KB, a
cold ``json.dumps`` every post-apply state, ~24-32 % of a simulation).  The A1
change replaces it with ``PyrantsCState.information_state_key``: a 128-bit C
hash of exactly the fields ``private_view_json`` serialises, plus the action
history.

The load-bearing property is *equivalence*: for any two observations of one
game, ``key equal  <=>  string equal``.  A key that omits a serialised field
splits one information set; a key that includes a hidden field merges none but
splits many.  These tests pin both directions and the bot wiring.
"""

from __future__ import annotations

import numpy as np
import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401


def _load_c_game(num_players: int = 2):
    return pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})


def _mid_game_state(game, shuffle_seed=42, n_moves=40):
    state = game.new_initial_state()
    state.apply_action(shuffle_seed)
    rng = np.random.RandomState(shuffle_seed)
    for _ in range(n_moves):
        if state.is_terminal():
            break
        cp = state.current_player()
        if cp < 0:
            break
        legal = state.legal_actions()
        if not legal:
            break
        state.apply_action(int(rng.choice(legal)))
    return state


def _observations(game, *, num_plies: int, determinizations: int):
    """Every ``(player, string)`` stock key and its replacement over a run.

    The stock bot keys by ``(current_player, information_state_string())``, so
    the equivalence to hold is: for a fixed player, ``key equal <=> string
    equal``.  Two different players may share a view string and must still get
    different keys, which is why the player is part of every sample.
    """
    state = game.new_initial_state()
    state.apply_action(42)
    rng = np.random.RandomState(42)
    out = []

    def record(s):
        for p in range(game.num_players()):
            out.append((p, s.information_state_string(p), s.information_state_key(p)))

    for ply in range(num_plies):
        if state.is_terminal():
            break
        record(state)
        for observer in range(game.num_players()):
            for k in range(determinizations):
                d = state.resample_from_infostate(
                    observer, np.random.RandomState(1000 * ply + k)
                )
                record(d)
        legal = state.legal_actions()
        if not legal:
            break
        state.apply_action(int(rng.choice(legal)))
    return out


class TestInformationStateKey:
    def test_key_shape_is_hashable_tuple(self, requires_c_engine):
        """The key is a small tuple of ints, safe as a dict key."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        p = state.current_player()
        if p < 0:
            pytest.skip("game ended early")
        key = state.information_state_key(p)
        assert isinstance(key, tuple)
        assert len(key) == 4
        assert key[0] == p
        assert all(isinstance(v, int) for v in key)
        assert hash(key) is not None

    def test_determinization_preserves_observer_key(self, requires_c_engine):
        """F-013 invariant: the observing player's key is unchanged by determinize."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        p = state.current_player()
        if p < 0:
            pytest.skip("game ended early")
        root_key = state.information_state_key(p)
        for k in range(8):
            d = state.resample_from_infostate(p, np.random.RandomState(100 + k))
            assert d.information_state_key(p) == root_key
            assert d.information_state_string(p) == state.information_state_string(p)

    def test_key_equivalence_classes_match_string(self, requires_c_engine):
        """key equal <=> string equal over a trajectory and its determinizations.

        Grouping in both directions catches both failure modes: one key group
        holding two strings is a false merge; one string group holding two keys
        is a false split.
        """
        game = _load_c_game(2)
        observations = _observations(game, num_plies=10, determinizations=6)
        assert len(observations) > 100

        by_string: dict[tuple, set] = {}
        by_key: dict[tuple, set] = {}
        for player, string, key in observations:
            by_string.setdefault((player, string), set()).add(key)
            by_key.setdefault(key, set()).add((player, string))

        false_splits = [k for k, keys in by_string.items() if len(keys) > 1]
        false_merges = [k for k, strings in by_key.items() if len(strings) > 1]
        assert not false_splits, (
            f"{len(false_splits)} (player, string) groups have >1 key; "
            f"first={false_splits[0]!r}"
        )
        assert not false_merges, (
            f"{len(false_merges)} key groups have >1 (player, string); "
            f"first keys={false_merges[0]!r}"
        )

    def test_own_hand_identity_changes_key(self, requires_c_engine):
        """A same-count own-hand substitution splits the key (false-merge guard)."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        p = state.current_player()
        if p < 0:
            pytest.skip("game ended early")
        pid = game.get_player_ids()[p]
        adapter = state._adapter
        ps = adapter._state._s.players[adapter.player_index(pid)]
        from engine_c.bindings.engine_bindings import _lib

        ps.hand_count = 2
        ps.hand[0] = _lib.intern(b"noble")
        ps.hand[1] = _lib.intern(b"soldier")
        adapter._view_cache.clear()

        before_key = state.information_state_key(p)
        before_string = state.information_state_string(p)
        ps.hand[0] = _lib.intern(b"bounty_hunter")
        adapter._view_cache.clear()
        assert state.information_state_string(p) != before_string
        assert state.information_state_key(p) != before_key

    def test_hidden_deck_identity_does_not_change_key(self, requires_c_engine):
        """A same-count own-deck substitution must not split the key."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        p = state.current_player()
        if p < 0:
            pytest.skip("game ended early")
        pid = game.get_player_ids()[p]
        adapter = state._adapter
        ps = adapter._state._s.players[adapter.player_index(pid)]
        from engine_c.bindings.engine_bindings import _lib

        ps.deck_count = 2
        ps.deck[0] = _lib.intern(b"noble")
        ps.deck[1] = _lib.intern(b"soldier")
        adapter._view_cache.clear()

        before_key = state.information_state_key(p)
        before_string = state.information_state_string(p)
        ps.deck[0] = _lib.intern(b"bounty_hunter")
        adapter._view_cache.clear()
        assert state.information_state_string(p) == before_string
        assert state.information_state_key(p) == before_key

    def test_every_serialised_field_splits_key(self, requires_c_engine):
        """Every field `private_view_json` serialises must move the hash.

        The C hash re-enumerates the serialised field set by hand, so a field
        added to `private_view_json` without a matching change in
        `engine_infostate_hash` would silently merge two information sets.
        Each mutation below changes exactly one serialised field and asserts
        both the string and the key move. Keep this list in step with
        `private_view_json` / `_build_public_dict`.
        """
        from engine_c.bindings.engine_bindings import _lib

        game = _load_c_game(2)

        def card(name):
            return _lib.intern(name.encode())

        def noop(_st, _pi):
            pass

        def me(st, pi):
            return st.players[pi]

        def them(st, pi):
            return st.players[1 - pi]

        def run(setup, mutate):
            state = _mid_game_state(game)
            p = state.current_player()
            if p < 0:
                pytest.skip("game ended early")
            adapter = state._adapter
            pi = adapter.player_index(game.get_player_ids()[p])
            st = adapter._state._s
            setup(st, pi)
            adapter._view_cache.clear()
            before_string = state.information_state_string(p)
            before_key = state.information_state_key(p)
            mutate(st, pi)
            adapter._view_cache.clear()
            assert state.information_state_string(p) != before_string
            assert state.information_state_key(p) != before_key

        def own_hand_setup(st, pi):
            me(st, pi).hand_count = 2
            me(st, pi).hand[0] = card("noble")
            me(st, pi).hand[1] = card("soldier")

        def own_discard_setup(st, pi):
            me(st, pi).discard_pile_count = 2
            me(st, pi).discard_pile[0] = card("noble")
            me(st, pi).discard_pile[1] = card("soldier")

        def own_played_setup(st, pi):
            me(st, pi).played_cards_count = 1
            me(st, pi).played_cards[0] = card("noble")

        def own_inner_setup(st, pi):
            me(st, pi).inner_circle_count = 1
            me(st, pi).inner_circle[0] = card("noble")

        def own_trophy_setup(st, pi):
            me(st, pi).trophy_hall_count = 1
            me(st, pi).trophy_hall[0] = card("p1")

        def other_hand_setup(st, pi):
            them(st, pi).hand_count = 2

        def market_row_setup(st, pi):
            st.market.row_count = 1
            st.market.row[0] = card("noble")

        def market_row_mutate(st, pi):
            st.market.row[0] = card("bounty_hunter")

        def own_deck_setup(st, pi):
            me(st, pi).deck_count = 2

        def market_deck_setup(st, pi):
            st.market.deck_count = 2

        def market_discard_setup(st, pi):
            st.market.discard_pile_count = 2

        def board_troop_setup(st, pi):
            st.nodes[0].troop_slot_count = 1
            st.nodes[0].troop_slots[0] = card("p1")

        def board_spy_setup(st, pi):
            st.nodes[0].spy_count = 1
            st.nodes[0].spies[0] = card("p1")

        cases = [
            ("round_number", noop, lambda st, pi: setattr(st, "round_number", st.round_number + 1)),
            ("phase", noop, lambda st, pi: setattr(st, "phase", 5 if st.phase != 5 else 4)),
            ("resource_power", noop, lambda st, pi: setattr(st.resource_pool, "power", st.resource_pool.power + 1)),
            ("resource_influence", noop, lambda st, pi: setattr(st.resource_pool, "influence", st.resource_pool.influence + 1)),
            ("devour_size", noop, lambda st, pi: setattr(st, "devour_pile_count", st.devour_pile_count + 1)),
            ("market_row", market_row_setup, market_row_mutate),
            ("market_deck_size", market_deck_setup, lambda st, pi: setattr(st.market, "deck_count", st.market.deck_count + 1)),
            ("market_discard_size", market_discard_setup, lambda st, pi: setattr(st.market, "discard_pile_count", st.market.discard_pile_count + 1)),
            ("other_player_hand_size", other_hand_setup, lambda st, pi: setattr(them(st, pi), "hand_count", them(st, pi).hand_count + 1)),
            ("own_hand_identity", own_hand_setup, lambda st, pi: me(st, pi).hand.__setitem__(0, card("bounty_hunter"))),
            ("own_discard_identity", own_discard_setup, lambda st, pi: me(st, pi).discard_pile.__setitem__(0, card("bounty_hunter"))),
            ("own_deck_size", own_deck_setup, lambda st, pi: setattr(me(st, pi), "deck_count", me(st, pi).deck_count + 1)),
            ("own_played_identity", own_played_setup, lambda st, pi: me(st, pi).played_cards.__setitem__(0, card("bounty_hunter"))),
            ("own_inner_circle_identity", own_inner_setup, lambda st, pi: me(st, pi).inner_circle.__setitem__(0, card("bounty_hunter"))),
            ("own_trophy_hall_identity", own_trophy_setup, lambda st, pi: me(st, pi).trophy_hall.__setitem__(0, card("p2"))),
            ("own_barracks", noop, lambda st, pi: setattr(me(st, pi), "barracks", me(st, pi).barracks + 1)),
            ("own_spies_available", noop, lambda st, pi: setattr(me(st, pi), "spies_available", me(st, pi).spies_available + 1)),
            ("own_vp_tokens", noop, lambda st, pi: setattr(me(st, pi), "vp_tokens", me(st, pi).vp_tokens + 1)),
            ("own_score", noop, lambda st, pi: setattr(me(st, pi), "score", me(st, pi).score + 1)),
            ("board_troop_slots", board_troop_setup, lambda st, pi: st.nodes[0].troop_slots.__setitem__(0, card("p2"))),
            ("board_spies", board_spy_setup, lambda st, pi: st.nodes[0].spies.__setitem__(0, card("p2"))),
            ("board_vp_tokens", noop, lambda st, pi: setattr(st.nodes[0], "vp_tokens", st.nodes[0].vp_tokens + 1)),
        ]
        for name, setup, mutate in cases:
            try:
                run(setup, mutate)
            except AssertionError as exc:
                raise AssertionError(f"serialised field {name!r} did not split the key") from exc

    def test_bot_get_state_key_uses_information_state_key(self, requires_c_engine):
        """The factory's bot keys nodes by information_state_key, not the string."""
        from open_spiel.python.algorithms.ismcts import ISMCTSFinalPolicyType
        from open_spiel.python.algorithms.mcts import RandomRolloutEvaluator

        from openspiel_pyrants.ismcts_factory import make_ismcts_bot

        game = _load_c_game(2)
        state = _mid_game_state(game)
        p = state.current_player()
        if p < 0:
            pytest.skip("game ended early")
        bot = make_ismcts_bot(
            game=game,
            seed=1,
            num_sims=5,
            uct_c=1.4,
            max_world_samples=8,
            final_policy_type=ISMCTSFinalPolicyType.NORMALIZED_VISITED_COUNT,
            evaluator=RandomRolloutEvaluator(
                n_rollouts=1, random_state=np.random.RandomState(1)
            ),
        )
        assert bot.get_state_key(state) == state.information_state_key(p)
        d = state.resample_from_infostate(p, np.random.RandomState(7))
        assert bot.get_state_key(d) == bot.get_state_key(state)
