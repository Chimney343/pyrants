"""Mechanically check docs/**/*.md for the drift that manual audits keep re-finding by hand.

This is a best-effort linter over prose Markdown, not a full parser. It checks four things:

1. Path existence  — every backtick-quoted `path/to/file[:LINE[-LINE]]` citation and every
   markdown link `[label](relative/path#Lxx)` resolves to a real file in the tree.
2. Line bounds     — for `path:LINE[-LINE]` citations, LINE is still within the file's current
   line count (catches the "file survived, content shifted" case existence-checking misses).
3. `just <task>` references — every `` `just <task>` `` mention names a recipe that still
   exists in the justfile.
4. Index drift     — `docs/README.md`'s declared subfolder list matches `docs/`'s actual
   subdirectories.

Findings against the "living tier" (docs that are supposed to always be accurate — see
LIVING_TIER below) are ERRORs and fail the check. Findings against everything else under
docs/ (archive/, validation/ ledger entries, source/, generated/) are INFO: those are
point-in-time snapshots by design and are not held to a currency bar, but a broken reference
is still worth surfacing. Pass --strict to fail on INFO findings too.

This does not (and cannot, cheaply) check that a citation's *content* still matches what it
claims — only that the path and line range still exist. A human pass is still needed for that;
see docs/README.md and AGENTS.md's Pull Request Guidelines for when to do one.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# Directories never worth walking for the basename index or scanning for citations.
EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".repowise",
    ".ruff_cache",
    ".pytest_cache",
    ".vscode",
}
# Kilo's own worktree checkouts are full duplicate copies of the tree; walking them
# both pollutes the basename index with ambiguous duplicates and double-scans every doc.
EXCLUDE_PATH_PARTS = {(".kilo", "worktrees")}

KNOWN_EXTS = {
    ".py", ".c", ".h", ".md", ".json", ".jsonl", ".txt", ".csv", ".js", ".mjs",
    ".dll", ".lib", ".a", ".exe", ".xlsx", ".lock", ".toml", ".yaml", ".yml",
    ".def", ".bat", ".ps1", ".cfg", ".ini",
}
# Line-countable (text) extensions; skip line-bounds checks for anything else (binaries).
TEXT_EXTS = {".py", ".c", ".h", ".md", ".json", ".jsonl", ".txt", ".csv", ".js", ".mjs",
             ".toml", ".yaml", ".yml", ".def", ".bat", ".ps1", ".cfg", ".ini"}

LIVING_TIER = {
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    DOCS / "README.md",
    DOCS / "engine-status.md",
    DOCS / "board-creator-status.md",
    DOCS / "openspiel-architecture.md",
    DOCS / "openspiel-integration.md",
    DOCS / "repo-structure.md",
    *(DOCS / "adr").glob("*.md"),
}

CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
PATHLINE_RE = re.compile(r"^([\w./\\-]+\.\w+):(\d+)(?:-(\d+))?$")
BAREPATH_RE = re.compile(r"^([\w./\\-]+\.\w+)$")
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
JUST_TASK_RE = re.compile(r"`just ([\w-]+)")
SUBFOLDER_BULLET_RE = re.compile(r"^-\s+`([\w.-]+)/`", re.MULTILINE)
DATE_HEADER_RE = re.compile(r"\b(?:As of|Generated)\s+(\d{4}-\d{2}-\d{2})")
RECIPE_NAME_RE = re.compile(r"^([a-zA-Z][\w-]*)")


@dataclass
class Finding:
    doc: Path
    message: str
    severity: str  # "ERROR" or "INFO"


@dataclass
class FileIndex:
    by_basename: dict[str, list[Path]] = field(default_factory=dict)

    def lookup(self, name: str) -> list[Path]:
        return self.by_basename.get(name, [])


def build_file_index(root: Path) -> FileIndex:
    idx = FileIndex()
    for dirpath, _dirnames, filenames in _walk(root):
        for fn in filenames:
            idx.by_basename.setdefault(fn, []).append(Path(dirpath) / fn)
    return idx


def _walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        rel_parts = tuple(p.lower() for p in Path(dirpath).relative_to(root).parts)
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIR_NAMES
            and (rel_parts + (d.lower(),))[-2:] not in EXCLUDE_PATH_PARTS
        ]
        yield dirpath, dirnames, filenames


def iter_doc_files() -> list[Path]:
    return sorted(p for p in DOCS.rglob("*.md"))


def tier_of(doc: Path) -> str:
    return "LIVING" if doc in LIVING_TIER else "OTHER"


def resolve_path(raw: str, doc: Path, index: FileIndex) -> tuple[str, Path | None]:
    """Returns (status, path) where status is 'ok', 'ambiguous', or 'missing'.

    'ambiguous' means the bare filename matched more than one file in the tree (e.g. a
    generic harness script name reused across validation runs) — the checker can't tell
    which one a citation means, so it's neither confirmed nor flagged as broken."""
    raw = raw.strip().strip("()")
    if raw.startswith(("http://", "https://", "mailto:", "#")):
        return "ok", None
    candidate = ROOT / raw
    if candidate.exists():
        return "ok", candidate
    candidate2 = doc.parent / raw
    if candidate2.exists():
        return "ok", candidate2
    # Fall back to a basename-only lookup even for multi-segment paths: many doc tables
    # write paths relative to a section header (e.g. a row under "### Game Setup
    # (`game_setup/`)" naming "scenario_generation/rosters.py"), not the repo root.
    basename = Path(raw).name
    matches = index.lookup(basename)
    if len(matches) == 1:
        return "ok", matches[0]
    if len(matches) > 1:
        return "ambiguous", None
    return "missing", None


# Local build outputs: never committed, not gitignored either — just absent until
# `just build-c` (or the GCC equivalent) runs. A citation to one of these isn't a doc bug.
BUILD_ARTIFACT_EXTS = {".dll", ".lib", ".a", ".exe"}


def is_external_path(raw: str) -> bool:
    if raw.startswith(".venv/") or "site-packages" in raw:
        return True
    return Path(raw).suffix.lower() in BUILD_ARTIFACT_EXTS


def check_citations(doc: Path, text: str, index: FileIndex, findings: list[Finding]) -> None:
    severity = "ERROR" if tier_of(doc) == "LIVING" else "INFO"

    seen: set[str] = set()
    for span in CODE_SPAN_RE.findall(text):
        span = span.strip()
        m = PATHLINE_RE.match(span)
        bare = False
        if not m:
            m2 = BAREPATH_RE.match(span)
            if not m2:
                continue
            path_str, line1, line2 = m2.group(1), None, None
            bare = True
        else:
            path_str, line1, line2 = m.group(1), m.group(2), m.group(3)
        if Path(path_str).suffix.lower() not in KNOWN_EXTS:
            continue
        if is_external_path(path_str):
            continue
        key = f"{path_str}:{line1}-{line2}" if not bare else path_str
        if key in seen:
            continue
        seen.add(key)

        status, resolved = resolve_path(path_str, doc, index)
        if status == "missing":
            findings.append(Finding(doc, f"citation `{span}` — no such file `{path_str}`", severity))
            continue
        if status == "ambiguous" or resolved is None:
            continue
        if line1 and resolved.suffix.lower() in TEXT_EXTS:
            try:
                line_count = sum(1 for _ in resolved.open(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            max_line = int(line2) if line2 else int(line1)
            if max_line > line_count:
                findings.append(Finding(
                    doc,
                    f"citation `{span}` — {resolved.relative_to(ROOT).as_posix()} has only "
                    f"{line_count} lines",
                    severity,
                ))

    for raw in LINK_RE.findall(text):
        target, _, _anchor = raw.partition("#")
        if not target or is_external_path(target):
            continue
        if Path(target).suffix.lower() not in KNOWN_EXTS:
            continue
        key = f"link:{raw}"
        if key in seen:
            continue
        seen.add(key)
        status, _resolved = resolve_path(target, doc, index)
        if status == "missing":
            findings.append(Finding(doc, f"link `({raw})` — no such file `{target}`", severity))


def check_just_tasks(doc: Path, text: str, recipe_names: set[str], findings: list[Finding]) -> None:
    severity = "ERROR" if tier_of(doc) == "LIVING" else "INFO"
    for task in sorted(set(JUST_TASK_RE.findall(text))):
        if task not in recipe_names:
            findings.append(Finding(doc, f"`just {task}` — no such justfile recipe", severity))


def load_justfile_recipes(justfile: Path) -> set[str]:
    names: set[str] = set()
    for line in justfile.read_text(encoding="utf-8").splitlines():
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        if ":=" in line.split(":")[0]:
            continue
        m = RECIPE_NAME_RE.match(line)
        if m:
            names.add(m.group(1))
    return names


def check_index_drift(findings: list[Finding]) -> None:
    readme = DOCS / "README.md"
    if not readme.exists():
        return
    text = readme.read_text(encoding="utf-8")
    declared = set(SUBFOLDER_BULLET_RE.findall(text))
    actual = {p.name for p in DOCS.iterdir() if p.is_dir()}
    missing = actual - declared
    stale = declared - actual
    for name in sorted(missing):
        findings.append(Finding(readme, f"docs/{name}/ exists but isn't listed in the Subfolders index", "ERROR"))
    for name in sorted(stale):
        findings.append(Finding(readme, f"docs/README.md lists `{name}/` but it no longer exists", "ERROR"))


def check_recency(findings: list[Finding]) -> None:
    """Advisory only: flag when a living-tier doc's 'As of DATE' predates the last commit
    touching a file it cites. Noisy by nature (unrelated edits still bump the date), so this
    never raises severity above INFO."""
    for doc in sorted(LIVING_TIER):
        if not doc.exists():
            continue
        text = doc.read_text(encoding="utf-8")
        date_match = DATE_HEADER_RE.search(text)
        if not date_match:
            continue
        doc_date = date_match.group(1)
        cited_paths = set()
        for span in CODE_SPAN_RE.findall(text):
            m = PATHLINE_RE.match(span.strip()) or BAREPATH_RE.match(span.strip())
            if m and Path(m.group(1)).suffix.lower() in KNOWN_EXTS and not is_external_path(m.group(1)):
                candidate = ROOT / m.group(1)
                if candidate.exists():
                    cited_paths.add(candidate)
        newer = []
        for path in sorted(cited_paths)[:200]:
            try:
                out = subprocess.run(
                    ["git", "log", "-1", "--format=%cd", "--date=short", "--", str(path)],
                    cwd=ROOT, capture_output=True, text=True, timeout=5, check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            last = out.stdout.strip()
            if last and last > doc_date:
                newer.append((path.relative_to(ROOT).as_posix(), last))
        if newer:
            sample = ", ".join(f"{p} ({d})" for p, d in newer[:5])
            more = f" (+{len(newer) - 5} more)" if len(newer) > 5 else ""
            findings.append(Finding(
                doc,
                f"dated '{doc_date}' but cites files committed later: {sample}{more}",
                "INFO",
            ))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strict", action="store_true", help="fail on INFO findings too, not just ERROR")
    parser.add_argument("--no-recency", action="store_true", help="skip the git-log recency advisory (slower, noisier)")
    args = parser.parse_args()

    index = build_file_index(ROOT)
    recipe_names = load_justfile_recipes(ROOT / "justfile")

    findings: list[Finding] = []
    for doc in iter_doc_files():
        text = doc.read_text(encoding="utf-8", errors="replace")
        check_citations(doc, text, index, findings)
        check_just_tasks(doc, text, recipe_names, findings)
    check_index_drift(findings)
    if not args.no_recency:
        check_recency(findings)

    errors = [f for f in findings if f.severity == "ERROR"]
    infos = [f for f in findings if f.severity == "INFO"]

    for f in errors + infos:
        rel = f.doc.relative_to(ROOT).as_posix()
        print(f"[{f.severity}] {rel}: {f.message}")

    print()
    print(f"{len(errors)} error(s), {len(infos)} info finding(s) across {len(iter_doc_files())} doc files.")

    if errors or (args.strict and infos):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
