"""Schema, migration and history contracts. All writes use temporary databases.

Synthetic hierarchy/relationship examples test constraints, not legal parsing.
"""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts import offline_importer as oi
from scripts import structural_store as ss


class StructuralTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'db.sqlite3'
        self.conn = sqlite3.connect(self.db)
        self.addCleanup(self.conn.close)
        self.conn.executescript(oi.SCHEMA)
        self.conn.execute("INSERT INTO documents(act_slug,title,scope_status) VALUES ('demo','Synthetic','phase1_candidate')")
        self.conn.commit()
        ss.migrate(self.conn)
        self.conn.row_factory = sqlite3.Row
        (self.root / 'data/discovery').mkdir(parents=True)
        self.raw = {'demo-pdf': b'%PDF-synthetic-v1'}
        self.write_meta(self.raw['demo-pdf'])
        self.review = dict(provision_key='demo:6', act_slug='demo', section_number='6', heading='Synthetic heading',
            selected_representation='pdf', extraction_method_version='test-parser-v1', admission_status='admitted',
            source_representation=dict(capture='demo-pdf',sha256=ss.sha(self.raw['demo-pdf']),pdf_page_from=1,pdf_page_to=1),
            expected_output=dict(body_text_sha256=ss.sha('Example 🧭 provision.'.encode()),footnote_text_sha256='no-footnote-expected'))
        self.record = {k:self.review[k] for k in ('provision_key','act_slug','section_number','heading',
            'selected_representation','extraction_method_version','admission_status')}
        self.record.update(body_text='Example 🧭 provision.',body_text_sha256=self.review['expected_output']['body_text_sha256'],
            footnote_text=None,footnote_text_sha256=None,pdf_page_from=1,pdf_page_to=1)
        self.reviewer = {'reviewer_id':'synthetic-test-only'}

    def write_meta(self, raw):
        (self.root / 'data/discovery/demo-pdf.json').write_text(json.dumps(dict(sha256=ss.sha(raw),
            effective_url='https://example.invalid/synthetic', fetched_at_utc=None,body_path='data/discovery/demo-pdf.body')))

    def promote(self):
        with self.conn:
            ss.promote(self.conn,self.root,self.record,self.review,self.reviewer,self.raw,{'test':True})

    def version(self):
        return dict(self.conn.execute('SELECT v.* FROM node_versions v JOIN current_versions c USING(version_id)').fetchone())

    def test_reimport_is_idempotent_in_all_structural_history(self):
        self.promote()
        before={t:[tuple(r) for r in self.conn.execute(f'SELECT * FROM {t}')] for t in ss.IMMUTABLE}
        self.promote()
        self.assertEqual(before,{t:[tuple(r) for r in self.conn.execute(f'SELECT * FROM {t}')] for t in ss.IMMUTABLE})
        self.assertEqual(len(self.conn.execute('SELECT * FROM current_versions').fetchall()),1)
        self.assertFalse(self.conn.execute('PRAGMA foreign_key_check').fetchall())

    def test_new_source_requires_new_review_and_preserves_old_version(self):
        self.promote(); first=self.version()
        self.raw['demo-pdf']=b'%PDF-synthetic-v2'
        self.write_meta(self.raw['demo-pdf'])
        with self.assertRaises(ValueError): self.promote()
        self.assertEqual(self.version(),first)
        self.review['source_representation']['sha256']=ss.sha(self.raw['demo-pdf'])
        self.promote();second=self.version()
        self.assertEqual(first['node_id'],second['node_id'])
        self.assertNotEqual(first['version_id'],second['version_id'])
        self.assertEqual(len(list((self.root / 'data/import/source-blobs').glob('*.body'))),2)
        self.assertTrue(any(p.read_bytes()==b'%PDF-synthetic-v1' for p in (self.root / 'data/import/source-blobs').glob('*.body')))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM source_snapshots').fetchone()[0],2)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM node_versions').fetchone()[0],2)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM version_admissions').fetchone()[0],2)

    def test_review_revision_binds_new_admission_without_changing_text_version(self):
        self.promote();first=self.version()
        self.review['review_note']='synthetic second review'
        self.promote()
        self.assertEqual(self.version(),first)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM version_admissions').fetchone()[0],2)

    def test_parent_scope_cycles_and_history_are_enforced(self):
        self.promote();parent=self.version()
        ss.keep(self.conn,'structural_nodes',dict(node_id='clause-node',act_slug='demo'))
        child={**parent,'node_id':'clause-node','version_id':'synthetic-child','parent_version_id':parent['version_id'],
               'sibling_ordinal':0,'kind':'clause','display_label':'(a)'}
        ss.keep(self.conn,'node_versions',child)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('UPDATE node_versions SET parent_version_id=? WHERE version_id=?', ('synthetic-child',parent['version_id']))
        for bad in ({**child,'version_id':'cycle','parent_version_id':'cycle'},
                    {**child,'version_id':'orphan','parent_version_id':'missing'},
                    {**child,'version_id':'duplicate-position'}):
            with self.assertRaises(sqlite3.IntegrityError): ss.keep(self.conn,'node_versions',bad)
        self.conn.execute("INSERT INTO documents(act_slug) VALUES ('other')")
        ss.keep(self.conn,'structural_nodes',dict(node_id='other-node',act_slug='other'))
        with self.assertRaises(sqlite3.IntegrityError):
            ss.keep(self.conn,'node_versions',{**parent,'version_id':'wrong-act','node_id':'other-node'})
        # A different extraction of the SAME document also cannot supply a parent.
        extraction=dict(self.conn.execute('SELECT * FROM extractions').fetchone())
        ss.keep(self.conn,'extractions',{**extraction,'extraction_id':'other-extraction'})
        with self.assertRaises(sqlite3.IntegrityError):
            ss.keep(self.conn,'node_versions',{**child,'version_id':'wrong-extraction',
                'extraction_id':'other-extraction','sibling_ordinal':1})
        self.conn.rollback()

    def test_exact_unicode_passage_and_footnote_separation(self):
        self.record['footnote_text']='1. Synthetic amendment note.'
        h=ss.sha(self.record['footnote_text'].encode())
        self.record['footnote_text_sha256']=h;self.review['expected_output']['footnote_text_sha256']=h
        self.promote();v=self.version()
        passages={r['field']:dict(r) for r in self.conn.execute('SELECT * FROM passages')}
        self.assertEqual(passages['body']['char_end'],len(self.record['body_text']))
        self.assertEqual(passages['footnote']['text'],self.record['footnote_text'])
        with self.assertRaises(sqlite3.IntegrityError):
            ss.keep(self.conn,'passages',dict(passage_id='bad',version_id=v['version_id'],field='body',
                strategy_version='test',char_start=0,char_end=3,text='wrong'))
        self.conn.rollback()

    def test_admission_cannot_be_attached_to_another_alias(self):
        self.promote()
        ss.keep(self.conn,'structural_nodes',dict(node_id='other-node',act_slug='demo'))
        ss.keep(self.conn,'provision_aliases',dict(provision_key='demo:99',node_id='other-node'))
        current=self.conn.execute('SELECT * FROM current_versions').fetchone()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('INSERT INTO current_versions VALUES (?,?,?)',('demo:99',current['version_id'],current['admission_id']))
        self.conn.rollback()

    def test_relationship_requires_document_and_source_evidence(self):
        self.promote()
        self.conn.execute("INSERT INTO documents(act_slug) VALUES ('parent-act')")
        snap=self.version()['pdf_snapshot_id']
        rel=dict(relationship_id='synthetic-rel',from_act_slug='demo',to_act_slug='parent-act',
            relation_type='rules-made-under',evidence_snapshot_id=snap,evidence_anchor_json='{"page":1}')
        ss.keep(self.conn,'instrument_relationships',rel)
        with self.assertRaises(sqlite3.IntegrityError):
            ss.keep(self.conn,'instrument_relationships',{**rel,'relationship_id':'bad',
                'from_act_slug':'parent-act','to_act_slug':'demo'})
        self.conn.rollback()

    def test_unreviewed_output_cannot_be_promoted(self):
        self.record['body_text']+=' unchecked'
        with self.assertRaises(ValueError):self.promote()
        self.assertEqual(self.conn.execute('SELECT count(*) FROM current_versions').fetchone()[0],0)


class MigrationTests(unittest.TestCase):
    def test_failed_migration_rolls_back_and_backup_restores_legacy_database(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'legacy.sqlite3'
            conn=sqlite3.connect(path)
            try:
                conn.executescript(oi.SCHEMA)
                conn.execute("INSERT INTO documents(act_slug,title) VALUES ('legacy','Preserve me')")
                conn.commit()
                with patch.object(ss,'DDL',ss.DDL+['INVALID SQL']):
                    with self.assertRaises(sqlite3.OperationalError):ss.migrate(conn)
                self.assertEqual(ss.schema_version(conn),0)
                self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name='node_versions'").fetchone())
                backup=ss.migrate(conn)
                self.assertIsNotNone(backup)
                self.assertEqual(ss.schema_version(conn),1)
                self.assertIsNone(ss.migrate(conn))
                restored=sqlite3.connect(Path(temp)/'restored.sqlite3')
                source=sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True)
                try:
                    source.backup(restored)
                    self.assertEqual(ss.schema_version(restored),0)
                    self.assertEqual(restored.execute('SELECT title FROM documents').fetchone()[0],'Preserve me')
                    self.assertEqual(restored.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                finally:source.close();restored.close()
            finally:conn.close()

    def test_unknown_version_is_rejected(self):
        conn=sqlite3.connect(':memory:')
        try:
            conn.executescript('CREATE TABLE structural_schema(version); INSERT INTO structural_schema VALUES (99);')
            with self.assertRaises(ValueError):ss.migrate(conn)
        finally:conn.close()

    def test_real_legacy_rows_are_revalidated_not_blindly_backfilled(self):
        count = len(oi.load_review_records())
        conn=sqlite3.connect(':memory:')
        try:
            conn.executescript(oi.SCHEMA)
            conn.execute("INSERT INTO provisions(provision_key,admission_status,body_text) VALUES ('unreviewed:1','admitted','untrusted')")
            conn.commit()
            ss.migrate(conn)
            self.assertEqual(conn.execute('SELECT count(*) FROM current_versions').fetchone()[0],0)
            oi.import_all(conn)
            self.assertEqual(conn.execute('SELECT count(*) FROM current_versions').fetchone()[0],count)
            self.assertEqual(conn.execute("SELECT admission_status FROM provisions WHERE provision_key='unreviewed:1'").fetchone()[0],'invalidated_review_record_removed')
            counts={t:conn.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ss.IMMUTABLE}
            oi.import_all(conn)
            self.assertEqual(counts,{t:conn.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ss.IMMUTABLE})
            reviews=oi.load_review_records();reviews.pop('rti-2005:8')
            with patch.object(oi,'load_review_records',return_value=reviews):oi.import_all(conn)
            self.assertEqual(conn.execute('SELECT count(*) FROM current_versions').fetchone()[0],count-1)
            self.assertEqual(conn.execute('SELECT count(*) FROM node_versions WHERE parent_version_id IS NULL').fetchone()[0],count)
            oi.import_all(conn)
            self.assertEqual(conn.execute('SELECT count(*) FROM current_versions').fetchone()[0],count)
        finally:conn.close()
