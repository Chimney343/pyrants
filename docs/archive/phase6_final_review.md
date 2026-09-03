# Phase 6 Final Review

Date: 2026-04-27

## Findings

### High

1. Cleanup reshuffle is deterministic instead of shuffled.
- Evidence: [engine/rules.py](engine/rules.py#L187), [engine/rules.py](engine/rules.py#L197), [engine/rules.py](engine/rules.py#L199)
- Source requirement: [tyrants-of-the-underdark-logic.md](tyrants-of-the-underdark-logic.md#L31)
- Impact: Draw order becomes predictable after first deck exhaustion, which conflicts with required shuffle behavior and can materially change outcomes.
- Recommendation: Inject a shuffle dependency (rng or shuffler callable) into cleanup transition logic and add deterministic-seed tests.

2. Final scoring uses troop-majority control while end-of-turn scoring uses control markers.
- Evidence: [engine/scoring.py](engine/scoring.py#L60), [engine/scoring.py](engine/scoring.py#L67), [engine/scoring.py](engine/scoring.py#L82)
- Impact: If control markers and troop-majority state diverge, running score and final score can be inconsistent.
- Recommendation: Define a single source of truth for site control in rules text and apply it consistently in both end-of-turn and final scoring paths.

### Medium

3. Declared Python floor is 3.12+, but implementation was validated in a 3.11 runtime.
- Evidence: [pyproject.toml](pyproject.toml#L5)
- Impact: Packaging and CI can reject environments where local tests currently pass, creating deployment ambiguity.
- Recommendation: Either raise runtime and CI to 3.12 or lower project requirement if 3.11 support is intended.

4. Test coverage does not validate shuffle randomness or control-source consistency.
- Evidence: [tests/test_state_machine.py](tests/test_state_machine.py#L36)
- Impact: The current deterministic reshuffle behavior is not caught by tests; scoring consistency between marker and majority logic is also untested.
- Recommendation: Add tests for reshuffle behavior and an explicit scoring consistency case.

## What Passed

- Full test suite pass: 14 tests.
- CLI smoke path validated (state render, legal command output, graceful quit).

## Summary

The implementation is structurally sound and test-green, but two high-risk rules-behavior inconsistencies should be resolved before expanding card or action logic.

## Follow-Up Plan

- Actionable next steps for both user inputs and implementation work are documented in [next_steps.md](next_steps.md).
- A tracked revisit checklist is in [revisit_later.md](revisit_later.md).