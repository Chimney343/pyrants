"""Player-view differential tests (G1) and their guards.

F-013 Part B made the Python board projection cheap and cached it across
``clone``/``determinize``. Candidate 5 moved the whole player view into the C
visibility module (``engine_c/visibility.c``, ADR-0007), so the Python
projection and its cache are gone. What these tests still pin:

- T1  byte-identity vs frozen reference vectors (G1)          — all phases
- T2  the view's ``board_nodes`` == ``build_c_board_view``'s six fields
- T3  corpus composition guard (spies + full troop slots)
- T5  board-static fields survive applies                      — control
- T6  sym memo invalidated by ``intern_destroy``
- T7  repeated ``private_view_json`` renders once per player   — L1 cache
- T8  destroyed adapter never serves a cached view             — control
- T9  determinize does not change board occupancy              — control

T4, T10, T11 and T12 tested the deleted Python projection cache. T10's
invariant (determinize never touches the board) is now checked more strongly
in C: ``engine_c/tests/test_visibility.c`` asserts determinization leaves the
observer's whole view byte-identical.
"""

from __future__ import annotations

import contextlib
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


def _board_nodes(adapter, pid) -> list[dict]:
    """The ``public.board_nodes`` component of *pid*'s view."""
    return json.loads(adapter.private_view_json(pid))["public"]["board_nodes"]


@contextlib.contextmanager
def _count_view_renders():
    """Count ``engine_player_view_json`` C calls by wrapping the CDLL attribute.

    Setting the attribute on the shared ``_lib`` CDLL object patches every
    module that imported it, so this counts renders whichever layer asks.
    """
    from engine_c.bindings.engine_bindings import _lib

    orig = _lib.engine_player_view_json
    seen = []

    def wrapped(*args):
        seen.append(1)
        return orig(*args)

    _lib.engine_player_view_json = wrapped
    try:
        yield seen
    finally:
        _lib.engine_player_view_json = orig


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
        """T2 — the view's ``board_nodes`` equal the six fields derived from the
        general-purpose ``build_c_board_view`` over the whole corpus."""
        from engine_c.bindings.view import build_c_board_view

        for cs in _iter_corpus():
            fast = _board_nodes(cs.adapter, cs.player_ids[0])
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
            assert fast == ref, f"view board_nodes diverged for {cs.state_id}"

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


class TestBoardStaticFields:
    def test_board_static_fields_survive_applies(self, requires_c_engine):
        """T5 — control: ``node_id``/``control_vp``/``total_control_vp_per_turn``
        read back after 60 ``apply()``s equal the values read at move 0."""
        game = _load_c_game(2)
        state = _mid_game_state(game, shuffle_seed=42, n_moves=0)
        adapter = state._adapter
        pid = game.get_player_ids()[0]

        def static_fields():
            return [
                (n["node_id"], n["control_vp"], n["total_control_vp_per_turn"])
                for n in _board_nodes(adapter, pid)
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
        """T7 — L1: 10 unmutated calls for one player id render the view
        exactly once; a second player id on the same adapter renders a second
        time (per-player keying, not a single-slot cache)."""
        game = _load_c_game(2)
        state = _mid_game_state(game)
        adapter = state._adapter
        pids = state._game.get_player_ids()
        cp = state.current_player()
        pid = pids[cp if cp >= 0 else 0]
        other_pid = pids[1 if cp == 0 else 0]

        with _count_view_renders() as renders:
            for _ in range(10):
                adapter.private_view_json(pid)
            assert len(renders) == 1, f"expected exactly 1 render, got {len(renders)}"
            adapter.private_view_json(other_pid)
            assert len(renders) == 2, (
                f"second player id should render again, got {len(renders)}"
            )

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
        """T9 — control: for K>=50 seeds across >=10 roots, a determinized
        child's board occupancy equals its parent's."""
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
            parent_nodes = _board_nodes(adapter, pid)
            for k in range(50):
                child = adapter.determinize(pid, 5000 + k)
                assert child is not None
                assert _board_nodes(child, pid) == parent_nodes, (
                    "determinize changed board occupancy"
                )
                checked += 1
        assert checked >= 500
