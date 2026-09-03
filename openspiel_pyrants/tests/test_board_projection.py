"""F-013 Part B projection differential tests (G1, G3) and their guards.

The F-013 Part B fix makes the board projection cheap — not just cached — by
(a) reading ``CGameView`` straight into the six ``board_nodes`` output fields,
(b) memoizing sym→str, (c) hoisting the board-static fields (``node_id``,
``control_vp``, ``total_control_vp_per_turn``) into an adapter slot that
survives ``apply()``, (d) caching the finished ``private_view_json`` string per
player, and (e) propagating the projection across ``clone``/``determinize``.

House pattern (same as ``test_board_view_cache.py`` and
``test_observation_completeness.py``): the controls that must hold regardless
of the fix (T5, T8, T9, T10, T12) are written first, the differential that
pins the fix to the pre-fix implementation (T1, frozen in Phase 0) is the load
bearing one, and the genuinely red tests (T4, T6, T7, T11) fail for the stated
reason before their Phase is implemented.

Test ↔ phase mapping (``docs/validation/f013-part-b-fix-plan.md`` § 4.1):

- T1  byte-identity vs frozen reference vectors (G1)          — all phases
- T2  fast projection == ``build_c_board_view`` six fields     — Phase 2 (L3)
- T3  corpus composition guard (spies + full troop slots)      — Phase 0/1
- T4  exactly one ``engine_build_view``, zero ``build_c_board_view`` — Phase 2
- T5  board-static fields survive applies                      — control
- T6  sym memo invalidated by ``intern_destroy``               — Phase 2
- T7  repeated ``private_view_json`` serializes once           — Phase 3 (L1)
- T8  destroyed adapter never serves a cached view             — control
- T9  determinize does not change board occupancy              — control (Phase 4)
- T10 structural trip-wire: ``engine_determinize`` is board-free — control
- T11 clone/determinize inherit the parent projection          — Phase 4 (L2)
- T12 inherited projection is not aliased across adapters      — control (Phase 4)
"""

from __future__ import annotations

import contextlib
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pyspiel
import pytest

import openspiel_pyrants  # noqa: F401

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VECTORS_FILE = _REPO_ROOT / "docs" / "validation" / "baseline" / "f013b_view_vectors.jsonl"
_STATE_C_FILE = _REPO_ROOT / "engine_c" / "state.c"

_SYS_PATH_INSERT = (
    f"import sys; sys.path.insert(0, {str(_REPO_ROOT)!r}); "
    f"sys.path.insert(0, {str(_REPO_ROOT / 'openspiel_pyrants' / 'tests')!r})"
)


def _load_c_game(num_players: int = 2):
    return pyspiel.load_game("python_pyrants_c", {"num_players": str(num_players)})


def _mid_game_state(game, shuffle_seed=42, n_moves=40):
    """A state a few plies past the initial chance node, with a live adapter."""
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


def _iter_corpus():
    """Stream the F-013 Part B corpus one live state at a time.

    States must be consumed (not collected): each owns a 512 KB C arena and
    the shared scenario engine dies when the generator is exhausted.
    """
    from _f013b_corpus import iter_corpus_states

    yield from iter_corpus_states()


def _load_reference_vectors() -> dict[tuple[str, str], str]:
    """{(state_id, player_id): frozen private_view_json string}."""
    refs: dict[tuple[str, str], str] = {}
    with open(_VECTORS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            refs[(row["state_id"], row["player_id"])] = row["view"]
    return refs


@contextlib.contextmanager
def _count_engine_build_views():
    """Count ``engine_build_view`` C calls by wrapping the CDLL attribute.

    Setting the attribute on the shared ``_lib`` CDLL object patches every
    module that imported it (``view``, ``c_adapter``), so this counts cold
    projections regardless of which Python layer triggers them.
    """
    from engine_c.bindings.engine_bindings import _lib

    orig = _lib.engine_build_view
    seen = []

    def wrapped(ptr, view):
        seen.append(1)
        return orig(ptr, view)

    _lib.engine_build_view = wrapped
    try:
        yield seen
    finally:
        _lib.engine_build_view = orig


class TestProjectionDifferential:
    def test_private_view_json_byte_identical_to_reference(self, requires_c_engine):
        """T1 — G1: live output equals the Phase-0 frozen reference for every
        corpus state and every player. This must stay true through all phases."""
        refs = _load_reference_vectors()
        assert len(refs) >= 600, f"expected >=600 vectors, got {len(refs)}"
        n = 0
        for cs in _iter_corpus():
            for pid in cs.player_ids:
                live = cs.adapter.private_view_json(pid)
                expected = refs[(cs.state_id, pid)]
                assert live == expected, (
                    f"state {cs.state_id} player {pid} diverged from the "
                    f"Phase-0 reference"
                )
                n += 1
        assert n == len(refs)

    def test_board_projection_matches_build_c_board_view(self, requires_c_engine):
        """T2 — the fast projection (Phase 2+) equals the six ``board_nodes``
        fields derived from the general-purpose ``build_c_board_view`` over the
        whole corpus. Written against ``_project_board_nodes`` so it is RED
        until Phase 2 provides the fast path."""
        from engine_c.bindings.view import build_c_board_view

        for cs in _iter_corpus():
            fast = cs.adapter._project_board_nodes()
            view = build_c_board_view(cs.adapter)
            ref = [
                {
                    "node_id": n.node_id,
                    "troop_slots": list(n.troop_slots),
                    "spies": list(n.spies),
                    "control_vp": n.control_vp,
                    "total_control_vp_per_turn": n.total_control_vp_per_turn,
                    "vp_tokens": n.vp_tokens,
                }
                for n in view.board_nodes
            ]
            assert fast == ref, f"fast projection diverged for {cs.state_id}"

    def test_projection_corpus_covers_spies_and_full_troop_slots(self):
        """T3 — coverage guard for T1/T2: the frozen reference corpus must
        contain >=300 states, >=20 with a spy on the board and >=20 with a
        fully-occupied troop-slot list, from >=5 playout seeds. Without it,
        T1/T2 are vacuous on ``spies`` (random playouts never place one)."""
        assert _VECTORS_FILE.exists(), f"reference vectors missing: {_VECTORS_FILE}"

        n_states = 0
        spy_state_ids: set[str] = set()
        full_state_ids: set[str] = set()
        state_ids: set[str] = set()
        # Escaped-JSON substrings that appear in the raw JSONL lines.
        spy_marker = '\\"spies\\": [\\"'
        troop_slot_re = re.compile(r'\\"troop_slots\\": \[(.*?)\]')

        with open(_VECTORS_FILE, encoding="utf-8") as f:
            for line in f:
                m = re.search(r'"state_id": "([^"]+)"', line)
                if not m:
                    continue
                sid = m.group(1)
                state_ids.add(sid)
                if spy_marker in line:
                    spy_state_ids.add(sid)
                slots = troop_slot_re.findall(line)
                if any(s and "null" not in s for s in slots):
                    full_state_ids.add(sid)

        n_states = len(state_ids)
        assert n_states >= 300, f"corpus has {n_states} states (<300)"
        assert len(spy_state_ids) >= 20, (
            f"corpus has {len(spy_state_ids)} spy states (<20); T1/T2 are "
            f"vacuous on the spies field"
        )
        assert len(full_state_ids) >= 20, (
            f"corpus has {len(full_state_ids)} full troop-slot states (<20)"
        )


class TestProjectionFastPath:
    def test_projection_makes_exactly_one_engine_build_view_call(
        self, requires_c_engine
    ):
        """T4 — a cold ``_board_nodes_view()`` triggers exactly one
        ``engine_build_view`` and zero ``view.build_c_board_view`` calls (the
        adapter must stop routing through the general-purpose API)."""
        from unittest import mock

        import engine_c.bindings.view as view_mod

        game = _load_c_game(2)
        state = _mid_game_state(game)
        adapter = state._adapter
        assert adapter._board_cache is None

        with _count_engine_build_views() as ev, mock.patch.object(
            view_mod, "build_c_board_view", wraps=view_mod.build_c_board_view
        ) as spy:
            adapter._board_nodes_view()
            adapter._board_nodes_view()
        assert len(ev) == 1, f"expected exactly 1 engine_build_view, got {len(ev)}"
        assert spy.call_count == 0, (
            f"expected zero view.build_c_board_view calls, got {spy.call_count}"
        )

    def test_board_static_fields_survive_applies(self, requires_c_engine):
        """T5 — control: ``node_id``/``control_vp``/``total_control_vp_per_turn``
        read back after 60 ``apply()``s equal the values read at move 0. This is
        the invariant L3's static-field hoisting rests on; it must hold with or
        without the hoist."""
        game = _load_c_game(2)
        state = _mid_game_state(game, shuffle_seed=42, n_moves=0)
        adapter = state._adapter

        def static_fields():
            nodes = adapter._board_nodes_view()
            return [
                (n["node_id"], n["control_vp"], n["total_control_vp_per_turn"])
                for n in nodes
            ]

        first = static_fields()
        rng = np.random.RandomState(2026)
        for _ in range(60):
            if state.is_terminal() or state.current_player() < 0:
                break
            legal = state.legal_actions()
            if not legal:
                break
            state.apply_action(int(rng.choice(legal)))
        second = static_fields()
        assert second == first, "board-static fields changed across 60 applies"

    def test_sym_cache_is_invalidated_by_intern_destroy(self, requires_c_engine):
        """T6 — the shared sym→str memo must not serve a stale string after
        ``intern_destroy()`` + re-intern reassigns sym ids. Runs in a subprocess
        because ``intern_destroy`` tears down the process-global C intern table
        the rest of the OpenSpiel suite depends on."""
        code = f"""
{_SYS_PATH_INSERT}
from engine_c.bindings.engine_bindings import _lib, intern_destroy, sym_str

_lib.intern_init(4096)
alpha = _lib.intern(b"alpha")
assert alpha == 1, f"first intern should be sym 1, got {{alpha}}"
assert sym_str(alpha) == "alpha"
intern_destroy()  # must also clear the memo
_lib.intern_init(4096)
beta = _lib.intern(b"beta")
assert beta == 1, f"re-intern should reuse sym 1, got {{beta}}"
got = sym_str(beta)
assert got == "beta", f"memo served stale {{got!r}} after intern_destroy"
print("sym-cache-clear-ok")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"subprocess failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )


class TestSerializedViewCache:
    def test_repeated_private_view_json_serializes_once(self, requires_c_engine):
        """T7 — L1: 10 unmutated calls for one player id trigger exactly one
        projection *and* one ``json.dumps``; a second player id on the same
        adapter triggers a second serialization (per-player keying, not a
        single-slot cache)."""
        import json as _json
        from unittest import mock

        game = _load_c_game(2)
        state = _mid_game_state(game)
        adapter = state._adapter
        pids = state._game.get_player_ids()
        cp = state.current_player()
        pid = pids[cp if cp >= 0 else 0]
        other_pid = pids[1 if cp == 0 else 0]

        with _count_engine_build_views() as ev, mock.patch(
            "engine_c.bindings.c_adapter.json.dumps", wraps=_json.dumps
        ) as spy:
            for _ in range(10):
                adapter.private_view_json(pid)
            assert spy.call_count == 1, (
                f"expected exactly 1 json.dumps, got {spy.call_count}"
            )
            adapter.private_view_json(other_pid)
            assert spy.call_count == 2, (
                f"second player id should re-serialize, got {spy.call_count}"
            )
        assert len(ev) == 1, f"expected exactly 1 projection, got {len(ev)}"

    def test_destroyed_adapter_does_not_serve_a_cached_view(self, requires_c_engine):
        """T8 — control: after ``destroy()`` a cached view must never be served;
        the call must raise exactly as it does today (nothing about the state
        survives)."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        adapter = state._adapter
        pids = state._game.get_player_ids()
        pid = pids[0]

        adapter.private_view_json(pid)  # warm the caches
        adapter.destroy()
        with pytest.raises((AttributeError, RuntimeError)):
            adapter.private_view_json(pid)


class TestDeterminizeProjectionInvariant:
    def test_determinize_does_not_change_board_occupancy(self, requires_c_engine):
        """T9 — control (Phase 4's invariant): for K>=50 seeds across >=10
        roots, a determinized child's board occupancy equals its parent's.
        Written and green before propagation is implemented, never after."""
        game = _load_c_game(2)
        roots = []
        for seed in range(11, 61):
            if len(roots) >= 10:
                break
            state = _mid_game_state(game, shuffle_seed=seed, n_moves=40)
            if state._adapter is not None and not state.is_terminal():
                roots.append(state)
        assert len(roots) >= 10

        checked = 0
        for root in roots:
            adapter = root._adapter
            pid = root._game.get_player_ids()[root.current_player()]
            parent_nodes = adapter._board_nodes_view()
            for k in range(50):
                child = adapter.determinize(pid, 5000 + k)
                assert child is not None
                assert child._board_nodes_view() == parent_nodes, (
                    "determinize changed board occupancy"
                )
                checked += 1
        assert checked >= 500

    def test_engine_determinize_does_not_reference_board_state(
        self, requires_c_engine
    ):
        """T10 — structural trip-wire: ``engine_determinize``'s body in
        ``engine_c/state.c`` must not touch the board. If a future edit makes
        determinize board-touching, Phase 4's projection propagation goes
        silently unsound — this catches it in C, where the invariant lives."""
        src = _STATE_C_FILE.read_text(encoding="utf-8")
        start = src.find("GameState *engine_determinize(")
        assert start != -1, "engine_determinize not found in state.c"
        # Extract the function body by brace depth.
        body_start = src.find("{", start)
        depth = 0
        i = body_start
        while i < len(src):
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = src[body_start : i + 1]
        forbidden = ("->nodes", "node_count", "troop_slot", "spy")
        hits = [tok for tok in forbidden if tok in body]
        assert not hits, (
            f"engine_determinize now references board state: {hits} — "
            f"Phase 4 projection propagation would be unsound"
        )

    def test_clone_and_determinize_inherit_the_parent_projection(
        self, requires_c_engine
    ):
        """T11 — Phase 4: a warm parent's ``determinize()`` and ``deepcopy()``
        children perform zero fresh board projections on their first view.
        Supersedes ``test_determinize_and_clone_get_independent_fresh_caches``,
        which asserted the opposite; safe to invert because T9+T10 lock down
        the engine invariant the old test hedged against."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        adapter = state._adapter
        pids = state._game.get_player_ids()
        cp = state.current_player()
        pid = pids[cp if cp >= 0 else 0]

        adapter.private_view_json(pid)  # warm the parent board projection
        d = adapter.determinize(pid, 12345)
        c = copy.deepcopy(adapter)
        assert d is not None

        with _count_engine_build_views() as ev:
            d.private_view_json(pid)
            c.private_view_json(pid)
        assert len(ev) == 0, (
            f"children performed {len(ev)} fresh projections; expected 0 "
            f"(inherited from the warm parent)"
        )

    def test_inherited_projection_is_not_aliased_across_adapters(
        self, requires_c_engine
    ):
        """T12 — control: mutating the list — and the dicts inside it —
        returned by a child's ``_board_nodes_view()`` must not change what the
        parent or a sibling subsequently returns. Once projection data is
        shared across a family (Phase 4), an aliased structure would corrupt
        siblings through one member."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        adapter = state._adapter
        pids = state._game.get_player_ids()
        cp = state.current_player()
        pid = pids[cp if cp >= 0 else 0]

        parent_before = adapter._board_nodes_view()
        adapter.private_view_json(pid)  # warm
        d = adapter.determinize(pid, 777)
        c = copy.deepcopy(adapter)
        assert d is not None

        child_nodes = d._board_nodes_view()
        assert child_nodes, "child view should be non-empty"
        child_nodes.append({"node_id": "mutant"})
        child_nodes[0]["vp_tokens"] = 9999
        del child_nodes[0]["control_vp"]
        # A re-read through the child itself may be corrupted by that mutation —
        # that is the child's own business — but the parent and the sibling
        # (which never saw the mutated object) must be untouched.
        assert adapter._board_nodes_view() == parent_before
        assert c._board_nodes_view() == parent_before
