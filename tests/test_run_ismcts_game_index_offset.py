"""A2 tests: ``--game-index-offset`` runs one slice of the seed stream.

``docs/ismcts-walltime-plan.md`` § A2 adds ``--game-index-offset N`` so a run
plays game indices ``[N, N + num_games)`` of the same seed stream, and derives
every per-game seed (deck pair, shuffle seed, seat seeds) from the *absolute*
index ``N + local``. Games ``[k, k+m)`` of an offset run must therefore be
byte-identical to games ``[k, k+m)`` of an un-offset ``--num-games >= k+m`` run
with the same seed.

The pure spec helper is the unit under test for the seed-derivation invariant;
the C-engine test drives ``main()`` to pin directory naming and summary fields.
"""

from __future__ import annotations

import json

import openspiel_pyrants  # noqa: F401
from scripts._run_layout import only_run_dir
from scripts.run_ismcts import _build_game_specs, _build_ismcts_setup_json


def test_offset_specs_equal_unoffset_slice() -> None:
    seed = 42
    full = _build_game_specs(seed=seed, shuffle_seed=0, num_games=4, game_index_offset=0)
    shard = _build_game_specs(seed=seed, shuffle_seed=0, num_games=2, game_index_offset=2)
    assert shard == full[2:4]


def test_offset_specs_use_absolute_index_for_seeds() -> None:
    seed = 42
    specs = _build_game_specs(seed=seed, shuffle_seed=0, num_games=2, game_index_offset=5)
    assert [s["game_index"] for s in specs] == [5, 6]
    assert [s["shuffle_seed"] for s in specs] == [seed + 5, seed + 6]
    for s in specs:
        _, deck_a, deck_b = _build_ismcts_setup_json(base_seed=seed, game_index=s["game_index"])
        assert (s["deck_a_id"], s["deck_b_id"]) == (deck_a, deck_b)


def test_explicit_shuffle_seed_still_overrides_offset() -> None:
    specs = _build_game_specs(seed=42, shuffle_seed=7, num_games=3, game_index_offset=10)
    assert [s["game_index"] for s in specs] == [10, 11, 12]
    assert [s["shuffle_seed"] for s in specs] == [7, 7, 7]


def test_zero_offset_is_identity() -> None:
    specs = _build_game_specs(seed=42, shuffle_seed=0, num_games=3, game_index_offset=0)
    assert [s["game_index"] for s in specs] == [0, 1, 2]
    assert [s["shuffle_seed"] for s in specs] == [42, 43, 44]


def test_main_offset_writes_absolute_game_dir_and_summary(requires_c_engine, tmp_path) -> None:
    import sys

    from scripts.run_ismcts import main

    argv = [
        "run_ismcts",
        "--output-dir",
        str(tmp_path),
        "--game",
        "python_pyrants_c",
        "--num-games",
        "1",
        "--num-sims",
        "2",
        "--max-rounds",
        "3",
        "--workers",
        "1",
        "--game-index-offset",
        "3",
    ]
    old = sys.argv
    sys.argv = argv
    try:
        main()
    finally:
        sys.argv = old

    run_dir = only_run_dir(tmp_path)
    assert (run_dir / "game_0003").is_dir()
    assert not (run_dir / "game_0000").exists()

    summary = json.loads((run_dir / "game_0003" / "summary.json").read_text(encoding="utf-8"))
    assert summary["game_index"] == 3
    assert summary["game_index_offset"] == 3

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config"]["game_index_offset"] == 3
    assert manifest["games"][0]["game_index"] == 3
    # default --seed 42, --shuffle-seed 0 => shuffle seed = 42 + absolute index
    assert manifest["games"][0]["shuffle_seed"] == 45
