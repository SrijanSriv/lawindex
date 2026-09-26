"""Checkpoint safety on a persistent private corpus/database copy."""
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from scripts import offline_importer as oi
from scripts import import_queue as queue


class QueueTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in ('discovery','review'):
            shutil.copytree(oi.ROOT / 'data' / name, self.root / 'data' / name)
        # Preserve the original four-provision regression fixture explicitly.
        for path in (self.root / 'data/review').glob('*.review.json'):
            if json.loads(path.read_text())['extraction_method_version'] != oi.EXTRACTION_METHOD_VERSION:
                path.unlink()
        for name,value in [('ROOT',self.root),('DATA',self.root/'data/discovery'),('REVIEW',self.root/'data/review')]:
            p=patch.object(oi,name,value);p.start();self.addCleanup(p.stop)
        self.db=self.root/'test.sqlite3'
        self.conn=sqlite3.connect(self.db);self.addCleanup(self.conn.close)
        oi.import_all(self.conn)

    def test_identical_resume_skips_extraction_and_does_not_invent_attempts(self):
        count=self.conn.execute('SELECT count(*) FROM import_attempts').fetchone()[0]
        with patch.object(oi,'build_provision_record',side_effect=AssertionError('must not extract')):
            stats=oi.import_all(self.conn,resume=True)
        self.assertEqual(stats['provisions_skipped'],4)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM import_attempts').fetchone()[0],count)

    def test_interrupted_run_skips_only_previously_committed_success(self):
        original=oi.build_provision_record;calls=[]
        def interrupt(review,raw):
            calls.append(review['provision_key'])
            if len(calls)==2:raise KeyboardInterrupt()
            return original(review,raw)
        with patch.object(oi,'build_provision_record',side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):oi.import_all(self.conn)
        self.conn.close();self.conn=sqlite3.connect(self.db);self.addCleanup(self.conn.close)
        resumed=[]
        def observe(review,raw):
            resumed.append(review['provision_key']);return original(review,raw)
        with patch.object(oi,'build_provision_record',side_effect=observe):
            stats=oi.import_all(self.conn,resume=True)
        self.assertEqual(stats['provisions_skipped'],1)
        self.assertNotIn(calls[0],resumed)
        self.assertEqual(len(resumed),3)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM import_jobs WHERE status='succeeded'").fetchone()[0],4)

    def test_changed_source_revokes_approval_even_with_resume(self):
        p=self.root/'data/discovery/rti-2005-pdf.body';p.write_bytes(p.read_bytes()+b'changed')
        stats=oi.import_all(self.conn,resume=True)
        self.assertEqual(stats['provisions_skipped'],0)
        self.assertFalse(self.conn.execute("SELECT 1 FROM current_versions WHERE provision_key='rti-2005:8'").fetchone())
        self.assertEqual(self.conn.execute("SELECT admission_status FROM provisions WHERE provision_key='rti-2005:8'").fetchone()[0],'invalidated_source_changed')

    def test_review_change_and_removal_cannot_reuse_success(self):
        p=self.root/'data/review/rti-2005-section-8.review.json'
        review=json.loads(p.read_text());review['admission_status']='review_pending';p.write_text(json.dumps(review))
        self.assertEqual(oi.import_all(self.conn,resume=True)['provisions_skipped'],0)
        self.assertFalse(self.conn.execute("SELECT 1 FROM current_versions WHERE provision_key='rti-2005:8'").fetchone())
        p.unlink();oi.import_all(self.conn,resume=True)
        self.assertEqual(self.conn.execute("SELECT status FROM import_jobs WHERE provision_key='rti-2005:8'").fetchone()[0],'removed')

    def test_changed_projection_is_reverified_not_skipped(self):
        self.conn.execute("UPDATE provisions SET body_text='unreviewed' WHERE provision_key='rti-2005:8'");self.conn.commit()
        stats=oi.import_all(self.conn,resume=True)
        self.assertEqual(stats['provisions_skipped'],3)
        self.assertNotEqual(self.conn.execute("SELECT body_text FROM provisions WHERE provision_key='rti-2005:8'").fetchone()[0],'unreviewed')

    def test_missing_archived_blob_requires_full_revalidation(self):
        blob=next((self.root/'data/import/source-blobs').glob('*.body'));blob.unlink()
        stats=oi.import_all(self.conn,resume=True)
        self.assertLess(stats['provisions_skipped'],4)
        self.assertTrue(blob.exists())
        self.assertEqual(stats['provisions_admitted'],4)

    def test_failed_job_is_retried_not_skipped(self):
        key='rti-2005:8'
        original=oi.build_provision_record
        def fail(review,raw):
            if review['provision_key']==key:raise ValueError('synthetic failure')
            return original(review,raw)
        with patch.object(oi,'build_provision_record',side_effect=fail):oi.import_all(self.conn)
        stats=oi.import_all(self.conn,resume=True)
        self.assertEqual(stats['provisions_skipped'],3)
        self.assertEqual(stats['provisions_admitted'],4)

    def test_inputs_include_conflicts_reviewers_manifest_and_tool(self):
        args=(self.root,oi.load_manifest(),oi.load_review_records(),oi.load_conflict_records())
        original=queue.input_fingerprint(*args)
        for relative in ('data/review/reviewer.json','data/review/conflicts/RTI-001.json','data/discovery/corpus-manifest.json'):
            p=self.root/relative;raw=p.read_bytes();p.write_bytes(raw+b' ')
            self.assertNotEqual(queue.input_fingerprint(*args),original)
            p.write_bytes(raw)
        with patch.object(queue.sys,'version','synthetic new runtime'):
            self.assertNotEqual(queue.input_fingerprint(*args),original)
        with patch.object(queue.subprocess,'run',return_value=queue.subprocess.CompletedProcess([],0,b'new tool',b'')):
            self.assertNotEqual(queue.input_fingerprint(*args),original)

    def test_code_and_external_reviewer_dependencies_invalidate(self):
        scripts=self.root/'scripts';scripts.mkdir()
        code=scripts/'import_queue.py';code.write_text('# first implementation\n')
        args=[self.root,oi.load_manifest(),oi.load_review_records(),oi.load_conflict_records()]
        outside=self.root/'external-reviewer.json';outside.write_text('{"reviewer_id":"first"}')
        next(iter(args[2].values()))['review']['reviewer_ref']='external-reviewer.json'
        with patch.object(queue,'__file__',str(code)):
            first=queue.input_fingerprint(*args)
            code.write_text('# second implementation\n')
            self.assertNotEqual(queue.input_fingerprint(*args),first)
            second=queue.input_fingerprint(*args)
            outside.write_text('{"reviewer_id":"second"}')
            self.assertNotEqual(queue.input_fingerprint(*args),second)
