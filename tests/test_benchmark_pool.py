"""Tests for scripts/pool_candidates.py, scripts/judging_packets.py,
scripts/show_provision.py and scripts/merge_judgments.py, against small
in-memory fixtures -- never the live Snapshot() or the query set/judgments
the main agent is still writing.
"""
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from lawindex.benchmark import validate_judgments
from lawindex.retrieval import SearchFilters
from scripts import judging_packets as jp
from scripts import merge_judgments as mj
from scripts import pool_candidates as pc
from scripts import show_provision as sp


def record(key, act_slug, act_title, section_number, heading, body_text, footnote_text=None,
           year=None, ministry=None, document_type=None):
    return {"key": key, "act_slug": act_slug, "act_title": act_title, "section_number": section_number,
            "heading": heading, "body_text": body_text, "footnote_text": footnote_text,
            "metadata": {"year": year, "ministry": ministry, "document_type": document_type}}


# Two Acts, a handful of provisions, used across the pooling tests.
RECORDS = {
    "act-a:1": record("act-a:1", "act-a", "Act A", "1", "Penalty for offences",
                       "A person who contravenes shall be liable to penalty.", year="2001", ministry="M1"),
    "act-a:2": record("act-a:2", "act-a", "Act A", "2", "Definitions",
                       "In this Act, unless context otherwise requires, penalty means punishment.",
                       year="2001", ministry="M1"),
    "act-b:1": record("act-b:1", "act-b", "Act B", "1", "Appeals",
                       "An appeal against an order imposing penalty may be filed.", year="2010", ministry="M2"),
}


class TermExtractionTests(unittest.TestCase):
    def test_lowercase_stopwords_digits_dedup_in_order(self):
        terms = pc.extract_terms("The consumer's limitation period, limitation 2005")
        # "s" (from consumer's) and "the" are stopwords; "2005" is a pure digit
        # token; the second "limitation" is a duplicate.
        self.assertEqual(terms, ["consumer", "limitation", "period"])

    def test_no_terms_left(self):
        self.assertEqual(pc.extract_terms("the and of"), [])


class Bm25PoolingTests(unittest.TestCase):
    def setUp(self):
        self.conn = pc.build_search_index(RECORDS)
        self.addCleanup(self.conn.close)

    def test_no_terms_returns_nothing(self):
        self.assertEqual(pc.bm25_rank(self.conn, [], "bm25_fields"), [])

    def test_heading_weighted_method_favours_heading_match_ties_broken_by_key(self):
        # "penalty" is in act-a:1's heading and in the body of the other two;
        # bm25_heading (title 1, heading 5, body 0, footnote 0) scores the
        # other two at zero, tied, broken by key.
        ranked = pc.bm25_rank(self.conn, ["penalty"], "bm25_heading")
        self.assertEqual(ranked, ["act-a:1", "act-a:2", "act-b:1"])

    def test_body_only_method_ignores_heading_match(self):
        ranked = pc.bm25_rank(self.conn, ["penalty"], "bm25_body")
        self.assertEqual(ranked, ["act-a:2", "act-b:1", "act-a:1"])

    def test_fields_method_is_or_of_terms(self):
        ranked = pc.bm25_rank(self.conn, ["penalty", "appeal"], "bm25_fields")
        self.assertEqual(set(ranked), {"act-a:1", "act-a:2", "act-b:1"})
        self.assertEqual(ranked[0], "act-b:1")  # only document with both terms

    def test_and_method_requires_every_term(self):
        ranked = pc.bm25_rank(self.conn, ["penalty", "appeal"], "bm25_and")
        self.assertEqual(ranked, ["act-b:1"])

    def test_filters_applied_before_depth_cut(self):
        ranked = pc.bm25_rank(self.conn, ["penalty"], "bm25_fields")
        filtered = pc.apply_filters(ranked, RECORDS, SearchFilters(act="act-a"), depth=10)
        self.assertEqual(filtered, ["act-a:1", "act-a:2"])

    def test_depth_cut_applied_after_filters(self):
        ranked = pc.bm25_rank(self.conn, ["penalty"], "bm25_fields")
        filtered = pc.apply_filters(ranked, RECORDS, SearchFilters(), depth=2)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered, ranked[:2])


class TfidfTests(unittest.TestCase):
    def test_no_terms_returns_nothing(self):
        self.assertEqual(pc.tfidf_rank(RECORDS, []), [])

    def test_drops_zero_similarity_documents(self):
        docs = {
            "d:1": record("d:1", "x", "X", "1", "", "alpha beta"),
            "d:2": record("d:2", "x", "X", "2", "", "beta gamma"),
            "d:3": record("d:3", "x", "X", "3", "", "gamma delta"),
        }
        # "alpha" appears only in d:1 (df=1 of 3); d:2 and d:3 share no term
        # with the query and must be dropped, not scored zero.
        self.assertEqual(pc.tfidf_rank(docs, ["alpha"]), ["d:1"])

    def test_hand_checked_cosine_ranking(self):
        docs = {
            "d:1": record("d:1", "x", "X", "1", "", "alpha alpha beta"),
            "d:2": record("d:2", "x", "X", "2", "", "alpha beta beta beta"),
            "d:3": record("d:3", "x", "X", "3", "", "gamma delta"),
        }
        # N=3; df(alpha)=df(beta)=2 (present in d:1, d:2), idf = log(3/2).
        # d:1 weights: alpha=2*idf, beta=1*idf -> ||d1||^2 = 5*idf^2, dot = 3*idf^2.
        # d:2 weights: alpha=1*idf, beta=3*idf -> ||d2||^2 = 10*idf^2, dot = 4*idf^2.
        # query weights: alpha=idf, beta=idf -> ||q||^2 = 2*idf^2.
        expected_sim1 = 3 / math.sqrt(10)   # 3*idf^2 / (idf*sqrt(2) * idf*sqrt(5))
        expected_sim2 = 4 / math.sqrt(20)   # 4*idf^2 / (idf*sqrt(2) * idf*sqrt(10))
        self.assertGreater(expected_sim1, expected_sim2)
        self.assertEqual(pc.tfidf_rank(docs, ["alpha", "beta"]), ["d:1", "d:2"])

    def test_ties_broken_by_key(self):
        docs = {
            "d:z": record("d:z", "x", "X", "1", "", "alpha"),
            "d:a": record("d:a", "x", "X", "2", "", "alpha"),
            # A third, alpha-free document keeps idf(alpha) > 0 (otherwise
            # df==N makes idf log(1)==0 and every similarity is legitimately
            # zero, which is a degenerate case, not a tie).
            "d:other": record("d:other", "x", "X", "3", "", "beta"),
        }
        self.assertEqual(pc.tfidf_rank(docs, ["alpha"]), ["d:a", "d:z"])


class JudgingPacketTests(unittest.TestCase):
    def test_shuffle_is_deterministic_per_judge_and_query(self):
        keys = [f"key-{i}" for i in range(8)]
        first = jp.shuffled_keys(keys, "A", "B-001")
        second = jp.shuffled_keys(keys, "A", "B-001")
        self.assertEqual(first, second)
        self.assertEqual(sorted(first), sorted(keys))

    def test_judges_see_different_orders(self):
        keys = [f"key-{i}" for i in range(8)]
        order_a = jp.shuffled_keys(keys, "A", "B-001")
        order_b = jp.shuffled_keys(keys, "B", "B-001")
        self.assertNotEqual(order_a, order_b)

    def test_no_rank_score_or_method_leaks_into_the_packet(self):
        query = {"id": "B-001", "query": "penalty for appeal", "intent": "find the penalty rule", "filters": {}}
        block = jp.render_query_block(query, ["act-a:1", "act-b:1"], RECORDS)
        for leaked in ("rank", "score", "found_by", "bm25", "tfidf"):
            self.assertNotIn(leaked, block.lower())
        self.assertIn("act-a:1", block)
        self.assertIn("Penalty for offences", block)

    def test_filters_shown_when_present(self):
        query = {"id": "B-002", "query": "q", "intent": "i", "filters": {"act": "act-a"}}
        block = jp.render_query_block(query, ["act-a:1"], RECORDS)
        self.assertIn("act-a", block)
        query_no_filters = {"id": "B-003", "query": "q", "intent": "i", "filters": {}}
        block2 = jp.render_query_block(query_no_filters, ["act-a:1"], RECORDS)
        self.assertNotIn("Filters", block2)

    def test_truncation_at_6000_characters(self):
        long_record = dict(RECORDS["act-a:1"])
        long_record["body_text"] = "x" * 7000
        rendered = jp.render_candidate("act-a:1", long_record)
        self.assertIn("[Truncated. Read the rest with: python3 scripts/show_provision.py act-a:1]", rendered)
        body_before_marker = rendered.split("[Truncated")[0]
        self.assertEqual(body_before_marker.count("x"), 6000)

    def test_short_body_not_truncated(self):
        rendered = jp.render_candidate("act-a:1", RECORDS["act-a:1"])
        self.assertNotIn("Truncated", rendered)


class ShowProvisionTests(unittest.TestCase):
    def test_show_keys_unknown_key_is_an_error(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = sp.show_keys(RECORDS, ["act-a:1", "nonexistent:9"], out=out)
        self.assertEqual(code, 1)

    def test_show_keys_prints_full_text(self):
        out = io.StringIO()
        code = sp.show_keys(RECORDS, ["act-a:1"], out=out)
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("Act A", text)
        self.assertIn("Penalty for offences", text)
        self.assertIn("A person who contravenes shall be liable to penalty.", text)

    def test_show_act_lists_sections_in_order(self):
        acts = {"act-a": {"title": "Act A"}, "act-b": {"title": "Act B"}}
        out = io.StringIO()
        code = sp.show_act(RECORDS, acts, "act-a", out=out)
        self.assertEqual(code, 0)
        lines = out.getvalue().splitlines()
        self.assertIn("1\tPenalty for offences", lines)
        self.assertIn("2\tDefinitions", lines)

    def test_show_act_unknown_act_is_an_error(self):
        self.assertEqual(sp.show_act(RECORDS, {"act-a": {"title": "Act A"}}, "nope"), 1)

    def test_grep_matches_heading_or_body_with_snippet(self):
        out = io.StringIO()
        code = sp.show_grep(RECORDS, "appeal", None, out=out)
        self.assertEqual(code, 0)
        self.assertIn("act-b:1", out.getvalue())

    def test_grep_scoped_to_act(self):
        out = io.StringIO()
        sp.show_grep(RECORDS, "penalty", "act-b", out=out)
        self.assertIn("act-b:1", out.getvalue())
        self.assertNotIn("act-a", out.getvalue())


# ---------------------------------------------------------------------------
# merge_judgments.py

def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


FP = "sha256:test-fingerprint"


def expected_for(judge, batch, queries):
    return {"judge": judge, "batch": batch, "corpus_fingerprint": FP, "queries": queries}


class CheckBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.judging = Path(self.tmp.name)
        self.expected_queries = {"B-001": ["act-a:1", "act-a:2"]}
        write_json(self.judging / "packets/A/batch-01.expected.json",
                   expected_for("A", 1, self.expected_queries))

    def good_lines(self):
        return [
            {"kind": "judgment", "query_id": "B-001", "provision_key": "act-a:1", "grade": 3,
             "rationale": "states the rule", "source": "pool"},
            {"kind": "judgment", "query_id": "B-001", "provision_key": "act-a:2", "grade": 0,
             "rationale": "off topic", "source": "pool"},
        ]

    def check(self, lines):
        write_jsonl(self.judging / "raw/A/batch-01.jsonl", lines)
        return mj.check_batch(self.judging, "A", 1, RECORDS)

    def test_ok(self):
        problems, counts = self.check(self.good_lines())
        self.assertEqual(problems, [])
        self.assertEqual(counts, {"judgments": 2, "manual": 0, "unindexed": 0})

    def test_missing_pair_is_a_problem(self):
        problems, _counts = self.check(self.good_lines()[:1])
        self.assertTrue(any("missing pool judgment" in p for p in problems))

    def test_duplicate_pool_pair_is_a_problem(self):
        problems, _counts = self.check(self.good_lines() + [self.good_lines()[0]])
        self.assertTrue(any("duplicate pool judgment" in p for p in problems))

    def test_bad_grade_is_a_problem(self):
        lines = self.good_lines()
        lines[0]["grade"] = 4
        problems, _counts = self.check(lines)
        self.assertTrue(any("grade must be 0-3" in p for p in problems))

    def test_bool_grade_is_a_problem(self):
        lines = self.good_lines()
        lines[0]["grade"] = True
        problems, _counts = self.check(lines)
        self.assertTrue(any("grade must be 0-3" in p for p in problems))

    def test_empty_rationale_is_a_problem(self):
        lines = self.good_lines()
        lines[0]["rationale"] = "   "
        problems, _counts = self.check(lines)
        self.assertTrue(any("rationale required" in p for p in problems))

    def test_manual_key_already_in_pool_is_a_problem(self):
        lines = self.good_lines() + [{"kind": "judgment", "query_id": "B-001", "provision_key": "act-a:1",
                                       "grade": 2, "rationale": "manual re-add", "source": "manual"}]
        problems, _counts = self.check(lines)
        self.assertTrue(any("already in the pool" in p for p in problems))

    def test_repeated_manual_key_is_a_problem(self):
        manual = {"kind": "judgment", "query_id": "B-001", "provision_key": "act-b:1", "grade": 2,
                  "rationale": "found by grep", "source": "manual"}
        problems, _counts = self.check(self.good_lines() + [manual, manual])
        self.assertTrue(any("repeated manual key" in p for p in problems))

    def test_manual_key_not_admitted_is_a_problem(self):
        manual = {"kind": "judgment", "query_id": "B-001", "provision_key": "no-such:1", "grade": 2,
                  "rationale": "found by grep", "source": "manual"}
        problems, _counts = self.check(self.good_lines() + [manual])
        self.assertTrue(any("not an admitted provision" in p for p in problems))

    def test_more_than_five_manual_is_a_problem(self):
        manuals = [{"kind": "judgment", "query_id": "B-001", "provision_key": f"act-b:{i}", "grade": 1,
                    "rationale": "manual", "source": "manual"} for i in range(6)]
        # act-b:0..5 are not admitted, but that is reported too; the count
        # check fires independently.
        problems, counts = self.check(self.good_lines() + manuals)
        self.assertTrue(any("more than five manual" in p for p in problems))
        self.assertEqual(counts["manual"], 6)

    def test_unindexed_target_must_be_non_empty(self):
        lines = self.good_lines() + [{"kind": "unindexed_target", "query_id": "B-001", "target": "  ",
                                       "rationale": "held back"}]
        problems, _counts = self.check(lines)
        self.assertTrue(any("target must be non-empty" in p for p in problems))

    def test_unindexed_target_ok(self):
        lines = self.good_lines() + [{"kind": "unindexed_target", "query_id": "B-001",
                                       "target": "Some Rules, 2015", "rationale": "held back"}]
        problems, counts = self.check(lines)
        self.assertEqual(problems, [])
        self.assertEqual(counts["unindexed"], 1)

    def test_missing_files_are_reported(self):
        problems, _counts = mj.check_batch(self.judging, "B", 1, RECORDS)
        self.assertTrue(any("missing" in p for p in problems))


class AgreementTests(unittest.TestCase):
    def test_hand_computed_kappa_table(self):
        # (grade_a, grade_b): (3,3) agree-relevant, (0,0) agree-not-relevant,
        # (2,0) disagree across the line, (1,2) disagree across the line.
        # By hand: po=0.5, p_yes_a=p_yes_b=0.5, pe=0.5, kappa=(po-pe)/(1-pe)=0.
        pool_grades = {
            ("B-001", "k1"): {"A": (3, "ra1"), "B": (3, "rb1")},
            ("B-001", "k2"): {"A": (0, "ra2"), "B": (0, "rb2")},
            ("B-002", "k3"): {"A": (2, "ra3"), "B": (0, "rb3")},
            ("B-002", "k4"): {"A": (1, "ra4"), "B": (2, "rb4")},
        }
        query_category = {"B-001": "topic", "B-002": "citation"}
        agreement = mj.compute_agreement(pool_grades, query_category)
        overall = agreement["overall"]
        self.assertEqual(overall["pairs"], 4)
        self.assertAlmostEqual(overall["exact_agreement"], 0.5)
        self.assertAlmostEqual(overall["within_one_agreement"], 0.75)
        self.assertAlmostEqual(overall["kappa"], 0.0)
        self.assertAlmostEqual(agreement["by_category"]["topic"]["kappa"], 1.0)
        self.assertAlmostEqual(agreement["by_category"]["citation"]["kappa"], -1.0)

    def test_empty_is_none(self):
        stats = mj.compute_agreement({}, {})
        self.assertEqual(stats["overall"]["pairs"], 0)
        self.assertIsNone(stats["overall"]["kappa"])


class MergeJudgmentsTests(unittest.TestCase):
    """End-to-end merge over a small two-query, two-batch-free pool."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.judging = Path(self.tmp.name)
        self.records = dict(RECORDS)
        self.records["act-b:2"] = record("act-b:2", "act-b", "Act B", "2", "Powers of the appellate authority",
                                          "The appellate authority may confirm, modify or set aside the order.",
                                          year="2010")
        self.records["act-b:3"] = record("act-b:3", "act-b", "Act B", "3", "Penalties",
                                          "A penalty may also be imposed under this section.", year="2010")
        self.queries = [
            {"id": "B-001", "level": "provision", "category": "topic"},
            {"id": "B-002", "level": "provision", "category": "citation"},
        ]
        expected_queries = {"B-001": ["act-a:1", "act-a:2"], "B-002": ["act-b:1", "act-b:2"]}
        for judge in ("A", "B"):
            write_json(self.judging / f"packets/{judge}/batch-01.expected.json",
                       expected_for(judge, 1, expected_queries))

        judge_a_lines = [
            {"kind": "judgment", "query_id": "B-001", "provision_key": "act-a:1", "grade": 3,
             "rationale": "A: answers directly", "source": "pool"},
            {"kind": "judgment", "query_id": "B-001", "provision_key": "act-a:2", "grade": 0,
             "rationale": "A: off topic", "source": "pool"},
            {"kind": "judgment", "query_id": "B-002", "provision_key": "act-b:1", "grade": 2,
             "rationale": "A: relevant", "source": "pool"},
            {"kind": "judgment", "query_id": "B-002", "provision_key": "act-b:2", "grade": 1,
             "rationale": "A: marginal", "source": "pool"},
            {"kind": "judgment", "query_id": "B-002", "provision_key": "act-b:3", "grade": 2,
             "rationale": "A: manual add, relevant", "source": "manual"},
            {"kind": "unindexed_target", "query_id": "B-001", "target": "Some Rules, 2015",
             "rationale": "A: held back"},
        ]
        judge_b_lines = [
            {"kind": "judgment", "query_id": "B-001", "provision_key": "act-a:1", "grade": 3,
             "rationale": "B: agrees", "source": "pool"},
            {"kind": "judgment", "query_id": "B-001", "provision_key": "act-a:2", "grade": 1,
             "rationale": "B: marginal not zero", "source": "pool"},
            {"kind": "judgment", "query_id": "B-002", "provision_key": "act-b:1", "grade": 0,
             "rationale": "B: not relevant", "source": "pool"},
            {"kind": "judgment", "query_id": "B-002", "provision_key": "act-b:2", "grade": 2,
             "rationale": "B: relevant not marginal", "source": "pool"},
        ]
        write_jsonl(self.judging / "raw/A/batch-01.jsonl", judge_a_lines)
        write_jsonl(self.judging / "raw/B/batch-01.jsonl", judge_b_lines)

    def test_incomplete_without_adjudication_file(self):
        with self.assertRaises(mj.MergeIncomplete) as ctx:
            mj.merge_judgments(self.judging, self.judging / "judgments.v1.jsonl", self.queries, self.records)
        self.assertEqual(ctx.exception.remaining, 3)
        # Side files are still written so the main agent can adjudicate.
        self.assertTrue((self.judging / "to_adjudicate.jsonl").exists())
        self.assertTrue((self.judging / "agreement.json").exists())
        self.assertTrue((self.judging / "unindexed_targets.json").exists())
        to_adjudicate = [json.loads(line) for line in
                          (self.judging / "to_adjudicate.jsonl").read_text().splitlines()]
        pairs = [(row["query_id"], row["provision_key"]) for row in to_adjudicate]
        self.assertEqual(pairs, [("B-002", "act-b:1"), ("B-002", "act-b:2"), ("B-002", "act-b:3")])
        manual_row = next(r for r in to_adjudicate if r["provision_key"] == "act-b:3")
        self.assertEqual(manual_row["source"], "manual")
        self.assertIsNone(manual_row["grade_b"])
        self.assertEqual(manual_row["grade_a"], 2)

    def test_incomplete_with_partial_adjudication(self):
        write_jsonl(self.judging / "adjudication.jsonl", [
            {"query_id": "B-002", "provision_key": "act-b:1", "grade": 2, "rationale": "adjudicated: relevant"},
        ])
        with self.assertRaises(mj.MergeIncomplete) as ctx:
            mj.merge_judgments(self.judging, self.judging / "judgments.v1.jsonl", self.queries, self.records)
        self.assertEqual(ctx.exception.remaining, 2)

    def test_complete_adjudication_writes_valid_judgments(self):
        write_jsonl(self.judging / "adjudication.jsonl", [
            {"query_id": "B-002", "provision_key": "act-b:1", "grade": 2, "rationale": "adjudicated: relevant"},
            {"query_id": "B-002", "provision_key": "act-b:2", "grade": 1, "rationale": "adjudicated: marginal"},
            {"query_id": "B-002", "provision_key": "act-b:3", "grade": 2, "rationale": "adjudicated: manual ok"},
        ])
        out_path = self.judging / "judgments.v1.jsonl"
        judgments = mj.merge_judgments(self.judging, out_path, self.queries, self.records)
        self.assertEqual(len(judgments), 5)
        self.assertTrue(out_path.exists())

        by_pair = {(j["query_id"], j["provision_key"]): j for j in judgments}
        agreed = by_pair[("B-001", "act-a:1")]
        self.assertEqual(agreed["resolution"], "agreed")
        self.assertEqual(agreed["grade"], 3)
        self.assertEqual(agreed["rationale"], "A: answers directly")

        lowered = by_pair[("B-001", "act-a:2")]
        self.assertEqual(lowered["resolution"], "lower_of_adjacent")
        self.assertEqual(lowered["grade"], 0)  # min(0, 1)
        self.assertEqual(lowered["rationale"], "A: off topic")  # judge A's rationale

        adjudicated_pool = by_pair[("B-002", "act-b:1")]
        self.assertEqual(adjudicated_pool["resolution"], "adjudicated")
        self.assertEqual(adjudicated_pool["grade"], 2)
        self.assertEqual(adjudicated_pool["grades"], {"A": 2, "B": 0})

        adjudicated_manual = by_pair[("B-002", "act-b:3")]
        self.assertEqual(adjudicated_manual["source"], "manual")
        self.assertEqual(adjudicated_manual["resolution"], "adjudicated")
        self.assertEqual(adjudicated_manual["grades"], {"A": 2})

        # Re-validate independently, as the real merge protocol would.
        validate_judgments(judgments, self.queries, records=self.records, fingerprint=FP)
        for j in judgments:
            self.assertEqual(j["corpus_fingerprint"], FP)
            self.assertEqual(j["reviewer_type"], "ai_model")

    def test_batches_that_fail_check_block_merge(self):
        write_jsonl(self.judging / "raw/A/batch-01.jsonl", [
            {"kind": "judgment", "query_id": "B-001", "provision_key": "act-a:1", "grade": 9,
             "rationale": "bad grade", "source": "pool"},
        ])
        with self.assertRaises(ValueError):
            mj.merge_judgments(self.judging, self.judging / "out.jsonl", self.queries, self.records)


if __name__ == "__main__":
    unittest.main()
