"""Factory for building reproducible IS-MCTS bots.

F-010: the stock ``ISMCTSBot`` resampler falls back to a freshly-constructed,
unseeded ``pyspiel.UniformProbabilitySampler`` on every call, so ``--seed`` did
not reproduce a run. ``make_ismcts_bot`` installs a seeded numpy resampler via
the public ``ISMCTSBot.set_resampler`` hook, decoupled from the bot's own
``random_state`` so an evaluator change cannot silently shift determinization
seeds and break replay of old runs.

See ``docs/validation/f010-fix-plan.md`` § 5.1 and ``findings.md`` F-010.
"""

from __future__ import annotations

import numpy as np
from open_spiel.python.algorithms.ismcts import ISMCTSBot

# XOR salt so the resampling stream never coincides with the bot's random_state
# stream even when the caller passes the same numeric seed to both.
_RESAMPLE_SEED_XOR = 0x5F10


def make_ismcts_bot(
    game,
    *,
    seed,
    num_sims,
    uct_c,
    max_world_samples,
    final_policy_type,
    evaluator,
    resample_rng=None,
):
    """Build an ISMCTSBot whose world sampling is reproducible from ``seed``.

    Args:
        game: the pyspiel.Game.
        seed: integer seed for the bot's own ``random_state`` stream.
        num_sims: ``max_simulations`` passed to the stock bot.
        uct_c: UCB1 exploration constant.
        max_world_samples: stock-bot ``max_world_samples``.
        final_policy_type: an ``ISMCTSFinalPolicyType`` member.
        evaluator: the rollout evaluator (already constructed by the caller).
        resample_rng: optional explicit RNG for world sampling. Defaults to a
            dedicated ``np.random.RandomState(seed ^ 0x5F10)`` stream, separate
            from the bot's ``random_state`` so the two do not share draws.

    Returns:
        An ``ISMCTSBot`` whose determinization sampling is seeded and
        reproducible from ``seed``.
    """
    rng = np.random.RandomState(seed)
    bot = ISMCTSBot(
        game=game,
        evaluator=evaluator,
        uct_c=uct_c,
        max_simulations=num_sims,
        max_world_samples=max_world_samples,
        random_state=rng,
        final_policy_type=final_policy_type,
    )
    # The stock bot's fallback resampler uses an UNSEEDED pyspiel sampler
    # (F-010). Route world sampling through a seeded numpy stream instead.
    r_rng = (
        resample_rng
        if resample_rng is not None
        else np.random.RandomState(seed ^ _RESAMPLE_SEED_XOR)
    )
    bot.set_resampler(lambda state, player: state.resample_from_infostate(player, r_rng))
    return bot
