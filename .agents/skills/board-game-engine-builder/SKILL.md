---
name: board-game-engine-builder
description: Use this skill whenever the user wants to build a Python engine for a board game, card game, tabletop game, or any rules-driven game from a rulebook. Triggers on "build an engine for [game]", "implement [game] in Python", "make a [game] simulator", pasted game rules with implementation intent, or any request to turn game rules into headless engine code with a play interface. Use this even when the user names a well-known game (chess, Catan, Magic) — the skill prevents fabricating canonical rules from memory and forces working from the user's pasted source. Covers architecture conventions (engine purity, Pydantic types, pure-function transitions), review-gated phase sequence (rules intake → domain model → state machine → rules engine → tests → CLI → implementation), and anti-fabrication tagging for every rule referenced.
---

# Board Game Engine Builder

Build Python game engines from pasted rules. Engine is headless and pure; play interface is separate. Work in review-gated phases — never autonomously progress past a gate.

## Hard rules

- **Treat the user's pasted rules as the only source of truth.** Even for famous games (chess, Catan, MTG), do not pull canonical rules from memory. If a rule is missing, ask.
- **Tag every rule reference** with `[from rules: §X]`, `[inferred]`, or `[gap]`. Surface every `[inferred]` and `[gap]` at the gate for explicit confirmation.
- **Stop at every gate.** Output `🛑 GATE: awaiting review`, name the next phase, then stop. Do not continue until the user approves.
- **Engine module has zero I/O.** No `print`, no `input`, no file access in `engine/*`. Interface code lives only in `interface/*`.
- **All state transitions are pure functions.** `apply(state, move) -> new_state`. No mutation of input state.

## Phase sequence

Each phase ends with a gate. Output exactly one phase per turn.

| Phase | Deliverable | Gate question |
|-------|-------------|---------------|
| **0 — Rules Intake** | Structured restatement: components, actions, turn structure, victory conditions. Every claim tagged with source. List every ambiguity under `❓ Rule Gaps`. | "Rules captured correctly? Any gaps to fill before specifying the engine?" |
| **1 — Domain Model** | Pydantic v2 models in `engine/state.py`: `GameState`, `Player`, `Piece`, `Board`, plus any game-specific entities. Data shapes only — no methods. | "Does this domain model match the game?" |
| **2 — State Machine** | Turn/phase structure as explicit states and transitions. Mermaid diagram. Guard conditions named. | "Is the turn flow correct?" |
| **3 — Rules Engine** | Function signatures only, in `engine/rules.py`: `legal_moves(state) -> list[Move]`, `apply(state, move) -> GameState`, `is_terminal(state) -> bool`, `winner(state) -> Player \| None`. Each signature's docstring names the source rule it implements. | "All rules covered? Any missing predicates?" |
| **4 — Test Specification** | Pytest parametrize-ready table: setup state → action → expected state. Cover normal play, every rule edge case, every illegal-move rejection. | "Right tests? Anything missing?" |
| **5 — Interface Spec** | `interface/cli.py` contract: command grammar, display format, input validation, error messages. Engine remains import-clean. | "Does the interface contract work?" |
| **6 — Implementation** | Implement file by file, in dependency order: `state.py` → `moves.py` → `errors.py` → `phases.py` → `rules.py` → tests → interface. Output `✅ [file]` after each. After all engine modules: run tests. After tests pass: implement interface. | (Run tests, report results, gate before interface implementation.) |

Start at **Phase 0** unless the user explicitly says otherwise.

## Architecture conventions (locked)

Override only on explicit user instruction.

**Stack**
- Python 3.12+
- Pydantic v2 for all domain types
- `pytest` + parametrize for tests
- `uv` for dependencies
- No game-specific libraries unless requested

**Project structure**
```
engine/
  state.py        # Pydantic models: GameState, Player, Board, etc.
  moves.py        # Move types and Pydantic validation
  rules.py        # legal_moves, apply, is_terminal, winner
  phases.py       # State machine for turn structure
  errors.py       # IllegalMoveError, RuleViolationError, etc.
interface/
  cli.py          # Play loop
  display.py      # Board rendering
  parser.py       # Command parsing
tests/
  test_rules.py
  test_state_machine.py
  test_cli.py
```

**Engine purity rules**
- No I/O in `engine/*`. Caught by code review and an import-lint test.
- All transitions return new state. `GameState` fully Pydantic-serializable — gives save/load and replay testing for free.
- Errors are typed exceptions, never strings or magic returns.

**Interface separation**
- `interface/*` imports `engine/*`. Engine never imports interface.
- Interface is replaceable. CLI today, pygame or web later, no engine changes.

## Output format

Every phase response uses this shape:

```
## Phase [N]: [Name]

[Phase content — spec only for phases 0–5; code for phase 6]

❓ Rule Gaps (if any):
- [ambiguity] — [what's needed from the user]

🛑 GATE: awaiting review
Next: Phase [N+1] — [name]
```

Nothing after the gate marker. No "let me know if…" filler. No preamble before the phase header.

## Rule gap handling

When pasted rules are ambiguous, missing, or contradictory:

1. List the gap under `❓ Rule Gaps` in the current phase.
2. State exactly what's needed: "What happens when [specific situation]?"
3. Stop at the gate. Do not propose a default unless asked.

Actively probe these gap categories — they are commonly under-specified in rulebooks:

- Tie-breaking
- Behavior when a player has no legal move (skip / lose / forced action)
- Simultaneous resolution order
- Boundary conditions (board edges, hand limits, deck/bag exhaustion)
- Information visibility (hidden hands, face-down cards, fog of war)
- Turn order under non-standard conditions (after a skip, after elimination, after a reversal)
- Action economy (does drawing count as your turn? can you pass?)

## Anti-fabrication tagging

Every rule restatement carries a tag:

- `[from rules: §X]` — directly supported by pasted text. Cite the section/line.
- `[inferred]` — derived from context. **Must be confirmed at the gate.**
- `[gap]` — cannot be resolved from pasted rules. **Blocks phase exit until user resolves.**

If any `[inferred]` or `[gap]` tags exist, the gate question must list them explicitly, not bury them.

## Pre-gate checklist

Run silently before emitting `🛑 GATE`:

- Every component from the rules represented in the domain model?
- Every action represented as a `Move` variant?
- Every victory condition checked in `is_terminal` / `winner`?
- Every illegal action rejected by `legal_moves`?
- All `[inferred]` tags surfaced in the gate question?
- Engine layer free of I/O?
- Could a different coder implement this phase without making design decisions?

If the last answer is no, the spec is incomplete — tighten before gating.

## Implementation phase specifics

When phase 6 begins (only after phase 5 approval):

1. Implement files in dependency order. Do not skip ahead.
2. After each file: output `✅ engine/state.py` (or equivalent), then continue to the next file. No gate between engine files unless an `[inferred]` rule surfaces during coding.
3. Write the import-lint test alongside `engine/state.py`: a test that fails if any `engine/*` module imports from `interface/*` or uses `print`/`input`.
4. After all engine files plus tests are written: run `pytest`. Report results.
5. **Gate before implementing interface.** If tests fail, fix and re-run before gating.
6. Implement interface files. Manual smoke test the CLI. Report and gate for final review.

If during implementation you discover a rule the spec missed: stop, surface it as a `[gap]`, gate. Do not silently invent behavior.

## First-turn behavior

If the user has not yet pasted rules, respond with exactly:

> "Paste the rules of the board game. I'll start with Phase 0 — Rules Intake."

Do not ask for the game name, target audience, or any other framing — the rules are sufficient.