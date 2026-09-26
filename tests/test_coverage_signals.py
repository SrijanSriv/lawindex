"""Coverage signals and per-Act balance (Phase 3 audit items B1 and B2).

Notices say where a query reaches outside the index; they never hide results.
The per-Act cap stops one long Act taking over a generic query's page, but
leaves a focused query's strong results in place and never changes `total`.
"""
import json
import threading
import unittest
from urllib.request import urlopen

from lawindex.retrieval import Candidate, COMPETITIVE_SHARE, cap_per_act
from lawindex.search import ROOT, Snapshot
from lawindex.server import make_server


def records_for(acts):
    return {key: {'act_slug': act} for key, act in acts.items()}


class CapPerActTests(unittest.TestCase):
    def test_generic_query_is_spread_and_reports_what_it_held_back(self):
        # Ten close scores, eight from one Act.
        acts = {f'a{i}': 'big' for i in range(8)} | {'b0': 'b', 'c0': 'c'}
        candidates = [Candidate(k, -10.0 + i * 0.1) for i, k in enumerate(acts)]
        page, left_out = cap_per_act(candidates, records_for(acts), 3, 5)
        self.assertEqual([c.key for c in page], ['a0', 'a1', 'a2', 'b0', 'c0'])
        self.assertEqual(left_out, {'big': 5})

    def test_focused_query_keeps_its_strong_results(self):
        # One Act scores far above everything else: the weak matches from
        # other Acts must not be promoted over it.
        acts = {f'a{i}': 'big' for i in range(6)} | {'b0': 'b', 'c0': 'c'}
        scores = [-15.0, -14.9, -14.8, -14.7, -14.6, -14.5, -5.0, -4.0]
        candidates = [Candidate(k, s) for k, s in zip(acts, scores)]
        self.assertLess(5.0, COMPETITIVE_SHARE * 15.0)
        page, _ = cap_per_act(candidates, records_for(acts), 3, 5)
        self.assertEqual([c.key for c in page], ['a0', 'a1', 'a2', 'a3', 'a4'])

    def test_page_is_filled_in_rank_order_when_other_acts_run_out(self):
        acts = {f'a{i}': 'big' for i in range(6)} | {'b0': 'b'}
        candidates = [Candidate(k, -10.0) for k in acts]
        page, left_out = cap_per_act(candidates, records_for(acts), 2, 5)
        self.assertEqual(len(page), 5)
        self.assertEqual([c.key for c in page], ['a0', 'a1', 'a2', 'a3', 'b0'])
        self.assertEqual(left_out, {'big': 2})
        self.assertEqual(cap_per_act([], {}, 3, 5), ([], {}))


class SearchBalanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Snapshot(ROOT)

    def acts(self, result):
        counts = {}
        for r in result['results']:
            counts[r['act_slug']] = counts.get(r['act_slug'], 0) + 1
        return counts

    def test_generic_query_no_longer_dominated_and_total_is_unchanged(self):
        result = self.s.search('power to make rules')
        cap = result['trace']['diversity']['per_act_cap']
        self.assertTrue(result['trace']['diversity']['applied'])
        self.assertLessEqual(max(self.acts(result).values()), cap)
        self.assertGreaterEqual(len(self.acts(result)), 4)
        # Every match still counts; only the page composition changed.
        from lawindex.retrieval import LexicalRetriever, RetrievalRequest, SearchFilters
        from lawindex.search import ALIASES
        plain = LexicalRetriever(ALIASES).retrieve(self.s.records, RetrievalRequest(
            result['trace']['match_expression'], None, (), SearchFilters(), 10))
        self.assertEqual(result['total'], plain.total)
        held = {m['act_slug']: m['close_matches_not_shown'] for m in result['more_in_acts']}
        self.assertTrue(held and all(count > 0 for count in held.values()))

    def test_focused_query_keeps_its_act(self):
        result = self.s.search('seafarer wages abandoned')
        self.assertEqual(set(self.acts(result)), {'merchant-shipping-2025'})
        self.assertFalse(result['trace']['diversity']['applied'])
        self.assertEqual(result['more_in_acts'], [])

    def test_no_cap_when_the_query_names_an_act(self):
        for query, kwargs in [('RTI appeal', {}), ('Act 22 of 2005 appeal', {})]:
            result = self.s.search(query, **kwargs)
            self.assertIsNone(result['trace']['diversity']['per_act_cap'], query)
            self.assertEqual(result['more_in_acts'], [], query)


class CoverageNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Snapshot(ROOT)

    def codes(self, query):
        return [n['code'] for n in self.s.search(query)['notices']]

    def test_each_kind_of_uncovered_query_is_named(self):
        for query, code in [('National Green Tribunal Act, 2010', 'act_not_indexed'),
                            ('RTI First Schedule oath or affirmation', 'schedules_not_indexed'),
                            ('RTI Rules 2012 application fee', 'instruments_not_indexed'),
                            ('rti rules, 2012 fee', 'instruments_not_indexed'),
                            ('Supreme Court judgments interpreting the right to information', 'case_law_not_indexed'),
                            ('Uttar Pradesh rent control eviction rules', 'state_law_not_indexed'),
                            ('quantum entanglement photon lattice', 'weak_match')]:
            self.assertIn(code, self.codes(query), query)

    def test_in_scope_queries_carry_no_notice(self):
        for query in ['RTI Act section 6', 'power to make rules', 'appeal to the High Court',
                      'seafarer wages abandoned', 'processing personal data of children',
                      'Do I need to explain why I want information in an RTI request?']:
            self.assertEqual(self.codes(query), [], query)

    def test_notices_never_hide_results_and_scope_is_always_stated(self):
        result = self.s.search('Uttar Pradesh rent control eviction rules')
        self.assertTrue(result['results'])
        scope = result['scope']
        self.assertEqual(scope['provision_count'], len(self.s.records))
        self.assertEqual(scope['act_count'], len({p['act_slug'] for p in self.s.records.values()}))
        for words in ('schedules', 'rules and regulations', 'state laws', 'court judgments', 'held back'):
            self.assertIn(words, scope['statement'])
        # Quoting changes citation parsing, not scope: a quoted schedule is
        # still a schedule the index does not hold.
        self.assertIn('schedules_not_indexed', self.codes('"Second Schedule"'))

    def test_http_response_carries_notices_scope_and_more_in_acts(self):
        server = make_server(ROOT, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/search?q=power%20to%20make%20rules') as response:
            data = json.load(response)
        self.assertIn('statement', data['scope'])
        self.assertEqual(data['notices'], [])
        self.assertTrue(data['more_in_acts'])
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/search?q=RTI%20Rules%202012%20fee') as response:
            self.assertIn('instruments_not_indexed', [n['code'] for n in json.load(response)['notices']])


if __name__ == '__main__':
    unittest.main()
