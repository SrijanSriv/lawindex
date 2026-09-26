"""No network: adversarial checks for bounded capture and non-admitting candidates."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import acquire_phase3 as ac
from scripts import phase3_candidates as pc
from lawindex.coverage import build_coverage


class PipelineTests(unittest.TestCase):
    def test_url_boundary_rejects_redirect_destinations(self):
        for url in ['http://indiacode.gov.in/server/api/a','https://evil.test/server/api/a',
                    'https://indiacode.gov.in.evil.test/server/api/a','https://indiacode.gov.in:443/server/api/a',
                    'https://indiacode.gov.in/server/api/a#fragment','https://user@indiacode.gov.in/server/api/a']:
            with self.assertRaises(ValueError):ac.validate_url(url)
        self.assertEqual(ac.validate_url(ac.BASE+'/core/items/example'),ac.BASE+'/core/items/example')

    def test_inventory_cap_duplicates_and_path_safety(self):
        for records in [[],[dict(slug=f'a-{i}',title=f'Act {i}') for i in range(21)],
                        [dict(slug='a',title='A'),dict(slug='a',title='B')],
                        [dict(slug='../a',title='A')]]:
            with self.assertRaises(ValueError):ac.validate_inventory(dict(records=records))

    def test_cached_success_rechecks_hash_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp);url=ac.BASE+'/example';raw=b'{}';digest=ac.sha(raw)
            (dest/'blobs').mkdir();(dest/'blobs'/(digest+'.body')).write_bytes(raw)
            ac.atomic_json(dest/'receipts'/(ac.sha(url.encode())+'.json'),dict(url=url,status=200,curl_exit=0,sha256=digest))
            with patch.object(ac.subprocess,'run',side_effect=AssertionError('network not expected')):
                self.assertEqual(ac.Capture(dest).get(url),raw)
                (dest/'blobs'/(digest+'.body')).write_bytes(b'changed')
                with self.assertRaises(ValueError):ac.Capture(dest).get(url)

    def test_partial_200_is_not_reused_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp);url=ac.BASE+'/example'
            ac.atomic_json(dest/'receipts'/(ac.sha(url.encode())+'.json'),dict(url=url,status=200,curl_exit=18,sha256='0'*64))
            with patch.object(ac.subprocess,'run',return_value=SimpleNamespace(stdout=b'302',stderr=b'',returncode=0)) as run:
                with self.assertRaises(ValueError):ac.Capture(dest).get(url)
                self.assertEqual(run.call_count,1)
                self.assertNotIn('--location',run.call_args.args[0])

    def test_retry_is_bounded_and_failure_observations_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ac.time,'sleep'),patch.object(ac.subprocess,'run',return_value=SimpleNamespace(stdout=b'503',stderr=b'',returncode=0)) as run:
                with self.assertRaises(ValueError):ac.Capture(Path(tmp)).get(ac.BASE+'/example')
                self.assertEqual(run.call_count,3)
                self.assertEqual(len(list((Path(tmp)/'observations').glob('*.json'))),3)

    def test_whitespace_only_alignment_preserves_punctuation_and_boundaries(self):
        self.assertEqual(pc.locate('Legal text.', ['Heading. Legal\n text.'])['pdf_page_from'],1)
        for body,pages in [('cat',['concatenate']),('Legal text',['Legal texts']),
                           ('Legal text.',['Legal text!']),('same',['same same'])]:
            with self.assertRaises(ValueError):pc.locate(body,pages)
        result=pc.locate('first second',['first','second'])
        self.assertEqual((result['pdf_page_from'],result['pdf_page_to']),(1,2))

    def test_unknown_markup_quarantines_instead_of_silently_deleting(self):
        self.assertEqual(pc.plain('word<sup>1</sup><br/>next &amp; last'),'word1\nnext & last')
        for html in ('<table><tr><td>x</td></tr></table>','<script>x</script>','<img src=x>'):
            with self.assertRaises(ValueError):pc.plain(html)

    def test_actual_acquisition_materialization_is_hash_bound(self):
        act=json.loads((ac.DEST/'acts/rti-2005.json').read_text())
        ac.verify_acquisition(act)
        for mutate in (lambda a:a['sections'][0].update(name='changed'),
                       lambda a:a.update(section_count=0),
                       lambda a:a['pdfs'][0].update(sha256='0'*64),
                       lambda a:a['item'].update(name='changed')):
            changed=copy.deepcopy(act);mutate(changed)
            with self.assertRaises(ValueError):ac.verify_acquisition(changed)

    def test_missing_and_failed_acts_have_explicit_unknown_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            inventory=dict(inventory_id='test',records=[dict(slug='a',title='A'),dict(slug='b',title='B')])
            ac.atomic_json(root/'data/phase3/inventory.v1.json',inventory)
            ac.atomic_json(root/'data/phase3/acquisition/acts/b.json',dict(slug='b',inventory_sha256=ac.sha(ac.canonical(inventory).encode()),status='acquisition_failed',error='503'))
            report=build_coverage(root,SimpleNamespace(records={}))
            self.assertEqual(report['selected_act_count'],2)
            self.assertEqual(report['captured_act_count'],0)
            self.assertEqual([r['acquisition_status'] for r in report['rows']],['not_requested','acquisition_failed'])
            self.assertTrue(all(r['source_section_count'] is None for r in report['rows']))

    def test_coverage_cannot_admit_candidate_text(self):
        report=build_coverage(ac.ROOT,SimpleNamespace(records={}))
        self.assertEqual(report['selected_act_count'],20)
        self.assertEqual(report['searchable_provision_count'],0)
        self.assertTrue(all(not row['full_act_coverage_verified'] for row in report['rows']))


if __name__=='__main__':unittest.main()
