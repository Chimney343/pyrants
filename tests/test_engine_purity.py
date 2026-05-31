"""Purity guardrails for engine modules."""

from __future__ import annotations

import ast
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1] / "engine"
FORBIDDEN_CALLS = {"print", "input", "open"}


def test_engine_has_no_interface_imports_or_direct_io() -> None:
    violations: list[str] = []

    for file_path in ENGINE_DIR.glob("*.py"):
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for imported in node.names:
                    if imported.name == "interface" or imported.name.startswith("interface."):
                        violations.append(f"{file_path.name}: imports interface module")

            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "interface" or module.startswith("interface."):
                    violations.append(f"{file_path.name}: imports from interface module")

            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_CALLS:
                    violations.append(f"{file_path.name}: forbidden call '{node.func.id}'")

    assert not violations, "\n".join(violations)
