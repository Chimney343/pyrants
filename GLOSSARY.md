# Glossary

Architecture vocabulary for the pyrants deepening work. Terms are added when a
module's shape is settled, not before.

## Shared vocabulary

- **module** - anything with an interface and an implementation.
- **interface** - everything a caller must know: types, invariants, call
  order, error modes, and memory layout.
- **depth** - a deep module puts a lot of behaviour behind a small interface.
  A shallow module's interface is about as complex as its implementation.
- **seam** - where one module's interface meets another's and something could
  be substituted.
- **adapter** - the concrete thing plugged into a seam.
- **leverage** - how many callers one interface serves.
- **locality** - whether a change or bug stays in one place.
- **deletion test** - if the module were deleted, would complexity concentrate
  elsewhere (it earns its keep) or simply vanish or move (it is shallow)?
- **one adapter / two adapters** - one adapter means a hypothetical seam; two
  adapters make it real.

## Settled modules

- **build manifest** - the pair `engine_c/sources.txt` (library sources) and
  `engine_c/tests.txt` (test executables and their sources), plus
  `scripts/check_build_manifest.py`. All C build paths and `just test-c` read
  it, so the MSVC, ASan, profiling, and GCC lists cannot drift.
- **layout probe** - the C module `engine_c/layout.c` exposing
  `engine_layout_size(type)` and `engine_layout_offset(type, field)` from a
  table built with `sizeof`/`offsetof`. `engine_c/bindings/layout_probe.py`
  compares every mirrored ctypes struct against it at import.
- **mirrored struct** - a Python `ctypes.Structure`/`Union` that reads a C
  struct's memory directly. Mirrored structs are listed in
  `_MIRRORED_STRUCTS` in `engine_c/bindings/engine_bindings.py`; the layout
  probe asserts their size and field offsets.
- **legal move** - a move `engine_apply` accepts. `engine_legal_moves` and
  `CEngineAdapter.legal_moves` return only legal moves, so callers no longer
  filter UI placeholders or re-check end-main legality.
- **display move** - a viewer-facing `(move, applicable)` pair returned by
  `engine_display_moves` / `CSession.display_moves`. It includes legal moves
  (applicable = true) plus display-only entries such as a non-viable modal
  option or an end-main-phase entry blocked by a deferred promotion
  (applicable = false).
- **move display query** - the C `engine_display_moves` and its Python
  `display_moves()` adapters. The legal-move query compacts the applicable
  entries; the display query keeps the viewer's full ordered list.
- **move capacity** - the frozen number of moves a buffer can hold,
  `ENGINE_MOVE_CAPACITY` (1024) in `engine_c/state.h`, exported as
  `engine_move_capacity()`. It is the single source for the C rollout buffer,
  the Python binding buffers, and `NUM_DISTINCT_ACTIONS`. Both move queries
  return how many moves *exist*, which can exceed it; a caller that asks for
  more than the capacity gets an error (`MoveCapacityError` in Python) instead
  of a silently short list.
- **enumeration probe** - `legal_generic_target_selection_probe()`, the
  existence-only variant of target enumeration. The engine's own "is this list
  empty?" checks use it so they stop at the first target instead of counting
  the whole space; public move queries count.
- **op** - one card action verb (`return_spy`, `place_spy`, ...). An op module
  owns its needs-selection rule, target enumeration, typed target, apply and
  describe.
- **op table** - the central `CardOp` dispatch table in `engine_c/ops/`. A
  migrated op answers from the table; unmigrated ops fall back to the legacy
  action/selection registries.
- **op target** - the typed internal record (`OpTarget`) built from the frozen
  `Move` payload at the apply boundary. The payload string stays the wire
  format; apply/describe consume the typed record.
- **op dispatcher** - an op whose own surface is a set of effect kinds
  (`custom_effect` today). It is not a leaf op; it needs a catalog-level
  effect-kind decomposition rather than a shallow per-op wrapper, and is
  deferred to candidate 4.
- **catalog field** - a named, loader-validated value on a card or action
  (`on_discard` is the first). The runtime reads the field from the loaded
  definition instead of branching on card ids or untyped strings.
- **card property** - a catalog field describing a card-wide rule, such as
  `on_discard: "inner_circle"` or the planned negative-card flag.
- **option viability predicate** - a named catalog field describing when a
  modal option is offered (Gauth/Cloaker/Mummy Lord/Grazzt use the validated
  predicates in place of card-id branches).
- **timing trigger** - the loader-validated `immediate`/`end_of_turn`
  action field. End-of-turn actions are deferred to the EOT phase and applied
  once; they must not execute inline during pending-generic resolution.
- **action variant** - the loader-mapped `CardAction.variant` enum for a
  compared `source_fragment` family. The descriptive string stays for labels;
  the runtime switches on the validated enum. The `force_discard` modes are
  the first migrated family.
- **decision stack** - the C module `engine_c/pending.c` that owns everything
  the engine waits on: the immediate and end-of-turn promotion stacks, the paid
  ability and the generic choice. It owns their ordering, stack mechanics,
  clone, hash, describe and persistence behind one interface.
- **decision record** - what the decision stack answers about a waiting
  decision: the kind, its priority, and how many are queued. ADR-0006 kept it
  internal to C; ADR-0011 has C render it as one JSON record
  (`engine_pending_decision_json`, same size-query contract as the player view)
  that the game handle decodes, so no Python code reads pending storage.
- **game handle** - the module `engine_c/bindings/handle.py` that owns one game
  for every Python caller: setup from a seed or files, apply, clone,
  determinize, legal and display moves, the decision record, views, the tree
  key, the rollout, and replay from an in-memory log. Its interface carries no
  ctypes type, raw pointer or `CState`, so a C-side implementation could later
  take over its body without moving a caller (ADR-0011, Proposed). `PyrantsCState`
  and `CSession` are its two adapters.
- **handle failure family** - `EngineError(RuntimeError)` and its subclasses
  `EngineApplyRejected`, `EngineCloneFailed`, `EngineDeterminizeFailed` and
  `MoveCapacityError`. The base is not for catching, so an adapter that keeps
  its old failure contract catches only the one subclass it means.
- **run artifact** - the on-disk format of one IS-MCTS game: `manifest.json`,
  `replay.json`, `summary.json` and `decisions.jsonl`. The `run_artifacts/`
  package owns reading it today and the writer side once candidate 9's recorder
  lands. The game handle replays from an in-memory log and knows nothing about
  these files.
- **pending kind** - the `PendingKind` enum naming one waiting mechanism
  (`immediate`, `end_of_turn`, `ability`, `generic`, and `chance`, which is
  reserved for ADR-0002's postponed F-003 frame and is not built).
- **scenario schema** - the versioned layout of a scenario document.
  Version 2 adds `schema_version`, `state.pending` and the shuffle stream;
  version 1 documents (no `pending`) still load, with no pending decision.
- **visibility module** - the C module `engine_c/visibility.c` that answers
  "what does player p know?". Its visibility rule drives the player view, the
  tree key and determinization (ADR-0007).
- **visibility rule** - the module's table: for each card zone and each
  relation (self or opponent), whether the observer sees the cards or only a
  count, and whether determinization resamples the zone. A zone the rule shows
  is never resampled. Under the owner's rule (ADR-0008) a player sees every
  discard pile and the devour pile, and no player sees any deck, its own
  included.
- **player view** - one player's view of a state, rendered by the visibility
  module's single walk. As JSON it is `private_view_json`, the OpenSpiel
  observation string.
- **tree key** - `engine_infostate_hash`: a 128-bit fingerprint of the same
  walk as the player view, so two states share a key exactly when they share a
  view. Only comparable inside one process.
- **resampled zone** - a zone determinization reshuffles. A player's resampled
  zones are pooled, sorted by card id, and shuffled together; a shared one is
  sorted and shuffled alone. The sort makes a sampled world depend only on the
  observer's information and the seed, never on the real arrangement. A deck,
  the observer's own included, is a resampled zone.
- **deduced multiset** - what can be worked out from public history but is not
  seen directly: an opponent's hand+deck+discard bag, your own deck's remainder,
  what is left in the market deck. `nn/public.py` computes these; by decision
  they stay outside the player view. The opponent bag still folds in the now-
  visible discard pile, so the NN tensor is unchanged by the owner's rule
  (ADR-0008); this is a known gap between the rule and the tensor.
