"""Tests for scripts/unjudged_packets.py. Fixtures are synthetic; nothing here
writes under data/benchmark/.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from lawindex.benchmark import read_jsonl
from scripts import judging_packets as jp
from scripts import unjudged_packets as up

ROOT = Path(__file__).resolve().parents[1]
FINGERPRINT = "sha256:test-fingerprint"
FIRST_SEEN = ["act-a:7", "act-a:1", "act-a:4", "act-a:0", "act-a:6", "act-a:2", "act-a:5", "act-a:3"]
DEV_TEXT = "dev-only-marker-phrase"
TEST_ID = "B-070"
TEST_TEXT = "test-only-marker-phrase"


def record(key):
    act, number = key.split(":")
    return {"key": key, "act_slug": act, "act_title": f"Title {act}", "section_number": number,
            "heading": f"Heading {key}", "body_text": f"Body of {key}.", "footnote_text": None}


def records_for(keys):
    return {key: record(key) for key in keys}


def query(qid, split, text, filters=None):
    return {"id": qid, "query": text, "intent": f"intent for {qid}", "filters": filters or {},
            "split": split}


def run(rows, fingerprint=FINGERPRINT):
    return {"manifest": {"corpus_fingerprint": fingerprint}, "queries": rows}


def row(qid, split, keys):
    return {"id": qid, "split": split, "unjudged_in_top_10": keys}


def raw_lines(expected_queries):
    lines = []
    for qid, keys in expected_queries.items():
        for key in keys:
            lines.append({"kind": "judgment", "query_id": qid, "provision_key": key, "grade": 1,
                          "rationale": "synthetic for check", "source": "pool"})
    return lines


class CollectTests(unittest.TestCase):
    def test_dedup_across_runs_keeps_first_seen_and_drops_judged_pairs(self):
        runs = [
            run([
                row("B-002", "dev", ["act-a:7", "act-a:1", "act-a:1"]),
                row("B-010", "dev", ["act-a:2"]),
                row("B-070", "test", ["act-b:1"]),
                row("B-003", "dev", None),
                row("B-004", "dev", []),
            ]),
            run([
                row("B-002", "dev", ["act-a:1", "act-a:4"]),
                row("B-010", "dev", ["act-a:2"]),
                row("B-030", "test", ["act-b:1"]),
            ]),
        ]
        judged = up.judged_pairs_from_rows([
            {"query_id": "B-010", "provision_key": "act-a:2", "grade": 2},
            {"query_id": "B-002", "provision_key": "act-a:7", "grade": 0},
        ])
        collected = up.collect_unjudged(runs, judged)
        self.assertEqual(collected["B-002"], {"split": "dev", "keys": ["act-a:1", "act-a:4"]})
        self.assertNotIn("B-010", collected)
        self.assertNotIn("B-003", collected)
        self.assertNotIn("B-004", collected)
        # Same provision, two queries: the pair is what is de-duplicated.
        self.assertEqual(collected["B-070"]["keys"], ["act-b:1"])
        self.assertEqual(collected["B-030"]["keys"], ["act-b:1"])

    def test_judged_pairs_come_from_judgment_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "judgments.jsonl"
            path.write_text(json.dumps({"query_id": "B-002", "provision_key": "act-a:1"}) + "\n")
            pairs = up.judged_pairs_from_rows(read_jsonl(path))
        self.assertEqual(pairs, {("B-002", "act-a:1")})

    def test_runs_that_disagree_on_split_are_rejected(self):
        runs = [run([row("B-002", "dev", ["act-a:1"])]), run([row("B-002", "test", ["act-a:4"])])]
        with self.assertRaises(ValueError):
            up.collect_unjudged(runs, set())

    def test_run_without_queries_is_rejected(self):
        with self.assertRaises(ValueError):
            up.collect_unjudged([{"manifest": {"corpus_fingerprint": FINGERPRINT}}], set())


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.judging = Path(self.tmp.name)
        self.records = records_for(FIRST_SEEN + ["act-b:1"])
        self.queries = [
            query("B-002", "dev", DEV_TEXT, filters={"act": "act-a"}),
            query(TEST_ID, "test", TEST_TEXT),
        ]
        self.runs = [run([
            row("B-002", "dev", list(FIRST_SEEN)),
            row(TEST_ID, "test", ["act-b:1"]),
        ])]

    def _write(self, judge="A", batch_size=1, judging=None):
        return up.execute(self.runs, self.queries, self.records, set(), FINGERPRINT, judge,
                          batch_size, judging or self.judging)

    def test_batches_and_shuffle_match_judging_packets(self):
        out = StringIO()
        with redirect_stdout(out):
            self._write()
        other = self.judging / "again"
        with redirect_stdout(StringIO()):
            self._write(judging=other)
        first = json.loads((self.judging / "packets/A/batch-01.expected.json").read_text())
        second = json.loads((other / "packets/A/batch-01.expected.json").read_text())
        self.assertEqual(first, second)
        self.assertEqual((self.judging / "packets/A/batch-01.md").read_text(),
                         (other / "packets/A/batch-01.md").read_text())
        self.assertEqual(list(first["queries"]), ["B-002"])
        self.assertEqual(first["queries"]["B-002"], jp.shuffled_keys(FIRST_SEEN, "A", "B-002"))
        self.assertNotEqual(first["queries"]["B-002"], jp.shuffled_keys(sorted(FIRST_SEEN), "A", "B-002"))
        self.assertEqual(first["judge"], "A")
        self.assertEqual(first["batch"], 1)
        self.assertEqual(first["corpus_fingerprint"], FINGERPRINT)
        later = json.loads((self.judging / "packets/A/batch-02.expected.json").read_text())
        self.assertEqual(list(later["queries"]), [TEST_ID])
        self.assertEqual(later["queries"][TEST_ID], ["act-b:1"])

        judge_b = self.judging / "judge-b"
        with redirect_stdout(StringIO()):
            self._write(judge="B", judging=judge_b)
        expected_b = json.loads((judge_b / "packets/B/batch-01.expected.json").read_text())
        self.assertEqual(expected_b["queries"]["B-002"], jp.shuffled_keys(FIRST_SEEN, "B", "B-002"))
        self.assertNotEqual(expected_b["queries"]["B-002"], first["queries"]["B-002"])

        packet = (self.judging / "packets/A/batch-01.md").read_text()
        self.assertIn("# Judging packet: judge A, batch 01", packet)
        self.assertIn(DEV_TEXT, packet)
        self.assertIn("Heading act-a:7", packet)
        self.assertIn('"act": "act-a"', packet)
        headings = [line[4:] for line in packet.splitlines() if line.startswith("### ")]
        self.assertEqual(headings, first["queries"]["B-002"])

    def test_stdout_counts_only_and_check_accepts_the_directory(self):
        out = StringIO()
        with redirect_stdout(out):
            self._write()
        text = out.getvalue()
        self.assertEqual(text, "dev: 1 query, 8 pairs\ntest: 1 query, 1 pair\n")
        self.assertNotIn(TEST_ID, text)
        self.assertNotIn(TEST_TEXT, text)
        self.assertNotIn(DEV_TEXT, text)
        self.assertNotIn("B-002", text)

        test_packet = (self.judging / "packets/A/batch-02.md").read_text()
        self.assertIn(TEST_ID, test_packet)
        self.assertIn(TEST_TEXT, test_packet)

        for batch in (1, 2):
            expected_path = self.judging / f"packets/A/batch-{batch:02d}.expected.json"
            expected = json.loads(expected_path.read_text())
            raw_path = self.judging / f"raw/A/batch-{batch:02d}.jsonl"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text("".join(json.dumps(line) + "\n" for line in raw_lines(expected["queries"])))
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts/merge_judgments.py"), "check",
                 "--judge", "A", "--batch", str(batch), "--judging", str(self.judging)],
                cwd=ROOT, capture_output=True, text=True, check=False, timeout=180,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            pair_count = sum(len(keys) for keys in expected["queries"].values())
            self.assertIn(f"OK {pair_count} judgments, 0 manual, 0 unindexed", completed.stdout)

    def test_dropped_pairs_are_absent_from_the_packet(self):
        runs = [
            run([row("B-002", "dev", ["act-a:1", "act-a:4"])]),
            run([row("B-002", "dev", ["act-a:4", "act-a:0"]), row("B-010", "dev", ["act-a:2"])]),
        ]
        queries = [query("B-002", "dev", DEV_TEXT), query("B-010", "dev", "other dev query")]
        out = StringIO()
        with redirect_stdout(out):
            up.execute(runs, queries, self.records, {("B-002", "act-a:1"), ("B-010", "act-a:2")},
                       FINGERPRINT, "A", 8, self.judging)
        expected = json.loads((self.judging / "packets/A/batch-01.expected.json").read_text())
        self.assertEqual(set(expected["queries"]), {"B-002"})
        self.assertEqual(sorted(expected["queries"]["B-002"]), ["act-a:0", "act-a:4"])
        self.assertEqual(expected["queries"]["B-002"], jp.shuffled_keys(["act-a:4", "act-a:0"], "A", "B-002"))
        self.assertIn("dev: 1 query, 2 pairs", out.getvalue())
        self.assertIn("test: 0 queries, 0 pairs", out.getvalue())

    def test_missing_provision_writes_nothing(self):
        runs = [run([row("B-002", "dev", ["missing:1"])])]
        with self.assertRaises(ValueError):
            up.execute(runs, self.queries, self.records, set(), FINGERPRINT, "A", 8, self.judging)
        self.assertFalse((self.judging / "packets").exists())

    def test_fingerprint_mismatch_writes_nothing(self):
        runs = [run([row("B-002", "dev", ["act-a:1"])], fingerprint="sha256:other")]
        with self.assertRaises(ValueError):
            up.execute(runs, self.queries, self.records, set(), FINGERPRINT, "A", 8, self.judging)
        self.assertFalse((self.judging / "packets").exists())

    def test_default_directory_is_judging_v2(self):
        self.assertEqual(up.DEFAULT_OUT, ROOT / "data/benchmark/judging-v2")
        self.assertFalse(str(up.DEFAULT_OUT).endswith("data/benchmark/judging"))
