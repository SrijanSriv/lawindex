#!/usr/bin/env python3
"""Read-only operator report for Phase 3 acquisition/candidate coverage.

Renders exactly the semantics of GET /api/inventory (lawindex/coverage.py's
build_coverage, over a live lawindex.search.Snapshot) for a terminal
operator instead of a browser. It performs no acquisition, no extraction,
no database write, no subprocess, and no network access: it only reads
data/phase3/inventory.v1.json, retained acquisition/candidate evidence
under data/phase3/, and the existing offline search database.

data/phase3/coverage.json (if present) is a stored point-in-time report and
is never read here -- see docs/phase-3/ACQUISITION_AND_CANDIDATES.md.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawindex.search import Snapshot, Unavailable  # noqa: E402
from lawindex.coverage import build_coverage  # noqa: E402

REPORT_SCHEMA_VERSION = 1


class ReportError(Exception):
    """Expected missing/malformed Phase 3 data; not a bug in this reporter."""


def build_report(root: Path) -> dict:
    try:
        snapshot = Snapshot(root)
    except Unavailable as error:
        raise ReportError(f"live search snapshot unavailable: {error}") from error
    try:
        return build_coverage(root, snapshot)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ReportError(f"Phase 3 inventory is unavailable or invalid: {error}") from error


def _count(value, singular):
    return "Unknown" if value is None else f"{value} {singular}{'' if value == 1 else 's'}"


def render_text(report: dict) -> str:
    lines = []
    lines.append("LawIndex Phase 3 coverage report")
    lines.append(f"inventory: {report['inventory_id']} (sha256 {report['inventory_sha256']})")
    lines.append("")
    lines.append(f"selected Acts: {report['selected_act_count']}")
    lines.append(f"captured Acts: {report['captured_act_count']}")
    lines.append(f"searchable Acts: {report['searchable_act_count']}")
    lines.append(f"searchable provisions: {report['searchable_provision_count']}")
    lines.append("")
    for row in report["rows"]:
        lines.append(f"{row['title']} ({row['slug']})")
        lines.append(f"  acquisition status: {row['acquisition_status']}")
        lines.append(f"  source-listed sections: {_count(row['source_section_count'], 'section')}")
        lines.append(f"  candidate status: {row['candidate_status']}")
        lines.append(f"  agreement-review-pending: {_count(row['agreement_review_pending_count'], 'candidate')}")
        lines.append(f"  typographic-agreement-review-pending: {_count(row.get('typographic_agreement_review_pending_count'), 'candidate')}")
        lines.append(f"  quarantined: {_count(row['quarantined_count'], 'candidate')}")
        for reason, count in (row.get('quarantine_reasons') or {}).items():
            lines.append(f"    - {reason}: {count}")
        lines.append(f"  searchable provisions: {row['searchable_provision_count']}")
        lines.append(f"  full Act coverage verified: {row['full_act_coverage_verified']}")
        if row["diagnostic"]:
            lines.append(f"  diagnostic: {row['diagnostic']}")
        lines.append("")
    lines.append("limitations:")
    for note in report["limitations"]:
        lines.append(f"  - {note}")
    return "\n".join(lines) + "\n"


def render_json(report: dict) -> str:
    payload = dict(report, report_schema_version=REPORT_SCHEMA_VERSION)
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--root", default=str(ROOT), help="repository root (defaults to this checkout)")
    args = parser.parse_args(argv)

    try:
        report = build_report(Path(args.root))
    except ReportError as error:
        print(f"report_phase3_coverage: error: {error}", file=sys.stderr)
        return 1

    output = render_json(report) if args.format == "json" else render_text(report)
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
