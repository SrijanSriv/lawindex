"""The weak-match diagnostic: hand-checked shares, sweep counts, and the held-out split."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lawindex import benchmark
from lawindex.search import ROOT, WEAK_MATCH_SHARE
from scripts import analyze_notices as notices


def record(slug, title, heading, body):
    return {"act_slug": slug, "act_title": title, "heading": heading, "body_text": body}


class ShareTests(unittest.TestCase):
    def test_share_matches_hand_checked_stems_and_aliases(self):
        # words: requests->request, information->inform, rti, photon.
        # First result only contains "photon" (1/4). Second contains "request",
        # "information" and the RTI alias, not "photon" (3/4). Best is 3/4.
        words = ["requests", "information", "rti", "photon"]
        records = {
            "other:1": record("other", "Other", "Misc", "photon"),
            "rti:1": record("rti-2005", "Alpha", "Beta", "request information"),
        }
        results = [{"key": "other:1"}, {"key": "rti:1"}]
        self.assertEqual(notices.best_share(words, results, records), 0.75)
        self.assertEqual(notices.best_share(["requests"], [{"key": "rti:1"}], records), 1.0)
        self.assertEqual(notices.best_share(["quantity"], [{"key": "rti:1"}], records), 0.0)
        # "quantity" must not meet an unrelated "quantum".
        quantum = {"q:1": record("other", "X", "Y", "quantum")}
        self.assertEqual(notices.best_share(["quantity"], [{"key": "q:1"}], quantum), 0.0)
        self.assertIsNone(notices.best_share(words, [], records))
        self.assertIsNone(notices.best_share([], results, records))

    def test_content_words_drop_section_numbers_and_question_words(self):
        self.assertEqual(
            notices.content_words("why explain whether section 18 photon lattice energy"),
            ["photon", "lattice", "energy"])
        self.assertEqual(notices.content_words("POSH inquiry conciliation"),
                         ["posh", "inquiry", "conciliation"])

    def test_half_share_agrees_only_inside_the_notice_gate(self):
        self.assertEqual(WEAK_MATCH_SHARE, 0.5)
        self.assertFalse(notices.notice_would_fire(2, [{"key": "a"}], 0.0))
        self.assertFalse(notices.notice_would_fire(4, [], 0.0))
        self.assertFalse(notices.notice_would_fire(4, [{"key": "a"}], 0.5))
        self.assertTrue(notices.notice_would_fire(3, [{"key": "a"}], 0.499))
        query = {"id": "B-001", "split": "dev", "scope": "in_corpus", "category": "topic",
                 "query": "photon lattice energy"}
        response = {"results": [{"key": "q:1"}], "notices": [{"code": "weak_match"}]}
        records = {"q:1": record("other", "X", "Y", "nothing related here at all")}
        row = notices.measure_query(query, response, records)
        self.assertEqual(row["content_words"], 3)
        self.assertEqual(row["best_share"], 0.0)
        self.assertTrue(row["agrees"])
        response["notices"] = []
        self.assertFalse(notices.measure_query(query, response, records)["agrees"])


class SweepTests(unittest.TestCase):
    def test_sweep_counts_on_synthetic_rows(self):
        def row(scope, words, share):
            return {"scope": scope, "content_words": words, "best_share": share}

        rows = [
            row("in_corpus", 3, 0.19),
            row("in_corpus", 4, 0.30),
            row("in_corpus", 5, 0.50),
            row("in_corpus", 5, 0.60),
            row("in_corpus", 2, 0.00),
            row("in_corpus", 6, None),
            row("out_of_corpus", 3, 0.25),
            row("partial", 4, 0.25),
            row("partial", 5, 0.45),
            row("out_of_corpus", 5, 0.90),
        ]
        expected = []
        in_corpus = {
            (0.2, 3): 1, (0.2, 4): 0, (0.2, 5): 0,
            (0.3, 3): 1, (0.3, 4): 0, (0.3, 5): 0,
            (0.4, 3): 2, (0.4, 4): 1, (0.4, 5): 0,
            (0.5, 3): 2, (0.5, 4): 1, (0.5, 5): 0,
            (0.6, 3): 3, (0.6, 4): 2, (0.6, 5): 1,
        }
        out_or_partial = {
            (0.2, 3): 0, (0.2, 4): 0, (0.2, 5): 0,
            (0.3, 3): 2, (0.3, 4): 1, (0.3, 5): 0,
            (0.4, 3): 2, (0.4, 4): 1, (0.4, 5): 0,
            (0.5, 3): 3, (0.5, 4): 2, (0.5, 5): 1,
            (0.6, 3): 3, (0.6, 4): 2, (0.6, 5): 1,
        }
        for threshold in notices.THRESHOLDS:
            for min_words in notices.MIN_WORD_COUNTS:
                key = (threshold, min_words)
                expected.append({"threshold": threshold, "min_words": min_words,
                                 "in_corpus": in_corpus[key],
                                 "out_or_partial": out_or_partial[key]})
        self.assertEqual(notices.sweep(rows), expected)

    def test_render_and_json_omit_test_split_rows(self):
        dev = [{"id": "B-001", "scope": "in_corpus", "category": "topic",
                "content_words": 3, "best_share": 0.25, "weak_match": True}]
        test = [{"id": "B-777", "scope": "out_of_corpus", "category": "topic",
                 "content_words": 4, "best_share": 0.1, "weak_match": True}]
        dev_sweep, test_sweep = notices.sweep(dev), notices.sweep(test)
        text = notices.render(dev, dev_sweep, test_sweep)
        self.assertIn("B-001", text)
        self.assertNotIn("B-777", text)
        self.assertIn("test sweep", text)
        blob = json.dumps(notices.payload(dev, dev_sweep, test_sweep))
        self.assertNotIn("B-777", json.dumps(notices.payload(dev, dev_sweep, test_sweep)["test"]))
        self.assertIn("B-001", blob)


class RealRunTests(unittest.TestCase):
    def test_printed_output_has_no_test_split_query_id(self):
        queries = benchmark.load_queries(benchmark.QUERIES)
        test_ids = [query["id"] for query in queries if query["split"] == "test"]
        dev_ids = [query["id"] for query in queries if query["split"] == "dev"]
        self.assertTrue(test_ids and dev_ids)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notices.json"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "analyze_notices.py"), "--json", str(path)],
                cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            written = path.read_text()
        output = completed.stdout + completed.stderr
        for qid in test_ids:
            self.assertNotIn(qid, output)
            self.assertNotIn(qid, written)
        for qid in dev_ids:
            self.assertIn(qid, output)
            self.assertIn(qid, written)
        data = json.loads(written)
        self.assertTrue(data["consistent"])
        self.assertNotIn("queries", data["test"])
        self.assertIsNone(re.search(r"B-\d{3}", json.dumps(data["test"])))
        self.assertEqual(len(data["dev"]["queries"]), len(dev_ids))
        self.assertEqual(len(data["dev"]["sweep"]), 15)
        self.assertEqual(len(data["test"]["sweep"]), 15)


if __name__ == "__main__":
    unittest.main()
