"""Phrase/citation parsing, excerpt context and neighbour navigation.

Constraints narrow; nothing here widens admission or falls back to another
Act or section. Read-only against the live ten-provision snapshot.
"""
import json
import threading
import unittest
from urllib.request import urlopen

from lawindex.retrieval import SearchFilters
from lawindex.retrieval import section_order
from lawindex.search import ROOT, Snapshot, excerpt, excerpt_context, parse_query
from lawindex.server import make_server


class ParseQueryTests(unittest.TestCase):
    def test_phrases_are_literal_and_outside_reference_parsing(self):
        parsed = parse_query('complaint "three months" “in writing”')
        self.assertEqual(parsed['phrases'], [('three', 'months'), ('in', 'writing')])
        self.assertEqual(parsed['terms'], ['complaint'])
        # A quoted "section 6" is a phrase, not a section constraint.
        parsed = parse_query('"section 6" information')
        self.assertIsNone(parsed['section'])
        self.assertEqual(parsed['phrases'], [('section', '6')])
        self.assertEqual(parse_query('"" "!!!" information')['phrases'], [])
        self.assertEqual(len(parse_query(' '.join('"w%d"' % i for i in range(9)))['phrases']), 5)

    def test_cited_title_is_the_capitalised_name_before_act(self):
        for query, title in [('National Green Tribunal Act, 2010', 'National Green Tribunal'),
                             ('The Right to Information Act, 2005 section 8', 'The Right to Information'),
                             ('Environment (Protection) Act, 1986', 'Environment (Protection)'),
                             ('complaint under the POSH Act, 2013', 'POSH'),
                             ('Act, 2013', None), ('appeal procedure Act, 2005', None),
                             ('The Act, 2005', None), ('Act 22 of 2005', None), ('2005 Act appeal', None)]:
            self.assertEqual(parse_query(query)['cited_title'], title, query)
        # Quoted text is literal and never a citation.
        self.assertIsNone(parse_query('"National Green Tribunal Act, 2010"')['cited_title'])

    def test_citations_constrain_and_never_become_terms(self):
        parsed = parse_query('Act 22 of 2005 section 6 appeal')
        self.assertEqual((parsed['act_number'], parsed['year'], parsed['section']), ('22', '2005', '6'))
        self.assertEqual(parsed['terms'], ['6', 'appeal'])
        for query in ['RTI Act, 2005', 'RTI Act of 2005', '2005 Act', 'act 2005']:
            self.assertEqual(parse_query(query)['year'], '2005', query)
            self.assertNotIn('2005', parse_query(query)['terms'], query)
        parsed = parse_query('No. 022 of 2005')
        self.assertEqual(parsed['act_number'], '22')
        # A bare year with no "Act" is ordinary text, not a citation.
        self.assertIsNone(parse_query('appeal 2010')['year'])
        with self.assertRaises(ValueError):
            parse_query('x' * 501)


class ExcerptContextTests(unittest.TestCase):
    TEXT = ('(1) First rule applies:\n Provided that an exception exists.\n (2) Second rule refers to sub-section (1) '
            'and clause (a).\n (3) Third rule.')

    def test_context_follows_line_start_markers_not_cross_references(self):
        self.assertEqual(excerpt_context(self.TEXT, self.TEXT.index('First')), {'subsection': '1', 'proviso': False})
        self.assertEqual(excerpt_context(self.TEXT, self.TEXT.index('exception')), {'subsection': '1', 'proviso': True})
        self.assertEqual(excerpt_context(self.TEXT, self.TEXT.index('refers')), {'subsection': '2', 'proviso': False})
        self.assertEqual(excerpt_context(self.TEXT, self.TEXT.index('clause')), {'subsection': '2', 'proviso': False})
        self.assertEqual(excerpt_context(self.TEXT, self.TEXT.index('Third')), {'subsection': '3', 'proviso': False})
        self.assertIsNone(excerpt_context(self.TEXT, None))
        heading = '8. Exemption.—(1) Notwithstanding anything.'
        self.assertEqual(excerpt_context(heading, heading.index('Exemption')), {'subsection': None, 'proviso': False})
        self.assertEqual(excerpt_context(heading, heading.index('Notwithstanding')), {'subsection': '1', 'proviso': False})

    def test_phrase_anchors_window_and_highlights_whole_phrase(self):
        text = 'reason first. ' + 'x ' * 200 + 'no reason to give any reason here.'
        e = excerpt(text, ['reason'], (('give', 'any', 'reason'),))
        self.assertIn('give any reason', e['text'])
        self.assertEqual(e['text'], text[e['start']:e['end']])
        self.assertIn('give any reason', [seg['text'] for seg in e['segments'] if seg['match']])
        self.assertEqual(''.join(seg['text'] for seg in e['segments']), e['text'])
        # No phrase occurrence: fall back to the first term, never fail.
        self.assertEqual(excerpt(text, ['reason'], (('absent', 'phrase'),))['start'], 0)
        self.assertIsNone(excerpt('nothing matches', ['zzz'])['context'])


class SnapshotQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Snapshot(ROOT)

    def keys(self, query, **filters):
        return [r['key'] for r in self.s.search(query, filters=SearchFilters(**filters))['results']]

    def test_phrase_is_a_constraint_applied_before_ranking(self):
        self.assertEqual(self.keys('"give any reason"'), ['rti-2005:6'])
        self.assertEqual(self.keys('"zzz never present"'), [])
        loose = self.s.search('information')['total']
        constrained = self.s.search('information "three months"', limit=20)
        self.assertGreater(loose, constrained['total'])
        self.assertIn('posh-2013:9', [r['key'] for r in constrained['results']])
        # FTS5 phrases are stemmed, so "three month's wages" satisfies "three months".
        for r in constrained['results']:
            self.assertRegex(self.s.records[r['key']]['body_text'], r'(?i)\bthree\W+month')
        self.assertEqual(constrained['trace']['phrases'], ['three months'])
        # Phrase constraints intersect with Act and section references.
        self.assertEqual(self.keys('RTI "three months"'), [])
        nine = self.s.search('section 9 "three months"', limit=20)['results']
        self.assertIn('posh-2013:9', [r['key'] for r in nine])
        self.assertTrue(all(r['section_number'] == '9' for r in nine))
        for query in ['"', '" OR *', '"NEAR(a b)"', '"x" "y" "z" "w" "v" "u"']:
            self.assertIsInstance(self.s.search(query)['results'], list)

    def test_citation_constraints_have_no_fallback(self):
        rti = {k for k in self.s.records if k.startswith('rti-2005:')}
        cited = self.s.search('Act 22 of 2005', limit=20)
        self.assertEqual(cited['total'], len(rti))
        self.assertTrue({r['key'] for r in cited['results']} <= rti)
        self.assertEqual(self.keys('Act 22 of 2005 section 6'), ['rti-2005:6'])
        self.assertEqual(self.keys('Act 99 of 2005'), [])
        self.assertEqual(self.keys('Act 22 of 2013'), [])
        # A cited year selects every Act of that year, by recorded year or by
        # the year in its own title -- the Competition Act, 2002 is Act 12 of
        # 2003, so both citations must reach it.
        cited = self.s.search('Act, 2013', limit=20)
        self.assertEqual(cited['total'], sum(
            '2013' in {p['metadata']['year'], p['title_year']} for p in self.s.records.values()))
        # The trace is bounded to returned candidates, so a corpus-wide year
        # citation is checked by its total; naming the Act narrows it exactly.
        posh = self.s.search('POSH Act, 2013', limit=20)
        self.assertEqual(posh['total'], sum(k.startswith('posh-2013:') for k in self.s.records))
        self.assertTrue(all(r['key'].startswith('posh-2013:') for r in posh['results']))
        self.assertEqual(self.keys('POSH Act, 2005'), [])
        for r in cited['results']:
            self.assertIn('2013', {r['metadata']['year'], r['title_year']}, r['key'])
        self.assertEqual(self.keys('Act 22 of 2005 section 99'), [])
        # A cited title naming no admitted Act is an empty answer. It is never
        # a fallback to another Act of the same year (the FCRA is also 2010),
        # nor a lexical match on provisions that merely mention that year.
        result = self.s.search('National Green Tribunal Act, 2010')
        self.assertEqual(result['results'], [])
        self.assertEqual(result['trace']['citation'], {'act_number': None, 'year': '2010',
                                                       'cited_title': 'National Green Tribunal',
                                                       'cited_title_unmatched': True})
        self.assertNotIn('2010', result['trace']['terms'])
        self.assertTrue(any(r['metadata']['year'] == '2010' for r in self.s.records.values()))
        # A cited title that does name an admitted Act narrows to it, including
        # a parenthesised title and one whose title year differs from its record.
        for query, slug in [('Foreign Contribution (Regulation) Act, 2010 section 24', 'fcra-2010'),
                            ('Environment (Protection) Act, 1986 section 3', 'environment-1986'),
                            ('Competition Act, 2002 section 7', 'competition-2002')]:
            found = self.s.search(query)
            self.assertFalse(found['trace']['citation']['cited_title_unmatched'], query)
            self.assertTrue(found['results'] and all(r['act_slug'] == slug for r in found['results']), query)
        # With no capitalised name before "Act", the year alone constrains.
        self.assertIsNone(self.s.search('appeal procedure Act, 2005')['trace']['citation']['cited_title'])
        self.assertTrue(all(r['act_slug'] == 'rti-2005' for r in self.s.search('appeal Act, 2005')['results']))
        self.assertEqual(self.keys('Act, 2013', year='2005'), [])
        self.assertEqual(self.s.search('Act, 2005', filters=SearchFilters(act='rti-2005'))['total'],
                         sum(k.startswith('rti-2005:') for k in self.s.records))

    def test_manifest_titles_resolve_without_hard_coded_aliases(self):
        for query, slug in [('Right to Information Act section 8', 'rti-2005'),
                            ('the right to information act, 2005 s. 3', 'rti-2005'),
                            ('Environment (Protection) Act section 4', 'environment-1986'),
                            ('POSH section 10', 'posh-2013'),
                            ('Sexual Harassment of Women at Workplace Act section 9', 'posh-2013')]:
            trace = self.s.search(query)['trace']
            self.assertEqual(trace['act_filters'], [slug], query)
        # A word inside a title is not a title: "information" alone selects nothing.
        self.assertEqual(self.s.search('information')['trace']['act_filters'], [])

    def test_result_excerpts_carry_context_from_reviewed_text(self):
        result = self.s.search('"give any reason"')
        self.assertEqual(result['results'][0]['excerpt']['context'], {'subsection': '2', 'proviso': False})
        result = self.s.search('"Provided further that"', limit=20, filters=SearchFilters(act='posh-2013'))
        posh = next(r for r in result['results'] if r['key'] == 'posh-2013:9')
        self.assertEqual(posh['excerpt']['context'], {'subsection': '1', 'proviso': True})
        for r in result['results']:
            self.assertTrue(r['excerpt']['context']['proviso'], r['key'])
        self.assertIn('not a separate structural admission', result['excerpt_context_note'])
        for r in self.s.search('information')['results']:
            e = r['excerpt']
            self.assertEqual(e['text'], self.s.records[r['key']]['body_text'][e['start']:e['end']])

    def test_navigation_orders_sections_naturally_and_stays_within_admitted(self):
        self.assertEqual(sorted(['10', '5A', '9', '3'], key=section_order), ['3', '5A', '9', '10'])
        nav = self.s.navigation('environment-1986:5A')
        labels = [p['section_number'] for p in nav['admitted']]
        self.assertEqual(labels, sorted(labels, key=section_order))
        index = labels.index('5A')
        self.assertEqual(nav['previous']['section_number'], labels[index - 1])
        self.assertEqual(nav['next']['section_number'], labels[index + 1])
        rti = self.s.navigation('rti-2005:6')
        first = self.s.navigation(rti['admitted'][0]['key'])
        last = self.s.navigation(rti['admitted'][-1]['key'])
        self.assertIsNone(first['previous'])
        self.assertIsNone(last['next'])
        self.assertEqual(first['source_section_count'], 31)
        self.assertIn('not indexed or reviewed', first['note'])
        with self.assertRaises(KeyError):
            self.s.navigation('rti-2005:99')
        corpus = self.s.corpus()
        for act in corpus['acts']:
            labels = [p['section_number'] for p in act['provisions']]
            self.assertEqual(labels, sorted(labels, key=section_order))

    def test_http_provision_includes_navigation(self):
        server = make_server(ROOT, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        first = Snapshot(ROOT).navigation('posh-2013:9')['admitted'][0]['key']
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/provisions/posh-2013%3A9') as response:
            data = json.load(response)
        self.assertEqual(data['navigation']['next']['key'], 'posh-2013:10')
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/provisions/{first.replace(":", "%3A")}') as response:
            self.assertIsNone(json.load(response)['navigation']['previous'])
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/search?q=%22three%20months%22') as response:
            data = json.load(response)
        self.assertIn('posh-2013:9', [r['key'] for r in data['results']])
        records = Snapshot(ROOT).records
        for r in data['results']:
            self.assertRegex(records[r['key']]['body_text'], r'(?i)\bthree\W+month')
        self.assertEqual(data['trace']['phrases'], ['three months'])


if __name__ == '__main__':
    unittest.main()
