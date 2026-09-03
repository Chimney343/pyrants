"""F-013 Part B census: where the private-view cost actually goes (one search).

Wall-clock and call counts are environment-sensitive, so this is a script, not
a pytest. It runs one ``num_sims=200`` search from the ``f013_timing`` root and
emits, on a single line each:

1. ``private_view_json`` reads, the distinct ``(adapter identity, generation,
   player)`` triple count, and the read-multiplicity histogram. Adapter
   identities are pinned (a strong reference is held to every constructed
   adapter) so ``id()`` cannot recycle and collapse the distinct count.
2. Board projections performed (each = one ``engine_build_view`` C call),
   split between generation-0 projections (the clone/determinize set that L2
   can propagate away) and post-``apply`` projections.
3. Micro-timings measured on a fresh mid-game adapter (never on the search's
   adapters, so warming the caches cannot shift the census): the C call alone,
   ``CGameView()`` allocation alone, ``build_c_board_view``, cold
   ``_board_nodes_view``, warm ``private_view_json``, and ``json.dumps`` with
   and without ``board_nodes``.

The script is deliberately tolerant of the Phase 2-4 internal renames: it
spies on the adapter's *public surface* (``private_view_json`` / ``apply`` /
construction) plus the ``engine_build_view`` C primitive, all of which keep
their signatures across the phases.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RandomBot, fresh, load, make_bot  # noqa: E402

from engine_c.bindings import c_adapter as cad_mod
from engine_c.bindings.engine_bindings import _lib  # noqa: E402

NUM_SIMS = 200

# ---------------------------------------------------------------------------
# Instrumentation state (module-level, never stored on the adapter objects).
# ---------------------------------------------------------------------------
_pinned = {}      # id(adapter) -> adapter  (strong ref keeps ids from recycling)
_gen = {}         # id(adapter) -> int generation (bumped on apply)
_key_seen = {}    # (id, gen, pid) -> read count
_read_total = 0
_dump_total = 0
_proj_events = []  # generation of the adapter in flight when engine_build_view ran
_active = [None]   # adapter whose private_view_json is currently executing


def _pin(adapter):
    _pinned[id(adapter)] = adapter
    if id(adapter) not in _gen:
        _gen[id(adapter)] = 0


_orig_init = cad_mod.CEngineAdapter.__init__
_orig_apply = cad_mod.CEngineAdapter.apply
_orig_pvj = cad_mod.CEngineAdapter.private_view_json
_orig_ebv = _lib.engine_build_view
_orig_dumps = json.dumps


def _wrap_init(self, *args, **kwargs):
    _orig_init(self, *args, **kwargs)
    _pin(self)


def _wrap_apply(self, move):
    result = _orig_apply(self, move)
    _gen[id(self)] = _gen.get(id(self), 0) + 1
    return result


def _wrap_pvj(self, player_id):
    global _read_total
    _read_total += 1
    _active[0] = self
    try:
        return _orig_pvj(self, player_id)
    finally:
        _key_seen[(id(self), _gen.get(id(self), 0), player_id)] = (
            _key_seen.get((id(self), _gen.get(id(self), 0), player_id), 0) + 1
        )
        _active[0] = None


def _wrap_dumps(*args, **kwargs):
    global _dump_total
    _dump_total += 1
    return _orig_dumps(*args, **kwargs)


def _wrap_ebv(ptr, view):
    cur = _active[0]
    _proj_events.append(_gen.get(id(cur), -1) if cur is not None else -1)
    return _orig_ebv(ptr, view)


def install():
    cad_mod.CEngineAdapter.__init__ = _wrap_init
    cad_mod.CEngineAdapter.apply = _wrap_apply
    cad_mod.CEngineAdapter.private_view_json = _wrap_pvj
    json.dumps = _wrap_dumps
    _lib.engine_build_view = _wrap_ebv


def restore():
    cad_mod.CEngineAdapter.__init__ = _orig_init
    cad_mod.CEngineAdapter.apply = _orig_apply
    cad_mod.CEngineAdapter.private_view_json = _orig_pvj
    json.dumps = _orig_dumps
    _lib.engine_build_view = _orig_ebv


# ---------------------------------------------------------------------------
# Micro-timing helpers (measured on a throwaway mid-game adapter).
# ---------------------------------------------------------------------------


def _timed(fn, n):
    # warm-up call, then measure
    fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t0) / n * 1e6  # µs


def _micro_timings(adapter):
    import ctypes

    from engine_c.bindings.engine_bindings import CGameView

    state_ptr = adapter._state._ptr
    out = {}
    _buf = CGameView()

    def _c_call():
        _orig_ebv(state_ptr, ctypes.byref(_buf))

    def _alloc():
        return CGameView()

    out["engine_build_view_alone"] = _timed(_c_call, 200)

    alloc_n = 2000
    t0 = time.perf_counter()
    for _ in range(alloc_n):
        _alloc()
    out["cgameview_alloc"] = (time.perf_counter() - t0) / alloc_n * 1e6

    def _build_c_board_view():
        from engine_c.bindings.view import build_c_board_view

        build_c_board_view(adapter)

    out["build_c_board_view"] = _timed(_build_c_board_view, 100)

    def _board_cold():
        # True cold: drop the static template as well, so this measures a
        # first-projection-on-a-fresh-adapter (what a clone would pay).
        adapter._board_cache = None
        adapter._board_static = None
        return adapter._ensure_board_nodes()

    out["board_nodes_view_cold"] = _timed(_board_cold, 100)

    def _pvj():
        return adapter.private_view_json(adapter.player_ids[0])

    _pvj()  # warm both the board cache and the L1 string cache
    out["private_view_json_warm"] = _timed(_pvj, 100)

    # json.dumps with and without board_nodes, from a warm private-view dict.
    restore()  # dumps must not be double-counted during the micro-timing dumps
    try:
        payload = json.loads(adapter.private_view_json(adapter.player_ids[0]))
        pub_no_board = dict(payload["public"])
        pub_no_board.pop("board_nodes")

        dumps_plain_n = 500
        t0 = time.perf_counter()
        for _ in range(dumps_plain_n):
            json.dumps(payload, sort_keys=True)
        full = (time.perf_counter() - t0) / dumps_plain_n * 1e6

        t0 = time.perf_counter()
        for _ in range(dumps_plain_n):
            json.dumps({**payload, "public": pub_no_board}, sort_keys=True)
        no_board = (time.perf_counter() - t0) / dumps_plain_n * 1e6
    finally:
        install()

    out["json_dumps_full"] = full
    out["json_dumps_without_board_nodes"] = no_board
    out["board_nodes_json_share"] = full - no_board
    return out


# ---------------------------------------------------------------------------
# The census itself.
# ---------------------------------------------------------------------------

def main():
    game = load(2)
    root = fresh(game, 42)
    bot = RandomBot(131)
    for _ in range(40):
        if root.is_terminal() or root.current_player() < 0:
            break
        root.apply_action(bot.step(root))

    install()
    search_bot = make_bot(game, num_sims=NUM_SIMS, seed=1000)
    search_bot.step_with_policy(root.clone())
    restore()

    # Micro-timing adapter: a separate mid-game state created AFTER restore so
    # its construction/applies are not part of the census, and held by a live
    # PyrantsCState reference so __del__ cannot destroy it mid-measurement.
    micro_state = fresh(game, 42)
    mbot = RandomBot(2025)
    for _ in range(40):
        if micro_state.is_terminal() or micro_state.current_player() < 0:
            break
        micro_state.apply_action(mbot.step(micro_state))
    micro_adapter = micro_state._adapter

    reads = _read_total
    distinct = len(_key_seen)
    histogram = {}
    for (_id, _g, _p), count in _key_seen.items():
        histogram[count] = histogram.get(count, 0) + 1
    repeats = reads - distinct
    projections = len(_proj_events)
    gen0 = sum(1 for g in _proj_events if g == 0)
    post_apply = projections - gen0
    adapters = len(_pinned)
    applies = sum(_gen.values())
    hit_rate = (reads - projections) / reads if reads else 0.0

    def hist_str():
        parts = []
        for k in sorted(histogram):
            parts.append(f"{k}x:{histogram[k]}")
        return ", ".join(parts)

    print(f"f013b_census num_sims={NUM_SIMS}")
    print(f"reads={reads} distinct={distinct} repeats={repeats}")
    print(f"read_multiplicity_histogram={{{hist_str()}}}")
    print(f"adapters_constructed={adapters} apply_generations={applies}")
    print(f"board_projections={projections} gen0={gen0} post_apply={post_apply}")
    print(f"board_cache_hits={reads - projections} hit_rate={hit_rate:.1%}")
    print(f"json_dumps={_dump_total} (served_without_serialization={reads - _dump_total})")
    micro = _micro_timings(micro_adapter)
    for k in sorted(micro):
        print(f"micro {k}={micro[k]:.1f}us")


if __name__ == "__main__":
    main()
