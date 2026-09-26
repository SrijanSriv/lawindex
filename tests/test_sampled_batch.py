"""Sampled-batch tooling: deterministic selection, enforced coverage, and a
sample that is always presented as a sample.

The plan is the authorization; the importer is still the only writer. These
tests exercise the tooling end to end on a synthetic Act so they never depend
on how much of the real corpus happens to be admitted.
"""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import offline_importer as oi
from scripts import record_sample_review as rsr
from scripts import sample_review_plan as srp
from scripts import phase3_candidates as pc
from scripts import sampled_agreement as sa
from lawindex.search import ROOT, Snapshot, review_basis

PLAN = ROOT / 'data/phase3/review-plans/rti-2005.json'


class PlanSelectionTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(PLAN.read_text())

    def test_selection_is_deterministic_and_cannot_be_re_rolled(self):
        again = srp.build_plan('rti-2005')
        self.assertEqual(again['seed'], self.plan['seed'])
        self.assertEqual(again['selected_keys'], self.plan['selected_keys'])
        self.assertEqual(srp.build_plan('rti-2005')['selected_keys'], again['selected_keys'])
        # The seed is a function of hash-bound inputs only.
        self.assertEqual(again['seed'], srp.sha(
            (srp.PLANNER_VERSION + '|rti-2005|' + again['candidates_sha256']).encode()))

    def test_every_risk_case_is_mandatory_and_every_stratum_is_sampled(self):
        mandatory = set(self.plan['mandatory_keys'])
        for entry in self.plan['population']:
            risky = entry['has_footnote'] or entry['page_break_gap_count']
            self.assertEqual(entry['key'] in mandatory, bool(risky), entry['key'])
        strata = {e['stratum'] for e in self.plan['population'] if e['key'] not in mandatory}
        self.assertEqual(set(self.plan['strata']), strata)
        for name, group in self.plan['strata'].items():
            self.assertGreaterEqual(group['sampled'], min(group['population'], srp.SAMPLE_FLOOR))
            self.assertTrue(set(group['keys']) <= set(self.plan['selected_keys']))
        self.assertEqual(set(self.plan['selected_keys']),
                         mandatory | {k for g in self.plan['strata'].values() for k in g['keys']})
        # A sample is a sample: some aligned provision is deliberately unseen.
        self.assertLess(len(self.plan['selected_keys']), self.plan['population_count'])

    def test_population_is_only_aligned_candidates_with_their_digests(self):
        report = json.loads((ROOT / 'data/phase3/candidates/rti-2005.json').read_text())
        aligned = {c['key']: c for c in report['candidates'] if c['status'] in srp.ALIGNED}
        self.assertEqual({e['key'] for e in self.plan['population']}, set(aligned))
        for entry in self.plan['population']:
            self.assertEqual(entry['body_text_sha256'], aligned[entry['key']]['body_text_sha256'])
        self.assertEqual(srp.sha(srp.canonical(report).encode()), self.plan['candidates_sha256'])


class RecordReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data/phase3/review-plans').mkdir(parents=True)
        (self.root / 'data/review').mkdir(parents=True)
        self.plan = json.loads(PLAN.read_text())
        self.reviewer_ref = 'data/review/reviewer-phase3-sampled-2026-09-22.json'
        shutil.copy(ROOT / self.reviewer_ref, self.root / self.reviewer_ref)
        self.plan['review'], self.plan['status'] = None, 'awaiting_review'
        srp.plan_path('rti-2005', self.root).write_text(json.dumps(self.plan))
        self.good = {k: {'decision': 'verified_equivalent', 'note': 'checked'}
                     for k in self.plan['selected_keys']}

    def record(self, outcomes):
        return rsr.record('rti-2005', outcomes, self.reviewer_ref, '2026-09-22', 'note', self.root)

    def test_passing_review_records_outcomes_and_evidence(self):
        plan = self.record(self.good)
        self.assertEqual(plan['review']['decision'], 'act_batch_admitted')
        self.assertEqual(plan['status'], 'reviewed')
        self.assertEqual(set(plan['review']['outcomes']), set(self.plan['selected_keys']))
        self.assertEqual(plan['review']['render_evidence'], self.plan['render_sha256'])
        self.assertIn('not looked at individually', plan['review']['scope_note'])

    def test_incomplete_unknown_or_unexplained_outcomes_are_refused(self):
        partial = dict(self.good)
        partial.pop(self.plan['selected_keys'][0])
        for outcomes in [partial, {**self.good, 'rti-2005:99': {'decision': 'verified_equivalent', 'note': 'x'}},
                         {**self.good, self.plan['selected_keys'][0]: {'decision': 'looks_fine', 'note': 'x'}},
                         {**self.good, self.plan['selected_keys'][0]: {'decision': 'verified_equivalent'}}]:
            with self.assertRaises(ValueError):
                self.record(outcomes)

    def test_one_discrepancy_rejects_the_whole_act_batch(self):
        outcomes = dict(self.good)
        failing = self.plan['selected_keys'][2]
        outcomes[failing] = {'decision': 'discrepancy', 'note': 'heading absorbed'}
        plan = self.record(outcomes)
        self.assertEqual(plan['review']['decision'], 'act_batch_rejected')
        self.assertEqual(plan['review']['failed_keys'], [failing])
        with self.assertRaises(ValueError):
            srp.check_authorizes(plan, self.plan['population'][0]['key'], 'x', None)

    def test_a_recorded_review_is_not_silently_replaced(self):
        self.record(self.good)
        with self.assertRaises(ValueError):
            self.record(self.good)


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(PLAN.read_text())
        self.entry = next(e for e in self.plan['population'] if e['key'] not in self.plan['selected_keys'])

    def authorize(self, plan=None):
        plan = plan or self.plan
        return srp.check_authorizes(plan, self.entry['key'],
                                    self.entry['body_text_sha256'], self.entry['footnote_text_sha256'])

    def test_a_passing_plan_authorizes_its_whole_population(self):
        self.assertEqual(self.authorize()['key'], self.entry['key'])
        for entry in self.plan['population']:
            srp.check_authorizes(self.plan, entry['key'], entry['body_text_sha256'], entry['footnote_text_sha256'])

    def test_unknown_provisions_changed_digests_and_stale_versions_are_refused(self):
        with self.assertRaises(ValueError):
            srp.check_authorizes(self.plan, 'rti-2005:999', 'x', None)
        with self.assertRaises(ValueError):
            srp.check_authorizes(self.plan, self.entry['key'], '0' * 64, self.entry['footnote_text_sha256'])
        for field, value in [('planner_version', 'other'), ('parser_version', 'older'), ('status', 'awaiting_review')]:
            plan = copy.deepcopy(self.plan)
            plan[field] = value
            with self.assertRaises(ValueError):
                self.authorize(plan)


class SampledAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reviews = {k: r for k, r in oi.load_review_records().items()
                       if r['extraction_method_version'] == oi.SAMPLED_AGREEMENT_VERSION}
        # Each record states whether it was one of its own Act's sampled
        # sections; never infer that from some other Act's plan.
        cls.unsampled = next(k for k, r in sorted(cls.reviews.items())
                             if not r['review']['visually_reviewed'] and r['agreement']['normalizations'])
        cls.sampled = next(k for k, r in sorted(cls.reviews.items()) if r['review']['visually_reviewed'])

    def raw_for(self, review):
        return {name: oi.load_capture_bytes(name) for name in
                (review['source_representation']['capture'], review['pdf_anchor']['capture'])}

    def test_both_sampled_and_unsampled_provisions_admit_and_declare_their_basis(self):
        for key, individually in [(self.sampled, True), (self.unsampled, False)]:
            review = self.reviews[key]
            built = oi.build_provision_record(review, self.raw_for(review))
            self.assertEqual(built['admission_status'], 'admitted', key)
            self.assertEqual(built['extraction_method_version'], oi.SAMPLED_AGREEMENT_VERSION)
            basis = review_basis(review)
            self.assertEqual(basis['review_class'], sa.REVIEW_CLASS)
            self.assertIs(basis['individually_reviewed'], individually)
            self.assertLess(basis['sampled_count'], basis['sample_population'])

    def test_normalization_claims_must_match_the_ladder_and_the_pdf(self):
        review = copy.deepcopy(self.reviews[self.unsampled])
        review['agreement']['normalizations'] = ['quote']       # not a ladder prefix
        with self.assertRaises(ValueError):
            oi.build_provision_record(review, self.raw_for(review))
        review = copy.deepcopy(self.reviews[self.unsampled])
        review['agreement']['normalization_level'] = len(pc.NORMALIZATION_NAMES) + 5
        with self.assertRaises(ValueError):
            oi.build_provision_record(review, self.raw_for(review))
        review = copy.deepcopy(self.reviews[self.unsampled])
        review['pdf_anchor']['pdf_page_from'] += 1
        with self.assertRaises(ValueError):
            oi.build_provision_record(review, self.raw_for(review))

    def test_changed_source_still_invalidates_without_storing_text(self):
        review = self.reviews[self.unsampled]
        raw = self.raw_for(review)
        raw[review['source_representation']['capture']] += b' '
        built = oi.build_provision_record(review, raw)
        self.assertEqual(built['admission_status'], 'invalidated_source_changed')
        self.assertIsNone(built['body_text'])

    def test_search_marks_unsampled_provisions_and_the_corpus_stays_consistent(self):
        snapshot = Snapshot(ROOT)
        served = snapshot.records[self.unsampled]['review']
        self.assertFalse(served['individually_reviewed'])
        self.assertIn('but not this one', served['basis'])
        self.assertTrue(snapshot.records[self.sampled]['review']['individually_reviewed'])
        self.assertEqual(snapshot.excluded_count, 0)
        with self.assertRaises(ValueError):
            review_basis({'review': {'review_class': sa.REVIEW_CLASS,
                                     'sample_plan': {'selected_count': 5, 'population_count': 2}}})


if __name__ == '__main__':
    unittest.main()
