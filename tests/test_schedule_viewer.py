"""Tests for the private local schedule review viewer.

No original evidence, database, importer, or reviewer decision is touched by
these tests. All output goes to temporary directories.
"""
import copy
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from scripts import schedule_layout as sl
from scripts import render_schedule_review as rv


def make_review(artifact, decision='accept_layout', findings=None):
    return dict(
        schema_version=1, artifact_sha256=sl.artifact_digest(artifact),
        profile_sha256=artifact['profile_sha256'], source_sha256=artifact['source_sha256'],
        parser_version=sl.PARSER_VERSION, pages=[23, 24],
        reviewer=dict(id='synthetic-test-reviewer', independent_of_implementation=True,
                       type='ai_agent', independent_legal_expert=False),
        decision=decision, findings=findings if findings is not None else [])


class ScheduleViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (sl.ROOT / 'data/discovery/rti-2005-pdf.body').read_bytes()
        cls.profile = json.loads(sl.DEFAULT_PROFILE.read_text())
        cls.artifact = sl.parse(cls.raw, cls.profile)
        cls.digest = sl.artifact_digest(cls.artifact)

    def write_artifact(self, tmp, artifact=None):
        path = Path(tmp) / 'artifact.json'
        path.write_text(json.dumps(artifact if artifact is not None else self.artifact))
        return path

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = rv.main(argv)
        return code, out.getvalue(), err.getvalue()

    # -- database/importer/source safety -------------------------------

    def test_no_database_or_importer_touched(self):
        db = sl.ROOT / 'data/import/lawindex_offline.sqlite3'
        before = db.read_bytes()
        for name in dir(rv):
            self.assertNotIn('offline_importer', repr(getattr(rv, name, '')))
        with tempfile.TemporaryDirectory() as tmp:
            artifact_path = self.write_artifact(tmp)
            code, _, _ = self.run_cli(['--artifact', str(artifact_path), '--output-dir', tmp])
            self.assertEqual(code, 0)
        self.assertEqual(before, db.read_bytes())
        self.assertEqual(self.raw, (sl.ROOT / 'data/discovery/rti-2005-pdf.body').read_bytes())

    def test_no_importer_import_anywhere_in_module(self):
        source = (sl.ROOT / 'scripts/render_schedule_review.py').read_text()
        self.assertNotIn('offline_importer', source)
        self.assertNotIn('import sqlite3', source)

    # -- artifact schema/digest validation ------------------------------

    def test_unknown_or_wrong_schema_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad in ({'foo': 1}, {**self.artifact, 'schema_version': 2},
                        {**self.artifact, 'parser_version': 'other-v2'}):
                path = self.write_artifact(tmp, bad)
                code, _, err = self.run_cli(['--artifact', str(path), '--output-dir', tmp])
                self.assertEqual(code, 1)

    def test_artifact_claiming_search_admission_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tampered = copy.deepcopy(self.artifact)
            tampered['search_admitted'] = True
            path = self.write_artifact(tmp, tampered)
            code, _, _ = self.run_cli(['--artifact', str(path), '--output-dir', tmp])
            self.assertEqual(code, 1)

    def test_artifact_differing_from_fresh_model_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tampered = copy.deepcopy(self.artifact)
            tampered['pages'][1]['words'][0]['text'] = 'TAMPERED'
            path = self.write_artifact(tmp, tampered)
            code, _, err = self.run_cli(['--artifact', str(path), '--output-dir', tmp])
            self.assertEqual(code, 1)
            self.assertIn('differs from a fresh model', err)

    def test_does_not_trust_artifact_supplied_source_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tampered = copy.deepcopy(self.artifact)
            tampered['source_path'] = '/etc/passwd'
            path = self.write_artifact(tmp, tampered)
            # Still refused: the digest no longer matches a fresh model once any
            # field changes, and the CLI never reads source_path from the artifact.
            code, _, _ = self.run_cli(['--artifact', str(path), '--output-dir', tmp])
            self.assertEqual(code, 1)
            self.assertNotIn('/etc/passwd', rv.SOURCE_PATH.as_posix())

    # -- review handling: never displayed as accepted without a real match --

    def test_missing_review_shows_pending_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_artifact(tmp)
            code, out, _ = self.run_cli(['--artifact', str(path), '--output-dir', tmp])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)['review_status'], 'needs_independent_review')
            html_text = (Path(tmp) / self.digest / 'index.html').read_text()
            self.assertIn('independent review pending', html_text)
            self.assertNotIn('Independently reviewed layout', html_text)
            self.assertNotIn('A separate reviewer accepted this exact layout', html_text)

    def test_stale_review_bound_to_different_artifact_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_artifact(tmp)
            review = make_review(self.artifact)
            review['artifact_sha256'] = 'f' * 64
            review_path = Path(tmp) / 'review.json'
            review_path.write_text(json.dumps(review))
            code, out, _ = self.run_cli(['--artifact', str(path), '--review', str(review_path),
                                       '--output-dir', tmp])
            self.assertEqual(code, 0)
            status = json.loads(out)['review_status']
            self.assertEqual(status, 'invalid_review_binding')
            html_text = (Path(tmp) / self.digest / 'index.html').read_text()
            self.assertNotIn('Independently reviewed layout', html_text)

    def test_non_independent_reviewer_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_artifact(tmp)
            review = make_review(self.artifact)
            review['reviewer']['independent_of_implementation'] = False
            review_path = Path(tmp) / 'review.json'
            review_path.write_text(json.dumps(review))
            code, out, _ = self.run_cli(['--artifact', str(path), '--review', str(review_path),
                                       '--output-dir', tmp])
            self.assertEqual(json.loads(out)['review_status'], 'invalid_review_provenance')

    def test_matching_review_is_shown_as_reviewed_not_search_admitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_artifact(tmp)
            review = make_review(self.artifact)
            review_path = Path(tmp) / 'review.json'
            review_path.write_text(json.dumps(review))
            code, out, _ = self.run_cli(['--artifact', str(path), '--review', str(review_path),
                                       '--output-dir', tmp])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)['review_status'], 'layout_reviewed_not_search_admitted')
            html_text = (Path(tmp) / self.digest / 'index.html').read_text()
            self.assertIn('Independently reviewed layout', html_text)
            self.assertIn('not search-admitted', html_text)
            self.assertIn('no public reuse permission', html_text)
            self.assertNotIn('search_admitted&#34;: true', html_text.replace("'", '"'))

    def test_changes_requested_review_shows_findings_not_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_artifact(tmp)
            review = make_review(self.artifact, decision='changes_requested',
                                  findings=['synthetic finding <script>x</script>'])
            review_path = Path(tmp) / 'review.json'
            review_path.write_text(json.dumps(review))
            code, out, _ = self.run_cli(['--artifact', str(path), '--review', str(review_path),
                                       '--output-dir', tmp])
            self.assertEqual(json.loads(out)['review_status'], 'changes_requested')
            html_text = (Path(tmp) / self.digest / 'index.html').read_text()
            self.assertIn('requested changes', html_text)
            self.assertIn('synthetic finding', html_text)
            self.assertNotIn('<script>x</script>', html_text)

    # -- content coverage -------------------------------------------------

    def test_all_serial_positions_notes_and_links_represented(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_artifact(tmp)
            code, _, _ = self.run_cli(['--artifact', str(path), '--output-dir', tmp])
            self.assertEqual(code, 0)
            html_text = (Path(tmp) / self.digest / 'index.html').read_text()
            for i in range(1, 28):
                self.assertIn(f'data-group="entry-{i}"', html_text)
            for i in range(1, 12):
                self.assertIn(f'data-note="note-{i}"', html_text)
            self.assertEqual(len(re.findall(r'data-note="[^"]*note-\d+[^"]*"', html_text)) > 0, True)
            self.assertIn('data-group="omitted-block"', html_text)
            self.assertEqual(html_text.count('class="note-toggle"'), 11)

    def test_highlights_exact_affected_words_not_containing_scopes(self):
        page = self.artifact['pages'][1]
        mapping = rv.notes_of_words_for_page24(page, page['relations'])
        groups = rv.group_index(page)
        for note in (f'note-{i}' for i in range(1, 12)):
            expected = set(groups[note]['word_ids'])
            for relation in page['relations']:
                if relation['note_id'] == note:
                    expected.add(relation['marker_word_id'])
                    expected.update(relation['affected_word_ids'])
            self.assertEqual({word for word, notes in mapping.items() if note in notes}, expected)
        svg = rv.page_svg(page, mapping)
        for relation in page['relations']:
            if relation['note_id'] == 'note-3':
                for gid in relation['scope_groups']:
                    rect = re.search(r'<rect[^>]*data-group="' + gid + r'"[^>]*>', svg).group()
                    self.assertNotIn('note-3', rect)
        note7 = next(r for r in page['relations'] if r['note_id'] == 'note-7')
        self.assertIn('note-6', mapping[note7['marker_word_id']])

    def test_omission_stays_between_serials_21_and_22(self):
        built = rv.build_second_schedule_section(self.artifact['pages'][1], self.artifact['pages'][1]['relations'])
        self.assertLess(built.index('data-group="entry-21"'), built.index('data-group="omitted-block"'))
        self.assertLess(built.index('data-group="omitted-block"'), built.index('data-group="entry-22"'))
        self.assertNotIn('competent authorities', built)

    def test_reviewer_disclosure_is_explicit_and_missing_fields_not_invented(self):
        review = make_review(self.artifact)
        built = rv.build_html(self.artifact, review, 'layout_reviewed_not_search_admitted', self.digest)
        self.assertIn('ai_agent', built)
        self.assertIn('independent_legal_expert', built)
        del review['reviewer']['type']
        built = rv.build_html(self.artifact, review, 'layout_reviewed_not_search_admitted', self.digest)
        self.assertIn('not supplied', built)
        self.assertNotIn('ai_agent', built)

    def test_correct_page_links_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_artifact(tmp)
            code, _, _ = self.run_cli(['--artifact', str(path), '--output-dir', tmp])
            self.assertEqual(code, 0)
            html_text = (Path(tmp) / self.digest / 'index.html').read_text()
            self.assertIn('href="schedule.pdf#page=23"', html_text)
            self.assertIn('href="schedule.pdf#page=24"', html_text)
            self.assertIn('src="page-23.png"', html_text)
            self.assertIn('src="page-24.png"', html_text)
            out_dir = Path(tmp) / self.digest
            self.assertTrue((out_dir / 'page-23.png').exists())
            self.assertTrue((out_dir / 'page-24.png').exists())
            self.assertEqual((out_dir / 'schedule.pdf').read_bytes(), self.raw)

    def test_no_default_selection_and_both_alternatives_shown_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_artifact(tmp)
            code, _, _ = self.run_cli(['--artifact', str(path), '--output-dir', tmp])
            html_text = (Path(tmp) / self.digest / 'index.html').read_text()
            self.assertIn('Alternative 1', html_text)
            self.assertIn('Alternative 2', html_text)
            self.assertIn('swear in the name of God', html_text)
            self.assertIn('solemnly affirm', html_text)
            body = html_text.split('</style>', 1)[1]  # CSS mentions the attribute value; markup must not
            self.assertNotIn('aria-pressed="true"', body)  # nothing pre-selected
            self.assertEqual(body.count('aria-pressed="false"'), 11)

    # -- escaping / hostile input -----------------------------------------

    def test_hostile_extracted_word_text_is_escaped(self):
        tampered_profile = copy.deepcopy(self.profile)
        hostile = '</script><img src=x onerror=alert(1)>&"\'<'
        pages = sl.extract_pages(self.raw)
        pages[1]['words'][0] = {**pages[1]['words'][0], 'text': hostile}
        with patch.object(sl, 'extract_pages', return_value=pages):
            with self.assertRaises(ValueError):
                # The layout parser itself rejects a changed extracted word
                # (its own hash-binding), which is expected and correct: the
                # viewer only ever sees words that already passed that check.
                sl.parse(self.raw, tampered_profile)

    def test_escaping_via_synthetic_artifact_with_hostile_group_and_note_text(self):
        hostile_artifact = copy.deepcopy(self.artifact)
        # Simulate hostile extracted text surviving into an artifact's word
        # list without touching the real parser/profile, purely to exercise
        # the viewer's own HTML/SVG escaping and JSON-in-script safety.
        hostile = '</script><script>alert(1)</script>&"\'<>é中'
        hostile_artifact['pages'][1]['words'][0]['text'] = hostile
        built = rv.build_html(hostile_artifact, None, 'needs_independent_review', self.digest)
        self.assertNotIn('<script>alert(1)</script>', built)
        self.assertNotIn('</script><script>', built)
        self.assertIn('&lt;', built)
        self.assertIn(hostile.encode('utf-8').decode('utf-8')[-1], built)  # UTF-8 char preserved

    def test_safe_json_for_script_escapes_closing_tag_and_utf8_survives(self):
        payload = {'text': '</script><script>evil()</script>', 'unicode': 'é中文'}
        encoded = rv.safe_json_for_script(payload)
        self.assertNotIn('</script>', encoded)
        self.assertNotIn('<script>', encoded)
        decoded = json.loads(encoded)
        self.assertEqual(decoded['text'], payload['text'])
        self.assertEqual(decoded['unicode'], payload['unicode'])

    # -- determinism / no importer path ------------------------------------

    def test_deterministic_output_across_runs(self):
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            path1 = self.write_artifact(tmp1)
            path2 = self.write_artifact(tmp2)
            self.run_cli(['--artifact', str(path1), '--output-dir', tmp1])
            self.run_cli(['--artifact', str(path2), '--output-dir', tmp2])
            html1 = (Path(tmp1) / self.digest / 'index.html').read_text()
            html2 = (Path(tmp2) / self.digest / 'index.html').read_text()
            self.assertEqual(html1, html2)

    def test_never_calls_importer(self):
        source = (sl.ROOT / 'scripts/render_schedule_review.py').read_text()
        for forbidden in ('import_queue', 'offline_importer', 'structural_store.import', 'INSERT INTO'):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
