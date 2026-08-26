"""Regression guard: deterimization_c.py must stay unreferenced by the live
C-backend path before it can be safely deleted. If this test ever fails,
someone wired the stub back in and the removal plan needs revisiting."""
from __future__ import annotations

import ast
from pathlib import Path

LIVE_C_BACKEND_FILES = [
    "openspiel_pyrants/game_c.py",
    "openspiel_pyrants/state_c.py",
    "openspiel_pyrants/observer_c.py",
    "openspiel_pyrants/action_encoding_c.py",
    "engine_c/bindings/c_adapter.py",
]

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_deterimization_c_not_imported_by_live_c_backend():
    for rel in LIVE_C_BACKEND_FILES:
        path = ROOT / rel
        imports = _imports(path)
        assert not any("deterimization_c" in name for name in imports), (
            f"{rel} imports deterimization_c — it is no longer dead code, "
            f"do not delete it without re-auditing this plan"
        )
