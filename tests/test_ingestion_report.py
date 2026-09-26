"""Behavioral tests for scripts/report_ingestion.py.

Every test builds its own synthetic temporary SQLite database and review
directory -- none of this touches the real data/import or data/review
fixtures. The report is a read-only tool, so several tests also assert the
database bytes and review files are byte-identical before and after a run,
including a run that ends in an error.
"""
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

from scripts import report_ingestion as ri

IMPORT_ATTEMPTS_SCHEMA = """
CREATE TABLE import_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    provision_key TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    source_hashes_json TEXT NOT NULL DEFAULT '{}',
    review_sha256 TEXT NOT NULL DEFAULT '',
    extraction_method_version TEXT NOT NULL DEFAULT '',
    admission_status TEXT,
    error_type TEXT
);
"""

PROVISIONS_SCHEMA = """
CREATE TABLE provisions (
    provision_key TEXT PRIMARY KEY,
    act_slug TEXT,
    admission_status TEXT
);
"""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_review(review_dir: Path, filename: str, provision_key, extra=None):
    record = {"provision_key": provision_key, "act_slug": "test-act", "section_number": "1"}
    if extra:
        record.update(extra)
    (review_dir / filename).write_text(json.dumps(record))


def insert_attempt(conn, provision_key, status, admission_status=None,
                    started_at="2026-01-01T00:00:00.000Z", finished_at="2026-01-01T00:00:01.000Z",
                    error_type=None):
    conn.execute(
        "INSERT INTO import_attempts (provision_key, started_at, finished_at, status, admission_status, error_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (provision_key, started_at, finished_at, status, admission_status, error_type),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def run_cli(args) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ri.main(args)
    return code, out.getvalue(), err.getvalue()


class ReportIngestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.review_dir = self.root / "review"
        self.review_dir.mkdir()
        self.db_path = self.root / "db.sqlite3"

    def make_db(self, with_provisions=True):
        conn = sqlite3.connect(self.db_path)
        conn.executescript(IMPORT_ATTEMPTS_SCHEMA)
        if with_provisions:
            conn.executescript(PROVISIONS_SCHEMA)
        conn.commit()
        return conn

    # -- failure-mode tests -------------------------------------------------

    def test_missing_db_does_not_create_file(self):
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir)])
        self.assertNotEqual(code, 0)
        self.assertFalse(self.db_path.exists())
        self.assertIn("database not found", err)

    def test_unsupported_schema_missing_import_attempts_table(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE something_else (x INTEGER)")
        conn.commit()
        conn.close()
        before = sha256_file(self.db_path)
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir)])
        self.assertNotEqual(code, 0)
        self.assertIn("import_attempts", err)
        self.assertEqual(sha256_file(self.db_path), before)

    def test_corrupt_db_file(self):
        self.db_path.write_bytes(b"this is not a sqlite database")
        before = self.db_path.read_bytes()
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir)])
        self.assertNotEqual(code, 0)
        self.assertEqual(self.db_path.read_bytes(), before)

    def test_malformed_review_json_reported_clearly(self):
        conn = self.make_db()
        conn.close()
        (self.review_dir / "bad.review.json").write_text("{not valid json")
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir)])
        self.assertNotEqual(code, 0)
        self.assertIn("bad.review.json", err)

    def test_review_missing_provision_key_rejected(self):
        conn = self.make_db()
        conn.close()
        (self.review_dir / "no-key.review.json").write_text(json.dumps({"act_slug": "x"}))
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir)])
        self.assertNotEqual(code, 0)
        self.assertIn("provision_key", err)

    def test_duplicate_review_keys_rejected(self):
        conn = self.make_db()
        conn.close()
        write_review(self.review_dir, "a.review.json", "act:1")
        write_review(self.review_dir, "b.review.json", "act:1")
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir)])
        self.assertNotEqual(code, 0)
        self.assertIn("duplicate", err.lower())
        self.assertIn("act:1", err)

    def test_special_character_in_db_filename_does_not_create_stray_file(self):
        # A raw f"file:{path}" URI treats '#' as the start of a URI fragment
        # and truncates the path there, which previously made sqlite3 open
        # (and, on a writable connection, create) a different file named
        # "copy" instead of "copy#1.sqlite3". Path.as_uri() percent-encodes
        # '#' so this must not happen.
        special_db = self.root / "copy#1.sqlite3"
        conn = sqlite3.connect(special_db)
        conn.executescript(IMPORT_ATTEMPTS_SCHEMA)
        conn.executescript(PROVISIONS_SCHEMA)
        insert_attempt(conn, "act:1", "succeeded", "admitted")
        conn.close()
        write_review(self.review_dir, "a.review.json", "act:1")

        code, out, err = run_cli(["--db", str(special_db), "--review-dir", str(self.review_dir), "--format", "json"])
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertEqual(report["rows"][0]["provision_key"], "act:1")
        self.assertFalse((self.root / "copy").exists())
        self.assertTrue(special_db.exists())

    def test_missing_columns_reported_clearly_not_as_traceback(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE import_attempts (attempt_id INTEGER PRIMARY KEY, provision_key TEXT, status TEXT)"
        )
        conn.execute("CREATE TABLE provisions (provision_key TEXT PRIMARY KEY)")
        conn.commit()
        conn.close()
        before = sha256_file(self.db_path)
        write_review(self.review_dir, "a.review.json", "act:1")

        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        self.assertNotEqual(code, 0)
        self.assertIn("missing column", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(sha256_file(self.db_path), before)

    def test_invalid_utf8_review_file_reported_clearly_not_as_traceback(self):
        conn = self.make_db()
        conn.close()
        (self.review_dir / "bad.review.json").write_bytes(b"\xff\xfe{not valid utf-8}")

        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        self.assertNotEqual(code, 0)
        self.assertIn("bad.review.json", err)
        self.assertIn("UTF-8", err)
        self.assertNotIn("Traceback", err)

    def test_read_transaction_rolls_back_and_never_leaves_a_transaction_open(self):
        conn = self.make_db()
        conn.close()
        reader = ri.open_readonly(self.db_path)
        self.addCleanup(reader.close)
        with ri.read_transaction(reader):
            reader.execute("SELECT 1 FROM import_attempts")
            self.assertTrue(reader.in_transaction)
        self.assertFalse(reader.in_transaction)

    def test_journal_and_admission_queries_share_one_read_transaction(self):
        conn = self.make_db()
        insert_attempt(conn, "act:1", "succeeded", "admitted")
        conn.close()
        write_review(self.review_dir, "a.review.json", "act:1")

        in_transaction_flags = []
        original_latest = ri.fetch_latest_attempts
        original_canonical = ri.fetch_canonical_admission

        def spy_latest(conn):
            in_transaction_flags.append(conn.in_transaction)
            return original_latest(conn)

        def spy_canonical(conn):
            in_transaction_flags.append(conn.in_transaction)
            return original_canonical(conn)

        with mock.patch.object(ri, "fetch_latest_attempts", side_effect=spy_latest), \
             mock.patch.object(ri, "fetch_canonical_admission", side_effect=spy_canonical):
            code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])

        self.assertEqual(code, 0, err)
        # Both queries observed an already-open transaction -- i.e. they ran
        # inside the same explicit read transaction, not as two independent
        # implicit reads that could straddle a concurrent write.
        self.assertEqual(in_transaction_flags, [True, True])

    def test_missing_review_dir(self):
        conn = self.make_db()
        conn.close()
        missing = self.root / "no-such-review-dir"
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(missing)])
        self.assertNotEqual(code, 0)

    def test_bytes_unchanged_after_success_and_after_failure(self):
        conn = self.make_db()
        insert_attempt(conn, "act:1", "succeeded", "admitted")
        conn.close()
        write_review(self.review_dir, "a.review.json", "act:1")
        db_before = sha256_file(self.db_path)
        review_file = self.review_dir / "a.review.json"
        review_before = review_file.read_bytes()

        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir)])
        self.assertEqual(code, 0)
        self.assertEqual(sha256_file(self.db_path), db_before)
        self.assertEqual(review_file.read_bytes(), review_before)

        # Now force a failure path (duplicate key) and check bytes again.
        write_review(self.review_dir, "dup.review.json", "act:1")
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir)])
        self.assertNotEqual(code, 0)
        self.assertEqual(sha256_file(self.db_path), db_before)
        self.assertEqual(review_file.read_bytes(), review_before)

    # -- behavioral tests -----------------------------------------------

    def test_current_item_without_attempt_is_not_attempted(self):
        conn = self.make_db()
        conn.close()
        write_review(self.review_dir, "a.review.json", "act:1")
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["current_review_inventory_count"], 1)
        row = report["rows"][0]
        self.assertEqual(row["provision_key"], "act:1")
        self.assertTrue(row["in_current_review"])
        self.assertEqual(row["latest_attempt"]["status"], "not_attempted")
        self.assertIsNone(row["latest_attempt"]["attempt_id"])
        self.assertEqual(report["status_counts"]["not_attempted"], 1)

    def test_latest_attempt_chosen_by_attempt_id_not_timestamp(self):
        conn = self.make_db()
        # attempt_id 1 has a LATER timestamp than attempt_id 2 (clock skew) --
        # the report must still treat attempt_id 2 as latest.
        insert_attempt(conn, "act:1", "succeeded", "admitted",
                        started_at="2026-01-05T00:00:00.000Z", finished_at="2026-01-05T00:00:01.000Z")
        insert_attempt(conn, "act:1", "quarantined", "invalidated_body_text_changed",
                        started_at="2026-01-01T00:00:00.000Z", finished_at="2026-01-01T00:00:01.000Z")
        conn.close()
        write_review(self.review_dir, "a.review.json", "act:1")
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        row = report["rows"][0]
        self.assertEqual(row["latest_attempt"]["attempt_id"], 2)
        self.assertEqual(row["latest_attempt"]["status"], "quarantined")
        self.assertEqual(row["latest_attempt"]["attempt_count"], 2)

    def test_failed_then_succeeded_history_shows_latest_and_count(self):
        conn = self.make_db()
        insert_attempt(conn, "act:1", "failed", None, error_type="FileNotFoundError")
        insert_attempt(conn, "act:1", "succeeded", "admitted")
        conn.close()
        write_review(self.review_dir, "a.review.json", "act:1")
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        report = json.loads(out)
        row = report["rows"][0]
        self.assertEqual(row["latest_attempt"]["status"], "succeeded")
        self.assertEqual(row["latest_attempt"]["attempt_count"], 2)

    def test_historical_only_removed_review_not_counted_as_current(self):
        conn = self.make_db()
        insert_attempt(conn, "removed:1", "succeeded", "admitted")
        conn.close()
        # No review file at all for removed:1 -- it's no longer in current inventory.
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["current_review_inventory_count"], 0)
        self.assertEqual(report["historical_only_count"], 1)
        row = report["rows"][0]
        self.assertEqual(row["provision_key"], "removed:1")
        self.assertFalse(row["in_current_review"])
        # A historical-only row must never bump current-inventory status counts.
        self.assertEqual(sum(report["status_counts"].values()), 0)

    def test_running_shown_as_running_or_interrupted_in_display_json_keeps_running(self):
        conn = self.make_db()
        insert_attempt(conn, "act:1", "running", None, finished_at=None)
        conn.close()
        write_review(self.review_dir, "a.review.json", "act:1")

        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        report = json.loads(out)
        row = report["rows"][0]
        self.assertEqual(row["latest_attempt"]["status"], "running")
        self.assertEqual(row["latest_attempt"]["display_status"], "running_or_interrupted")
        self.assertEqual(report["status_counts"]["running_or_interrupted"], 1)

        code, text_out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "text"])
        self.assertIn("running_or_interrupted", text_out)

    def test_canonical_admission_status_differs_from_latest_attempt(self):
        conn = self.make_db()
        insert_attempt(conn, "act:1", "succeeded", "admitted")
        # The provisions row has since been invalidated (e.g. review record
        # removed) even though the journal's latest attempt still says
        # succeeded/admitted -- both must be visible and distinct.
        conn.execute(
            "INSERT INTO provisions (provision_key, act_slug, admission_status) VALUES (?, ?, ?)",
            ("act:1", "test-act", "invalidated_review_record_removed"),
        )
        conn.commit()
        conn.close()
        write_review(self.review_dir, "a.review.json", "act:1")
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        report = json.loads(out)
        row = report["rows"][0]
        self.assertEqual(row["latest_attempt"]["admission_status"], "admitted")
        self.assertEqual(row["canonical_admission_status"], "invalidated_review_record_removed")
        self.assertNotEqual(row["latest_attempt"]["admission_status"], row["canonical_admission_status"])

    def test_no_provisions_row_gives_null_canonical_status(self):
        conn = self.make_db()
        insert_attempt(conn, "act:1", "failed", None, error_type="AdmissionError")
        conn.close()
        write_review(self.review_dir, "a.review.json", "act:1")
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        report = json.loads(out)
        self.assertIsNone(report["rows"][0]["canonical_admission_status"])

    def test_valid_report_deterministic_ordering_and_summed_counts(self):
        conn = self.make_db()
        insert_attempt(conn, "zzz:9", "succeeded", "admitted")
        insert_attempt(conn, "aaa:1", "failed", None, error_type="OSError")
        conn.close()
        write_review(self.review_dir, "z.review.json", "zzz:9")
        write_review(self.review_dir, "a.review.json", "aaa:1")
        write_review(self.review_dir, "m.review.json", "mmm:5")  # not attempted

        code1, out1, err1 = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        code2, out2, err2 = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        self.assertEqual(code1, 0)
        self.assertEqual(out1, out2)  # deterministic across repeated runs

        report = json.loads(out1)
        keys = [row["provision_key"] for row in report["rows"]]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(keys, ["aaa:1", "mmm:5", "zzz:9"])

        current_rows = [r for r in report["rows"] if r["in_current_review"]]
        self.assertEqual(len(current_rows), report["current_review_inventory_count"])
        self.assertEqual(sum(report["status_counts"].values()), report["current_review_inventory_count"])

    def test_report_declares_limitations_notice(self):
        conn = self.make_db()
        conn.close()
        write_review(self.review_dir, "a.review.json", "act:1")
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        report = json.loads(out)
        limitations_text = " ".join(report["limitations"]).lower()
        self.assertIn("full coverage", limitations_text)
        self.assertIn("permission", limitations_text)

    def test_exit_zero_even_when_report_describes_failures(self):
        conn = self.make_db()
        insert_attempt(conn, "act:1", "failed", None, error_type="OSError")
        conn.close()
        write_review(self.review_dir, "a.review.json", "act:1")
        code, out, err = run_cli(["--db", str(self.db_path), "--review-dir", str(self.review_dir), "--format", "json"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["status_counts"]["failed"], 1)


if __name__ == "__main__":
    unittest.main()
