#!/usr/bin/env python3
"""Read-only operator report over the Phase 2 ingestion journal.

Reads the offline importer's SQLite database (see scripts/offline_importer.py
and docs/phase-2/ARCHITECTURE.md) and the current *.review.json inventory
under data/review/, and prints a report of what is currently reviewed, what
has ever been attempted, and how those two views differ. It never writes to
the database, never writes to the review directory, never opens a network
connection, and never invokes a subprocess.

This is a reporting tool, not a verifier: it does not re-check source bytes,
re-run extraction, or re-evaluate legal correctness or reuse permission. A
journal status of "succeeded" describes what a past attempt recorded, not a
guarantee about the current state of the canonical `provisions` row -- the
two are shown separately on purpose. See docs/phase-2/REPORTING.md for the
documented JSON shape and docs/phase-2/ARCHITECTURE.md for the underlying
journal semantics.
"""
import argparse
import json
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/import/lawindex_offline.sqlite3"
DEFAULT_REVIEW_DIR = ROOT / "data/review"

REPORT_SCHEMA_VERSION = 1

REQUIRED_TABLES = ("import_attempts", "provisions")
REQUIRED_COLUMNS = {
    "import_attempts": (
        "attempt_id", "provision_key", "started_at", "finished_at",
        "status", "admission_status", "error_type",
    ),
    "provisions": ("provision_key", "admission_status"),
}

# Attempt statuses the journal can record (see ARCHITECTURE.md's Outcomes
# table). "running" is renamed to "running_or_interrupted" for display only
# -- this report has no way to know whether the process that started it is
# still alive, so it is deliberately ambiguous rather than presented as a
# live progress indicator.
DISPLAY_STATUS_OVERRIDES = {"running": "running_or_interrupted"}
NOT_ATTEMPTED = "not_attempted"

STATUS_COUNT_BUCKETS = (
    NOT_ATTEMPTED,
    "succeeded",
    "quarantined",
    "failed",
    "interrupted",
    "running_or_interrupted",
)

LIMITATIONS = [
    "This report describes journal and inventory bookkeeping only. It does not "
    "reverify source bytes, re-run extraction, re-check review sign-off, or make "
    "any legal-correctness determination.",
    "A journal status of 'succeeded' or a canonical admission status of 'admitted' "
    "describes what a past import run recorded; it is not re-verified by this report "
    "and is not proof of current readiness.",
    "Reviewed provisions do not establish full coverage of their Acts. "
    "Consult live search coverage for the currently eligible provision inventory.",
    "The user reports ministry permission for up to 20 chosen Acts for the personal, "
    "non-commercial project; see data/phase3/access-authorization.json. "
    "Permission is separate from technical import status and this report does not verify the grant.",
    "A 'running_or_interrupted' status means the journal has no committed terminal "
    "state for that attempt. This report cannot tell whether the process that "
    "started it is still running, crashed, or was killed.",
]


class ReportError(Exception):
    """A condition that prevents rendering a trustworthy report."""


def _fail(message: str) -> "None":
    raise ReportError(message)


def load_review_inventory(review_dir: Path) -> dict:
    """Return {provision_key: review_json_path} for the current inventory.

    Raises ReportError on a missing directory, malformed JSON, a review
    record missing its required provision_key, or a duplicate provision_key
    across files -- all conditions that make the "current inventory" view
    unreliable rather than merely incomplete.
    """
    if not review_dir.is_dir():
        _fail(f"review directory not found: {review_dir}")

    inventory: dict[str, Path] = {}
    for path in sorted(review_dir.glob("*.review.json")):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            _fail(f"review file {path.name} is not valid UTF-8: {exc}")
            return {}  # unreachable, keeps type-checkers happy
        try:
            record = json.loads(text)
        except json.JSONDecodeError as exc:
            _fail(f"malformed review JSON in {path.name}: {exc}")
            return {}  # unreachable, keeps type-checkers happy
        if not isinstance(record, dict):
            _fail(f"malformed review record in {path.name}: expected a JSON object")
        key = record.get("provision_key")
        if not isinstance(key, str) or not key:
            _fail(f"review record in {path.name} is missing a required non-empty provision_key")
        if key in inventory:
            _fail(
                f"duplicate provision_key {key!r} in {path.name} "
                f"(already declared in {inventory[key].name})"
            )
        inventory[key] = path
    return inventory


def open_readonly(db_path: Path) -> sqlite3.Connection:
    """Open db_path strictly read-only. Never creates a database file.

    Builds the connection URI with Path.as_uri() rather than string
    interpolation: as_uri() percent-encodes characters that are otherwise
    significant in a sqlite URI (notably '#' and '?'), which a raw
    f"file:{path}" would pass through unescaped -- against a path such as
    "copy#1.sqlite" that previously truncated the path at '#' and made
    sqlite3 open (and, if writable, create) a different file named "copy".
    """
    if not db_path.exists():
        _fail(f"database not found: {db_path}")
    if not db_path.is_file():
        _fail(f"database path is not a file: {db_path}")
    uri = db_path.resolve().as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        # Autocommit mode: SELECTs never implicitly open a transaction, so we
        # can explicitly BEGIN a single read transaction spanning every query
        # this report issues (see read_transaction below).
        conn.isolation_level = None
        conn.execute("SELECT 1")
    except sqlite3.Error as exc:
        _fail(f"could not open database read-only: {exc}")
        raise  # unreachable
    return conn


@contextmanager
def read_transaction(conn: sqlite3.Connection):
    """Run every query inside one explicit read transaction.

    Without this, two separate SELECTs (e.g. the latest-attempts query and
    the canonical-admission query) are not guaranteed to see the same
    database snapshot if scripts/offline_importer.py is writing concurrently
    -- each is its own implicit read otherwise, so a report could combine a
    journal row from before a write with a provisions row from after it, a
    combination that never actually existed together. An explicit BEGIN
    pins one snapshot for the whole report. The connection is read-only, so
    this transaction is always rolled back (never committed) regardless of
    outcome; it exists purely for read consistency, not to persist anything.
    """
    conn.execute("BEGIN")
    try:
        yield
    finally:
        conn.execute("ROLLBACK")


def check_schema(conn: sqlite3.Connection) -> None:
    try:
        existing_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    except sqlite3.DatabaseError as exc:
        _fail(f"database is corrupt or unreadable: {exc}")
        return  # unreachable
    missing_tables = [t for t in REQUIRED_TABLES if t not in existing_tables]
    if missing_tables:
        _fail(
            "database schema does not support reporting (missing table(s): "
            + ", ".join(missing_tables)
            + "); this looks like a database built before the import_attempts "
            "journal existed. Run the importer to upgrade it before reporting."
        )

    for table, required_columns in REQUIRED_COLUMNS.items():
        try:
            existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        except sqlite3.DatabaseError as exc:
            _fail(f"could not inspect table {table!r}: {exc}")
            return  # unreachable
        missing_columns = [c for c in required_columns if c not in existing_columns]
        if missing_columns:
            _fail(
                f"database schema does not support reporting (table {table!r} is "
                f"missing column(s): {', '.join(missing_columns)}); this looks like "
                "an incompatible or older schema. Run the importer to upgrade it "
                "before reporting."
            )


def fetch_latest_attempts(conn: sqlite3.Connection) -> dict:
    """One row per provision_key: its greatest-attempt_id attempt, plus a total count.

    Ordering is strictly by attempt_id, never by started_at/finished_at --
    per docs/phase-2/REPORT_AGENT_PROMPT.md, timestamp ordering is
    explicitly disallowed for "latest".
    """
    rows = conn.execute(
        """
        SELECT a.provision_key, a.attempt_id, a.status, a.admission_status,
               a.started_at, a.finished_at, a.error_type, counts.attempt_count
        FROM import_attempts a
        JOIN (
            SELECT provision_key, MAX(attempt_id) AS max_id, COUNT(*) AS attempt_count
            FROM import_attempts
            GROUP BY provision_key
        ) counts
        ON a.provision_key = counts.provision_key AND a.attempt_id = counts.max_id
        """
    ).fetchall()
    result = {}
    for provision_key, attempt_id, status, admission_status, started_at, finished_at, error_type, attempt_count in rows:
        result[provision_key] = {
            "attempt_id": attempt_id,
            "status": status,
            "display_status": DISPLAY_STATUS_OVERRIDES.get(status, status),
            "admission_status": admission_status,
            "started_at": started_at,
            "finished_at": finished_at,
            "error_type": error_type,
            "attempt_count": attempt_count,
        }
    return result


def fetch_canonical_admission(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT provision_key, admission_status FROM provisions"
    ).fetchall()
    return {provision_key: admission_status for provision_key, admission_status in rows}


def build_report(conn: sqlite3.Connection, review_inventory: dict) -> dict:
    latest_attempts = fetch_latest_attempts(conn)
    canonical_admission = fetch_canonical_admission(conn)

    all_keys = sorted(set(review_inventory) | set(latest_attempts))

    rows = []
    status_counts = {bucket: 0 for bucket in STATUS_COUNT_BUCKETS}
    historical_only_count = 0

    for key in all_keys:
        in_current_review = key in review_inventory
        attempt = latest_attempts.get(key)
        if attempt is None:
            latest_attempt_row = {
                "attempt_id": None,
                "status": NOT_ATTEMPTED,
                "display_status": NOT_ATTEMPTED,
                "admission_status": None,
                "started_at": None,
                "finished_at": None,
                "error_type": None,
                "attempt_count": 0,
            }
        else:
            latest_attempt_row = attempt

        row = {
            "provision_key": key,
            "in_current_review": in_current_review,
            "latest_attempt": latest_attempt_row,
            "canonical_admission_status": canonical_admission.get(key),
        }
        rows.append(row)

        if in_current_review:
            status_counts[latest_attempt_row["display_status"]] += 1
        else:
            historical_only_count += 1

    report = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "current_review_inventory_count": len(review_inventory),
        "status_counts": status_counts,
        "historical_only_count": historical_only_count,
        "rows": rows,
        "limitations": LIMITATIONS,
    }
    return report


def render_text(report: dict, db_path: Path, review_dir: Path) -> str:
    lines = []
    lines.append("LawIndex offline ingestion journal report")
    lines.append(f"database: {db_path}")
    lines.append(f"review directory: {review_dir}")
    lines.append("")
    lines.append(f"current review inventory: {report['current_review_inventory_count']}")
    lines.append(f"historical-only (attempted, no longer in current review): {report['historical_only_count']}")
    lines.append("")
    lines.append("status counts over current review inventory:")
    for bucket in STATUS_COUNT_BUCKETS:
        lines.append(f"  {bucket}: {report['status_counts'][bucket]}")
    lines.append("")
    lines.append("provisions:")
    for row in report["rows"]:
        attempt = row["latest_attempt"]
        membership = "current" if row["in_current_review"] else "historical-only"
        lines.append(f"  {row['provision_key']} [{membership}]")
        lines.append(
            f"    latest attempt: {attempt['display_status']}"
            + (f" (attempt_id={attempt['attempt_id']})" if attempt["attempt_id"] is not None else "")
            + f", attempts so far: {attempt['attempt_count']}"
        )
        if attempt["display_status"] != NOT_ATTEMPTED:
            lines.append(
                f"      journal admission_status: {attempt['admission_status']}"
                f", started_at: {attempt['started_at']}, finished_at: {attempt['finished_at']}"
                f", error_type: {attempt['error_type']}"
            )
        lines.append(f"    current canonical admission_status: {row['canonical_admission_status']}")
    lines.append("")
    lines.append("limitations:")
    for note in report["limitations"]:
        lines.append(f"  - {note}")
    return "\n".join(lines) + "\n"


def render_json(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="path to the offline importer's SQLite database (read-only)")
    parser.add_argument("--review-dir", default=str(DEFAULT_REVIEW_DIR), help="path to the current *.review.json inventory")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    review_dir = Path(args.review_dir)

    try:
        review_inventory = load_review_inventory(review_dir)
        conn = open_readonly(db_path)
        try:
            with read_transaction(conn):
                check_schema(conn)
                report = build_report(conn, review_inventory)
        except sqlite3.Error as exc:
            # A safety net around whatever check_schema's explicit column
            # checks didn't anticipate -- e.g. a column present but of a
            # shape that trips a query in a way PRAGMA table_info alone
            # wouldn't catch. Surface it as the same clean diagnostic rather
            # than an unhandled traceback.
            _fail(f"database query failed against this schema: {exc}")
        finally:
            conn.close()
    except ReportError as exc:
        print(f"report_ingestion: error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        sys.stdout.write(render_json(report))
    else:
        sys.stdout.write(render_text(report, db_path, review_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
