"""F-013 gate G4 timing probe: end-to-end ISMCTS search wall-time.

Wall-clock assertions are flaky in CI, so this is a script, not a pytest.
Run before (Phase 0) and after (Phase 4) the F-013 board-cache fix and compare
the mean against ``docs/validation/baseline/f013_timing.pre.txt``.

Measures N searches from one fixed mid-game root at a fixed ``num_sims``. The
search's information-state keys flow through ``private_view_json``, whose board
projection is the target of the F-013 cache, so the post-fix wall-time reflects
whether the redundant per-simulation board rebuild actually dropped.
"""
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RandomBot, fresh, load, make_bot  # noqa: E402

NUM_SIMS = 200
N_SEARCHES = 10

game = load(2)
root = fresh(game, 42)
bot = RandomBot(131)
for _ in range(40):
    if root.is_terminal() or root.current_player() < 0:
        break
    root.apply_action(bot.step(root))

times = []
for i in range(N_SEARCHES):
    search_bot = make_bot(game, num_sims=NUM_SIMS, seed=1000 + i)
    t0 = time.perf_counter()
    search_bot.step_with_policy(root.clone())
    times.append(time.perf_counter() - t0)

mean = statistics.mean(times)
print(f"f013_timing num_sims={NUM_SIMS} searches={N_SEARCHES} mean_wall={mean:.4f}s")
print(f"per-search={[round(t, 4) for t in times]}")
