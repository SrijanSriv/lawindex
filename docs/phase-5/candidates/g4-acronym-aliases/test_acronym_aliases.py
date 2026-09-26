"""Acronym aliases select an Act by whole word and never a bare "IT"."""
import unittest

from lawindex.search import ROOT, Snapshot


class AcronymAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Snapshot(ROOT)

    def test_rera_section_18_returns_that_section_first(self):
        result = self.s.search('RERA section 18')
        self.assertTrue(result['results'])
        self.assertEqual(result['results'][0]['key'], 'real-estate-2016:18')

    def test_dpdp_act_citation_selects_the_indexed_act(self):
        result = self.s.search('DPDP Act 2023 obligations of data fiduciary')
        self.assertNotIn('act_not_indexed', [notice['code'] for notice in result['notices']])
        self.assertEqual(result['trace']['act_filters'], ['dpdp-2023'])

    def test_ordinary_word_it_selects_no_act(self):
        result = self.s.search('how does it apply')
        self.assertEqual(result['trace']['act_filters'], [])


if __name__ == '__main__':
    unittest.main()
