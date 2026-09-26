"""Adoption report against docs/phase-4/TARGETS.md. Synthetic runs, no network."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lawindex.adoption import FLOORS, adoption_report, format_adoption_report

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data" / "benchmark" / "runs" / "baseline-lexical-v1.json"
SCRIPT = ROOT / "scripts" / "run_benchmark.py"


def _metric(mean, n=10):
    return {"mean": mean, "n": n}


def _aggregate(test_ndcg, mrr=0.70, mrr_doc=0.90, judged_test=1.0, judged_dev=1.0,
               false_notice=0.05, notice_recall=0.70, categories=None):
    if categories is None:
        categories = {"category:topic": (0.80, 8), "category:small": (0.90, 7)}
    aggregate = {
        "split:test": {
            "ndcg_at_10": _metric(test_ndcg),
            "mrr": _metric(mrr),
            "mrr_doc": _metric(mrr_doc),
            "judged_at_10": _metric(judged_test),
        },
        "split:dev": {"judged_at_10": _metric(judged_dev)},
        "overall": {
            "false_notice_rate": _metric(false_notice),
            "notice_recall": _metric(notice_recall),
        },
    }
    for name, (mean, n) in categories.items():
        aggregate[name] = {"ndcg_at_10": _metric(mean, n)}
    return aggregate


def _queries(test_score, doc_success=1.0, doc_count=13, omit_one_success=False):
    rows = [{"id": f"qq-scored-{i}", "split": "test", "level": "provision",
             "ndcg_at_10": test_score} for i in range(3)]
    for i in range(doc_count):
        rows.append({"id": f"qq-doc-{i}", "split": "test" if i % 2 else "dev",
                     "level": "document", "ndcg_at_10": None,
                     "success_at_1_doc": doc_success})
    if omit_one_success:
        del rows[-1]["success_at_1_doc"]
    return rows


def _runs(base_ndcg=0.60, cand_ndcg=0.64, base_score=0.50, cand_score=0.54,
          doc_count=13, doc_success=1.0, omit_one_success=False, categories=None, **cand_metrics):
    baseline = {"aggregate": _aggregate(base_ndcg, categories=categories),
                "queries": _queries(base_score, doc_count=doc_count)}
    candidate = {"aggregate": _aggregate(cand_ndcg, categories=categories, **cand_metrics),
                 "queries": _queries(cand_score, doc_success=doc_success, doc_count=doc_count,
                                     omit_one_success=omit_one_success)}
    return baseline, candidate


def _by(report, name):
    found = [check for check in report["checks"] if check["name"] == name]
    if len(found) != 1:
        raise AssertionError(f"{name}: {len(found)} checks")
    return found[0]


class AdoptionReportTests(unittest.TestCase):
    def test_floor_numbers_match_targets(self):
        self.assertEqual(FLOORS, {
            "ndcg_gain": 0.03,
            "ndcg_at_10": 0.63,
            "mrr": 0.69,
            "mrr_doc": 0.88,
            "document_queries": 13,
            "false_notice_rate": 0.10,
            "notice_recall": 0.68,
            "category_min_n": 8,
            "category_max_loss": 0.05,
            "judged_at_10": 0.9,
        })

    def test_all_conditions_pass(self):
        baseline, candidate = _runs()
        documents = [row for row in candidate["queries"] if row["level"] == "document"]
        self.assertEqual({row["split"] for row in documents}, {"dev", "test"})
        report = adoption_report(baseline, candidate)
        self.assertEqual(report["verdict"], "ALL CONDITIONS MET")
        self.assertTrue(all(check["passed"] and not check["missing"] for check in report["checks"]))
        self.assertEqual(_by(report, "ndcg_gain")["value"], 0.04)
        self.assertEqual(_by(report, "ndcg_gain")["threshold"], ">= 0.03")
        self.assertEqual(_by(report, "paired_ci")["value"], (0.04, 0.04))
        self.assertEqual(_by(report, "document_first_act")["value"], {"successes": 13, "rows": 13})
        names = [check["name"] for check in report["checks"]]
        self.assertIn("category:topic", names)
        self.assertNotIn("category:small", names)
        text = format_adoption_report(report)
        self.assertTrue(text.endswith("ALL CONDITIONS MET"))
        self.assertNotIn("NOT MET", text)
        for row in candidate["queries"]:
            self.assertNotIn(row["id"], text)

    def test_gain_passes_at_0_03_and_fails_below(self):
        report = adoption_report(*_runs(base_ndcg=0.60, cand_ndcg=0.63))
        self.assertEqual(_by(report, "ndcg_gain")["value"], 0.03)
        self.assertTrue(_by(report, "ndcg_gain")["passed"])
        self.assertEqual(report["verdict"], "ALL CONDITIONS MET")

        report = adoption_report(*_runs(base_ndcg=0.70, cand_ndcg=0.72))
        self.assertEqual(_by(report, "ndcg_gain")["value"], 0.02)
        self.assertFalse(_by(report, "ndcg_gain")["passed"])
        self.assertFalse(_by(report, "ndcg_gain")["missing"])
        self.assertEqual(report["verdict"], "NOT MET: ndcg_gain")

    def test_ndcg_floor_is_the_candidate_mean(self):
        report = adoption_report(*_runs(base_ndcg=0.50, cand_ndcg=0.63))
        self.assertTrue(_by(report, "ndcg_at_10")["passed"])
        self.assertTrue(_by(report, "ndcg_gain")["passed"])

        report = adoption_report(*_runs(base_ndcg=0.50, cand_ndcg=0.62))
        self.assertFalse(_by(report, "ndcg_at_10")["passed"])
        self.assertEqual(_by(report, "ndcg_at_10")["value"], 0.62)
        self.assertTrue(_by(report, "ndcg_gain")["passed"])
        self.assertEqual(report["verdict"], "NOT MET: ndcg_at_10")

    def test_interval_above_zero_passes_and_touching_zero_fails(self):
        report = adoption_report(*_runs(base_score=0.50, cand_score=0.50))
        check = _by(report, "paired_ci")
        self.assertEqual(check["value"], (0.0, 0.0))
        self.assertFalse(check["passed"])
        self.assertFalse(check["missing"])
        self.assertTrue(_by(report, "ndcg_gain")["passed"])
        self.assertEqual(report["verdict"], "NOT MET: paired_ci")

        report = adoption_report(*_runs(base_score=0.50, cand_score=0.40))
        self.assertEqual(_by(report, "paired_ci")["value"], (-0.1, -0.1))
        self.assertFalse(_by(report, "paired_ci")["passed"])

    def test_interval_missing_when_the_test_split_cannot_be_paired(self):
        baseline, candidate = _runs()
        for row in candidate["queries"]:
            if row["level"] == "provision":
                row["ndcg_at_10"] = None
        report = adoption_report(baseline, candidate)
        check = _by(report, "paired_ci")
        self.assertTrue(check["missing"])
        self.assertFalse(check["passed"])
        self.assertIn("paired_ci: value=missing threshold=both ends > 0 fail",
                      format_adoption_report(report))
        self.assertEqual(report["verdict"], "NOT MET: paired_ci")

    def test_floors_pass_on_the_boundary_and_fail_past_it(self):
        cases = [
            ("mrr", "split:test", "mrr", 0.69, True),
            ("mrr", "split:test", "mrr", 0.68, False),
            ("mrr_doc", "split:test", "mrr_doc", 0.88, True),
            ("mrr_doc", "split:test", "mrr_doc", 0.87, False),
            ("false_notice_rate", "overall", "false_notice_rate", 0.10, True),
            ("false_notice_rate", "overall", "false_notice_rate", 0.11, False),
            ("notice_recall", "overall", "notice_recall", 0.68, True),
            ("notice_recall", "overall", "notice_recall", 0.67, False),
            ("judged_at_10:dev", "split:dev", "judged_at_10", 0.9, True),
            ("judged_at_10:dev", "split:dev", "judged_at_10", 0.89, False),
            ("judged_at_10:test", "split:test", "judged_at_10", 0.9, True),
            ("judged_at_10:test", "split:test", "judged_at_10", 0.89, False),
        ]
        for name, group, metric, mean, expect_pass in cases:
            with self.subTest(name=name, mean=mean):
                baseline, candidate = _runs()
                candidate["aggregate"][group][metric]["mean"] = mean
                report = adoption_report(baseline, candidate)
                check = _by(report, name)
                self.assertEqual(check["passed"], expect_pass)
                self.assertFalse(check["missing"])
                if expect_pass:
                    self.assertEqual(report["verdict"], "ALL CONDITIONS MET")
                else:
                    self.assertEqual(report["verdict"], f"NOT MET: {name}")

    def test_document_floor_requires_13_of_13(self):
        report = adoption_report(*_runs(doc_count=12))
        self.assertEqual(_by(report, "document_first_act")["value"], {"successes": 12, "rows": 12})
        self.assertFalse(_by(report, "document_first_act")["passed"])
        self.assertEqual(report["verdict"], "NOT MET: document_first_act")

        report = adoption_report(*_runs(doc_count=14))
        self.assertEqual(_by(report, "document_first_act")["value"], {"successes": 14, "rows": 14})
        self.assertFalse(_by(report, "document_first_act")["passed"])

        baseline, candidate = _runs()
        candidate["queries"][-1]["success_at_1_doc"] = 0.0
        report = adoption_report(baseline, candidate)
        self.assertEqual(_by(report, "document_first_act")["value"], {"successes": 12, "rows": 13})
        self.assertFalse(_by(report, "document_first_act")["passed"])
        self.assertFalse(_by(report, "document_first_act")["missing"])

        report = adoption_report(*_runs(doc_count=0))
        self.assertEqual(_by(report, "document_first_act")["value"], {"successes": 0, "rows": 0})
        self.assertFalse(_by(report, "document_first_act")["missing"])
        self.assertFalse(_by(report, "document_first_act")["passed"])

    def test_category_at_eight_is_checked_and_below_eight_is_ignored(self):
        baseline, candidate = _runs()
        candidate["aggregate"]["category:topic"]["ndcg_at_10"]["mean"] = 0.75
        candidate["aggregate"]["category:small"]["ndcg_at_10"]["mean"] = 0.10
        report = adoption_report(baseline, candidate)
        self.assertEqual(_by(report, "category:topic")["value"], -0.05)
        self.assertTrue(_by(report, "category:topic")["passed"])
        self.assertNotIn("category:small", [check["name"] for check in report["checks"]])
        self.assertEqual(report["verdict"], "ALL CONDITIONS MET")

        baseline, candidate = _runs()
        candidate["aggregate"]["category:topic"]["ndcg_at_10"]["mean"] = 0.74
        candidate["aggregate"]["category:small"]["ndcg_at_10"]["mean"] = 0.10
        report = adoption_report(baseline, candidate)
        self.assertEqual(_by(report, "category:topic")["value"], -0.06)
        self.assertFalse(_by(report, "category:topic")["passed"])
        self.assertNotIn("category:small", [check["name"] for check in report["checks"]])
        self.assertEqual(report["verdict"], "NOT MET: category:topic")

        baseline, candidate = _runs()
        for run, acronym, topic in ((baseline, 0.80, 0.80), (candidate, 0.70, 0.70)):
            run["aggregate"]["category:acronym"] = {"ndcg_at_10": {"mean": acronym, "n": 8}}
            run["aggregate"]["category:topic"]["ndcg_at_10"]["mean"] = topic
        report = adoption_report(baseline, candidate)
        self.assertEqual(report["verdict"], "NOT MET: category:acronym, category:topic")

    def test_missing_values_fail_and_say_so(self):
        baseline, candidate = _runs()
        baseline["aggregate"]["split:test"]["ndcg_at_10"]["mean"] = None
        report = adoption_report(baseline, candidate)
        self.assertTrue(_by(report, "ndcg_gain")["missing"])
        self.assertFalse(_by(report, "ndcg_gain")["passed"])
        self.assertTrue(_by(report, "ndcg_at_10")["passed"])
        self.assertIn("ndcg_gain: value=missing threshold=>= 0.03 fail",
                      format_adoption_report(report))
        self.assertEqual(report["verdict"], "NOT MET: ndcg_gain")

        baseline, candidate = _runs(omit_one_success=True)
        report = adoption_report(baseline, candidate)
        self.assertTrue(_by(report, "document_first_act")["missing"])
        self.assertIn("document_first_act: value=missing threshold=13 of 13 fail",
                      format_adoption_report(report))
        self.assertEqual(report["verdict"], "NOT MET: document_first_act")

        baseline, candidate = _runs()
        del candidate["aggregate"]["category:topic"]
        report = adoption_report(baseline, candidate)
        self.assertTrue(_by(report, "category:topic")["missing"])
        self.assertNotIn("category:small", [check["name"] for check in report["checks"]])
        self.assertEqual(report["verdict"], "NOT MET: category:topic")

        baseline, candidate = _runs()
        baseline["aggregate"]["category:topic"]["ndcg_at_10"].pop("n")
        report = adoption_report(baseline, candidate)
        self.assertTrue(_by(report, "category:topic")["missing"])
        self.assertEqual(report["verdict"], "NOT MET: category:topic")


class AdoptionCliTests(unittest.TestCase):
    def test_adoption_requires_both_run_files(self):
        alone = subprocess.run([sys.executable, str(SCRIPT), "--adoption"],
                               cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(alone.returncode, 0)
        self.assertIn("valid only together with --baseline and --candidate", alone.stderr)
        self.assertNotIn("ALL CONDITIONS MET", alone.stdout)
        self.assertNotIn("NOT MET", alone.stdout)

        baseline_only = subprocess.run(
            [sys.executable, str(SCRIPT), "--adoption", "--baseline", str(BASELINE)],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(baseline_only.returncode, 0)
        self.assertIn("valid only together with --baseline and --candidate", baseline_only.stderr)

        combined = subprocess.run(
            [sys.executable, str(SCRIPT), "--baseline", str(BASELINE), "--candidate", str(BASELINE),
             "--adoption", "--out", "/tmp/lawindex-g1-should-not-exist.json"],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(combined.returncode, 0)
        self.assertIn("do not combine it with a new run", combined.stderr)
        self.assertFalse(Path("/tmp/lawindex-g1-should-not-exist.json").exists())

    def test_adoption_prints_no_query_ids(self):
        shared = {"id": "qq-held-7f3a", "split": "test", "level": "provision", "ndcg_at_10": 0.5}
        extra = {"id": "qq-only-candidate-9c1e", "split": "test", "level": "provision", "ndcg_at_10": 0.2}
        with tempfile.TemporaryDirectory() as tmp:
            baseline = Path(tmp) / "baseline.json"
            candidate = Path(tmp) / "candidate.json"
            baseline.write_text(json.dumps({"queries": [shared], "aggregate": {}}) + "\n")
            candidate.write_text(json.dumps({"queries": [shared, extra], "aggregate": {}}) + "\n")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--baseline", str(baseline), "--candidate", str(candidate),
                 "--adoption"],
                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("unpaired: 1 queries", proc.stdout)
        self.assertNotIn("qq-held-7f3a", proc.stdout)
        self.assertNotIn("qq-only-candidate-9c1e", proc.stdout)

    def test_real_baseline_against_itself(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--baseline", str(BASELINE), "--candidate", str(BASELINE),
             "--adoption"],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("1000 resamples, seed 0", proc.stdout)
        expected = [
            "ndcg_gain: value=0.000000 threshold=>= 0.03 fail",
            "paired_ci: value=[0.000000, 0.000000] threshold=both ends > 0 fail",
            "ndcg_at_10: value=0.651230 threshold=>= 0.63 pass",
            "mrr: value=0.709605 threshold=>= 0.69 pass",
            "mrr_doc: value=0.904570 threshold=>= 0.88 pass",
            "document_first_act: value=13 of 13 threshold=13 of 13 pass",
            "false_notice_rate: value=0.066667 threshold=<= 0.10 pass",
            "notice_recall: value=0.684211 threshold=>= 0.68 pass",
            "category:acronym: value=0.000000 threshold=>= -0.05 pass",
            "category:broad_discovery: value=0.000000 threshold=>= -0.05 pass",
            "category:citation: value=0.000000 threshold=>= -0.05 pass",
            "category:filtered: value=0.000000 threshold=>= -0.05 pass",
            "category:ordinary_language: value=0.000000 threshold=>= -0.05 pass",
            "category:terminology_mismatch: value=0.000000 threshold=>= -0.05 pass",
            "category:topic: value=0.000000 threshold=>= -0.05 pass",
            "judged_at_10:dev: value=1.000000 threshold=>= 0.9 pass",
            "judged_at_10:test: value=1.000000 threshold=>= 0.9 pass",
            "NOT MET: ndcg_gain, paired_ci",
        ]
        for line in expected:
            self.assertIn(line, proc.stdout)
        self.assertNotIn("category:exact_title", proc.stdout)
        self.assertNotIn("category:out_of_corpus", proc.stdout)
        self.assertNotIn("ALL CONDITIONS MET", proc.stdout)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(lines[-1], "NOT MET: ndcg_gain, paired_ci")
        self.assertLess(len(lines), 40)


if __name__ == "__main__":
    unittest.main()
