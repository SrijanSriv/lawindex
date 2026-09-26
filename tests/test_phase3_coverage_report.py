"""Tests for the read-only scripts/report_phase3_coverage.py operator CLI.

No network, no database writes, no acquisition/extraction/subprocess. Fixtures
are small temporary inventories built with the same helpers the existing
Phase 3 pipeline tests use (scripts.acquire_phase3.atomic_json/sha/canonical),
never the real data/ tree, except where a test explicitly checks that running
the report against the real repository leaves data/ untouched.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import acquire_phase3 as ac
from scripts import report_phase3_coverage as rc
from lawindex.search import Unavailable


def _fixture_root(tmp, records):
    root = Path(tmp)
    inventory = dict(inventory_id="test-inventory", records=records)
    ac.atomic_json(root / "data/phase3/inventory.v1.json", inventory)
    return root


class RenderTests(unittest.TestCase):
    """Unit tests against hand-built report dicts -- no backend calls."""

    def _report(self, rows):
        return dict(
            schema_version=1, inventory_id="test-inventory", inventory_sha256="abc",
            selected_act_count=len(rows),
            captured_act_count=sum(r["acquisition_status"] == "captured_review_pending" for r in rows),
            searchable_act_count=sum(r["searchable_provision_count"] > 0 for r in rows),
            searchable_provision_count=sum(r["searchable_provision_count"] for r in rows),
            rows=rows, limitations=["Captured is not admitted.", "Null means unknown; zero is a known zero."],
        )

    def test_null_counts_render_as_unknown_zero_renders_as_zero(self):
        rows = [
            dict(slug="a", title="Act A", acquisition_status="not_requested",
                 source_section_count=None, pdf_count=None, candidate_status="not_processed",
                 agreement_review_pending_count=None, quarantined_count=None,
                 searchable_provision_count=0, full_act_coverage_verified=False, diagnostic=None),
            dict(slug="b", title="Act B", acquisition_status="captured_review_pending",
                 source_section_count=0, pdf_count=1, candidate_status="parsed_review_pending",
                 agreement_review_pending_count=0, quarantined_count=0,
                 searchable_provision_count=2, full_act_coverage_verified=False, diagnostic=None),
        ]
        text = rc.render_text(self._report(rows))
        self.assertIn("source-listed sections: Unknown", text)
        self.assertIn("agreement-review-pending: Unknown", text)
        self.assertIn("quarantined: Unknown", text)
        # Act B has real zeros, not missing data -- these must read as "0 ...", never "Unknown".
        self.assertIn("source-listed sections: 0 section", text)
        self.assertIn("agreement-review-pending: 0 candidate", text)
        self.assertIn("quarantined: 0 candidate", text)

        payload = json.loads(rc.render_json(self._report(rows)))
        self.assertIsNone(payload["rows"][0]["source_section_count"])
        self.assertEqual(payload["rows"][1]["source_section_count"], 0)

    def test_all_rows_preserved_including_failures(self):
        rows = [
            dict(slug="a", title="Act A", acquisition_status="not_requested",
                 source_section_count=None, pdf_count=None, candidate_status="not_processed",
                 agreement_review_pending_count=None, quarantined_count=None,
                 searchable_provision_count=0, full_act_coverage_verified=False, diagnostic=None),
            dict(slug="b", title="Act B", acquisition_status="acquisition_failed",
                 source_section_count=None, pdf_count=None, candidate_status="not_processed",
                 agreement_review_pending_count=None, quarantined_count=None,
                 searchable_provision_count=0, full_act_coverage_verified=False, diagnostic="503 error"),
            dict(slug="c", title="Act C", acquisition_status="invalid_evidence",
                 source_section_count=None, pdf_count=None, candidate_status="unavailable",
                 agreement_review_pending_count=None, quarantined_count=None,
                 searchable_provision_count=0, full_act_coverage_verified=False, diagnostic="stale evidence"),
        ]
        report = self._report(rows)
        text = rc.render_text(report)
        for row in rows:
            self.assertIn(row["title"], text)
        self.assertIn("503 error", text)
        self.assertIn("stale evidence", text)
        payload = json.loads(rc.render_json(report))
        self.assertEqual([r["slug"] for r in payload["rows"]], ["a", "b", "c"])

    def test_json_and_text_report_the_same_top_level_counts(self):
        rows = [
            dict(slug="a", title="Act A", acquisition_status="captured_review_pending",
                 source_section_count=50, pdf_count=1, candidate_status="parsed_review_pending",
                 agreement_review_pending_count=40, quarantined_count=10,
                 searchable_provision_count=3, full_act_coverage_verified=False, diagnostic=None),
        ]
        report = self._report(rows)
        text = rc.render_text(report)
        payload = json.loads(rc.render_json(report))
        self.assertIn(f"selected Acts: {payload['selected_act_count']}", text)
        self.assertIn(f"captured Acts: {payload['captured_act_count']}", text)
        self.assertIn(f"searchable Acts: {payload['searchable_act_count']}", text)
        self.assertIn(f"searchable provisions: {payload['searchable_provision_count']}", text)
        self.assertEqual(payload["searchable_provision_count"], 3)

    def test_source_and_candidate_counts_not_mislabelled_as_searchable(self):
        # Source-listed sections (50) and candidate counts (40/10) are far larger
        # than what is actually searchable (2): the report must never present
        # those bookkeeping numbers as if they were searchable coverage.
        rows = [
            dict(slug="a", title="Act A", acquisition_status="captured_review_pending",
                 source_section_count=50, pdf_count=1, candidate_status="parsed_review_pending",
                 agreement_review_pending_count=40, quarantined_count=10,
                 searchable_provision_count=2, full_act_coverage_verified=False, diagnostic=None),
        ]
        report = self._report(rows)
        text = rc.render_text(report)
        row_lines = text.split("Act A (a)\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("source-listed sections: 50 section", row_lines)
        self.assertIn("agreement-review-pending: 40 candidate", row_lines)
        self.assertIn("quarantined: 10 candidate", row_lines)
        self.assertIn("searchable provisions: 2", row_lines)
        # The searchable-provisions line must carry the searchable count (2), never
        # the source/candidate bookkeeping counts (50/40/10).
        searchable_line = [l for l in row_lines.splitlines() if l.strip().startswith("searchable provisions:")][0]
        self.assertNotIn("50", searchable_line)
        self.assertNotIn("40", searchable_line)
        self.assertNotIn("10", searchable_line)

    def test_limitations_always_rendered(self):
        report = self._report([])
        text = rc.render_text(report)
        for note in report["limitations"]:
            self.assertIn(note, text)
        payload = json.loads(rc.render_json(report))
        self.assertEqual(payload["limitations"], report["limitations"])


class BuildReportTests(unittest.TestCase):
    """build_report composed against Snapshot + build_coverage, with small fixtures."""

    def test_missing_inventory_raises_clean_reporterror(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)  # no data/phase3/inventory.v1.json, no data/import db
            with self.assertRaises(rc.ReportError):
                rc.build_report(root)

    def test_snapshot_unavailable_is_caught_and_wrapped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture_root(tmp, [dict(slug="a", title="Act A")])
            with patch.object(rc, "Snapshot", side_effect=Unavailable("no import")):
                with self.assertRaises(rc.ReportError):
                    rc.build_report(root)

    def test_missing_and_failed_acts_still_produce_a_full_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture_root(tmp, [dict(slug="a", title="Act A"), dict(slug="b", title="Act B")])
            inventory = json.loads((root / "data/phase3/inventory.v1.json").read_text())
            ac.atomic_json(
                root / "data/phase3/acquisition/acts/b.json",
                dict(slug="b", inventory_sha256=ac.sha(ac.canonical(inventory).encode()),
                     status="acquisition_failed", error="503"),
            )
            with patch.object(rc, "Snapshot", return_value=SimpleNamespace(records={})):
                report = rc.build_report(root)
            self.assertEqual(report["selected_act_count"], 2)
            self.assertEqual([r["acquisition_status"] for r in report["rows"]],
                              ["not_requested", "acquisition_failed"])
            text = rc.render_text(report)
            self.assertIn("Act A", text)
            self.assertIn("Act B", text)
            self.assertIn("503", text)


class MainCliTests(unittest.TestCase):
    def test_clean_diagnostic_no_partial_stdout_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = rc.main(["--root", tmp])
            self.assertEqual(code, 1)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("report_phase3_coverage: error:", err.getvalue())

    def test_json_format_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture_root(tmp, [dict(slug="a", title="Act A")])
            out = io.StringIO()
            with patch.object(rc, "Snapshot", return_value=SimpleNamespace(records={})):
                with contextlib.redirect_stdout(out):
                    code = rc.main(["--root", str(root), "--format", "json"])
            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["selected_act_count"], 1)

    def test_default_format_is_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture_root(tmp, [dict(slug="a", title="Act A")])
            out = io.StringIO()
            with patch.object(rc, "Snapshot", return_value=SimpleNamespace(records={})):
                with contextlib.redirect_stdout(out):
                    code = rc.main(["--root", str(root)])
            self.assertEqual(code, 0)
            self.assertIn("LawIndex Phase 3 coverage report", out.getvalue())
            with self.assertRaises(json.JSONDecodeError):
                json.loads(out.getvalue())


class NoSideEffectsTests(unittest.TestCase):
    """The report must never write, spawn a subprocess, or touch the network."""

    def test_no_subprocess_invoked_against_real_repository(self):
        with patch.object(ac.subprocess, "run", side_effect=AssertionError("no subprocess expected")):
            report = rc.build_report(ac.ROOT)
            rc.render_text(report)
            rc.render_json(report)

    def test_real_repository_data_tree_is_unmodified(self):
        data_dir = ac.ROOT / "data"

        def _hash_tree():
            digest = hashlib.sha256()
            for path in sorted(p for p in data_dir.rglob("*") if p.is_file()):
                digest.update(str(path.relative_to(data_dir)).encode())
                digest.update(path.read_bytes())
            return digest.hexdigest()

        before = _hash_tree()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rc.main(["--root", str(ac.ROOT), "--format", "json"])
        self.assertEqual(code, 0)
        after = _hash_tree()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
