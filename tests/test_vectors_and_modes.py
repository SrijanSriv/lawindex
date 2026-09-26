"""Vector index binding and hybrid fusion, with a toy embedder. The toy embedder
exists only to exercise the index contract; it is not a retrieval method."""
import math
from pathlib import Path
import tempfile
import unittest

from lawindex import modes, vectors
from lawindex.retrieval import Candidate


def record(key, heading, body, title="The Toy Act, 2000"):
    return {"key": key, "act_title": title, "heading": heading, "body_text": body, "footnote_text": None}


RECORDS = {
    "toy:1": record("toy:1", "Wages", "wages paid to seafarers"),
    "toy:2": record("toy:2", "Leave", "annual leave with wages"),
    "toy:3": record("toy:3", "Offences", "penalty for an offence"),
}
VOCAB = ("wages", "seafarers", "leave", "penalty", "offence", "annual")


def toy_embed(texts):
    calls.append(len(texts))
    return [[text.lower().split().count(word) + 0.01 for word in VOCAB] for text in texts]


calls = []


class BuildTests(unittest.TestCase):
    def setUp(self):
        calls.clear()

    def test_vectors_are_unit_length_and_bound_to_corpus(self):
        index = vectors.build(RECORDS, toy_embed, "toy-v1")
        self.assertEqual(index.dim, len(VOCAB))
        self.assertEqual(sorted(index.vectors), sorted(RECORDS))
        for vector in index.vectors.values():
            self.assertAlmostEqual(math.sqrt(sum(v * v for v in vector)), 1.0, places=5)
        vectors.check(index, RECORDS, "toy-v1")

    def test_unchanged_text_is_not_re_embedded(self):
        first = vectors.build(RECORDS, toy_embed, "toy-v1", batch_size=2)
        self.assertEqual(calls, [2, 1])
        changed = dict(RECORDS, **{"toy:3": record("toy:3", "Offences", "fine for an offence")})
        calls.clear()
        second = vectors.build(changed, toy_embed, "toy-v1", previous=first)
        self.assertEqual(calls, [1])
        self.assertEqual(second.vectors["toy:1"], first.vectors["toy:1"])

    def test_another_model_re_embeds_everything(self):
        first = vectors.build(RECORDS, toy_embed, "toy-v1")
        calls.clear()
        vectors.build(RECORDS, toy_embed, "toy-v2", previous=first)
        self.assertEqual(calls, [3])

    def test_progress_is_reported_per_batch_and_resumes(self):
        partials = []
        vectors.build(RECORDS, toy_embed, "toy-v1", batch_size=2, on_batch=partials.append)
        self.assertEqual([len(p.vectors) for p in partials], [2, 3])
        calls.clear()
        vectors.build(RECORDS, toy_embed, "toy-v1", previous=partials[0])
        self.assertEqual(calls, [1])

    def test_bad_embedder_output_is_rejected(self):
        with self.assertRaises(ValueError):
            vectors.build(RECORDS, lambda texts: [[0.0] * 6 for _ in texts], "toy-v1")
        with self.assertRaises(ValueError):
            vectors.build(RECORDS, lambda texts: [[1.0] * (i + 2) for i, _ in enumerate(texts)], "toy-v1")
        with self.assertRaises(ValueError):
            vectors.build(RECORDS, lambda texts: [[1.0]], "toy-v1")
        with self.assertRaises(ValueError):
            vectors.build(RECORDS, toy_embed, "")


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.index = vectors.build(RECORDS, toy_embed, "toy-v1")

    def test_wrong_model_is_refused(self):
        with self.assertRaises(vectors.IndexMismatch):
            vectors.check(self.index, RECORDS, "toy-v2")

    def test_changed_corpus_is_refused(self):
        changed = dict(RECORDS, **{"toy:2": record("toy:2", "Leave", "leave")})
        with self.assertRaises(vectors.IndexMismatch):
            vectors.check(self.index, changed, "toy-v1")
        smaller = {k: v for k, v in RECORDS.items() if k != "toy:3"}
        with self.assertRaises(vectors.IndexMismatch):
            vectors.check(self.index, smaller, "toy-v1")


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.index = vectors.build(RECORDS, toy_embed, "toy-v1")

    def test_most_similar_first_and_only_eligible(self):
        query = toy_embed(["wages"])[0]
        ranked = vectors.search(self.index, query, set(RECORDS), 3)
        self.assertEqual([c.key for c in ranked][:2], ["toy:1", "toy:2"])
        self.assertGreater(ranked[0].score, ranked[-1].score)
        only = vectors.search(self.index, query, {"toy:3"}, 3)
        self.assertEqual([c.key for c in only], ["toy:3"])

    def test_wrong_dimension_query_is_refused(self):
        with self.assertRaises(vectors.IndexMismatch):
            vectors.search(self.index, [1.0, 2.0], set(RECORDS), 3)


class SaveLoadTests(unittest.TestCase):
    def test_round_trip_is_exact(self):
        index = vectors.build(RECORDS, toy_embed, "toy-v1")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.json"
            vectors.save(index, path)
            loaded = vectors.load(path)
        self.assertEqual(loaded, index)
        vectors.check(loaded, RECORDS, "toy-v1")

    def test_other_format_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.json"
            path.write_text('{"format": "something-else"}')
            with self.assertRaises(vectors.IndexMismatch):
                vectors.load(path)


class ModeTests(unittest.TestCase):
    def test_parse_mode(self):
        self.assertEqual(modes.parse_mode(None), "lexical")
        self.assertEqual(modes.parse_mode("hybrid"), "hybrid")
        with self.assertRaises(ValueError):
            modes.parse_mode("semantic")

    def test_fuse_uses_ranks_not_scores(self):
        # BM25 scores are negative and lower-first; cosine is higher-first. Only ranks count.
        lexical = [Candidate("a", -9.0), Candidate("b", -3.0)]
        vector = [Candidate("b", 0.9), Candidate("c", 0.8)]
        fused, ranks = modes.fuse(lexical, vector)
        # b: 1/62 + 1/61; a: 1/61; c: 1/62.
        self.assertEqual([c.key for c in fused], ["b", "a", "c"])
        self.assertAlmostEqual(fused[0].score, 1 / 62 + 1 / 61, places=9)
        self.assertEqual(ranks["b"], {"lexical": 2, "vector": 1})

    def test_fuse_depth_cuts_each_side(self):
        lexical = [Candidate(k, 0.0) for k in "abc"]
        vector = [Candidate(k, 0.0) for k in "xyz"]
        fused, _ = modes.fuse(lexical, vector, depth=1)
        self.assertEqual(sorted(c.key for c in fused), ["a", "x"])


def hashed_embed(texts, dim=64):
    import hashlib
    out = []
    for text in texts:
        vector = [0.01] * dim
        for word in text.lower().split():
            vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % dim] += 1.0
        out.append(vector)
    return out


class SearchModeTests(unittest.TestCase):
    """Snapshot.search in each mode, with a toy backend over the real corpus."""

    @classmethod
    def setUpClass(cls):
        from lawindex.embedding import VectorBackend
        from lawindex.search import Snapshot
        cls.snapshot = Snapshot()
        index = vectors.build(cls.snapshot.records, hashed_embed, "toy-hash-v1", batch_size=512)
        cls.backend = VectorBackend(index, lambda text: hashed_embed([text])[0], "toy-hash-v1")

    def search(self, query, **kwargs):
        return self.snapshot.search(query, limit=10, vector_backend=self.backend, **kwargs)

    def test_default_is_lexical(self):
        response = self.snapshot.search("information commission appeal")
        self.assertEqual(response["trace"]["mode"], "lexical")
        self.assertEqual(response["trace"]["method"], "sqlite-fts5-bm25-v1")

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            self.snapshot.search("appeal", mode="semantic")

    def test_vector_modes_need_a_backend(self):
        from lawindex.search import Unavailable
        for mode in ("vector", "hybrid"):
            with self.assertRaises(Unavailable):
                self.snapshot.search("appeal", mode=mode)

    def test_mismatched_model_is_refused(self):
        from lawindex.embedding import VectorBackend
        from lawindex.search import Unavailable
        wrong = VectorBackend(self.backend.index, self.backend.query_vector, "another-model")
        with self.assertRaises(Unavailable):
            self.snapshot.search("appeal", mode="vector", vector_backend=wrong)

    def test_filters_and_sections_hold_in_every_mode(self):
        from lawindex.retrieval import SearchFilters
        for mode in ("vector", "hybrid"):
            filtered = self.search("penalty for contravention", mode=mode, filters=SearchFilters(act="rti-2005"))
            self.assertTrue(filtered["results"])
            self.assertEqual({r["act_slug"] for r in filtered["results"]}, {"rti-2005"}, mode)
            cited = self.search("RTI section 6", mode=mode)
            self.assertEqual([r["key"] for r in cited["results"]], ["rti-2005:6"], mode)

    def test_results_are_admitted_and_traced(self):
        vector = self.search("wages of seafarers", mode="vector")
        self.assertTrue(vector["trace"]["method"].startswith("vector-cosine-v1:toy-hash-v1"))
        self.assertTrue(all(r["key"] in self.snapshot.records for r in vector["results"]))
        hybrid = self.search("wages of seafarers", mode="hybrid")
        self.assertEqual(hybrid["trace"]["mode"], "hybrid")
        ranks = hybrid["trace"]["side_ranks"]
        self.assertEqual(set(ranks), {r["key"] for r in hybrid["results"]})
        self.assertTrue(all(ranks[key] for key in ranks))

    def test_quoted_phrases_constrain_vector_results(self):
        response = self.search('"public authority" appeal', mode="vector")
        self.assertTrue(response["results"])
        for result in response["results"]:
            body = self.snapshot.records[result["key"]]["body_text"].lower()
            heading = self.snapshot.records[result["key"]]["heading"].lower()
            self.assertTrue("public authorit" in body or "public authorit" in heading, result["key"])


if __name__ == "__main__":
    unittest.main()
