"""Known central Act titles that are not among the indexed Acts.

Naming one adds an act_not_indexed notice. The notice does not hide results,
and a cited title the index does not hold still returns nothing, as before.
"""
import json
import unittest

from lawindex.search import ROOT, Snapshot, validate_known_titles


class KnownTitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Snapshot()

    def messages(self, query):
        return [n['message'] for n in self.s.search(query)['notices'] if n['code'] == 'act_not_indexed']

    def test_title_and_short_name_forms_ignore_case(self):
        cases = [
            ('Income-tax Act', 'Income-tax Act'),
            ('the income-tax act', 'Income-tax Act'),
            ('The Income-tax Act, 1961', 'Income-tax Act'),
            ('Income Tax Act', 'Income-tax Act'),
            ('IPC', 'Indian Penal Code'),
            ('ipc', 'Indian Penal Code'),
            ('CrPC', 'Code of Criminal Procedure'),
            ('crpc', 'Code of Criminal Procedure'),
            ('GST', 'Central Goods and Services Tax Act'),
            ('cgst act', 'Central Goods and Services Tax Act'),
            ('Companies Act, 2013', 'Companies Act'),
            ('the companies act', 'Companies Act'),
            ('Hindu Marriage Act', 'Hindu Marriage Act'),
            ('bns', 'Bharatiya Nyaya Sanhita'),
            ('BSA', 'Bharatiya Sakshya Adhiniyam'),
            ('National Green Tribunal Act, 2010', 'National Green Tribunal Act'),
        ]
        for query, fragment in cases:
            messages = self.messages(query)
            self.assertTrue(any(fragment in message for message in messages), (query, messages))

    def test_bnss_does_not_also_match_bns(self):
        bnss = self.messages('BNSS')
        self.assertEqual(bnss, self.messages('bnss'))
        self.assertEqual(len(bnss), 1)
        self.assertIn('Nagarik Suraksha', bnss[0])
        self.assertNotIn('Nyaya', bnss[0])
        self.assertEqual(self.messages('XBNS'), [])
        self.assertEqual(self.messages('BNSSX'), [])
        bns = self.messages('bns')
        self.assertEqual(len(bns), 1)
        self.assertIn('Nyaya', bns[0])
        self.assertNotIn('Suraksha', bns[0])

    def test_indexed_act_gets_no_notice(self):
        for query in ['The Right to Information Act, 2005 section 8',
                      'the right to information act',
                      'RTI Act section 6',
                      'Environment (Protection) Act section 3',
                      'POSH Act']:
            self.assertEqual(self.messages(query), [], query)

    def test_indexed_mention_does_not_hide_a_different_act(self):
        result = self.s.search('IPC and the Right to Information Act')
        messages = [n['message'] for n in result['notices'] if n['code'] == 'act_not_indexed']
        self.assertEqual(messages, ['\u201cThe Indian Penal Code, 1860\u201d is not one of the indexed Acts.'])
        self.assertTrue(result['results'])
        self.assertTrue(all(r['act_slug'] == 'rti-2005' for r in result['results']))

    def test_notice_does_not_hide_results(self):
        bare = self.s.search('seafarer wages abandoned')
        named = self.s.search('seafarer wages abandoned BNSS')
        self.assertTrue(bare['results'])
        self.assertEqual([r['key'] for r in named['results']], [r['key'] for r in bare['results']])
        self.assertEqual(named['total'], bare['total'])
        self.assertEqual(self.messages('seafarer wages abandoned'), [])
        self.assertIn('Nagarik Suraksha', self.messages('seafarer wages abandoned BNSS')[0])

    def test_unmatched_cited_title_is_unchanged(self):
        result = self.s.search('National Green Tribunal Act, 2010')
        self.assertEqual(result['results'], [])
        self.assertEqual(result['trace']['citation']['cited_title_unmatched'], True)
        shown = [n for n in result['notices'] if n['code'] == 'act_not_indexed']
        self.assertEqual(len(shown), 1)
        self.assertIn('no results are shown', shown[0]['message'])

    def test_validator_rejects_duplicates_short_names_and_collisions(self):
        indexed = [act['title'] for act in self.s.acts.values()]
        self.assertEqual(len(indexed), 20)
        good = {'title': 'The Sale of Goods Act, 1930', 'short_names': ['SOGA'], 'year': 1930}
        self.assertEqual(validate_known_titles([good], indexed), [good])
        with self.assertRaisesRegex(ValueError, 'short'):
            validate_known_titles([{**good, 'short_names': ['IT']}], indexed)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            validate_known_titles([good, {'title': 'The Sale of Goods Act, 1930', 'short_names': [], 'year': 1930}], indexed)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            validate_known_titles([
                good,
                {'title': 'Sale of Goods Act', 'short_names': [], 'year': 1930},
            ], indexed)
        with self.assertRaisesRegex(ValueError, 'collid'):
            validate_known_titles([
                {'title': 'The Right to Information Act, 2005', 'short_names': [], 'year': 2005},
            ], indexed)
        with self.assertRaisesRegex(ValueError, 'collid'):
            validate_known_titles([
                {'title': 'Right to Information Act', 'short_names': [], 'year': 2005},
            ], indexed)

    def test_list_is_names_only_and_recorded_as_unverified(self):
        data = json.loads((ROOT / 'data/reference/central_act_titles.v1.json').read_text())
        provenance = data['provenance'].lower()
        self.assertIn('model', provenance)
        self.assertIn('network', provenance)
        self.assertIn('unverified', provenance)
        self.assertLessEqual(len(data['titles']), 60)
        self.assertEqual(len(self.s.known_titles), len(data['titles']))
        for entry in data['titles']:
            self.assertEqual(set(entry), {'title', 'short_names', 'year'})
            self.assertNotIn('text', entry)
            for name in entry['short_names']:
                self.assertGreaterEqual(len(name.strip()), 3)


if __name__ == '__main__':
    unittest.main()
