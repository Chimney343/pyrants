# Cards Without tests/c_engine/ Test Files

Generated 2026-08-12. Catalog: 125 cards. Dedicated `tests/c_engine/test_card_*.py` files: 117. Cards without a dedicated C-engine test file: 8.

## Notes on naming / data quality

- **Conjurer** — has a dedicated C-engine test under a fuzzy name: `tests/c_engine/test_card_conjurer_behavior.py` (and `tests/test_card_conjurer.py`).
- **cloaker**, **nalfeshnee** — lowercase names in catalog (data quality). `nalfeshnee` has a dedicated test; `cloaker` does not.
- **Vampie Spawn** — catalog typo for "Vampire Spawn", which has a dedicated test (`test_card_vampire_spawn.py`).
- **Neogi** — top-level `tests/test_card_neogi.py` asserts only the catalog `execution_model`, not C-runtime behavior.
- **Mercenary Squad** — top-level `tests/test_card_mercenary_squad.py` exercises the C engine directly (not under `tests/c_engine/`).

## Cards without a dedicated `tests/c_engine/test_card_<id>.py`

| Card | Key | C-runtime coverage elsewhere |
|------|-----|------------------------------|
| Air Elemental | air_elemental | `tests/c_engine/test_engine_c.py` (integration) + legacy |
| Marilith | marilith | `tests/c_engine/test_engine_c.py` (integration) + legacy |
| Mercenary Squad | mercenary_squad | `tests/test_card_mercenary_squad.py` (C runtime) |
| Neogi | neogi | `tests/test_card_neogi.py` (catalog model only) |
| Brainwashed Slave | brainwashed_slave | legacy Python engine only |
| cloaker | cloaker | legacy Python engine only |
| Dragonclaw | dragonclaw | legacy Python engine only |
| Myconid Adult | myconid_adult | legacy Python engine only |

## Cards with no C-engine runtime coverage at all

These five are exercised only by the deprecated legacy Python engine (`tests/legacy_engine/`) or by catalog-shape assertions, never by the C engine:

- **brainwashed_slave** (Brainwashed Slave)
- **cloaker** (cloaker)
- **dragonclaw** (Dragonclaw)
- **myconid_adult** (Myconid Adult)
- **neogi** (Neogi — catalog `execution_model` only, no runtime test)
