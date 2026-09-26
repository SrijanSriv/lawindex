"""Phase 3 admission is an explicit reviewed decision, not a candidate count."""
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import offline_importer as oi
from scripts import structural_store as ss

BATCH = {'rti-2005:3', 'rti-2005:9', 'environment-1986:4',
         'environment-1986:8', 'posh-2013:9', 'posh-2013:10'}


class ReviewedHTMLTests(unittest.TestCase):
    def setUp(self):
        self.reviews = oi.load_review_records()
        self.review = copy.deepcopy(self.reviews['posh-2013:9'])
        self.raw = {name: oi.load_capture_bytes(name) for name in
                    [self.review['source_representation']['capture'], self.review['pdf_anchor']['capture']]}

    def build(self):
        return oi.build_provision_record(self.review, self.raw)

    def test_six_sections_have_explicit_visual_review_and_exact_output(self):
        for key in BATCH:
            review = self.reviews[key]
            raw = {name: oi.load_capture_bytes(name) for name in
                   [review['source_representation']['capture'], review['pdf_anchor']['capture']]}
            row = oi.build_provision_record(review, raw)
            self.assertEqual(row['admission_status'], 'admitted')
            self.assertEqual(oi.sha256_bytes(row['body_text'].encode()), review['expected_output']['body_text_sha256'])
            self.assertIsNone(row['footnote_text'])
            for file, digest in review['render_sha256'].items():
                self.assertEqual(oi.sha256_bytes((oi.ROOT / file).read_bytes()), digest)
        text = self.build()['body_text']
        self.assertEqual(text.count('Provided'), 2)
        self.assertIn('(2) Where the aggrieved woman', text)

    def test_wrong_uuid_parent_heading_or_label_rejected_even_with_matching_body(self):
        for path, value in [('section_item_uuid', 'missing'), ('act_id', 'wrong')]:
            with self.subTest(path=path):
                review = copy.deepcopy(self.review)
                review['source_representation'][path] = value
                with self.assertRaises(ValueError): oi.build_provision_record(review, self.raw)
        for field, value in [('heading', 'Another heading'), ('section_number', '10'), ('act_uuid', 'other')]:
            with self.subTest(field=field):
                review = copy.deepcopy(self.review); review[field] = value
                with self.assertRaises(ValueError): oi.build_provision_record(review, self.raw)

    def test_changed_source_invalidates_and_never_stores_text(self):
        self.raw[self.review['source_representation']['capture']] += b' '
        row = self.build()
        self.assertEqual(row['admission_status'], 'invalidated_source_changed')
        self.assertIsNone(row['body_text'])

    def test_missing_changed_pdf_or_wrong_page_is_rejected(self):
        anchor = self.review['pdf_anchor']
        for mutate in ['missing', 'changed', 'page']:
            with self.subTest(mutate=mutate):
                raw = dict(self.raw); review = copy.deepcopy(self.review)
                if mutate == 'missing': del raw[anchor['capture']]
                elif mutate == 'changed': raw[anchor['capture']] = b'changed'
                else: review['pdf_anchor']['pdf_page_from'] += 1
                with self.assertRaises((KeyError, ValueError)):
                    oi.build_provision_record(review, raw)

    def test_extractor_drift_fails_expected_digest(self):
        # Whitespace folding would still agree with the PDF; the reviewed
        # output digest independently prevents silently changing stored text.
        from scripts.phase3_candidates import plain
        with patch('scripts.phase3_candidates.plain', side_effect=lambda html: plain(html).replace(' ', '  ')):
            row = self.build()
        self.assertEqual(row['admission_status'], 'invalidated_body_text_changed')
        self.assertIsNone(row['body_text'])

    def test_missing_digest_and_unknown_method_do_not_admit(self):
        del self.review['expected_output']
        self.assertEqual(self.build()['admission_status'], 'invalidated_missing_expected_digest')
        self.review['extraction_method_version'] = 'future-unreviewed'
        self.assertEqual(self.build()['admission_status'], 'invalidated_extraction_method_changed')

    def test_unexpected_footnote_or_pdf_disagreement_fails_before_promotion(self):
        name = self.review['source_representation']['capture']
        source = json.loads(self.raw[name])
        target = next(r['_embedded']['indexableObject'] for r in source['_embedded']['searchResult']['_embedded']['objects']
                      if r['_embedded']['indexableObject']['uuid'] == self.review['source_representation']['section_item_uuid'])
        for field, text in [('dc.identifier.section_footnote', 'invented footnote'),
                            ('dc.identifier.section_page_note', 'invented legal wording')]:
            with self.subTest(field=field):
                # POSH s.9 carries no footnote field at all; absence must be restored as absence.
                original = copy.deepcopy(target['metadata'].get(field))
                target['metadata'][field] = [{'value': text}]
                raw = dict(self.raw); raw[name] = json.dumps(source).encode()
                review = copy.deepcopy(self.review); review['source_representation']['sha256'] = oi.sha256_bytes(raw[name])
                with self.assertRaises(ValueError): oi.build_provision_record(review, raw)
                if original is None: del target['metadata'][field]
                else: target['metadata'][field] = original

    def test_persistent_import_review_withdrawal_and_restoration_preserve_history(self):
        with tempfile.TemporaryDirectory() as directory:
            with sqlite3.connect(Path(directory)/'test.sqlite3') as conn:
                total = len(self.reviews)
                self.assertEqual(oi.import_all(conn)['provisions_admitted'], total)
                before = dict(conn.execute('SELECT provision_key,version_id FROM current_versions'))
                reviews = copy.deepcopy(self.reviews); del reviews['posh-2013:9']
                with patch.object(oi, 'load_review_records', return_value=reviews):
                    self.assertEqual(oi.import_all(conn)['provisions_admitted'], total - 1)
                self.assertIsNone(conn.execute("SELECT version_id FROM current_versions WHERE provision_key='posh-2013:9'").fetchone())
                self.assertEqual(conn.execute('SELECT count(*) FROM node_versions WHERE version_id=?',(before['posh-2013:9'],)).fetchone()[0], 1)
                total = len(self.reviews)
                self.assertEqual(oi.import_all(conn)['provisions_admitted'], total)
                self.assertEqual(before, dict(conn.execute('SELECT provision_key,version_id FROM current_versions')))
                self.assertEqual(oi.import_all(conn, resume=True)['provisions_skipped'], total)
                for key in BATCH:
                    method = conn.execute('SELECT extraction_method_version FROM import_attempts WHERE provision_key=? ORDER BY attempt_id DESC',(key,)).fetchone()[0]
                    self.assertEqual(method, oi.REVIEWED_HTML_VERSION)
