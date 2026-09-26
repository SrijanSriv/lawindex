"""Retained-source boundary checks and explicitly excluded schedule layouts."""
import copy
import json
from pathlib import Path
import sqlite3
import unittest
from scripts import clause_structure as cs, offline_importer as oi, structural_store as ss


class ClauseStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile=json.loads((oi.REVIEW/'structure/environment-1986-section-3.json').read_text())
        review=oi.load_review_records()['environment-1986:3']
        cls.raw=oi.load_capture_bytes('environment-1986-pdf')
        cls.record=oi.build_provision_record(review,{'environment-1986-pdf':cls.raw})
        cls.text=cls.record['body_text']

    def parse(self,text=None,profile=None):
        return cs.parse(self.text if text is None else text,self.profile if profile is None else profile,ss.sha(self.raw))

    def test_nested_clauses_and_qualification_remain_in_parent(self):
        nodes={n['path']:n for n in self.parse()}
        self.assertEqual(len(nodes),19)
        self.assertEqual(nodes['2/i/a']['parent'],'2/i')
        self.assertEqual(nodes['2/i/b']['parent'],'2/i')
        self.assertIn('Provided that different standards',nodes['2/iv']['text'])
        self.assertNotIn('(v) restriction',nodes['2/iv']['text'])
        self.assertIn('subject to the supervision and control',nodes['3']['text'])
        for n in nodes.values():
            self.assertEqual(n['text'],self.text[n['start']:n['end']])
            if n['parent']:
                p=nodes[n['parent']];self.assertTrue(p['start']<=n['start']<n['end']<=p['end'])

    def test_changed_text_or_source_requires_boundary_review(self):
        with self.assertRaises(ValueError):self.parse(text=self.text+' changed')
        with self.assertRaises(ValueError):cs.parse(self.text,self.profile,'wrong-source')

    def test_bad_profiles_are_refused(self):
        for mutation in ('duplicate','ordering','anchor','parent'):
            p=copy.deepcopy(self.profile)
            if mutation=='duplicate':p['nodes'].append(p['nodes'][0])
            if mutation=='ordering':p['nodes'][0],p['nodes'][1]=p['nodes'][1],p['nodes'][0]
            if mutation=='anchor':p['nodes'][0]['start_text']='(1) missing'
            if mutation=='parent':p['nodes'][0]['path']='9/1'
            with self.assertRaises(ValueError):self.parse(profile=p)

    def test_real_schedules_are_recognized_and_quarantined(self):
        fixture=json.loads((oi.REVIEW/'structure/rti-schedule-quarantine.json').read_text())
        raw=oi.load_capture_bytes(fixture['capture']);self.assertEqual(ss.sha(raw),fixture['source_sha256'])
        pages=oi.strip_page_footers(oi.pdftotext_layout(raw))
        for case in fixture['cases']:
            text=oi.strip_watermark(pages[case['page']-1]);self.assertEqual(ss.sha(text.encode()),case['text_sha256'])
            result=cs.schedule_outcome(text)
            self.assertEqual(result['status'],case['expected_status']);self.assertEqual(result['reason'],case['expected_reason'])
            self.assertEqual(result['children'],[])
        self.assertEqual(cs.schedule_outcome('unrecognized schedule')['status'],'unsupported_structure')

    def test_imported_children_have_no_independent_search_admission(self):
        conn=sqlite3.connect(':memory:')
        try:
            oi.import_all(conn)
            rows=conn.execute('''SELECT v.version_id,v.body_text,v.source_anchor_json FROM node_versions v
                JOIN node_versions root ON root.extraction_id=v.extraction_id
                JOIN current_versions c ON c.version_id=root.version_id
                WHERE c.provision_key='environment-1986:3' AND v.parent_version_id IS NOT NULL''').fetchall()
            self.assertEqual(len(rows),19)
            for version,text,anchor in rows:
                anchor=json.loads(anchor);self.assertEqual(text,self.text[anchor['start']:anchor['end']])
                self.assertEqual(anchor['mandatory_context_version_id'],anchor['root_version_id'])
                self.assertFalse(conn.execute('SELECT 1 FROM version_admissions WHERE version_id=?',(version,)).fetchone())
                self.assertFalse(conn.execute('SELECT 1 FROM current_versions WHERE version_id=?',(version,)).fetchone())
            self.assertEqual(conn.execute('SELECT count(*) FROM current_versions').fetchone()[0],len(oi.load_review_records()))
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        finally:conn.close()
