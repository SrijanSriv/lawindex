"""Behavioral checks, with all mutations confined to a temporary project copy."""
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from scripts import offline_importer as oi
from lawindex.search import ROOT, Snapshot, Unavailable, excerpt
from lawindex.server import make_server


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "data", self.root / "data")
        # Preserve the original four-provision regression fixture explicitly.
        for path in (self.root / 'data/review').glob('*.review.json'):
            if json.loads(path.read_text())['extraction_method_version'] != oi.EXTRACTION_METHOD_VERSION:
                path.unlink()
        self.db = self.root / "data/import/lawindex_offline.sqlite3"

    def snapshot(self):
        return Snapshot(self.root)

    def mutate_json(self, relative, fn):
        path = self.root / relative
        record = json.loads(path.read_text())
        fn(record)
        path.write_text(json.dumps(record))

    def test_reference_and_alias_queries(self):
        s = self.snapshot()
        for query, key in [("RTI section 6", "rti-2005:6"), ("EPA s. 5A", "environment-1986:5A"),
                           ("The Right to Information Act, 2005 section 8", "rti-2005:8")]:
            self.assertEqual([r["key"] for r in s.search(query)["results"]], [key])
        self.assertEqual(s.search("RTI section 99")["results"], [])

    def test_section_only_lookup_uses_metadata_independent_of_body_text(self):
        # rti-2005:6's admitted body text never repeats its own section number
        # ("(1) A person, who desires..."), unlike rti-2005:8 whose body happens
        # to start "8. Exemption...". A bare section reference must still
        # resolve rti-2005:6 -- the label is a structural fact about the
        # provision, not something the reviewed text is required to restate.
        s = self.snapshot()
        for query, key in [("section 6", "rti-2005:6"), ("s. 6", "rti-2005:6"),
                            ("section 5A", "environment-1986:5A"), ("s. 3", "environment-1986:3")]:
            self.assertEqual([r["key"] for r in s.search(query)["results"]], [key],
                              f"query {query!r} should resolve {key!r} from metadata alone")
        # An Act-qualified reference to a section that exists in a different
        # Act must not fall back to a same-numbered section elsewhere.
        self.assertEqual(s.search("EPA section 6")["results"], [])
        # A section number absent from the whole admitted slice returns
        # nothing -- never a substitute nearby section.
        self.assertEqual(s.search("section 99")["results"], [])
        self.assertEqual(s.search("RTI section 99")["results"], [])
        # The trace must accurately reflect that no lexical match was required.
        trace = s.search("section 6")["trace"]
        self.assertEqual(trace["section_filter"], "6")
        self.assertEqual(trace["match_expression"], "")

    def test_lexical_and_safe_query_input(self):
        s = self.snapshot()
        self.assertEqual(s.search("transfer application")["results"][0]["key"], "rti-2005:6")
        self.assertEqual(s.search("National Green Tribunal")["results"][0]["key"], "environment-1986:5A")
        for query in ["", "  ", "!!!", "zzzznomatch"]:
            self.assertEqual(s.search(query)["results"], [])
        for query in ['" OR * ) NEAR(', "<script>alert(1)</script>", "'; DROP TABLE provisions;--"]:
            self.assertIsInstance(s.search(query)["results"], list)
        with self.assertRaises(ValueError):
            s.search("x" * 501)

    def test_development_queries(self):
        s = self.snapshot()
        for line in (self.root / "data/review/dev-queries.v2.jsonl").read_text().splitlines():
            q = json.loads(line)
            self.assertEqual(s.search(q["query"])["results"][0]["key"], q["expected_provision_key"], q["id"])

    def test_excerpt_is_exact_plain_text_with_codepoint_offsets(self):
        text = "🧑 Example <script>alert(1)</script> information and more information."
        e = excerpt(text, ["information"])
        self.assertEqual(e["text"], text[e["start"]:e["end"]])
        self.assertEqual("".join(x["text"] for x in e["segments"]), e["text"])
        self.assertTrue(any(x["match"] for x in e["segments"]))
        s = self.snapshot()
        for r in s.search("information")["results"]:
            e = r["excerpt"]
            self.assertEqual(e["text"], s.records[r["key"]]["body_text"][e["start"]:e["end"]])

    def test_footnotes_conflicts_and_anchors(self):
        s = self.snapshot()
        p = s.records["rti-2005:8"]
        self.assertIn("Subs.", p["footnote_text"])
        self.assertEqual(p["conflicts"][0]["id"], "RTI-001")
        self.assertNotIn("unwarranted invasion", p["body_text"])
        self.assertEqual(s.records["rti-2005:6"]["source"]["pdf_page_from"], 9)
        self.assertEqual(len(s.records), 4)
        self.assertTrue(s.pdfs["rti-2005:8"].startswith(b"%PDF-"))

    def test_review_withdrawal_without_reimport_and_restoration(self):
        path = self.root / "data/review/rti-2005-section-8.review.json"
        raw = path.read_bytes()
        path.unlink()
        self.assertNotIn("rti-2005:8", self.snapshot().records)
        self.assertNotIn("rti-2005:8", self.snapshot().pdfs)
        path.write_bytes(raw)
        self.assertIn("rti-2005:8", self.snapshot().records)

    def test_manifest_removal_without_reimport(self):
        self.mutate_json("data/discovery/corpus-manifest.json", lambda m: m.update(records=[r for r in m["records"] if r["slug"] != "rti-2005"]))
        self.assertEqual(set(self.snapshot().records), {"environment-1986:3", "environment-1986:5A"})

    def test_database_revocation_and_restoration(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE provisions SET admission_status='review_pending' WHERE provision_key='rti-2005:8'")
        self.assertEqual(self.snapshot().search("RTI section 8")["results"], [])
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE provisions SET admission_status='admitted' WHERE provision_key='rti-2005:8'")
        self.assertIn("rti-2005:8", self.snapshot().records)

    def test_real_reimport_withdrawal_and_restoration(self):
        shutil.copytree(ROOT / "scripts", self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        def run_import():
            subprocess.run(["python3", "scripts/offline_importer.py"], cwd=self.root,
                           check=True, capture_output=True)
        run_import()
        path = self.root / "data/review/rti-2005-section-8.review.json"
        original = path.read_bytes()
        path.unlink()
        run_import()
        self.assertEqual(self.snapshot().search("RTI section 8")["results"], [])
        self.assertNotIn("rti-2005:8", self.snapshot().pdfs)
        path.write_bytes(original)
        run_import()
        self.assertEqual(self.snapshot().search("RTI section 8")["results"][0]["key"], "rti-2005:8")

    def test_source_change_blocks_search_detail_and_pdf(self):
        path = self.root / "data/discovery/rti-2005-pdf.body"
        path.write_bytes(path.read_bytes() + b"changed")
        s = self.snapshot()
        self.assertNotIn("rti-2005:8", s.records)
        self.assertNotIn("rti-2005:6", s.pdfs)
        self.assertEqual(s.search("RTI section 8")["results"], [])

    def test_database_text_tamper_is_rejected(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE provisions SET body_text='tampered' WHERE provision_key='rti-2005:8'")
        self.assertNotIn("rti-2005:8", self.snapshot().records)

    def test_anchor_and_missing_digest_are_rejected(self):
        self.mutate_json("data/review/rti-2005-section-6.review.json", lambda r: r["pdf_anchor"].update(pdf_page_from=7))
        self.mutate_json("data/review/rti-2005-section-8.review.json", lambda r: r.pop("expected_output"))
        self.assertNotIn("rti-2005:6", self.snapshot().records)
        self.assertNotIn("rti-2005:8", self.snapshot().records)

    def test_missing_conflict_fails_closed(self):
        (self.root / "data/review/conflicts/RTI-001.json").unlink()
        self.assertNotIn("rti-2005:8", self.snapshot().records)

    def test_missing_database_does_not_create_empty_database(self):
        self.db.unlink()
        with self.assertRaises(Unavailable):
            self.snapshot()
        self.assertFalse(self.db.exists())

    def test_http_contract_and_withdrawal(self):
        server = make_server(self.root, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        def get(path):
            return urlopen(base + path)
        with get("/api/search?q=RTI%20section%208") as response:
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(json.load(response)["results"][0]["key"], "rti-2005:8")
        with get("/api/provisions/rti-2005%3A8") as response:
            self.assertEqual(json.load(response)["provision"]["key"], "rti-2005:8")
        with get("/api/sources/rti-2005%3A8.pdf") as response:
            self.assertEqual(response.headers["Content-Type"], "application/pdf")
        for path, status in [("/api/search?limit=bad", 400), ("/api/search?limit=21", 400),
                             ("/api/provisions/unknown", 404), ("/../data/review/reviewer.json", 404),
                             ("/api/sources/../../data/discovery/rti-2005-pdf.body.pdf", 404)]:
            with self.assertRaises(HTTPError) as context:
                get(path)
            self.assertEqual(context.exception.code, status)
        (self.root / "data/review/rti-2005-section-8.review.json").unlink()
        for path in ["/api/provisions/rti-2005%3A8", "/api/sources/rti-2005%3A8.pdf"]:
            with self.assertRaises(HTTPError) as context:
                get(path)
            self.assertEqual(context.exception.code, 404)
        with get("/api/search?q=RTI%20section%208") as response:
            self.assertEqual(json.load(response)["results"], [])

    def test_structural_version_missing_never_falls_back_to_legacy_text(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("DELETE FROM current_versions WHERE provision_key='rti-2005:8'")
        snapshot = self.snapshot()
        self.assertNotIn('rti-2005:8', snapshot.records)
        self.assertIn('rti-2005:6', snapshot.records)

    def test_changed_reviewer_invalidates_structural_admission(self):
        self.mutate_json('data/review/reviewer.json', lambda r: r.update(reviewer_id='different-reviewer'))
        self.assertNotIn('rti-2005:6', self.snapshot().records)

    def test_structural_history_is_immutable(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE node_versions SET body_text='tampered'")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('DELETE FROM version_admissions')
        self.assertEqual(len(self.snapshot().records), 4)


if __name__ == "__main__":
    unittest.main()
