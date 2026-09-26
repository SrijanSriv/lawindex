"""Typographic equivalence tier: enumerated, symmetric, attributable, never admission.

The exact tier (level 0) is untouched. Every recovered candidate names the
minimal normalization level it needed; wording, punctuation and number
differences still quarantine, and short bodies cannot be substring-matched.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import phase3_candidates as pc
from lawindex.coverage import build_coverage


class NormalizationLadderTests(unittest.TestCase):
    def level(self, body, page):
        return pc.locate_minimal(body, [page])['normalizations']

    def test_exact_tier_is_unchanged(self):
        self.assertEqual(pc.locate('Legal text.', ['Heading. Legal\n text.'])['normalizations'], [])
        self.assertEqual(pc.locate('Legal text.', ['Heading. Legal\n text.'])['agreement'], 'entire body, whitespace folding only')
        for body, page in [('cat', 'concatenate'), ('Legal text', 'Legal texts'), ('same', 'same same')]:
            with self.assertRaises(ValueError):
                pc.locate(body, [page])

    def test_each_level_is_minimal_and_named(self):
        cases = [
            ('requires,-- (a) the officer shall decide', 'requires,— (a) the officer shall decide', 'dash'),
            ('members, namely:--- (a) six members of parliament', 'members, namely:— (a) six members of parliament', 'dash'),
            ('the term "access" with its variations', 'the term “access” with its variations', 'quote'),
            ('come into force on such date1 as the Government', 'come into force on such date2 as the Government', 'marker'),
            ('at the sub-divisional or other subdistrict level', 'at the sub-divisional or other sub- district level', 'hyphen'),
            ('made before that Court.] (3) Notwithstanding that', 'made before that Court .] (3) Notwithstanding that', 'punct-space'),
            ('is contained in (a) a document signed by the parties', 'is contained in— (a) a document signed by the parties', 'dash-drop'),
            ('Nothing in Section 58 shall apply in respect of', 'Nothing in section 58 shall apply in respect of', 'case'),
            ('For the purposes of this Act, copyright means the exclusive', 'For the purposes of this Act, "copyright" means the exclusive', 'quote-drop'),
            ('[43. [Penalty and compensation] for damage to computer', '43. [Penalty and compensation] for damage to computer', 'bracket-drop'),
            ('meet at any place it considers appropriate for consultation', 'meet at anyplace it considers appropriate for consultation', 'space-drop'),
        ]
        for body, page, expected in cases:
            with self.subTest(expected=expected):
                names = self.level(body, page)
                self.assertEqual(names[-1], expected, names)
                self.assertEqual(names, pc.NORMALIZATION_NAMES[:len(names)])

    def test_meaning_bearing_differences_never_align(self):
        for body, page in [
            ('the Central Government is satisfied', 'the Central Government Government is satisfied'),
            ('acknowledgment must be received', 'acknowledgement must be received'),
            ('section 64 and section 68. (d) any other', 'section 64 and section 68; (d) any other'),
            ('by [Commercial Court]. If any question', 'by [Appellate Board]. If any question'),
            ('within a period of 2-3 months of the date', 'within a period of 23 months of the date'),
            ('(3) An arbitrator may be challenged only if', '(2) An arbitrator may be challenged only if'),
            ('Omitted.', 'xOmitted.y'),
        ]:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    pc.locate_minimal(body, [page])

    def test_space_drop_requires_uniqueness_and_a_minimum_length(self):
        long_body = '23. Members and staff of Authorities to be public servants. The members shall be public servants.'
        self.assertEqual(self.level(long_body, 'servants.' + long_body.replace(' ', '') + ' 24. Next')[-1], 'space-drop')
        with self.assertRaises(ValueError):
            pc.locate_minimal(long_body, [long_body.replace(' ', '') + ' ' + long_body.replace(' ', '')])
        with self.assertRaises(ValueError):
            pc.locate('Rep. by s. 65.', ['x Rep.bys.65. y'], pc.SPACE_DROP_LEVEL)

    def test_footnote_numbers_are_dropped_only_for_footnotes_at_marker_level(self):
        pages = ['... appointment. 2. Subs. by s. 9, ibid., for the words.']
        self.assertEqual(pc.locate('1. Subs. by s. 9, ibid., for the words.', pages, pc.MARKER_LEVEL, footnote=True)['normalizations'][-1], 'marker')
        with self.assertRaises(ValueError):
            pc.locate('1. Subs. by s. 9, ibid., for the words.', pages, pc.MARKER_LEVEL)
        with self.assertRaises(ValueError):
            pc.locate('1. Subs. by s. 9, ibid., for the words.', pages, 0, footnote=True)


class PageBreakFootnoteTests(unittest.TestCase):
    BODY = ('(1) The tribunal shall decide the matter within thirty days of the date of their appointment, the appointment '
            'shall be made by the court on request of a party and the decision shall be final. (2) Nothing in this section applies.')

    def test_footnote_block_at_page_end_is_skipped_and_recorded(self):
        pages = ['Heading. ' + self.BODY[:95] + '\n1. Ins. by Act 3 of 2016, s. 8 (w.e.f. 23-10-2015).', self.BODY[95:] + ' 12. Next section.']
        found = pc.locate_minimal(self.BODY, pages)
        self.assertEqual(found['normalizations'], [pc.GAP_SKIP])
        self.assertEqual((found['pdf_page_from'], found['pdf_page_to']), (1, 2))
        self.assertEqual(found['pdf_page_break_gaps'][0]['pdf_page'], 1)
        self.assertTrue(found['pdf_page_break_gaps'][0]['skipped_text'].startswith('1. Ins. by Act 3 of 2016'))

    def test_non_footnote_gap_and_missing_continuation_are_rejected(self):
        with self.assertRaises(ValueError):
            pc.locate_across_footnote_blocks(self.BODY, ['Heading. ' + self.BODY[:95] + ' Some other text.', self.BODY[95:]], 0)
        with self.assertRaises(ValueError):
            pc.locate_across_footnote_blocks(self.BODY, ['Heading. ' + self.BODY[:95] + '\n1. Ins. by Act.', 'Unrelated page. ' + self.BODY[95:]], 0)

    def test_opening_quoted_in_a_footnote_does_not_defeat_alignment(self):
        pages = ['4. Abuse.' + self.BODY[:110] + '\n1. Subs. by Act 9 of 2023 for "' + self.BODY[:90] + '".', self.BODY[110:] + ' 5. Next.']
        self.assertEqual(pc.locate_across_footnote_blocks(self.BODY, pages, 0)['pdf_page_from'], 1)
        # Two complete copies remain ambiguous.
        with self.assertRaises(ValueError):
            pc.locate_across_footnote_blocks(self.BODY, [self.BODY[:95] + '\n1. Ins.', self.BODY[95:] + ' ' + self.BODY[:95] + '\n2. Ins.', self.BODY[95:]], 0)


class CandidateReportTests(unittest.TestCase):
    def test_live_candidates_are_consistent_and_attributed(self):
        exact = typographic = quarantined = 0
        for path in sorted((pc.ROOT / 'data/phase3/candidates').glob('*.json')):
            report = json.loads(path.read_text())
            for c in report['candidates']:
                self.assertEqual(c['parser_version'], pc.VERSION)
                self.assertFalse(c['search_admitted'])
                if c['status'] == 'agreement_review_pending':
                    exact += 1
                    self.assertEqual(c['normalizations'], [])
                elif c['status'] == 'typographic_agreement_review_pending':
                    typographic += 1
                    self.assertTrue(c['normalizations'])
                    names = [n for n in c['normalizations'] if n != pc.GAP_SKIP]
                    self.assertEqual(names, pc.NORMALIZATION_NAMES[:len(names)])
                    self.assertEqual(c['body_text_sha256'], pc.sha(c['body_text'].encode()))
                else:
                    quarantined += 1
                    self.assertEqual(c['status'], 'quarantined')
                    self.assertNotIn('body_text', c)
                    if c['reason'].startswith('full body') or c['reason'].startswith('section start'):
                        self.assertIn('divergence', c)
        self.assertEqual(exact, 896)
        self.assertGreater(typographic, 500)
        self.assertEqual(exact + typographic + quarantined, 1923)

    def test_coverage_reports_both_tiers_and_reasons(self):
        from lawindex.search import Snapshot
        report = build_coverage(pc.ROOT, Snapshot(pc.ROOT))
        rti = next(r for r in report['rows'] if r['slug'] == 'rti-2005')
        self.assertEqual(rti['agreement_review_pending_count'], 10)
        self.assertEqual(rti['typographic_agreement_review_pending_count'], 17)
        self.assertEqual(rti['quarantined_count'], sum(rti['quarantine_reasons'].values()))
        self.assertEqual(rti['searchable_provision_count'],
                         sum(k.startswith('rti-2005:') for k in Snapshot(pc.ROOT).records))
        self.assertTrue(any('typographic' in note for note in report['limitations']))
        # Neither tier adds anything to searchable counts.
        self.assertEqual(report['searchable_provision_count'], len(Snapshot(pc.ROOT).records))


if __name__ == '__main__':
    unittest.main()
