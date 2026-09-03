# IS-MCTS Replay Viewer (separate entry point, subclassing the game viewer)

## Goal

A Tk viewer that loads a simulated game from `artifacts/ismcts/**/replay.json`, steps
through it decision by decision, and auto-plays at an adjustable interval — reusing the
existing game-viewer GUI (map, market row, hand/played cards, sidebar, zoom, hover
popups) rather than reimplementing it.

Separate entry point (`just replay-viewer`), **not** a mode toggle inside the hotseat
viewer. Read-only: it never applies a move the log did not record.

---

## Prior art — read this before writing code

- `interface/replay_viewer.py` **existed and was deleted** in commit `956f603`
  ("remove legacy Python engine and dead artifacts"). It was a 1541-line copy-paste
  fork of the game viewer bound to the now-deleted Python engine (`engine.state`,
  `game_session.GameSession`, `game_view`). **Do not resurrect it** — it duplicated
  the entire rendering layer, which is exactly why it rotted.
- `.kilo/plans/enhanced-replay-viewer.md` is **stale**. It describes upgrading that
  deleted file and predates the C engine. Ignore it; this plan supersedes it.
- `.kilo/plans/1787952436270-ismcts-phase5-reconstruct-game-script.md` specifies a
  *pure log reader* (`scripts/reconstruct_game.py`, never built). That is a different,
  complementary deliverable — a text reader that must not import the C engine. This
  plan does the opposite: it **re-simulates** through the C engine to get full board
  state. Do not merge the two.

---

## Validated facts (a prototype confirmed all of these — do not re-derive)

A throwaway prototype rebuilt a `CSession` from `replay_context` and re-applied every
logged move. Results:

| Game | Players | Steps replayed | Per-step check vs `steps.jsonl` | Final scores |
|---|---|---|---|---|
| `artifacts/ismcts/game_0000` | 2 | 517 / 517 | scores + market row match at **every** step | exact |
| `experiments/sims_vs_wins/20260902T215139Z_65cdce971bcf/game_0000` | 4 | 997 / 997 | — | exact |
| `experiments/sims_vs_wins/20260902T194817Z_7e1b49b7277c/game_0003` | 4 | 1057 / 1057 | — | exact |
| `artifacts/ismcts/game_0001` (stale artifact) | 4 | 1045 / 1045 | market row matches | exact |

### Three traps

1. **The engine seed is NOT `replay_context.seed`.**
   `replay_context.seed` is the OpenSpiel *chance-node action id*. The C engine is
   seeded with a mixed value — see `openspiel_pyrants/state_c.py:16-21`:
   ```python
   _SEED_MIXER_MULTIPLIER = 2654435761
   _SEED_MIXER_MASK = 0x7FFFFFFF
   engine_seed = (shuffle_seed * _SEED_MIXER_MULTIPLIER) & _SEED_MIXER_MASK
   ```
   Getting this wrong yields a *plausible but different* game that desyncs within a few
   moves. There is a required test for this (see Task 5).

2. **Move matching is exact via `CMoveWrapper.to_payload()`.**
   `replay_log[].payload` was written by that same method — `scripts/run_ismcts.py:589`
   calls `state.move_to_payload(...)` → `move.to_payload()` (`engine_c/bindings/ce_api.py:177`),
   which normalizes move-type names (`resolve_generic` → `resolve_generic_choice`, etc.).
   So the match is plain dict equality against the live legal-move set:
   ```python
   match = next((m for m in session.legal_moves() if m.to_payload() == payload), None)
   ```
   Do **not** match on the `label` string or on `move_type` alone.

3. **`summary.json:setup_data_sha256` mismatches are advisory, not fatal.**
   The older `game_0001..0003` artifacts have a mismatching sha yet replay bit-perfectly
   (final scores and market rows identical). The difference is serialization-level, not
   semantic. Surface it as a warning banner; **never** block the replay on it. The real
   desync detector is per-step legal-move matching.

### Performance (measured, 1057-step 4-player game)

| Operation | Cost |
|---|---|
| `CEngine.initialize(...)` | 52 ms (once per loaded replay) |
| `CEngine.create_game(...)` | 1 ms |
| Full 1057-step replay | 78 ms (**0.07 ms/step**) |

**Consequence:** step-back and slider-seek are implemented as *destroy session → recreate
→ fast-forward*. Worst case ≈ 80 ms, imperceptible. **Do not build snapshot
checkpointing, an undo stack, or state serialization** — it is unnecessary complexity.

### Reference reconstruction (this exact code worked)

```python
from engine_c.bindings.ce_api import CEngine
from engine_c.bindings.session import CSession
from game_setup.market_setup import combine_two_deck_market_setup, discover_full_deck_profiles

ctx = replay["replay_context"]
profiles = {p.deck_id: p for p in discover_full_deck_profiles(DECKS_DIR)}
base_setup = json.loads(Path(ctx["setup_path"]).read_text(encoding="utf-8"))
setup_json = json.dumps(
    combine_two_deck_market_setup(base_setup, profiles[ctx["deck_a_id"]], profiles[ctx["deck_b_id"]])
    .to_setup_data()
)

eng = CEngine()
eng.initialize(
    catalog_path=ctx["card_path"],
    board_path=ctx["board_path"],
    setup_path=ctx["setup_path"],
    setup_data_json=setup_json,
)
session = CSession(eng, ctx["player_ids"], seed=engine_seed(ctx["seed"]))

for entry in replay["replay_log"]:
    if entry["payload"].get("move_type") == "__terminal__":
        break                      # sentinel, not a move
    move = next((m for m in session.legal_moves() if m.to_payload() == entry["payload"]), None)
    if move is None:
        raise ReplayDesyncError(...)
    session.submit_move(move)
```

### Artifact format reference

`artifacts/ismcts/**/game_XXXX/` contains:

| File | Use here |
|---|---|
| `replay.json` | **Required.** `replay_context` (board/card/setup paths, `player_ids`, `seed`, `deck_a_id`, `deck_b_id`) + `replay_log` (one entry per decision, plus a trailing `__terminal__` sentinel) + `step_count`, `winner_id`, `final_scores` |
| `summary.json` | Optional. Labels + `setup_data_sha256` + `outcome`/`winner`/`decision_count` |
| `decisions.jsonl` | Optional. Per-decision telemetry; line N ↔ `replay_log[N]` (`node` == `step_index`). Fields: `legal_moves`, `policy`, `visit_counts`, `chosen_action_id`, `chosen_move`, `wall_time_ms`, `sims_requested` |
| `steps.jsonl` | **Do not load** (2–4 MB, and some are stale/mixed-run). Offline verifier only |

`replay_log[]` entry: `{step_index, player_id, round_number, phase, move_type, label, payload}`.
Payload shapes seen in the corpus: `initial_placement`, `play_card`, `deploy`, `recruit`,
`end_main_phase`, `resolve_end_of_turn`, `resolve_cleanup`, `resolve_generic_choice`,
`promote_card`, `__terminal__`.

There are currently **18** `replay.json` files under `artifacts/ismcts/`.

---

## Architecture

Three new modules plus three surgical edits to `interface/game_viewer.py`.

```
interface/replay_loader.py   pure  — discovery, setup recomposition, seed mixer
interface/replay_player.py   pure  — CSession lifecycle, step/seek/desync
interface/replay_viewer.py   Tk    — ReplayViewerApp(GameViewerApp) + main()
```

`replay_loader` and `replay_player` must import **no Tk and no pyspiel** — that keeps
them unit-testable headless and keeps the viewer's startup free of the OpenSpiel import.

---

## Tasks

### 1. `interface/replay_loader.py` (pure)

```python
ENGINE_SEED_MULTIPLIER = 2654435761
ENGINE_SEED_MASK = 0x7FFFFFFF

def engine_seed(shuffle_seed: int) -> int:
    """Mirror openspiel_pyrants.state_c._public_to_seed without importing pyspiel."""
    return (int(shuffle_seed) * ENGINE_SEED_MULTIPLIER) & ENGINE_SEED_MASK
```
Add a comment pointing at `openspiel_pyrants/state_c.py:20` and note that
`tests/test_replay_loader.py` asserts parity.

```python
@dataclass(frozen=True)
class ReplayMeta:
    game_dir: Path
    run_id: str
    label: str            # "game_0003 · dragon/drow · seed 45 · 4p · 1026 moves · p2 win"
    player_ids: tuple[str, ...]
    deck_a_id: str
    deck_b_id: str
    shuffle_seed: int
    step_count: int
    outcome: str | None
    winner_id: str | None

def discover_replays(root: Path) -> list[ReplayMeta]:
    """rglob('replay.json'), newest-first; tolerate a missing/!unreadable summary.json."""

@dataclass
class ReplayBundle:
    meta: ReplayMeta
    replay: dict
    summary: dict | None
    decisions: list[dict]      # [] when decisions.jsonl is absent
    setup_json: str
    setup_sha_matches: bool | None   # None when summary.json has no sha

def load_replay(game_dir: Path) -> ReplayBundle: ...
```

**Path portability (required).** `replay_context` carries absolute Windows paths from the
machine that produced the run. Resolve each of `board_path` / `card_path` / `setup_path`;
if it does not exist, fall back to the module defaults already defined in
`interface/game_viewer.py` (`DEFAULT_BOARD_PATH`, `DEFAULT_CARD_PATH`, `DEFAULT_SETUP_PATH`)
and record that a substitution happened so the viewer can say so.

`decisions.jsonl` is small (315–672 KB); read it eagerly, skipping malformed lines.

### 2. `interface/replay_player.py` (pure)

```python
class ReplayDesyncError(RuntimeError):
    def __init__(self, step_index: int, expected: dict, legal: list[dict]): ...

class ReplayPlayer:
    def __init__(self, bundle: ReplayBundle) -> None: ...

    @property
    def index(self) -> int: ...          # moves applied so far, 0..total_steps
    @property
    def total_steps(self) -> int: ...    # len(replay_log) minus the __terminal__ sentinel
    @property
    def session(self) -> CSession: ...   # for build_c_game_view
    @property
    def is_terminal(self) -> bool: ...

    def entry_at(self, i: int) -> dict | None: ...      # replay_log[i]
    def decision_at(self, i: int) -> dict | None: ...   # decisions[i]
    def next_entry(self) -> dict | None: ...            # entry_at(self.index)

    def reset(self) -> None: ...
    def step_forward(self) -> bool: ...   # False at end
    def step_back(self) -> None: ...      # seek(index - 1)
    def seek(self, i: int) -> None: ...   # clamp, rebuild, fast-forward
    def close(self) -> None: ...
```

Rules:
- Build the `CEngine` **once** in `__init__` and reuse it across every rebuild.
- Every rebuild must `self._session.destroy()` the old session first (the arena leaks
  otherwise).
- Never submit the `__terminal__` sentinel.
- `seek()` clamps to `[0, total_steps]`.
- On no-match, raise `ReplayDesyncError` carrying the step index, the expected payload,
  and up to ~10 live legal payloads. Leave the session at the last good state.

### 3. Three edits to `interface/game_viewer.py` (no behavior change)

Keep the diff minimal — this file is a top-5 churn hotspot.

| # | Anchor | Change |
|---|---|---|
| 3a | `__init__`, `interface/game_viewer.py:658` | Add keyword-only `autostart: bool = True` to `__init__`; guard the trailing `self._start_new_game()` with `if autostart:` |
| 3b | `_build_ui`, `interface/game_viewer.py:664-721` | Move the `setup_controls` block (line 667) and the `action_controls` block (line 711) into a new overridable `def _build_control_bar(self, controls: ttk.Frame) -> None:`; `_build_ui` keeps `controls = ttk.Frame(frame)` + `controls.pack(fill=tk.X)` and calls `self._build_control_bar(controls)`. Everything from `content = ttk.Frame(frame)` (line 723) down is untouched |
| 3c | `_refresh_view`, `interface/game_viewer.py:1116-1120` | Initialize `self._suppress_score_dialog = False` in `__init__` and change the guard to `if view.is_terminal and not self._game_over_shown and not self._suppress_score_dialog:` |

**Acceptance for this task:** `just game-viewer` looks and behaves exactly as before, and
`pytest tests/test_game_viewer.py tests/test_game_renderer.py` passes unchanged.

### 4. `interface/replay_viewer.py` — `ReplayViewerApp(GameViewerApp)`

Construct the base with `autostart=False`, then load the selected replay.

**Control bar** (`_build_control_bar` override) — same `ttk` idiom, two stacked rows:

```
Replay: [game_0003 · dragon/drow · seed 45 · 4p · 1026 moves · p2 win ▾]  [Browse…] [Reload]
 |<   <   [ ▶ ]   >   >|    Speed: [0.50] s/step   [===|==============]  Step 217 / 1026
 Round 12 · main · p3 · deploy(target_node_id='route_1')          ⚠ setup hash differs
```

- Replay combobox populated from `discover_replays(ROOT_DIR / "artifacts" / "ismcts")`.
- `Browse…` → `filedialog.askopenfilename` for a `replay.json`, `initialdir` at
  `artifacts/ismcts`.
- Transport: `|<` reset, `<` step back, `▶/⏸` toggle, `>` step forward, `>|` seek to end.
- **Speed**: `ttk.Spinbox`, 0.05–5.0 s, increment 0.05, default 0.50, bound to a
  `tk.DoubleVar`.
- **Timeline**: `ttk.Scale` over `[0, total_steps]`. Drag → `seek()`. Guard against the
  feedback loop where a programmatic `.set()` re-triggers the scale command.
- Advisory warning label (yellow) when `setup_sha_matches is False` or a path was
  substituted.

**Autoplay loop**
```python
def _tick(self) -> None:
    if not self._playing: return
    if not self.player.step_forward():
        self._set_playing(False); return          # auto-pause at the end
    self._refresh_after_step()
    self._play_after_id = self.root.after(int(self.speed_var.get() * 1000), self._tick)
```
Read the interval from the var **each tick** so speed changes apply immediately. Store
`self._play_after_id`; `after_cancel` it on pause, on any seek, on load, and on window
close (bind `WM_DELETE_WINDOW`).

**Keyboard** — bind on `self.root`:
`Space` play/pause · `Ctrl+Left`/`Ctrl+Right` step · `Home`/`End` jump.
Deliberately **not** bare `Left`/`Right`: those are already bound on the market and hand
canvases (`interface/game_viewer.py:1975-2052`) and would collide when a card row has focus.

**Refresh after each step**
1. `self._suppress_score_dialog = True` during any multi-step fast-forward, restored after.
2. Call the inherited `self._refresh_view()` — it re-renders map, market, hand, played,
   VP breakdown, special stacks, and the other-player panels from `self.session`.
3. Point `self.session` at `self.player.session` (the base class reads `self.session`).
4. Update the transport labels and the timeline position.
5. **Highlight the recorded move**: find `self.player.next_entry()["payload"]` among
   `self._visible_legal_moves` (compare `legal_move.move.to_payload()`), then
   `selection_set` + `see()` that row. This turns the inherited Legal Moves listbox into
   the decision-by-decision review surface at zero extra cost.

**Board / layout / player count on load**
Reuse the inherited `_rebuild_package_for_loaded_state_c(view)`
(`interface/game_viewer.py:1068`) — it matches a layout by node-id set and sets
`player_count_var`, which is what makes 4-player replays and non-default maps render
correctly. Also set `self._deck_a_label` / `self._deck_b_label` from the bundle so the
market header reads correctly, and `self._demons_in_market` if either deck id is
`DEMONS_DECK_ID`.

**Read-only enforcement** — override to no-ops (optionally setting a status message):
`_apply_selected_legal_move` (`:1678`), `_apply_first_legal_move` (`:1668`),
`_on_legal_move_double_click` (`:2140`). Double-click currently *applies* a move.

**Decision inspector** — new `ttk.LabelFrame("Decision")` in the sidebar, above
"Legal Moves", fed from `decisions.jsonl`:
- chosen move · `sims_requested` · `wall_time_ms`
- a small listbox of the top-N policy entries: `p=0.42 (v=84)  play_card(card_id='noble')`,
  chosen entry marked
- when `decisions == []`: `(no decision telemetry)`

**`main()`** — mirror `interface/game_viewer.py:2182`'s multi-monitor/zoomed setup:
```
--artifacts-root  (default ROOT_DIR/"artifacts"/"ismcts")
--game-dir        (optional; load this replay immediately)
--board-path --layout-path --card-path --setup-path --decks-dir   (same defaults as game_viewer)
```

### 5. Tests

**`tests/test_replay_loader.py`**
- `test_engine_seed_matches_openspiel` — assert `engine_seed(n)` equals
  `openspiel_pyrants.state_c._public_to_seed(n)` for a spread of `n` (0, 1, 42, 43,
  2**16, 2**30). **This is the guard for trap #1.**
- `discover_replays` finds every `replay.json` under a tmp fixture tree; a directory with
  no `summary.json` still yields a usable `ReplayMeta`.
- Path fallback: a `replay_context` with a nonexistent `board_path` resolves to
  `DEFAULT_BOARD_PATH` and flags the substitution.

**`tests/test_replay_player.py`** (guard with
`pytest.mark.skipif(not GAME_DIR.exists())` so the suite survives a pruned `artifacts/`)
- `test_full_replay_is_deterministic` — replay `artifacts/ismcts/game_0000` end to end:
  `player.index == 517`, `is_terminal`, `session.final_scores() == replay["final_scores"]`
  (`{"p1": 64, "p2": 93}`), `session.winner_id() == "p2"`. **This is the regression test
  that would have caught the seed-mixer trap.**
- `test_seek_round_trips` — `seek(300)`, capture `(round_number, phase, current_player_id,
  per-player scores)`; `seek(50)`; `seek(300)`; assert the tuple is identical.
- `test_step_back` — `seek(10)`, `step_back()`, `index == 9` and state matches `seek(9)`.
- `test_desync_raises` — corrupt one payload in a loaded bundle; assert
  `ReplayDesyncError` with the right `step_index`, and that the session is still usable.
- `test_four_player_replay` — one of the `experiments/sims_vs_wins/**` 4-player games
  replays fully with matching final scores.

Keep the Tk layer untested beyond import (matching how `tests/test_game_viewer.py`
treats the existing viewer).

### 6. Offline verifier + justfile

`scripts/verify_replays.py` — walk `artifacts/ismcts`, replay each game headless, print a
per-game `OK / DESYNC@step / final-score mismatch` table, exit non-zero on any failure.
Cheap (≈80 ms/game) and it is the tool that proves an engine change broke replay
compatibility.

`justfile` additions, next to the existing `game-viewer` target (line 55):
```
replay-viewer:
    & {{python}} -m interface.replay_viewer

verify-replays:
    & {{python}} scripts/verify_replays.py
```

---

## Edge cases (all must be handled)

| Case | Handling |
|---|---|
| `setup_data_sha256` mismatch | Yellow advisory banner; replay proceeds. **Never block** |
| Desync mid-replay | Auto-pause, freeze at last good state, `messagebox` with step index + expected payload + sample legal payloads |
| Missing `summary.json` | Derive `ReplayMeta` from `replay.json` alone |
| Missing/truncated `decisions.jsonl` | Decision panel shows `(no decision telemetry)` |
| `replay_context` paths not on this machine | Fall back to repo defaults, flag the substitution |
| 4-player replay | `_rebuild_package_for_loaded_state_c` sets `player_count_var`; other-player panels populate |
| Trailing `__terminal__` entry | Never submitted; `total_steps` excludes it |
| Reaching terminal | Auto-pause; `ScoreDialog` fires once (suppressed during fast-forward) |
| Loading a second replay | Cancel timer, `close()` the old player, destroy the old session |
| Window close mid-play | `after_cancel` + `close()` via `WM_DELETE_WINDOW` |

---

## Phasing (each phase independently reviewable)

1. **`replay_loader.py` + `replay_player.py` + tests** — headless, no Tk. Gate: all
   tests in Task 5 green.
2. **`scripts/verify_replays.py`** — gate: all 18 artifacts report OK (or a *documented*
   desync for known-stale ones).
3. **Three `game_viewer.py` hooks** — gate: hotseat viewer visually unchanged, existing
   tests pass.
4. **`replay_viewer.py` skeleton** — load + step forward/back + seek + status, inherited
   rendering. Gate: a replay renders identically to hotseat at the same state.
5. **Autoplay** — timer, speed spinbox, timeline slider, keyboard.
6. **Decision inspector + chosen-move highlight in Legal Moves.**
7. **justfile targets + a short README/docs note.**

## Definition of done

- `just replay-viewer` opens, lists all 18 replays, loads any of them.
- Play/pause runs the game unattended at the configured interval; changing the speed
  takes effect on the next tick.
- Step forward/back and slider-drag land on any step in under ~100 ms.
- The move the bot actually chose is highlighted in the Legal Moves list at every step.
- The board, market, hand, played cards, VP breakdown and special stacks are visually
  identical to the hotseat viewer.
- `just verify-replays` is green.
- No move can be applied that the log did not record.
