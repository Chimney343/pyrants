# Plan: cache game-definition loading in IS-MCTS (cheapest perf win)

## Goal
Eliminate repeated JSON parsing and `GameDefinition` rebuilding that happens every time OpenSpiel deep-copies `PyrantsGame` during an IS-MCTS run.

## Why this is the cheapest win

From the `just ismcts-perf` profile (`artifacts/ismcts/performance_testing/cprofile.pstats`):

- `json.decoder.raw_decode` costs **4.70 s** across only **5,505 calls**.
- `openspiel_pyrants/game.py:_build_definition` is invoked **1,831 times**, each time re-reading `board.json`/`cards.json`/`setup.json` from disk and re-validating them into Pydantic models.
- The previous captured profile (`cprofile_after.pstats`) had only **879** `raw_decode` calls, so this is a clear regression/expansion at scale.

`GameDefinition` is immutable once built, so sharing it across game-object clones is safe and low-risk. A small localized change in `openspiel_pyrants/game.py` should recover ~3.5 % of total CPU time with no engine logic changes.

## Current behavior

`PyrantsGame.__deepcopy__` (line 92-97) does:

```python
def __deepcopy__(self, memo):
    cls = type(self)
    new_game = cls.__new__(cls)
    new_game.__init__(self.get_parameters())
    ...
```

`__init__` always calls `self._build_definition(resolved)`, which re-reads and re-validates the JSON payloads. OpenSpiel clones the game many times per MCTS iteration, causing the 1,831 rebuilds.

## Proposed change

### 1. Share the definition on deep-copy (primary fix)

Change `PyrantsGame.__deepcopy__` so the new instance reuses the existing `_definition` instead of reconstructing it:

```python
def __deepcopy__(self, memo):
    cls = type(self)
    new_game = cls.__new__(cls)
    new_game.__dict__["_params"] = dict(self._params)
    new_game.__dict__["_definition"] = self._definition
    new_game.__dict__["_player_ids"] = self._player_ids
    new_game.__dict__["_shuffle_seed_count"] = self._shuffle_seed_count
    memo[id(self)] = new_game
    return new_game
```

Because `_definition` is immutable, sharing is safe. The new instance still has independent `_params`, `_player_ids`, etc.

### 2. Add a module-level cache for file-based builds (defense in depth)

In `openspiel_pyrants/game.py`, cache `_build_definition` results keyed by the resolved parameter set. For the file-based path, use `(board_path, card_path, setup_path, mtime)`; for the `setup_data_json` path, use the JSON string content as key.

This protects any other code path that constructs `PyrantsGame` directly from re-parsing files.

```python
_definition_cache: dict[tuple[str, ...], GameDefinition] = {}

def _build_definition(self, resolved):
    board_path = resolved["board_path"]
    card_path = resolved["card_path"]
    setup_json = resolved.get("setup_data_json", "")
    if setup_json:
        cache_key = ("json", board_path, card_path, setup_json)
    else:
        setup_path = resolved["setup_path"]
        cache_key = (
            "files",
            board_path,
            card_path,
            setup_path,
            str(Path(board_path).stat().st_mtime),
            str(Path(card_path).stat().st_mtime),
            str(Path(setup_path).stat().st_mtime),
        )
    if cache_key not in _definition_cache:
        if setup_json:
            board_data = _json.loads(Path(board_path).read_text(encoding="utf-8"))
            card_data = _json.loads(Path(card_path).read_text(encoding="utf-8"))
            setup_data = _json.loads(setup_json)
            definition = build_game_definition_from_dicts(board_data, card_data, setup_data)
        else:
            definition = build_game_definition_from_files(
                Path(board_path), Path(card_path), Path(setup_path)
            )
        _definition_cache[cache_key] = definition
    return _definition_cache[cache_key]
```

Keep `_init_attrs` unchanged; it will benefit from the same cache.

## Acceptance criteria

1. `just ismcts-perf` runs to completion.
2. In the new `cprofile.pstats`:
   - `json.decoder.raw_decode` calls drop from ~5,500 to **< 100**.
   - `openspiel_pyrants/game.py:_build_definition` calls drop from ~1,800 to **< 100**.
   - Total CPU time improves by at least **2 s** (≈ 1.5 %).
3. Existing tests still pass: `just test`.
4. Engine-purity test still passes (no I/O introduced in `engine/`).

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Shared mutable state via `_definition` | `GameDefinition` and its sub-models are immutable Pydantic models; treat as read-only. |
| Cache grows unbounded | Only two parameter sets are used in practice; optionally bound with `functools.lru_cache` or a small dict. |
| File changes during long process not picked up | Include `st_mtime` in cache key. |
| `setup_data_json` differs per instance | Include the JSON string in the cache key. |
| OpenSpiel expects `__deepcopy__` to return fully initialized game | Set all attributes directly so `_init_attrs` is unnecessary. |

## Implementation steps

1. Read `openspiel_pyrants/game.py` fully to confirm attributes used.
2. Implement `__deepcopy__` reuse and module-level `_definition_cache`.
3. Run `ruff check .`.
4. Run `just test`.
5. Run `just ismcts-perf` and compare the new `cprofile_top.txt` against the baseline.
6. Update `artifacts/ismcts/performance_testing/comparison_report.md` with the new numbers.

## Files to change

- `openspiel_pyrants/game.py` only.

## Out of scope

- Larger copy/clone optimizations (`_cow_clone`, `deepcopy`, Pydantic validation) — those are bigger wins but require engine/state changes and more risk.
- `information_state_string` optimization — separate, more complex change.
