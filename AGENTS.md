# Project Guidelines

## Tool Preference

Prefer `codebase-memory-mcp` tools for codebase exploration, symbol lookup, and impact analysis. Fall back to `grep_search` / `file_search` only when MCP tools don't cover the query.

### Indexing

| Tool | Description |
|------|------------|
| `index_repository` | Index a repository into the graph. Auto-sync keeps it fresh after that. |
| `list_projects` | List all indexed projects with node/edge counts. |
| `delete_project` | Remove a project and all its graph data. |
| `index_status` | Check indexing status of a project. |

### Querying

| Tool | Description |
|------|------------|
| `search_graph` | Structured search by label, name pattern, file pattern, degree filters. Pagination via limit/offset. |
| `trace_call_path` | BFS traversal — who calls a function and what it calls. Depth 1-5. |
| `detect_changes` | Map git diff to affected symbols + blast radius with risk classification. |
| `query_graph` | Execute Cypher-like graph queries (read-only). |
| `get_graph_schema` | Node/edge counts, relationship patterns, property definitions per label. Run this first. |
| `get_code_snippet` | Read source code for a function by qualified name. |
| `get_architecture` | Codebase overview: languages, packages, routes, hotspots, clusters, ADR. |
| `search_code` | Grep-like text search within indexed project files. |
| `manage_adr` | CRUD for Architecture Decision Records. |
| `ingest_traces` | Ingest runtime traces to validate HTTP_CALLS edges. |

## Project Context

Python engine and terminal UI for *Tyrants of the Underdark* — a deck-building area-control board game. The engine is pure (no I/O), consuming validated JSON data files. The interface layer handles CLI rendering and interaction.

## Architecture

| Layer | Purpose |
|-------|---------|
| `engine/` | Pure game logic — state machine, rules, scoring, moves. No I/O. |
| `interface/` | Terminal UI — CLI, board renderer, dialogs, parser. |
| `game_setup/` | Loaders and board package assembly from JSON data. |
| `data/` | JSON fixtures — boards, cards, decks, layouts. |
| `tests/` | Pytest suite. Keep engine tests pure. |

## Key Conventions

- Keep `interface/__init__.py` free of eager imports from `interface/cli.py` (avoids `runpy` warnings).
- Starter decks contain duplicate card IDs by design — test zone sizes, not unique-card membership.
- Use `just` for task running (`just board-creator`, etc.). The venv is at `.venv/`.

## Build and Test

```bash
just board-creator    # launch the board creator UI
pytest -q             # run all tests
```
