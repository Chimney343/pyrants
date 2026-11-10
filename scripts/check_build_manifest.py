"""Validate engine_c's single source/test manifest.

``engine_c/sources.txt`` must list every library source exactly once.
``engine_c/tests.txt`` must list every C test source exactly once, grouped
under the executable that builds it. Any unlisted ``test_*.c`` is a signal
that a test was added without a build target (or should be deleted).

The Makefile's ``clean`` recipe must read its test binaries from ``tests.txt``
rather than hand-listing them, so a new test cannot be added to the build and
then left behind by ``make clean``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine_c"
SOURCES = ENGINE / "sources.txt"
TESTS = ENGINE / "tests.txt"
MAKEFILE = ENGINE / "Makefile"
# A clean recipe that derives its test binaries from tests.txt contains this
# redirection. A hand-written list never does.
CLEAN_MANIFEST_READ = re.compile(r"^\tdone < tests\.txt$", re.MULTILINE)


def _lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _clean_recipe(makefile_text: str) -> str | None:
    """Return the tab-indented recipe lines under the ``clean:`` target."""
    lines = makefile_text.splitlines()
    try:
        start = lines.index("clean:")
    except ValueError:
        return None
    recipe: list[str] = []
    for line in lines[start + 1 :]:
        if not line.startswith("\t"):
            break
        recipe.append(line)
    return "\n".join(recipe)


def main() -> int:
    errors: list[str] = []

    source_names = _lines(SOURCES)
    if len(set(source_names)) != len(source_names):
        errors.append("sources.txt: duplicate entries")
    for name in source_names:
        if not (ENGINE / name).is_file():
            errors.append(f"sources.txt: missing {name}")

    discovered_library = {
        path.relative_to(ENGINE).as_posix()
        for path in ENGINE.glob("*.c")
        if not path.name.startswith("test_") and path.name != "profile_runner.c"
    } | {
        path.relative_to(ENGINE).as_posix()
        for path in (ENGINE / "ops").glob("*.c")
    }
    listed_library = set(source_names)
    for name in sorted(discovered_library - listed_library):
        errors.append(f"sources.txt: unlisted library source {name}")
    for name in sorted(listed_library - discovered_library):
        errors.append(f"sources.txt: listed source is not an engine_c library file: {name}")

    test_sources: set[str] = set()
    exe_names: set[str] = set()
    for line in _lines(TESTS):
        if "|" not in line:
            errors.append(f"tests.txt: expected '<exe>|<sources>', got {line!r}")
            continue
        exe, raw_sources = (part.strip() for part in line.split("|", 1))
        if not exe or "/" in exe or "\\" in exe:
            errors.append(f"tests.txt: invalid executable name {exe!r}")
        if exe in exe_names:
            errors.append(f"tests.txt: duplicate executable {exe!r}")
        exe_names.add(exe)

        names = raw_sources.split()
        if not names:
            errors.append(f"tests.txt: {exe} has no sources")
        for name in names:
            if not (ENGINE / name).is_file():
                errors.append(f"tests.txt: {exe} missing source {name}")
            test_sources.add(Path(name).name)

    discovered_tests = {
        path.name for path in ENGINE.glob("test_*.c")
    } | {
        path.name for path in (ENGINE / "tests").glob("test_*.c")
    }
    for name in sorted(discovered_tests - test_sources):
        errors.append(f"tests.txt: unlisted test source {name}")
    for name in sorted(test_sources - discovered_tests):
        errors.append(f"tests.txt: listed test source not found: {name}")

    # `make clean` must take its test binaries from tests.txt. A hand-listed
    # clean recipe silently rots: test_visibility was added to tests.txt and
    # omitted from clean, so `make clean` left a stale binary behind.
    clean_block = _clean_recipe(MAKEFILE.read_text(encoding="utf-8"))
    if clean_block is None:
        errors.append("Makefile: no clean recipe")
    elif not CLEAN_MANIFEST_READ.search(clean_block):
        errors.append(
            "Makefile: clean recipe must read test binaries from tests.txt "
            "(expected a 'done < tests.txt' loop), not hand-list them"
        )

    if errors:
        print("build manifest check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        f"build manifest OK: {len(source_names)} library sources, "
        f"{len(exe_names)} test executables"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
