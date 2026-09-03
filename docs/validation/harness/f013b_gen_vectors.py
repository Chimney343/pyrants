"""F-013 Part B Phase 0: freeze reference ``private_view_json`` vectors.

Runs the whole F-013 Part B corpus (``openspiel_pyrants/tests/_f013b_corpus.py``)
through the *current* implementation and writes one JSON object per
``(state, player)`` pair to ``docs/validation/baseline/f013b_view_vectors.jsonl``.

This must be run **before** Phase 2 replaces the projection, and the output is
committed: the Phase 1+ differential tests (G1, T1) compare live
``private_view_json(pid)`` output against these frozen strings, so the frozen
vectors survive the implementation being swapped underneath them.

Usage:
    .venv/Scripts/python.exe -u docs/validation/harness/f013b_gen_vectors.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # noqa: E402
sys.path.insert(0, os.path.abspath(os.path.join(  # noqa: E402
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))  # repo root
sys.path.insert(0, os.path.abspath(os.path.join(  # noqa: E402
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
    "openspiel_pyrants", "tests")))

from _f013b_corpus import PLAYOUT_SEEDS, iter_corpus_states  # noqa: E402

_OUT = Path(__file__).resolve().parents[1] / "baseline" / "f013b_view_vectors.jsonl"


def main() -> None:
    # Stream the corpus: each state owns a 512 KB C arena and its scenario
    # engine dies when the generator is exhausted, so states must be consumed
    # one at a time, never collected and reused later.
    n_states = 0
    n_vectors = 0
    n_spy = 0
    n_full = 0
    by_source: dict[str, int] = {}
    with open(_OUT, "w", encoding="utf-8") as f:
        for cs in iter_corpus_states():
            n_states += 1
            by_source[cs.source] = by_source.get(cs.source, 0) + 1
            if cs.n_spies > 0:
                n_spy += 1
            if cs.n_full_slot_nodes > 0:
                n_full += 1
            for pid in cs.player_ids:
                view = cs.adapter.private_view_json(pid)
                f.write(
                    json.dumps(
                        {
                            "state_id": cs.state_id,
                            "player_id": pid,
                            "view": view,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                n_vectors += 1
    print(f"f013b_vectors states={n_states} vectors={n_vectors}")
    print(f"output={_OUT}")
    print(f"composition total={n_states}")
    print(f"composition with_spies={n_spy}")
    print(f"composition full_slot_nodes={n_full}")
    print(f"composition seeds={len(PLAYOUT_SEEDS)}")
    for src in sorted(by_source):
        print(f"composition by_source.{src}={by_source[src]}")


if __name__ == "__main__":
    main()
