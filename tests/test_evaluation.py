"""Hand-computed checks for lawindex/evaluation.py and an end-to-end reproducibility
check for scripts/run_benchmark.py --rankings-only. No network, no importer run."""
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from lawindex import evaluation as ev
from lawindex.benchmark import RELEVANT

ROOT = Path(__file__).resolve().parents[1]


class DcgTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(ev.dcg([]), 0)

    def test_hand_computed(self):
        # (2**3-1)/log2(2) + (2**2-1)/log2(3) + (2**0-1)/log2(4)
        expected = 7 / math.log2(2) + 3 / math.log2(3) + 0 / math.log2(4)
        self.assertAlmostEqual(ev.dcg([3, 2, 0]), expected, places=9)


class NdcgAtKTests(unittest.TestCase):
    def test_ideal_dcg_uses_judged_keys_not_retrieved(self):
        # "z" is judged grade 3 but never retrieved; the ideal ranking still
        # includes it, so the achievable ranking cannot reach nDCG 1.0.
        ranking = ["a", "b", "c"]
        grades = {"a": 3, "b": 1, "c": 2, "z": 3}
        actual = 7 / math.log2(2) + 1 / math.log2(3) + 3 / math.log2(4)
        ideal = 7 / math.log2(2) + 7 / math.log2(3) + 3 / math.log2(4) + 1 / math.log2(5)
        self.assertAlmostEqual(ev.ndcg_at_k(ranking, grades, 10), actual / ideal, places=9)

    def test_unjudged_keys_count_zero_gain(self):
        ranking = ["x", "a"]
        grades = {"a": 3}
        actual = 0 / math.log2(2) + 7 / math.log2(3)
        ideal = 7 / math.log2(2)
        self.assertAlmostEqual(ev.ndcg_at_k(ranking, grades, 10), actual / ideal, places=9)

    def test_none_when_ideal_dcg_is_zero(self):
        self.assertIsNone(ev.ndcg_at_k(["a", "b"], {}, 10))
        self.assertIsNone(ev.ndcg_at_k([], {}, 10))

    def test_k_truncates_both_actual_and_ideal(self):
        ranking = ["a", "b", "c", "d"]
        grades = {"a": 1, "b": 1, "c": 1, "d": 3}
        # k=1: only "a" (gain 1) is seen, against an ideal top-1 of grade 3.
        expected = (1 / math.log2(2)) / (7 / math.log2(2))
        self.assertAlmostEqual(ev.ndcg_at_k(ranking, grades, 1), expected, places=9)


class MrrTests(unittest.TestCase):
    def test_reciprocal_rank_of_first_relevant(self):
        self.assertEqual(ev.mrr(["a", "b", "c"], {"a": 1, "b": 3}), 0.5)

    def test_zero_when_nothing_relevant_within_cutoff(self):
        self.assertEqual(ev.mrr(["c", "a"], {"a": 1}), 0.0)

    def test_cutoff_excludes_later_relevant_key(self):
        self.assertEqual(ev.mrr(["a", "b"], {"b": 3}, cutoff=1), 0.0)


class RecallAtKTests(unittest.TestCase):
    def test_share_of_relevant_judged_keys_retrieved(self):
        grades = {"a": 3, "b": 2, "c": 0}
        self.assertEqual(ev.recall_at_k(["c", "a", "x"], grades, 2), 0.5)
        self.assertEqual(ev.recall_at_k(["c", "a", "b"], grades, 3), 1.0)

    def test_none_when_no_relevant_judged_keys(self):
        self.assertIsNone(ev.recall_at_k(["a"], {"a": 1, "b": 0}, 10))


class PrecisionAtKTests(unittest.TestCase):
    def test_short_ranking_still_divides_by_k(self):
        self.assertEqual(ev.precision_at_k(["a", "b"], {"a": 3}, 5), 0.2)

    def test_full_ranking(self):
        self.assertEqual(ev.precision_at_k(["a", "b", "c"], {"a": 3, "b": 2}, 3), 2 / 3)


class SuccessAtKBestTests(unittest.TestCase):
    def test_best_grade_is_two_not_three(self):
        grades = {"a": 2, "b": 2, "c": 1}
        self.assertEqual(ev.success_at_k_best(["c", "b"], grades, 3), 1.0)

    def test_zero_when_best_key_outside_top_k(self):
        grades = {"a": 2, "b": 2, "c": 1}
        self.assertEqual(ev.success_at_k_best(["c", "x", "y", "b"], grades, 3), 0.0)

    def test_none_when_best_judged_grade_below_relevant(self):
        self.assertIsNone(ev.success_at_k_best(["a"], {"a": 1}, 3))
        self.assertIsNone(ev.success_at_k_best(["a"], {}, 3))


class JudgedAtKTests(unittest.TestCase):
    def test_share_of_top_min_k_len(self):
        ranking = ["a", "b", "c", "d"]
        self.assertEqual(ev.judged_at_k(ranking, {"a": 1, "c": 2}, 10), 0.5)

    def test_none_for_empty_ranking(self):
        self.assertIsNone(ev.judged_at_k([], {"a": 1}, 10))


class ActRankingTests(unittest.TestCase):
    def test_deduplicates_keeping_first_appearance(self):
        act_of = {"p1": "actA", "p2": "actB", "p3": "actA", "p4": "actC"}
        self.assertEqual(ev.act_ranking(["p1", "p2", "p3", "p4"], act_of), ["actA", "actB", "actC"])

    def test_empty_ranking(self):
        self.assertEqual(ev.act_ranking([], {}), [])


class DocMetricsTests(unittest.TestCase):
    def test_hand_computed(self):
        act_of = {"p1": "actA", "p2": "actB", "p3": "actA", "p4": "actC"}
        result = ev.doc_metrics(["p1", "p2", "p3", "p4"], act_of, {"actB", "actC"})
        self.assertEqual(result, {"mrr_doc": 0.5, "success_at_1_doc": 0.0, "recall_at_3_doc": 1.0})

    def test_first_act_is_relevant(self):
        act_of = {"p1": "actA"}
        result = ev.doc_metrics(["p1"], act_of, {"actA"})
        self.assertEqual(result, {"mrr_doc": 1.0, "success_at_1_doc": 1.0, "recall_at_3_doc": 1.0})


class BootstrapCiTests(unittest.TestCase):
    def test_deterministic_for_same_seed(self):
        values = [0.1, 0.4, 0.9, 0.3, 0.7]
        first = ev.bootstrap_ci(values, resamples=200, seed=0)
        second = ev.bootstrap_ci(values, resamples=200, seed=0)
        self.assertEqual(first, second)

    def test_different_seed_can_differ(self):
        values = [0.1, 0.9, 0.2, 0.8, 0.3, 0.7]
        a = ev.bootstrap_ci(values, resamples=200, seed=0)
        b = ev.bootstrap_ci(values, resamples=200, seed=1)
        self.assertNotEqual(a, b)

    def test_none_for_empty_list(self):
        self.assertIsNone(ev.bootstrap_ci([]))

    def test_interval_brackets_degenerate_constant_list(self):
        lo, hi = ev.bootstrap_ci([0.5, 0.5, 0.5])
        self.assertEqual(lo, 0.5)
        self.assertEqual(hi, 0.5)


class PercentileTests(unittest.TestCase):
    def test_nearest_rank(self):
        values = [10, 20, 30, 40, 50]
        self.assertEqual(ev.percentile(values, 50), 30)   # rank = ceil(0.5*5) = 3
        self.assertEqual(ev.percentile(values, 95), 50)   # rank = ceil(0.95*5) = 5
        self.assertEqual(ev.percentile(values, 1), 10)    # rank = ceil(0.01*5) = 1

    def test_none_for_empty(self):
        self.assertIsNone(ev.percentile([], 50))


class EvaluateQueryTests(unittest.TestCase):
    def test_document_query(self):
        query = {"id": "B-100", "category": "exact_title", "scope": "in_corpus", "level": "document",
                 "split": "dev", "relevant_acts": ["actA"], "filters": {}}
        response = {"results": [{"key": "p1"}, {"key": "p3"}], "notices": [],
                    "trace": {"search_ms": 12.3}}
        records = {"p1": {"act_slug": "actA"}, "p3": {"act_slug": "actB"}}
        row = ev.evaluate_query(query, response, {}, records)
        self.assertEqual(row["excluded_reason"], "document_level")
        for name in ev.PROVISION_METRICS:
            self.assertIsNone(row[name])
        self.assertIsNone(row["unjudged_in_top_10"])
        # actA is retrieved first, so all three doc metrics are perfect.
        self.assertEqual(row["mrr_doc"], 1.0)
        self.assertEqual(row["success_at_1_doc"], 1.0)
        self.assertEqual(row["recall_at_3_doc"], 1.0)
        self.assertIsNone(row["notice_hit"])
        self.assertFalse(row["false_notice"])

    def test_out_of_corpus_query(self):
        query = {"id": "B-101", "category": "out_of_corpus", "scope": "out_of_corpus",
                 "level": "provision", "split": "test", "expected_notices": ["act_not_indexed"],
                 "filters": {}}
        response = {"results": [], "notices": [{"code": "act_not_indexed"}],
                    "trace": {"search_ms": 5.0}}
        row = ev.evaluate_query(query, response, {}, {})
        self.assertEqual(row["excluded_reason"], "out_of_corpus")
        for name in ev.PROVISION_METRICS:
            self.assertIsNone(row[name])
        for name in ev.DOC_METRICS:
            self.assertIsNone(row[name])
        self.assertTrue(row["notice_hit"])
        self.assertIsNone(row["false_notice"])  # only checked for in_corpus queries

    def test_in_corpus_query_with_false_notice(self):
        query = {"id": "B-102", "category": "topic", "scope": "in_corpus", "level": "provision",
                 "split": "dev", "filters": {}}
        response = {"results": [{"key": "p1"}], "notices": [{"code": "weak_match"}],
                    "trace": {"search_ms": 8.0}}
        records = {"p1": {"act_slug": "actA"}}
        row = ev.evaluate_query(query, response, {"p1": 3}, records)
        self.assertIsNone(row["excluded_reason"])
        self.assertEqual(row["ndcg_at_10"], 1.0)
        self.assertEqual(row["mrr"], 1.0)
        self.assertEqual(row["recall_at_10"], 1.0)
        self.assertEqual(row["recall_at_20"], 1.0)
        self.assertEqual(row["p_at_5"], 0.2)
        self.assertEqual(row["p_at_10"], 0.1)
        self.assertEqual(row["success_at_3"], 1.0)
        self.assertEqual(row["judged_at_10"], 1.0)
        self.assertEqual(row["unjudged_in_top_10"], [])
        self.assertEqual(row["mrr_doc"], 1.0)
        self.assertIsNone(row["notice_hit"])  # no expected_notices for this query
        self.assertTrue(row["false_notice"])  # weak_match on an in_corpus query

    def test_excluded_when_no_judged_key_reaches_relevant(self):
        query = {"id": "B-103", "category": "topic", "scope": "in_corpus", "level": "provision",
                 "split": "dev", "filters": {}}
        response = {"results": [{"key": "p1"}], "notices": [], "trace": {"search_ms": 1.0}}
        row = ev.evaluate_query(query, response, {"p1": 1}, {"p1": {"act_slug": "actA"}})
        self.assertEqual(row["excluded_reason"], "no_relevant_judged")

    def test_unjudged_in_top_10_lists_unjudged_keys(self):
        query = {"id": "B-104", "category": "topic", "scope": "in_corpus", "level": "provision",
                 "split": "dev", "filters": {}}
        response = {"results": [{"key": "p1"}, {"key": "x"}], "notices": [], "trace": {"search_ms": 1.0}}
        records = {"p1": {"act_slug": "actA"}, "x": {"act_slug": "actA"}}
        row = ev.evaluate_query(query, response, {"p1": RELEVANT}, records)
        self.assertEqual(row["unjudged_in_top_10"], ["x"])


class AggregateTests(unittest.TestCase):
    def _row(self, **overrides):
        row = {"id": "B-000", "category": "topic", "scope": "in_corpus", "level": "provision",
               "split": "dev", "ranking": [], "notices": [], "search_ms": 10.0,
               "excluded_reason": None, "unjudged_in_top_10": [], "notice_hit": None,
               "false_notice": False}
        for name in ev.PROVISION_METRICS + ev.DOC_METRICS:
            row[name] = None
        row.update(overrides)
        return row

    def test_ignores_none_when_averaging(self):
        rows = [self._row(id="B-001", ndcg_at_10=0.8, mrr=1.0),
                self._row(id="B-002", ndcg_at_10=None, mrr=None, excluded_reason="no_relevant_judged"),
                self._row(id="B-003", ndcg_at_10=0.4, mrr=0.5)]
        agg = ev.aggregate(rows)
        overall = agg["overall"]
        self.assertEqual(overall["n"], 3)
        self.assertAlmostEqual(overall["ndcg_at_10"]["mean"], 0.6)
        self.assertEqual(overall["ndcg_at_10"]["n"], 2)
        self.assertAlmostEqual(overall["mrr"]["mean"], 0.75)
        self.assertEqual(agg["excluded"]["no_relevant_judged"], ["B-002"])
        self.assertEqual(agg["excluded"]["document_level"], [])
        self.assertEqual(agg["excluded"]["out_of_corpus"], [])

    def test_groups_by_split_category_and_scope(self):
        rows = [self._row(id="B-001", split="dev", category="topic", scope="in_corpus", ndcg_at_10=1.0),
                self._row(id="B-002", split="test", category="citation", scope="partial", ndcg_at_10=0.0)]
        agg = ev.aggregate(rows)
        self.assertEqual(agg["split:dev"]["n"], 1)
        self.assertEqual(agg["split:test"]["n"], 1)
        self.assertEqual(agg["category:topic"]["n"], 1)
        self.assertEqual(agg["category:citation"]["n"], 1)
        self.assertEqual(agg["scope:in_corpus"]["n"], 1)
        self.assertEqual(agg["scope:partial"]["n"], 1)
        self.assertNotIn("p50_ms", agg["split:dev"])  # latency percentiles are overall-only

    def test_overall_latency_percentiles(self):
        rows = [self._row(id=f"B-{i:03d}", search_ms=float(i)) for i in range(1, 11)]
        agg = ev.aggregate(rows)
        self.assertEqual(agg["overall"]["p50_ms"], ev.percentile([float(i) for i in range(1, 11)], 50))
        self.assertEqual(agg["overall"]["p95_ms"], ev.percentile([float(i) for i in range(1, 11)], 95))

    def test_bootstrap_ci_present_for_ndcg_and_mrr_only(self):
        rows = [self._row(id="B-001", ndcg_at_10=0.5, mrr=0.5, recall_at_10=0.5)]
        overall = ev.aggregate(rows)["overall"]
        self.assertIn("ci95", overall["ndcg_at_10"])
        self.assertIn("ci95", overall["mrr"])
        self.assertNotIn("ci95", overall["recall_at_10"])


class RunBenchmarkEndToEndTests(unittest.TestCase):
    """Runs the real script against the real (already-imported) snapshot -- no
    network, no importer, no ranking change -- and checks it reproduces itself."""

    def test_rankings_only_reproduces(self):
        queries = [
            {"id": "B-001", "info_need": "N-001", "query": "right to information section 6",
             "intent": "find the provision on transfer of an application", "category": "citation",
             "level": "provision", "scope": "in_corpus", "filters": {}, "split": "dev",
             "origin": "seed:P0-001"},
            {"id": "B-002", "info_need": "N-002", "query": "environment protection national green tribunal",
             "intent": "find the National Green Tribunal provision", "category": "topic",
             "level": "provision", "scope": "in_corpus", "filters": {}, "split": "dev",
             "origin": "seed:P0-002"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            queries_path = tmp / "queries.jsonl"
            queries_path.write_text("\n".join(json.dumps(q) for q in queries) + "\n")
            out1, out2 = tmp / "run1.json", tmp / "run2.json"
            script = ROOT / "scripts" / "run_benchmark.py"

            first = subprocess.run([sys.executable, str(script), "--queries", str(queries_path),
                                    "--rankings-only", "--run-id", "run-test-1", "--out", str(out1)],
                                   cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue(out1.exists())
            data = json.loads(out1.read_text())
            self.assertEqual(len(data["queries"]), 2)
            self.assertIsNone(data["manifest"]["judgments_sha256"])
            self.assertTrue(data["manifest"]["rankings_only"])
            # rti-2005:6 is the expected top result, per tests/test_search.py.
            self.assertEqual(data["queries"][0]["ranking"][:1], ["rti-2005:6"])

            second = subprocess.run([sys.executable, str(script), "--queries", str(queries_path),
                                     "--rankings-only", "--run-id", "run-test-2", "--out", str(out2),
                                     "--compare", str(out1)],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("REPRODUCED", second.stdout)


class PairedNdcgComparisonTests(unittest.TestCase):
    """Hand-checked paired bootstrap. Difference is candidate minus baseline.

    For diffs [0.5, 0.25, 0.0] (id order), seed 0, 8 resamples, random.Random
    draws these index triples and means:

        [1, 1, 0] -> (0.25 + 0.25 + 0.5) / 3 = 1/3
        [1, 2, 1] -> (0.25 + 0.0 + 0.25) / 3 = 1/6
        [1, 1, 1] -> 0.25
        [1, 2, 0] -> (0.25 + 0.0 + 0.5) / 3 = 0.25
        [2, 0, 1] -> (0.0 + 0.5 + 0.25) / 3 = 0.25
        [0, 0, 2] -> (0.5 + 0.5 + 0.0) / 3 = 1/3
        [1, 2, 2] -> (0.25 + 0.0 + 0.0) / 3 = 1/12
        [2, 0, 1] -> 0.25

    Sorted means: 1/12, 1/6, 0.25, 0.25, 0.25, 0.25, 1/3, 1/3.
    Nearest-rank 2.5% is rank ceil(0.025*8)=1, so 1/12 -> 0.083333.
    Nearest-rank 97.5% is rank ceil(0.975*8)=8, so 1/3 -> 0.333333.
    The observed mean is (0.5 + 0.25 + 0.0) / 3 = 0.25.
    """

    def _row(self, qid, split, ndcg):
        return {"id": qid, "split": split, "ndcg_at_10": ndcg}

    def test_hand_checked_interval(self):
        baseline = [self._row("B-001", "test", 0.0), self._row("B-002", "test", 0.0),
                    self._row("B-003", "test", 0.0)]
        candidate = [self._row("B-001", "test", 0.5), self._row("B-002", "test", 0.25),
                     self._row("B-003", "test", 0.0)]
        report = ev.paired_ndcg_comparison(baseline, candidate, resamples=8, seed=0)
        self.assertEqual(report["splits"]["test"]["n"], 3)
        self.assertEqual(report["splits"]["test"]["mean_difference"], 0.25)
        self.assertEqual(report["splits"]["test"]["ci95"], (0.083333, 0.333333))
        self.assertEqual(report["unscored"], [])
        self.assertEqual(report["unpaired"], [])

    def test_identical_scores_are_zero_on_each_split(self):
        rows = [self._row("B-001", "dev", 0.4), self._row("B-002", "dev", 0.9),
                self._row("B-003", "test", 0.1), self._row("B-004", "test", 1.0)]
        report = ev.paired_ndcg_comparison(rows, list(reversed(rows)))
        self.assertEqual(report["resamples"], 1000)
        self.assertEqual(report["seed"], 0)
        for split in ("dev", "test"):
            self.assertEqual(report["splits"][split]["n"], 2)
            self.assertEqual(report["splits"][split]["mean_difference"], 0.0)
            self.assertEqual(report["splits"][split]["ci95"], (0.0, 0.0))

    def test_splits_do_not_share_queries(self):
        # Every dev difference is +0.5, so that interval is [0.5, 0.5] with no draws to check.
        # Every test difference is 0. A gain on dev must not move the test interval.
        baseline = [self._row("D-1", "dev", 0.25), self._row("D-2", "dev", 0.0),
                    self._row("T-1", "test", 0.8), self._row("T-2", "test", 0.2)]
        candidate = [self._row("D-1", "dev", 0.75), self._row("D-2", "dev", 0.5),
                     self._row("T-1", "test", 0.8), self._row("T-2", "test", 0.2)]
        report = ev.paired_ndcg_comparison(baseline, candidate)
        self.assertEqual(report["splits"]["dev"], {"n": 2, "mean_difference": 0.5, "ci95": (0.5, 0.5)})
        self.assertEqual(report["splits"]["test"], {"n": 2, "mean_difference": 0.0, "ci95": (0.0, 0.0)})

    def test_row_order_does_not_change_the_interval(self):
        baseline = [self._row("B-003", "test", 0.0), self._row("B-001", "test", 0.0),
                    self._row("B-002", "test", 0.0)]
        candidate = [self._row("B-002", "test", 0.25), self._row("B-003", "test", 0.0),
                     self._row("B-001", "test", 0.5)]
        report = ev.paired_ndcg_comparison(baseline, candidate, resamples=8, seed=0)
        self.assertEqual(report["splits"]["test"]["mean_difference"], 0.25)
        self.assertEqual(report["splits"]["test"]["ci95"], (0.083333, 0.333333))

    def test_missing_ndcg_and_one_sided_ids_are_left_out(self):
        baseline = [self._row("B-001", "dev", 0.5), self._row("B-002", "dev", None),
                    self._row("B-003", "dev", 0.2), self._row("B-004", "test", 1.0)]
        candidate = [self._row("B-001", "dev", 0.5), self._row("B-002", "dev", None),
                     self._row("B-003", "dev", None), self._row("B-005", "test", 0.4)]
        report = ev.paired_ndcg_comparison(baseline, candidate)
        self.assertEqual(list(report["splits"]), ["dev"])
        self.assertEqual(report["splits"]["dev"]["n"], 1)
        self.assertEqual(report["splits"]["dev"]["mean_difference"], 0.0)
        self.assertEqual(report["unscored"], ["B-002"])
        self.assertEqual(report["unpaired"], [
            {"id": "B-003", "reason": "ndcg_at_10 missing in candidate"},
            {"id": "B-004", "reason": "only in baseline"},
            {"id": "B-005", "reason": "only in candidate"},
        ])

    def test_defaults_are_one_thousand_resamples_seed_zero(self):
        baseline = [self._row("B-001", "dev", 0.0), self._row("B-002", "dev", 0.0),
                    self._row("B-003", "dev", 0.0)]
        candidate = [self._row("B-001", "dev", 0.5), self._row("B-002", "dev", 0.25),
                     self._row("B-003", "dev", 0.0)]
        self.assertEqual(ev.paired_ndcg_comparison(baseline, candidate),
                         ev.paired_ndcg_comparison(baseline, candidate, resamples=1000, seed=0))
        self.assertNotEqual(ev.paired_ndcg_comparison(baseline, candidate),
                            ev.paired_ndcg_comparison(baseline, candidate, resamples=1000, seed=1))

    def test_split_mismatch_and_duplicate_id_raise(self):
        with self.assertRaises(ValueError):
            ev.paired_ndcg_comparison([self._row("B-001", "dev", 0.2)],
                                      [self._row("B-001", "test", 0.2)])
        with self.assertRaises(ValueError):
            ev.paired_ndcg_comparison([self._row("B-001", "dev", 0.2), self._row("B-001", "dev", 0.3)],
                                      [self._row("B-001", "dev", 0.2)])

    def test_cli_compares_a_run_with_itself(self):
        rows = [self._row("B-001", "dev", 0.4), self._row("B-002", "test", 0.8),
                self._row("B-003", "dev", None)]
        script = ROOT / "scripts" / "run_benchmark.py"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.json"
            path.write_text(json.dumps({"queries": rows}) + "\n")
            proc = subprocess.run([sys.executable, str(script), "--baseline", str(path),
                                   "--candidate", str(path)],
                                  cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("1000 resamples, seed 0", proc.stdout)
            self.assertIn("split:dev      n=   1  mean difference=0.000000  95% CI [0.000000, 0.000000]",
                          proc.stdout)
            self.assertIn("split:test     n=   1  mean difference=0.000000  95% CI [0.000000, 0.000000]",
                          proc.stdout)
            self.assertIn("unscored: 1 queries", proc.stdout)
            self.assertNotIn("REPRODUCED", proc.stdout)

            rejected = subprocess.run([sys.executable, str(script), "--baseline", str(path),
                                       "--candidate", str(path), "--out", str(Path(tmp) / "nope.json")],
                                      cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse((Path(tmp) / "nope.json").exists())


if __name__ == "__main__":
    unittest.main()
