# Pyrants

Python engine and terminal UI for *Tyrants of the Underdark*, a deck-building area-control board game.

The engine is pure — it takes a game state and a move, returns a new state. No side effects, no I/O. The interface layer renders the board in the terminal and handles player interaction.

## Install

Requires Python 3.12+.

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install poetry
poetry install
```

Or use `just` if you have it installed:

```bash
just test    # verify the install works
```

## Commands

| Command | What it does |
|---------|-------------|
| `just board-creator` | Build and edit board topology and layouts |
| `just game-viewer` | Play interactively in the terminal |
| `just game-simulate` | Run headless simulations (auto-play) |
| `just replay-viewer` | Step through a recorded simulation |
| `just test` | Run the test suite |

Each command accepts `--help` via `just <name>-help`, e.g. `just game-simulate-help`.

## Architecture

```
engine/         Pure game logic — state, moves, rules, phases, scoring
interface/      Terminal UI — board renderer, dialogs, parser, viewers
game_setup/     Loaders that assemble game state from JSON data files
game_session.py Shared session controller (used by simulation and interactive play)
data/           JSON fixtures — boards, cards, decks, layouts, scenarios
tests/          pytest suite
```

The engine has no I/O. It imports nothing from `interface/` or `game_setup/`. This keeps it testable and reusable across the simulation, interactive viewer, and replay viewer.

## Data Format

All game content lives in `data/` as JSON:

- `data/boards/` — board topology (sites, routes, victory point values)
- `data/cards/` — card catalog and effect families
- `data/decks/` — deck definitions and starter rosters
- `data/layouts/` — visual layout coordinates for terminal rendering
- `data/scenarios/` — pre-built game states for testing

The board creator writes to `data/boards/` and `data/layouts/`.
