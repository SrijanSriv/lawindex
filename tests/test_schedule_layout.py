"""Positive retained-PDF layout fixtures plus admission/failure checks.

No original evidence, database, or reviewer decision is modified by these tests.
"""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout,redirect_stderr
from unittest.mock import patch
from scripts import schedule_layout as sl


class ScheduleLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=(sl.ROOT/'data/discovery/rti-2005-pdf.body').read_bytes()
        cls.profile=json.loads(sl.DEFAULT_PROFILE.read_text())
        cls.artifact=sl.parse(cls.raw,cls.profile)

    def test_all_words_retained_once_with_original_positions(self):
        original=sl.extract_pages(self.raw)
        self.assertEqual([len(p['words']) for p in self.artifact['pages']],[142,279])
        for page,source in zip(self.artifact['pages'],original):
            self.assertEqual(page['words'],source['words'])
            ids=[i for g in page['groups'] for i in g['word_ids']]
            self.assertEqual(len(ids),len(set(ids)))
            self.assertEqual(set(ids),{w['id'] for w in source['words']})
        self.assertFalse(self.artifact['search_admitted'])

    def test_oath_alternatives_and_shared_context_are_distinct(self):
        page=self.artifact['pages'][0];words={w['id']:w for w in page['words']};groups={g['id']:g for g in page['groups']}
        self.assertEqual([words[i]['text'] for i in groups['oath']['word_ids']],['swear','in','the','name','of','God'])
        self.assertEqual([words[i]['text'] for i in groups['affirmation']['word_ids']],['solemnly','affirm'])
        self.assertLess(groups['oath']['bbox'][1],groups['affirmation']['bbox'][1])
        self.assertEqual(page['relations'][0]['shared_suffix'],'continuation')
        # The common "that I will..." starts on the oath's printed line; it
        # must not be swallowed by that one alternative.
        self.assertEqual(words[groups['continuation']['word_ids'][0]]['text'],'that')

    def test_entries_omission_brackets_and_all_notes_survive(self):
        page=self.artifact['pages'][1];groups={g['id']:g for g in page['groups']};words={w['id']:w for w in page['words']}
        self.assertEqual(len([g for g in groups.values() if g['role']=='entry']),27)
        self.assertEqual(len([g for g in groups.values() if g['role']=='footnote']),11)
        self.assertEqual(len(page['relations']),13)
        refs={r['note_id']:r for r in page['relations']}
        self.assertEqual(refs['note-6']['scope_groups'],['entry-19','entry-20','entry-21','omitted-block'])
        self.assertEqual(refs['note-9']['scope_groups'],['entry-23','entry-24','entry-25'])
        self.assertEqual([words[w]['text'] for w in refs['note-3']['affected_word_ids']],['[Frontier]'])
        self.assertIn('*]',[words[w]['text'] for w in groups['omitted-block']['word_ids']])
        self.assertEqual(len([r for r in page['relations'] if r['note_id']=='note-5']),3)

    def test_changed_source_rejected_before_extraction(self):
        with patch.object(sl,'extract_pages',side_effect=AssertionError('must not extract')):
            with self.assertRaises(ValueError):sl.parse(self.raw+b'changed',self.profile)

    def test_changed_word_coordinates_rejected(self):
        pages=sl.extract_pages(self.raw);pages[0]['words'][0]['bbox'][0]+=0.01
        with patch.object(sl,'extract_pages',return_value=pages):
            with self.assertRaises(ValueError):sl.parse(self.raw,self.profile)

    def test_lost_duplicated_or_reassigned_words_rejected(self):
        for mode in ('lost','duplicate','reassigned'):
            profile=copy.deepcopy(self.profile);groups=profile['pages'][0]['groups']
            if mode=='lost':groups[0]['word_ids'].pop()
            elif mode=='duplicate':groups[1]['word_ids'].append(groups[0]['word_ids'][0])
            else:groups[1]['word_ids'].append(groups[0]['word_ids'].pop())
            with self.assertRaises(ValueError):sl.parse(self.raw,profile)

    def test_wrong_footnote_link_and_scope_rejected(self):
        for field,value in [('note_id','note-11'),('scope_groups',['entry-1'])]:
            profile=copy.deepcopy(self.profile);profile['pages'][1]['relations'][0][field]=value
            with self.assertRaises(ValueError):sl.parse(self.raw,profile)

    def test_baseline_and_parser_versions_are_required(self):
        for key in ('expected_artifact_payload_sha256','parser_version'):
            profile=copy.deepcopy(self.profile);profile[key]='wrong'
            with self.assertRaises(ValueError):sl.parse(self.raw,profile)

    def review(self):
        a=self.artifact
        return dict(schema_version=1,artifact_sha256=sl.artifact_digest(a),profile_sha256=a['profile_sha256'],
            source_sha256=a['source_sha256'],parser_version=sl.PARSER_VERSION,pages=[23,24],
            reviewer=dict(id='synthetic-test-reviewer',independent_of_implementation=True),
            decision='accept_layout',findings=[])

    def test_separate_review_bound_to_every_artifact_dependency(self):
        self.assertEqual(sl.assess_review(self.artifact,None),'needs_independent_review')
        self.assertEqual(sl.assess_review(self.artifact,self.review()),'layout_reviewed_not_search_admitted')
        for key in ('artifact_sha256','profile_sha256','source_sha256','parser_version'):
            review=self.review();review[key]='wrong'
            self.assertEqual(sl.assess_review(self.artifact,review),'invalid_review_binding')
        review=self.review();review['reviewer']['independent_of_implementation']=False
        self.assertEqual(sl.assess_review(self.artifact,review),'invalid_review_provenance')
        review=self.review();review['decision']='changes_requested';review['findings']=['synthetic finding']
        self.assertEqual(sl.assess_review(self.artifact,review),'changes_requested')
        self.assertFalse(self.artifact['search_admitted'])

    def test_cli_is_idempotent_without_touching_database_or_source(self):
        db=sl.ROOT/'data/import/lawindex_offline.sqlite3'
        before=db.read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            for _ in range(2):
                with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                    self.assertEqual(sl.main(['--output-dir',temp]),0)
            artifacts=list(Path(temp).glob('*.json'));self.assertEqual(len(artifacts),1)
            self.assertEqual(json.loads(artifacts[0].read_text()),self.artifact)
            artifacts[0].write_text('tampered')
            with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                self.assertEqual(sl.main(['--output-dir',temp]),1)
            self.assertEqual(artifacts[0].read_text(),'tampered')
        self.assertEqual(before,db.read_bytes())
        self.assertEqual(self.raw,(sl.ROOT/'data/discovery/rti-2005-pdf.body').read_bytes())
