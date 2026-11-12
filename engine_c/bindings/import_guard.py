"""AST scan for the ``engine_c/bindings`` import guard (ADR-0011).

``engine_c/bindings`` is the engine's Python seam. It may use ``game_setup`` and
its own package; it must not reach the GUI, the OpenSpiel wrapper, the runner
scripts or the artifact layout. Those five roots are the rule, and the test that
enforces it lives in ``tests/c_engine/test_bindings_import_guard.py``.

The scan walks the whole module, including imports inside functions and
``try`` blocks: a deferred import is still a dependency, and a head-only audit
would miss exactly the violation it exists to catch.

Imports nothing from the package: this module must stay safe to import from
anywhere in ``engine_c.bindings``.
"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_IMPORT_ROOTS = frozenset(
    {"interface", "openspiel_pyrants", "pyspiel", "scripts", "run_artifacts"}
)


def _root(module: str | None) -> str:
    return (module or "").split(".", 1)[0]


def find_forbidden_imports(path: str | Path) -> list[tuple[int, str]]:
    """Return ``(lineno, module)`` for every forbidden import in *path*.

    A relative import (``from . import x``, ``from ..x import y``) resolves
    inside the package, so it can never name a forbidden root and is skipped.
    Raises ``SyntaxError`` on unparsable source rather than passing it.
    """
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _root(alias.name) in FORBIDDEN_IMPORT_ROOTS:
                    found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if _root(node.module) in FORBIDDEN_IMPORT_ROOTS:
                found.append((node.lineno, node.module or ""))
    return found
