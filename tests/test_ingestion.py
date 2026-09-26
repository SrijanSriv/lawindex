"""Persistent-database failure/recovery tests; no original evidence is changed."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import offline_importer as oi


class IngestionTests(unittest.TestCase):
    def setUp(self):
        legacy = {k: v for k, v in oi.load_review_records().items()
                  if v['extraction_method_version'] == oi.EXTRACTION_METHOD_VERSION}
        loader = patch.object(oi, 'load_review_records', side_effect=lambda: __import__('copy').deepcopy(legacy))
        loader.start(); self.addCleanup(loader.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.sqlite3'
        self.conn = sqlite3.connect(self.path)
        self.addCleanup(self.conn.close)
        oi.import_all(self.conn)

    def test_missing_source_isolated_and_retry_recovers(self):
        original = oi.load_capture_bytes
        target = next(iter(oi.load_review_records().values()))['source_representation']['capture']
        def missing(name):
            if name == target:
                raise FileNotFoundError(name)
            return original(name)
        with patch.object(oi, 'load_capture_bytes', side_effect=missing):
            stats = oi.import_all(self.conn)
        self.assertGreater(stats['provisions_failed'], 0)
        self.assertGreater(stats['provisions_admitted'], 0)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM provisions WHERE admission_status = 'invalidated_import_failed' AND body_text IS NOT NULL").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM excerpts e JOIN provisions p USING(provision_key) WHERE p.admission_status != 'admitted'").fetchone()[0], 0)
        self.assertEqual(oi.import_all(self.conn)['provisions_admitted'], 4)
        self.assertGreater(self.conn.execute("SELECT count(*) FROM import_attempts WHERE status='failed'").fetchone()[0], 0)

    def test_interrupted_run_commits_completed_item_and_restarts(self):
        original = oi.build_provision_record
        calls = 0
        def interrupted(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt()
            return original(*args)
        with patch.object(oi, 'build_provision_record', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                oi.import_all(self.conn)
        self.conn.close()
        self.conn = sqlite3.connect(self.path)
        self.addCleanup(self.conn.close)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM provisions WHERE admission_status='admitted'").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM import_attempts WHERE status='running'").fetchone()[0], 1)
        self.assertEqual(oi.import_all(self.conn)['provisions_admitted'], 4)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM import_attempts WHERE status='interrupted'").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM provisions").fetchone()[0], 4)

    def test_changed_source_keeps_attempt_hash_history(self):
        review = next(iter(oi.load_review_records().values()))
        name = review['source_representation']['capture']
        oi.import_all(self.conn, {name: b'changed source'})
        rows = self.conn.execute('SELECT status, source_hashes_json FROM import_attempts WHERE provision_key=? ORDER BY attempt_id', (review['provision_key'],)).fetchall()
        self.assertEqual(rows[0][0], 'succeeded')
        self.assertEqual(rows[-1][0], 'quarantined')
        self.assertNotEqual(rows[0][1], rows[-1][1])

    def test_single_writer_lock(self):
        with oi.import_lock(self.path):
            with self.assertRaises(oi.AdmissionError):
                oi.import_all(self.conn)

    def test_extraction_timeout_isolated(self):
        with patch.object(oi, 'pdftotext_layout', side_effect=oi.subprocess.TimeoutExpired('pdftotext', 60)):
            stats = oi.import_all(self.conn)
        self.assertGreater(stats['provisions_failed'], 0)
        self.assertGreater(self.conn.execute("SELECT count(*) FROM import_attempts WHERE error_type='TimeoutExpired'").fetchone()[0], 0)
        self.assertEqual(oi.import_all(self.conn)['provisions_admitted'], 4)

    def test_failure_after_provision_write_rolls_back_and_revokes(self):
        reviews = oi.load_review_records()
        key = next(iter(reviews))
        reviews[key]['review']['reviewer_ref'] = 'missing-reviewer-for-test.json'
        with patch.object(oi, 'load_review_records', return_value=reviews):
            stats = oi.import_all(self.conn)
        self.assertEqual(stats['provisions_failed'], 1)
        self.assertEqual(stats['provisions_admitted'], 3)
        self.assertEqual(self.conn.execute('SELECT admission_status, body_text FROM provisions WHERE provision_key=?', (key,)).fetchone(), ('invalidated_import_failed', None))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM excerpts WHERE provision_key=?', (key,)).fetchone()[0], 0)

    def test_invalid_global_inventory_does_not_revoke_valid_rows(self):
        before = list(self.conn.execute('SELECT * FROM provisions ORDER BY provision_key'))
        with patch.object(oi, 'load_review_records', side_effect=ValueError('invalid inventory')):
            with self.assertRaises(ValueError):
                oi.import_all(self.conn)
        self.assertEqual(before, list(self.conn.execute('SELECT * FROM provisions ORDER BY provision_key')))
