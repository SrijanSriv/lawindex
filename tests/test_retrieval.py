"""Phase 3 retrieval boundaries: admission precedes ranking and constraints precede top-k."""
import unittest
from lawindex.retrieval import LexicalRetriever, RetrievalRequest, SearchFilters
from lawindex.search import Snapshot
from lawindex.server import make_server
import json
import threading
from urllib.request import urlopen
from urllib.error import HTTPError


def record(key, act, year, body='information', ministry=None):
    return dict(key=key, act_slug=act, act_title=act, section_number='6', heading='',
                body_text=body, footnote_text=None,
                metadata=dict(year=year, ministry=ministry, document_type='ACT'))


class RetrievalTests(unittest.TestCase):
    def test_constraints_before_limit_and_total_before_cut(self):
        records = {str(i): record(str(i), 'a' if i < 5 else 'b', '2005') for i in range(8)}
        request = RetrievalRequest('"information"', None, (), SearchFilters(act='b'), 2)
        result = LexicalRetriever({}).retrieve(records, request)
        self.assertEqual(result.total, 3)
        self.assertEqual([c.key for c in result.candidates], ['5', '6'])

    def test_missing_metadata_never_matches_and_filters_intersect(self):
        records = {'a': record('a', 'a', None), 'b': record('b', 'b', '2005', ministry='Example')}
        retriever = LexicalRetriever({})
        for filters, expected in [(SearchFilters(year='2005'), ['b']),
                                  (SearchFilters(ministry='example'), ['b']),
                                  (SearchFilters(act='a', year='2005'), []),
                                  (SearchFilters(document_type='Social'), [])]:
            result = retriever.retrieve(records, RetrievalRequest('', None, (), filters, 20))
            self.assertEqual([c.key for c in result.candidates], expected)

    def test_query_constraints_and_explicit_filters_intersect(self):
        s = Snapshot()
        self.assertEqual(s.search('RTI section 6', filters=SearchFilters(act='environment-1986'))['results'], [])
        expected = sum(p['metadata']['year'] == '2005' for p in s.records.values())
        self.assertGreater(expected, 0)
        result = s.search('', filters=SearchFilters(year='2005'), limit=1)
        self.assertEqual(result['total'], expected)
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['trace']['candidate_count'], expected)
        self.assertEqual(s.search('')['results'], [])

    def test_metadata_is_source_collection_not_subject_category(self):
        s = Snapshot()
        self.assertEqual(s.corpus()['filter_options']['document_type'], ['ACT'])
        self.assertEqual(s.records['rti-2005:6']['metadata']['year'], '2005')
        self.assertEqual(s.search('', filters=SearchFilters(document_type='Social'))['total'], 0)

    def test_invalid_filters_and_limits(self):
        for kwargs in [dict(year='05'), dict(year='２００５'), dict(year=2005),
                       dict(ministry=''), dict(act=' '), dict(document_type='x'*201)]:
            with self.assertRaises(ValueError):
                SearchFilters(**kwargs)
        s = Snapshot()
        for limit in (True, 0, 21, 1.5):
            with self.assertRaises(ValueError):
                s.search('RTI', limit)

    def test_live_admitted_input_only_and_no_unknown_act_fallback(self):
        s = Snapshot()
        before = s.search('', filters=SearchFilters(act='rti-2005'))['total']
        del s.records['rti-2005:8']
        self.assertEqual(s.search('', filters=SearchFilters(act='rti-2005'))['total'], before - 1)
        self.assertEqual(s.search('RTI', filters=SearchFilters(act='unknown'))['results'], [])
        self.assertEqual(s.search('RTI section 8')['results'], [])

    def test_http_filter_contract(self):
        server = make_server(port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'
        expected = sum(p['metadata']['year'] == '2005' for p in Snapshot().records.values())
        with urlopen(base + '/api/search?year=2005&limit=1') as response:
            result = json.load(response)
        self.assertEqual(result['total'], expected)
        self.assertEqual(len(result['results']), 1)
        for query in ('year=05', 'year=', 'year=2005&year=2005', 'act=', 'unknown=x'):
            with self.assertRaises(HTTPError) as error:
                urlopen(base + '/api/search?' + query)
            self.assertEqual(error.exception.code, 400)
        with urlopen(base + '/api/search?year=1900') as response:
            self.assertEqual(json.load(response)['results'], [])


if __name__ == '__main__':
    unittest.main()
