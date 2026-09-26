"""Tests for scripts/report_structure.py, the read-only clause-tree inspector.

Every database used here is a small synthetic fixture built in a temporary
directory with scripts.structural_store; none of it is real legislative
text or a real reviewed boundary profile. Tests either exercise the pure
tree-validation function directly with hand-built dicts (for malformed
shapes that the storage layer's own triggers already forbid constructing
through the normal write path -- missing parent, cycle, duplicate sibling
position) or run the full CLI/report against a real file-backed SQLite
database (for current-vs-historical roots, offsets, schema checks, WAL
concurrency, and file-safety behavior).
"""
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from scripts import offline_importer as oi
from scripts import structural_store as ss
from scripts import report_structure as rs


def make_synthetic_db(root: Path) -> Path:
    """A minimal file-backed database with the structural schema installed."""
    db_path = root / "db.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(oi.SCHEMA)
        conn.execute("INSERT INTO documents(act_slug,title,scope_status) VALUES ('demo','Synthetic','phase1_candidate')")
        conn.commit()
        ss.migrate(conn)
    finally:
        conn.close()
    return db_path


def write_capture_meta(root: Path, capture: str, raw: bytes) -> None:
    (root / "data/discovery").mkdir(parents=True, exist_ok=True)
    (root / f"data/discovery/{capture}.json").write_text(
        json.dumps(
            {
                "sha256": ss.sha(raw),
                "effective_url": "https://example.invalid/synthetic",
                "fetched_at_utc": None,
                "body_path": f"data/discovery/{capture}.body",
            }
        )
    )


class SyntheticRootFixture:
    """Promotes one synthetic root section ('demo:6') so tests can attach children."""

    def __init__(self, root: Path, body_text: str = "Example \U0001f9ed provision text."):
        self.root = root
        self.raw = {"demo-pdf": b"%PDF-synthetic-v1"}
        write_capture_meta(root, "demo-pdf", self.raw["demo-pdf"])
        self.body_text = body_text
        body_hash = ss.sha(body_text.encode())
        self.review = dict(
            provision_key="demo:6", act_slug="demo", section_number="6", heading="Synthetic heading",
            selected_representation="pdf", extraction_method_version="test-parser-v1", admission_status="admitted",
            source_representation=dict(capture="demo-pdf", sha256=ss.sha(self.raw["demo-pdf"]), pdf_page_from=4, pdf_page_to=5),
            expected_output=dict(body_text_sha256=body_hash, footnote_text_sha256="no-footnote-expected"),
        )
        self.record = {k: self.review[k] for k in (
            "provision_key", "act_slug", "section_number", "heading",
            "selected_representation", "extraction_method_version", "admission_status")}
        self.record.update(body_text=body_text, body_text_sha256=body_hash,
                            footnote_text=None, footnote_text_sha256=None, pdf_page_from=4, pdf_page_to=5)
        self.reviewer = {"reviewer_id": "synthetic-test-only"}

    def promote(self, conn):
        with conn:
            ss.promote(conn, self.root, self.record, self.review, self.reviewer, self.raw, {"test": True})

    def current_version(self, conn):
        row = conn.execute(
            "SELECT v.* FROM node_versions v JOIN current_versions c USING(version_id) "
            "WHERE c.provision_key=?", (self.review["provision_key"],)
        ).fetchone()
        return dict(row)


def insert_child(conn, *, node_id, extraction_id, parent_version_id, sibling_ordinal,
                  kind, display_label, body_text, act_slug="demo",
                  root_version_id=None, mandatory_context_version_id=None, offset_unit="unicode_code_points",
                  start=None, end=None, pdf_snapshot_id, pdf_page_from, pdf_page_to):
    ss.keep(conn, "structural_nodes", dict(node_id=node_id, act_slug=act_slug))
    anchor = dict(
        root_version_id=root_version_id, start=start, end=end, offset_unit=offset_unit,
        mandatory_context_version_id=mandatory_context_version_id, profile_sha256="synthetic",
    )
    row = dict(
        node_id=node_id, extraction_id=extraction_id, parent_version_id=parent_version_id,
        sibling_ordinal=sibling_ordinal, kind=kind, display_label=display_label, heading="",
        body_text=body_text, body_sha256=ss.sha(body_text.encode()),
        source_anchor_json=ss.canonical(anchor), pdf_snapshot_id=pdf_snapshot_id,
        pdf_page_from=pdf_page_from, pdf_page_to=pdf_page_to,
    )
    version_id = "synthetic-" + node_id
    return ss.keep(conn, "node_versions", {"version_id": version_id, **row})


class PureValidationTests(unittest.TestCase):
    """Exercises validate_and_build_tree/_child_offsets directly.

    These malformed shapes (missing parent, cycle, duplicate sibling
    position) are already rejected by structural_store's own insert-time
    triggers, so they cannot be produced through the normal write path --
    these tests check the report's own defense-in-depth validation, as if
    reading a database file that was edited outside that API.
    """

    def root_row(self, body_text="ABCDEFGHIJ"):
        return dict(version_id="root", parent_version_id=None, body_text=body_text)

    def test_valid_nested_tree_orders_by_ordinal_not_label(self):
        root = self.root_row()
        rows = {
            "root": root,
            "c10": dict(version_id="c10", parent_version_id="root", sibling_ordinal=1, kind="clause",
                        display_label="(10)", body_text="BCD",
                        source_anchor_json=ss.canonical(dict(root_version_id="root", mandatory_context_version_id="root",
                                                              offset_unit="unicode_code_points", start=1, end=4))),
            "c2": dict(version_id="c2", parent_version_id="root", sibling_ordinal=0, kind="clause",
                       display_label="(2)", body_text="A",
                       source_anchor_json=ss.canonical(dict(root_version_id="root", mandatory_context_version_id="root",
                                                             offset_unit="unicode_code_points", start=0, end=1))),
        }
        tree = rs.validate_and_build_tree(root, rows)
        self.assertEqual([n["display_label"] for n in tree], ["(2)", "(10)"])
        self.assertEqual(rs._count_descendants(tree), 2)

    def test_nested_grandchild_offsets_relative_to_root(self):
        root = self.root_row()
        rows = {
            "root": root,
            "sub": dict(version_id="sub", parent_version_id="root", sibling_ordinal=0, kind="subsection",
                        display_label="(1)", body_text="ABCDE",
                        source_anchor_json=ss.canonical(dict(root_version_id="root", mandatory_context_version_id="root",
                                                              offset_unit="unicode_code_points", start=0, end=5))),
            "clause": dict(version_id="clause", parent_version_id="sub", sibling_ordinal=0, kind="clause",
                           display_label="(a)", body_text="BC",
                           source_anchor_json=ss.canonical(dict(root_version_id="root", mandatory_context_version_id="root",
                                                                 offset_unit="unicode_code_points", start=1, end=3))),
        }
        tree = rs.validate_and_build_tree(root, rows)
        self.assertEqual(tree[0]["children"][0]["root_char_start"], 1)
        self.assertEqual(tree[0]["children"][0]["root_char_end"], 3)

    def test_duplicate_sibling_position_is_rejected(self):
        root = self.root_row()
        anchor = lambda s, e: ss.canonical(dict(root_version_id="root", mandatory_context_version_id="root",
                                                  offset_unit="unicode_code_points", start=s, end=e))
        rows = {
            "root": root,
            "a": dict(version_id="a", parent_version_id="root", sibling_ordinal=0, kind="clause",
                      display_label="(a)", body_text="A", source_anchor_json=anchor(0, 1)),
            "b": dict(version_id="b", parent_version_id="root", sibling_ordinal=0, kind="clause",
                      display_label="(b)", body_text="B", source_anchor_json=anchor(1, 2)),
        }
        with self.assertRaises(ValueError):
            rs.validate_and_build_tree(root, rows)

    def test_orphan_or_mutually_cyclic_descendants_are_rejected(self):
        root = self.root_row()
        anchor = ss.canonical(dict(root_version_id="root", mandatory_context_version_id="root",
                                    offset_unit="unicode_code_points", start=0, end=1))
        rows = {
            "root": root,
            "x": dict(version_id="x", parent_version_id="y", sibling_ordinal=0, kind="clause",
                      display_label="(x)", body_text="A", source_anchor_json=anchor),
            "y": dict(version_id="y", parent_version_id="x", sibling_ordinal=0, kind="clause",
                      display_label="(y)", body_text="A", source_anchor_json=anchor),
        }
        with self.assertRaisesRegex(ValueError, "orphan"):
            rs.validate_and_build_tree(root, rows)

    def test_missing_parent_reference_is_rejected(self):
        root = self.root_row()
        anchor = ss.canonical(dict(root_version_id="root", mandatory_context_version_id="root",
                                    offset_unit="unicode_code_points", start=0, end=1))
        rows = {
            "root": root,
            "orphan": dict(version_id="orphan", parent_version_id="does-not-exist", sibling_ordinal=0,
                            kind="clause", display_label="(a)", body_text="A", source_anchor_json=anchor),
        }
        with self.assertRaisesRegex(ValueError, "orphan"):
            rs.validate_and_build_tree(root, rows)

    def test_wrong_root_anchor_is_rejected(self):
        root = self.root_row()
        rows = {
            "root": root,
            "a": dict(version_id="a", parent_version_id="root", sibling_ordinal=0, kind="clause",
                      display_label="(a)", body_text="A",
                      source_anchor_json=ss.canonical(dict(root_version_id="someone-else",
                                                            mandatory_context_version_id="root",
                                                            offset_unit="unicode_code_points", start=0, end=1))),
        }
        with self.assertRaisesRegex(ValueError, "does not name the current root"):
            rs.validate_and_build_tree(root, rows)

    def test_offsets_outside_root_text_are_rejected(self):
        root = self.root_row()
        rows = {
            "root": root,
            "a": dict(version_id="a", parent_version_id="root", sibling_ordinal=0, kind="clause",
                      display_label="(a)", body_text="A",
                      source_anchor_json=ss.canonical(dict(root_version_id="root", mandatory_context_version_id="root",
                                                            offset_unit="unicode_code_points", start=0, end=999))),
        }
        with self.assertRaisesRegex(ValueError, "outside the root text"):
            rs.validate_and_build_tree(root, rows)

    def test_stored_text_not_matching_slice_is_rejected(self):
        root = self.root_row()
        rows = {
            "root": root,
            "a": dict(version_id="a", parent_version_id="root", sibling_ordinal=0, kind="clause",
                      display_label="(a)", body_text="WRONG",
                      source_anchor_json=ss.canonical(dict(root_version_id="root", mandatory_context_version_id="root",
                                                            offset_unit="unicode_code_points", start=0, end=1))),
        }
        with self.assertRaisesRegex(ValueError, "not the exact root slice"):
            rs.validate_and_build_tree(root, rows)

    def test_current_version_that_is_not_a_root_is_rejected(self):
        root = dict(version_id="child-mistakenly-current", parent_version_id="root", body_text="ABC")
        rows = {"root": dict(version_id="root", parent_version_id=None, body_text="ABC"), **{root["version_id"]: root}}
        with self.assertRaisesRegex(ValueError, "not a root"):
            rs.validate_and_build_tree(root, rows)


class ReportIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db_path = make_synthetic_db(self.root)

    def run_report(self, fmt="text", db_path=None):
        argv = ["--db", str(db_path or self.db_path), "--format", fmt]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = rs.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_no_profile_root_is_visible_with_explicit_zero_child_label(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            fixture = SyntheticRootFixture(self.root)
            fixture.promote(conn)
        finally:
            conn.close()
        code, out, err = self.run_report()
        self.assertEqual(code, 0, err)
        self.assertIn("demo:6", out)
        self.assertIn(rs.NO_STRUCTURE_LABEL, out)
        code, out, err = self.run_report(fmt="json")
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertEqual(report["roots"][0]["contextual_child_count"], 0)
        self.assertTrue(report["roots"][0]["no_reviewed_child_structure"])
        self.assertEqual(report["roots"][0]["children"], [])

    def test_nested_children_reported_with_offsets_and_length_no_body_text(self):
        body = "Subsection (1) applies, Clause (a) included, tail."
        sub_text = body  # subsection (1) spans the whole synthetic section
        clause_text = "Clause (a) included"
        sub_start, sub_end = 0, len(sub_text)
        clause_start = body.index(clause_text)
        clause_end = clause_start + len(clause_text)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            fixture = SyntheticRootFixture(self.root, body_text=body)
            fixture.promote(conn)
            root_version = fixture.current_version(conn)
            extraction_id = root_version["extraction_id"]
            pdf_id = root_version["pdf_snapshot_id"]
            sub_id = insert_child(
                conn, node_id="sub-1", extraction_id=extraction_id, parent_version_id=root_version["version_id"],
                sibling_ordinal=0, kind="subsection", display_label="(1)",
                body_text=sub_text,
                root_version_id=root_version["version_id"], mandatory_context_version_id=root_version["version_id"],
                start=sub_start, end=sub_end, pdf_snapshot_id=pdf_id, pdf_page_from=4, pdf_page_to=5,
            )
            insert_child(
                conn, node_id="clause-a", extraction_id=extraction_id, parent_version_id=sub_id,
                sibling_ordinal=0, kind="clause", display_label="(a)",
                body_text=clause_text,
                root_version_id=root_version["version_id"], mandatory_context_version_id=root_version["version_id"],
                start=clause_start, end=clause_end, pdf_snapshot_id=pdf_id, pdf_page_from=4, pdf_page_to=5,
            )
            conn.commit()
        finally:
            conn.close()
        code, out, err = self.run_report(fmt="json")
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        root = report["roots"][0]
        self.assertEqual(root["contextual_child_count"], 2)
        self.assertEqual(root["pdf_page_from"], 4)
        self.assertEqual(root["pdf_page_to"], 5)
        top = root["children"][0]
        self.assertEqual(top["display_label"], "(1)")
        self.assertEqual(top["root_char_start"], sub_start)
        self.assertEqual(top["root_char_end"], sub_end)
        self.assertEqual(top["text_length"], sub_end - sub_start)
        self.assertEqual(top["children"][0]["display_label"], "(a)")
        # Never renders body/footnote text.
        self.assertNotIn("Subsection (1) applies", out)
        self.assertNotIn("Clause (a)", out)

    def test_historical_root_children_never_leak_into_current_root(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            fixture = SyntheticRootFixture(self.root)
            fixture.promote(conn)
            v1 = fixture.current_version(conn)
            insert_child(
                conn, node_id="historical-child", extraction_id=v1["extraction_id"],
                parent_version_id=v1["version_id"], sibling_ordinal=0, kind="clause", display_label="(a)",
                body_text=fixture.body_text[:7],
                root_version_id=v1["version_id"], mandatory_context_version_id=v1["version_id"],
                start=0, end=7, pdf_snapshot_id=v1["pdf_snapshot_id"], pdf_page_from=4, pdf_page_to=5,
            )
            conn.commit()
            # New source bytes force a new review/version; v1 becomes historical.
            fixture.raw["demo-pdf"] = b"%PDF-synthetic-v2"
            write_capture_meta(self.root, "demo-pdf", fixture.raw["demo-pdf"])
            fixture.review["source_representation"]["sha256"] = ss.sha(fixture.raw["demo-pdf"])
            fixture.promote(conn)
            v2 = fixture.current_version(conn)
            self.assertNotEqual(v1["version_id"], v2["version_id"])
        finally:
            conn.close()
        code, out, err = self.run_report(fmt="json")
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertEqual(len(report["roots"]), 1)
        root = report["roots"][0]
        self.assertEqual(root["root_version_id"], v2["version_id"])
        self.assertEqual(root["contextual_child_count"], 0)
        self.assertTrue(root["no_reviewed_child_structure"])

    def test_heading_only_correction_shares_extraction_without_orphaning_history(self):
        """Regression: a heading-only re-review reuses the same extraction_id.

        extraction identity (scripts/structural_store.py's `extraction`
        dict) does not include heading, so re-promoting with the same body
        text and source bytes but a corrected heading reuses the existing
        extractions row and simply mints a new root node_versions row. The
        old root version is left behind as plain history sharing that same
        extraction_id -- it must never be reported as an orphan descendant
        of the new current root.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            fixture = SyntheticRootFixture(self.root)
            fixture.promote(conn)
            v1 = fixture.current_version(conn)

            fixture.review["heading"] = "Synthetic heading, corrected"
            fixture.record["heading"] = "Synthetic heading, corrected"
            fixture.promote(conn)
            v2 = fixture.current_version(conn)
            self.assertNotEqual(v1["version_id"], v2["version_id"])
            self.assertEqual(v1["extraction_id"], v2["extraction_id"])
        finally:
            conn.close()
        code, out, err = self.run_report(fmt="json")
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertEqual(len(report["roots"]), 1)
        root = report["roots"][0]
        self.assertEqual(root["root_version_id"], v2["version_id"])
        self.assertEqual(root["heading"], "Synthetic heading, corrected")
        self.assertEqual(root["contextual_child_count"], 0)

    def test_child_outside_immediate_parent_range_is_rejected(self):
        """Regression: a child within root bounds but outside its parent's own range.

        _child_offsets alone only bounds a descendant against the root's
        full text. A grandchild whose offsets fall inside the root text but
        outside its own immediate parent's [start, end) must still be
        rejected.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            body = "AAAA(1) narrow BBBB(a) wide CCCC"
            fixture = SyntheticRootFixture(self.root, body_text=body)
            fixture.promote(conn)
            root_version = fixture.current_version(conn)
            narrow_start, narrow_end = 0, body.index("BBBB")
            insert_child(
                conn, node_id="narrow-parent", extraction_id=root_version["extraction_id"],
                parent_version_id=root_version["version_id"], sibling_ordinal=0, kind="subsection",
                display_label="(1)", body_text=body[narrow_start:narrow_end],
                root_version_id=root_version["version_id"], mandatory_context_version_id=root_version["version_id"],
                start=narrow_start, end=narrow_end,
                pdf_snapshot_id=root_version["pdf_snapshot_id"], pdf_page_from=4, pdf_page_to=5,
            )
            # This grandchild's text is a real, exact slice of the ROOT, and
            # lies within the root's own bounds -- but it starts well after
            # its claimed parent (narrow-parent) already ended.
            outside_start = body.index("wide")
            outside_end = outside_start + len("wide")
            insert_child(
                conn, node_id="stray-clause", extraction_id=root_version["extraction_id"],
                parent_version_id="synthetic-narrow-parent", sibling_ordinal=0, kind="clause",
                display_label="(a)", body_text=body[outside_start:outside_end],
                root_version_id=root_version["version_id"], mandatory_context_version_id=root_version["version_id"],
                start=outside_start, end=outside_end,
                pdf_snapshot_id=root_version["pdf_snapshot_id"], pdf_page_from=4, pdf_page_to=5,
            )
            conn.commit()
        finally:
            conn.close()
        before = self.db_path.read_bytes()
        code, out, err = self.run_report()
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("immediate parent's range", err)
        self.assertEqual(self.db_path.read_bytes(), before)

    def test_overlapping_siblings_are_rejected(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            body = "AAAA(a) one BBBB(b) two CCCC"
            fixture = SyntheticRootFixture(self.root, body_text=body)
            fixture.promote(conn)
            root_version = fixture.current_version(conn)
            first_start, first_end = 0, body.index("two")  # deliberately runs past "(b)"'s start
            second_start = body.index("(b)")
            second_end = second_start + len("(b) two ")
            insert_child(
                conn, node_id="clause-a", extraction_id=root_version["extraction_id"],
                parent_version_id=root_version["version_id"], sibling_ordinal=0, kind="clause",
                display_label="(a)", body_text=body[first_start:first_end],
                root_version_id=root_version["version_id"], mandatory_context_version_id=root_version["version_id"],
                start=first_start, end=first_end,
                pdf_snapshot_id=root_version["pdf_snapshot_id"], pdf_page_from=4, pdf_page_to=5,
            )
            insert_child(
                conn, node_id="clause-b", extraction_id=root_version["extraction_id"],
                parent_version_id=root_version["version_id"], sibling_ordinal=1, kind="clause",
                display_label="(b)", body_text=body[second_start:second_end],
                root_version_id=root_version["version_id"], mandatory_context_version_id=root_version["version_id"],
                start=second_start, end=second_end,
                pdf_snapshot_id=root_version["pdf_snapshot_id"], pdf_page_from=4, pdf_page_to=5,
            )
            conn.commit()
        finally:
            conn.close()
        code, out, err = self.run_report()
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("overlaps a preceding sibling", err)

    def test_dangling_current_version_pointer_is_rejected_not_silently_dropped(self):
        """Regression: current_versions -> node_versions must be an inner check, not a silent drop.

        The trigger that keeps current_versions consistent forbids
        constructing this through the normal write path, so this test
        builds the dangling reference directly (foreign keys off, the
        consistency trigger dropped), representing a hand-edited or
        otherwise corrupted database file rather than one the importer
        could produce.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            fixture = SyntheticRootFixture(self.root)
            fixture.promote(conn)  # one legitimate, healthy root: demo:6
        finally:
            conn.close()

        corrupt_path = self.root / "dangling.sqlite3"
        conn = sqlite3.connect(corrupt_path)
        try:
            conn.executescript(oi.SCHEMA)
            conn.execute("INSERT INTO documents(act_slug,title,scope_status) VALUES ('demo','Synthetic','phase1_candidate')")
            conn.commit()
            ss.migrate(conn)
            conn.execute("DROP TRIGGER current_scope_insert")
            conn.execute("DROP TRIGGER current_scope_update")
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("INSERT INTO structural_nodes VALUES ('node-dangling','demo')")
            conn.execute("INSERT INTO provision_aliases VALUES ('demo:99','node-dangling')")
            conn.execute(
                "INSERT INTO current_versions VALUES ('demo:99','missing-version-id','missing-admission-id')"
            )
            conn.commit()
        finally:
            conn.close()

        code, out, err = self.run_report(db_path=corrupt_path)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("demo:99", err)
        self.assertIn("missing", err)

    def test_exact_unicode_offsets_with_multibyte_characters(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            body = "Sec \U0001f9ed (1) tail"
            fixture = SyntheticRootFixture(self.root, body_text=body)
            fixture.promote(conn)
            root_version = fixture.current_version(conn)
            start = body.index("(1)")
            end = start + len("(1)")
            insert_child(
                conn, node_id="unicode-child", extraction_id=root_version["extraction_id"],
                parent_version_id=root_version["version_id"], sibling_ordinal=0, kind="subsection",
                display_label="(1)", body_text=body[start:end],
                root_version_id=root_version["version_id"], mandatory_context_version_id=root_version["version_id"],
                start=start, end=end, pdf_snapshot_id=root_version["pdf_snapshot_id"], pdf_page_from=4, pdf_page_to=5,
            )
            conn.commit()
        finally:
            conn.close()
        code, out, err = self.run_report(fmt="json")
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        child = report["roots"][0]["children"][0]
        self.assertEqual(child["root_char_start"], start)
        self.assertEqual(child["root_char_end"], end)
        self.assertEqual(child["text_length"], end - start)

    def test_incorrect_stored_offsets_fail_cleanly_with_no_stdout(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            fixture = SyntheticRootFixture(self.root)
            fixture.promote(conn)
            root_version = fixture.current_version(conn)
            insert_child(
                conn, node_id="bad-offset-child", extraction_id=root_version["extraction_id"],
                parent_version_id=root_version["version_id"], sibling_ordinal=0, kind="clause",
                display_label="(a)", body_text="mismatched text",
                root_version_id=root_version["version_id"], mandatory_context_version_id=root_version["version_id"],
                start=0, end=5, pdf_snapshot_id=root_version["pdf_snapshot_id"], pdf_page_from=4, pdf_page_to=5,
            )
            conn.commit()
        finally:
            conn.close()
        before = self.db_path.read_bytes()
        code, out, err = self.run_report()
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("demo:6", err)
        self.assertEqual(self.db_path.read_bytes(), before)

    def test_wrong_root_anchor_fails_cleanly(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            fixture = SyntheticRootFixture(self.root)
            fixture.promote(conn)
            root_version = fixture.current_version(conn)
            insert_child(
                conn, node_id="wrong-anchor-child", extraction_id=root_version["extraction_id"],
                parent_version_id=root_version["version_id"], sibling_ordinal=0, kind="clause",
                display_label="(a)", body_text=fixture.body_text[:3],
                root_version_id="not-the-current-root", mandatory_context_version_id=root_version["version_id"],
                start=0, end=3, pdf_snapshot_id=root_version["pdf_snapshot_id"], pdf_page_from=4, pdf_page_to=5,
            )
            conn.commit()
        finally:
            conn.close()
        code, out, err = self.run_report()
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("report_structure: error", err)

    def test_malformed_schema_missing_structural_tables(self):
        legacy_path = self.root / "legacy.sqlite3"
        conn = sqlite3.connect(legacy_path)
        try:
            conn.executescript(oi.SCHEMA)
            conn.execute("INSERT INTO documents(act_slug,title) VALUES ('legacy','Preserve me')")
            conn.commit()
        finally:
            conn.close()
        code, out, err = self.run_report(db_path=legacy_path)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("no structural schema", err)

    def test_unsupported_schema_version(self):
        bad_path = self.root / "bad_version.sqlite3"
        conn = sqlite3.connect(bad_path)
        try:
            conn.executescript("CREATE TABLE structural_schema(version); INSERT INTO structural_schema VALUES (99);")
            conn.commit()
        finally:
            conn.close()
        code, out, err = self.run_report(db_path=bad_path)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("unsupported structural schema", err)

    def test_missing_database_is_reported_and_never_created(self):
        missing = self.root / "does-not-exist.sqlite3"
        code, out, err = self.run_report(db_path=missing)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("database not found", err)
        self.assertFalse(missing.exists())

    def test_filename_with_hash_question_mark_and_spaces(self):
        odd_dir = self.root / "odd name"
        odd_dir.mkdir()
        odd_path = odd_dir / "copy#1?.sqlite3"
        odd_path.write_bytes(self.db_path.read_bytes())
        conn = sqlite3.connect(odd_path)
        try:
            fixture = SyntheticRootFixture(self.root)
            fixture.promote(conn)
        finally:
            conn.close()
        code, out, err = self.run_report(db_path=odd_path)
        self.assertEqual(code, 0, err)
        self.assertIn("demo:6", out)

    def test_deterministic_json_across_runs(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            fixture = SyntheticRootFixture(self.root)
            fixture.promote(conn)
        finally:
            conn.close()
        _, out1, _ = self.run_report(fmt="json")
        _, out2, _ = self.run_report(fmt="json")
        self.assertEqual(out1, out2)

    def test_database_bytes_unchanged_after_success_and_failure(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            fixture = SyntheticRootFixture(self.root)
            fixture.promote(conn)
        finally:
            conn.close()
        before = self.db_path.read_bytes()
        code, _, _ = self.run_report(fmt="text")
        self.assertEqual(code, 0)
        self.assertEqual(self.db_path.read_bytes(), before)
        code, _, _ = self.run_report(fmt="json")
        self.assertEqual(code, 0)
        self.assertEqual(self.db_path.read_bytes(), before)

    def test_concurrent_writer_under_wal_sees_one_consistent_snapshot(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            fixture = SyntheticRootFixture(self.root)
            fixture.promote(conn)
        finally:
            conn.close()

        writer = sqlite3.connect(self.db_path)
        writer.row_factory = sqlite3.Row
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("BEGIN IMMEDIATE")
        root_version = dict(writer.execute(
            "SELECT v.* FROM node_versions v JOIN current_versions c USING(version_id)"
        ).fetchone())
        insert_child(
            writer, node_id="uncommitted-child", extraction_id=root_version["extraction_id"],
            parent_version_id=root_version["version_id"], sibling_ordinal=0, kind="clause",
            display_label="(a)", body_text=root_version["body_text"][:3],
            root_version_id=root_version["version_id"], mandatory_context_version_id=root_version["version_id"],
            start=0, end=3, pdf_snapshot_id=root_version["pdf_snapshot_id"], pdf_page_from=4, pdf_page_to=5,
        )
        # Not yet committed: a concurrent reader must not observe this row.
        try:
            code, out, err = self.run_report(fmt="json")
            self.assertEqual(code, 0, err)
            mid_write_report = json.loads(out)
            self.assertEqual(mid_write_report["roots"][0]["contextual_child_count"], 0)
        finally:
            writer.commit()
            writer.close()

        code, out, err = self.run_report(fmt="json")
        self.assertEqual(code, 0, err)
        after_commit_report = json.loads(out)
        self.assertEqual(after_commit_report["roots"][0]["contextual_child_count"], 1)


if __name__ == "__main__":
    unittest.main()
