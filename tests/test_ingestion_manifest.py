"""Ingestion-manifest migration: Phase 3 records are derived, labelled, and
never silently mixed with the hand-transcribed Phase 0 ones.
"""
import json
import re
import unittest
from pathlib import Path

from scripts import ingestion_manifest as im
from scripts import offline_importer as oi
from lawindex.search import ROOT, Snapshot, title_year

MANIFEST = json.loads((ROOT / 'data/discovery/corpus-manifest.json').read_text())
RECORDS = {r['slug']: r for r in MANIFEST['records']}
PHASE3 = {s: r for s, r in RECORDS.items() if r.get('record_basis') == 'derived_from_phase3_item_capture'}


class ManifestShapeTests(unittest.TestCase):
    def test_every_captured_phase3_act_is_now_in_the_manifest(self):
        captured = {p.stem for p in (im.DEST / 'acts').glob('*.json')}
        self.assertEqual(len(captured), 20)
        self.assertTrue(captured <= set(RECORDS))
        self.assertEqual(len(PHASE3), 10)
        self.assertEqual(len(RECORDS), 22)
        self.assertEqual(MANIFEST['schema_version'], 2)

    def test_derived_records_carry_the_fields_every_consumer_reads(self):
        for slug, record in PHASE3.items():
            for field in ('uuid', 'title', 'act_id', 'year', 'act_number', 'section_count_observed',
                          'source_url', 'pdf_viewer_url', 'ministry', 'collection_observed'):
                self.assertTrue(record.get(field), (slug, field))
            self.assertEqual(record['scope_status'], 'phase1_candidate')
            self.assertIs(record['ready_for_public_index'], False)
            for url in (record['source_url'], record['pdf_viewer_url'], record['metadata_url'], record['sections_url']):
                self.assertTrue(url.startswith('https://indiacode.gov.in/'), slug)
            self.assertEqual(record['record_evidence'], f'data/phase3/acquisition/acts/{slug}.json')

    def test_unobserved_fields_are_null_rather_than_invented(self):
        for slug, record in PHASE3.items():
            self.assertIsNone(record['last_modified_display'], slug)
            self.assertIsNone(record['notification_present'], slug)
            self.assertIsNone(record['linked_counts'], slug)

    def test_date_provenance_is_labelled_on_every_record(self):
        formats = {'DD-MM-YYYY': r'\d{2}-\d{2}-\d{4}', 'YYYY-MM-DD': r'\d{4}-\d{2}-\d{2}'}
        for slug, record in RECORDS.items():
            if not record.get('enact_date_raw'):
                continue
            fmt = record['enact_date_raw_format']
            self.assertIn(fmt, formats, slug)
            self.assertRegex(record['enact_date_raw'], formats[fmt], slug)
        self.assertEqual({r['enact_date_raw_format'] for r in PHASE3.values()}, {'YYYY-MM-DD'})
        self.assertIn('enact_date_raw_format', MANIFEST['date_format_warning'])

    def test_derivation_matches_the_retained_item_capture(self):
        inventory = {r['slug']: r for r in json.loads(
            (ROOT / 'data/phase3/inventory.v1.json').read_text())['records']}
        for slug, record in PHASE3.items():
            act = json.loads((im.DEST / 'acts' / (slug + '.json')).read_text())
            metadata = act['item']['metadata']
            self.assertEqual(record['uuid'], act['item']['uuid'])
            self.assertEqual(record['title'], metadata['dc.title'][0]['value'])
            self.assertEqual(record['act_id'], metadata['dc.identifier.act_id'][0]['value'])
            self.assertEqual(record['section_count_observed'], act['section_count'])
            self.assertEqual(record['rationale'], inventory[slug]['selection_reason'])
            self.assertEqual(im.record_for(slug, inventory), record)

    def test_derivation_refuses_ambiguous_or_missing_source_fields(self):
        inventory = {r['slug']: r for r in json.loads(
            (ROOT / 'data/phase3/inventory.v1.json').read_text())['records']}
        metadata = {'dc.title': [{'value': 'A'}, {'value': 'B'}]}
        with self.assertRaises(ValueError):
            im.one(metadata, 'dc.title')
        with self.assertRaises(ValueError):
            im.one({}, 'dc.identifier.act_id')
        self.assertIsNone(im.one({}, 'dc.type', optional=True))
        with self.assertRaises(ValueError):
            im.english_pdf({'slug': 'x', 'pdfs': []})
        with self.assertRaises(ValueError):
            im.english_pdf({'slug': 'x', 'pdfs': [{'name': 'a.pdf'}, {'name': 'b.pdf'}]})


class ManifestConsumerTests(unittest.TestCase):
    def test_importer_records_every_manifest_act_without_admitting_them(self):
        self.assertEqual(len(oi.load_manifest()), 22)
        snapshot = Snapshot(ROOT)
        admitted_acts = {key.split(':')[0] for key in snapshot.records}
        self.assertTrue(admitted_acts < set(RECORDS))
        for slug in PHASE3:
            if slug not in admitted_acts:
                self.assertEqual(sum(k.startswith(slug + ':') for k in snapshot.records), 0)

    def test_a_title_year_that_differs_from_the_recorded_year_stays_findable(self):
        # The Competition Act, 2002 is Act No. 12 of 2003 in the source.
        competition = RECORDS['competition-2002']
        self.assertEqual(competition['year'], '2003')
        self.assertEqual(title_year(competition['title']), '2002')
        mismatched = [s for s, r in RECORDS.items()
                      if r.get('year') and title_year(r['title']) and title_year(r['title']) != r['year']]
        self.assertEqual(mismatched, ['competition-2002'])

    def test_newly_manifested_acts_are_admissible_and_previously_blocked_ones_were_not(self):
        from scripts.admit_sampled_batch import build_records
        plan, records = build_records('food-security-2013')
        self.assertEqual(len(records), plan['population_count'])
        self.assertTrue(all(r['act_slug'] == 'food-security-2013' for r in records.values()))
        self.assertNotIn('food-security-2013', {r['slug'] for r in json.loads(
            (ROOT / 'data/phase3/inventory.v1.json').read_text())['records']} - set(RECORDS))


if __name__ == '__main__':
    unittest.main()
