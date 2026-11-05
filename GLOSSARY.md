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
