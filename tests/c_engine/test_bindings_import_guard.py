"""The import guard for ``engine_c/bindings`` (ADR-0011, brief F1).

``engine_c/bindings`` is the engine's Python seam: it may use ``game_setup`` and
its own package, and nothing above them. It must not reach the GUI
(``interface``), the OpenSpiel wrapper (``openspiel_pyrants``, ``pyspiel``), the
runner scripts (``scripts``) or the artifact layout (``run_artifacts``) — the
handle knows no filesystem artifact format.

The scan covers function-level imports too: ``import x`` inside a function is
still a dependency, and an audit that only reads module heads misses it.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from engine_c.bindings.import_guard import (  # noqa: E402
    FORBIDDEN_IMPORT_ROOTS,
    find_forbidden_imports,
)

BINDINGS_DIR = _REPO_ROOT / "engine_c" / "bindings"

assert BINDINGS_DIR.is_dir(), BINDINGS_DIR


def _report(path: Path) -> list[tuple[str, int, str]]:
    return [(path.name, lineno, module) for lineno, module in find_forbidden_imports(path)]


def test_the_rule_covers_the_five_named_packages():
    named = {"interface", "openspiel_pyrants", "pyspiel", "scripts", "run_artifacts"}
    assert named <= FORBIDDEN_IMPORT_ROOTS
    assert len(FORBIDDEN_IMPORT_ROOTS) == len(named)


def test_no_bindings_module_imports_upwards():
    violations = []
    for path in sorted(BINDINGS_DIR.glob("*.py")):
        violations.extend(_report(path))
    assert violations == [], (
        "engine_c/bindings must not import interface, openspiel_pyrants, pyspiel, "
        f"scripts or run_artifacts; found {violations}"
    )


def test_the_guard_sees_a_function_level_import():
    probe = BINDINGS_DIR / "_tmp_import_guard_probe.py"
    probe.write_text(
        "def late_import():\n"
        "    import json\n"
        "    import pyspiel  # noqa: F401\n"
        "    from interface import replay_loader  # noqa: F401\n",
        encoding="utf-8",
    )
    try:
        found = _report(probe)
        assert {module for _, _, module in found} == {"pyspiel", "interface"}, found
        assert {lineno for _, lineno, _ in found} == {3, 4}, found
    finally:
        probe.unlink()


def test_the_guard_reads_relative_and_standard_imports_as_clean():
    probe = BINDINGS_DIR / "_tmp_import_guard_probe.py"
    probe.write_text(
        "from __future__ import annotations\n"
        "import json\n"
        "from .ce_api import CEngine\n"
        "from .. import something\n"
        "from game_setup.loaders import assemble_catalog_text\n",
        encoding="utf-8",
    )
    try:
        assert _report(probe) == []
    finally:
        probe.unlink()


def test_the_guard_parses_every_file_it_is_given():
    for path in sorted(BINDINGS_DIR.glob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
