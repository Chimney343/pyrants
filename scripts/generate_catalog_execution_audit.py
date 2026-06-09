"""Generate docs/generated/catalog_execution_audit.md from catalog and probe artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.catalog_audit import (  # noqa: E402
    DEFAULT_CARD_PATH,
    DEFAULT_STUCK_REPORT_PATH,
    build_card_audit_entries,
    render_markdown_report,
)

DEFAULT_DOC_PATH = ROOT_DIR / "docs" / "generated" / "catalog_execution_audit.md"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-path", type=Path, default=DEFAULT_CARD_PATH)
    parser.add_argument("--stuck-report-path", type=Path, default=DEFAULT_STUCK_REPORT_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_DOC_PATH)
    return parser.parse_args()


def main() -> None:
    args = _args()
    entries = build_card_audit_entries(
        card_path=args.card_path,
        stuck_report_path=args.stuck_report_path,
    )
    report = render_markdown_report(
        entries,
        card_path=args.card_path,
        stuck_report_path=args.stuck_report_path,
    )
    args.out.write_text(report, encoding="utf-8")
    print(f"Wrote {args.out}")
    print(f"Cards audited: {len(entries)}")


if __name__ == "__main__":
    main()
