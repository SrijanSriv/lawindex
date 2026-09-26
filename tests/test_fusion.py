"""Hand-computed checks for reciprocal rank fusion. Not wired into search."""
import unittest

from lawindex.fusion import reciprocal_rank_fusion


class ReciprocalRankFusionTests(unittest.TestCase):
    def test_two_methods_with_overlap_at_k_60(self):
        # lexical: a rank 1, b rank 2, c rank 3
        # vector:  b rank 1, c rank 2, d rank 3
        # b: 1/(60+2) + 1/(60+1) = 1/62 + 1/61 = 0.016129032 + 0.016393443 = 0.032522475
        # c: 1/(60+3) + 1/(60+2) = 1/63 + 1/62 = 0.015873016 + 0.016129032 = 0.032002048
        # a: 1/(60+1) = 1/61 = 0.016393443
        # d: 1/(60+3) = 1/63 = 0.015873016
        result = reciprocal_rank_fusion({
            "lexical": ["a", "b", "c"],
            "vector": ["b", "c", "d"],
        })
        self.assertEqual(result, [
            {"key": "b", "score": 0.032522475, "ranks": {"lexical": 2, "vector": 1}},
            {"key": "c", "score": 0.032002048, "ranks": {"lexical": 3, "vector": 2}},
            {"key": "a", "score": 0.016393443, "ranks": {"lexical": 1}},
            {"key": "d", "score": 0.015873016, "ranks": {"vector": 3}},
        ])

    def test_two_methods_with_overlap_at_k_1(self):
        # lexical: a rank 1, b rank 2, c rank 3
        # vector:  b rank 1, c rank 2, d rank 3
        # b: 1/(1+2) + 1/(1+1) = 1/3 + 1/2 = 0.333333333 + 0.5 = 0.833333333
        # c: 1/(1+3) + 1/(1+2) = 1/4 + 1/3 = 0.25 + 0.333333333 = 0.583333333
        # a: 1/(1+1) = 1/2 = 0.5
        # d: 1/(1+3) = 1/4 = 0.25
        result = reciprocal_rank_fusion({
            "lexical": ["a", "b", "c"],
            "vector": ["b", "c", "d"],
        }, k=1)
        self.assertEqual(result, [
            {"key": "b", "score": 0.833333333, "ranks": {"lexical": 2, "vector": 1}},
            {"key": "c", "score": 0.583333333, "ranks": {"lexical": 3, "vector": 2}},
            {"key": "a", "score": 0.5, "ranks": {"lexical": 1}},
            {"key": "d", "score": 0.25, "ranks": {"vector": 3}},
        ])

    def test_higher_score_beats_better_rank_and_earlier_key(self):
        # z is rank 2 in both methods: 1/(60+2) + 1/(60+2) = 2/62 = 1/31 = 0.032258065
        # a is rank 1 in one method: 1/(60+1) = 1/61 = 0.016393443, best rank 1
        # m is rank 1 in the other: 1/61 = 0.016393443, best rank 1
        # z's score wins even though its best rank is 2 and "z" sorts after "a" and "m".
        result = reciprocal_rank_fusion({
            "one": ["a", "z"],
            "two": ["m", "z"],
        })
        self.assertEqual([row["key"] for row in result], ["z", "a", "m"])
        self.assertEqual(result[0]["score"], 0.032258065)
        self.assertEqual(min(result[0]["ranks"].values()), 2)
        self.assertEqual(result[1]["score"], 0.016393443)
        self.assertEqual(result[2]["score"], 0.016393443)

    def test_equal_score_breaks_on_best_rank(self):
        # k=1. p1 is rank 1 in both long lists: 1/2 + 1/2 = 1.0
        # p2 is rank 2 in both long lists: 1/3 + 1/3 = 2/3 = 0.666666667
        # b is rank 1 in one list only: 1/2 = 0.5, best rank 1
        # a is rank 3 in both long lists: 1/4 + 1/4 = 0.5, best rank 3
        # b and a share a score; the better rank (1) precedes rank 3, ahead of key order.
        result = reciprocal_rank_fusion({
            "m1": ["p1", "p2", "a"],
            "m2": ["p1", "p2", "a"],
            "m3": ["b"],
        }, k=1)
        self.assertEqual(result, [
            {"key": "p1", "score": 1.0, "ranks": {"m1": 1, "m2": 1}},
            {"key": "p2", "score": 0.666666667, "ranks": {"m1": 2, "m2": 2}},
            {"key": "b", "score": 0.5, "ranks": {"m3": 1}},
            {"key": "a", "score": 0.5, "ranks": {"m1": 3, "m2": 3}},
        ])

    def test_equal_score_and_best_rank_break_on_key(self):
        # a: lexical rank 2 + vector rank 1 = 1/62 + 1/61 = 0.032522475, best rank 1
        # b: lexical rank 1 + vector rank 2 = 1/61 + 1/62 = 0.032522475, best rank 1
        # same score and same best rank, so key ascending puts a before b.
        first = reciprocal_rank_fusion({
            "lexical": ["b", "a"],
            "vector": ["a", "b"],
        })
        second = reciprocal_rank_fusion({
            "vector": ["a", "b"],
            "lexical": ["b", "a"],
        })
        expected = [
            {"key": "a", "score": 0.032522475, "ranks": {"lexical": 2, "vector": 1}},
            {"key": "b", "score": 0.032522475, "ranks": {"lexical": 1, "vector": 2}},
        ]
        self.assertEqual(first, expected)
        self.assertEqual(second, expected)

    def test_duplicate_in_one_method_counts_at_best_rank(self):
        # lexical ["a", "b", "a"]: a stays rank 1; the later a is not also 1/(60+3).
        # vector ["b", "c", "b"]: b stays rank 1; the later b is not also 1/(60+3).
        # a: 1/(60+1) = 1/61 = 0.016393443
        # b: 1/(60+2) + 1/(60+1) = 1/62 + 1/61 = 0.032522475
        # c: 1/(60+2) = 1/62 = 0.016129032
        result = reciprocal_rank_fusion({
            "lexical": ["a", "b", "a"],
            "vector": ["b", "c", "b"],
        })
        self.assertEqual(result, [
            {"key": "b", "score": 0.032522475, "ranks": {"lexical": 2, "vector": 1}},
            {"key": "a", "score": 0.016393443, "ranks": {"lexical": 1}},
            {"key": "c", "score": 0.016129032, "ranks": {"vector": 2}},
        ])
        # ["a", "a", "b"]: a stays at rank 1 (1/61 = 0.016393443). b stays at
        # list position 3 (1/63 = 0.015873016), not compacted up to rank 2.
        shifted = reciprocal_rank_fusion({"lexical": ["a", "a", "b"]})
        self.assertEqual(shifted, [
            {"key": "a", "score": 0.016393443, "ranks": {"lexical": 1}},
            {"key": "b", "score": 0.015873016, "ranks": {"lexical": 3}},
        ])

    def test_limit_keeps_the_fused_prefix(self):
        rankings = {"lexical": ["a", "b", "c"], "vector": ["b", "c", "d"]}
        # Same scores as the k=60 overlap case. limit 2 keeps b then c.
        self.assertEqual(reciprocal_rank_fusion(rankings, limit=2), [
            {"key": "b", "score": 0.032522475, "ranks": {"lexical": 2, "vector": 1}},
            {"key": "c", "score": 0.032002048, "ranks": {"lexical": 3, "vector": 2}},
        ])
        self.assertEqual(
            len(reciprocal_rank_fusion(rankings, limit=10)),
            len(reciprocal_rank_fusion(rankings)),
        )

    def test_single_method_keeps_its_order(self):
        # c rank 1: 1/(60+1) = 1/61 = 0.016393443
        # a rank 2: 1/(60+2) = 1/62 = 0.016129032
        # b rank 3: 1/(60+3) = 1/63 = 0.015873016
        result = reciprocal_rank_fusion({"lexical": ["c", "a", "b"]})
        self.assertEqual([row["key"] for row in result], ["c", "a", "b"])
        self.assertEqual(result, [
            {"key": "c", "score": 0.016393443, "ranks": {"lexical": 1}},
            {"key": "a", "score": 0.016129032, "ranks": {"lexical": 2}},
            {"key": "b", "score": 0.015873016, "ranks": {"lexical": 3}},
        ])

    def test_empty_list_for_one_method_adds_nothing(self):
        # c rank 1: 1/61 = 0.016393443; a rank 2: 1/62 = 0.016129032.
        # The empty vector list contributes no ranks and no score.
        result = reciprocal_rank_fusion({"lexical": ["c", "a"], "vector": []})
        self.assertEqual(result, [
            {"key": "c", "score": 0.016393443, "ranks": {"lexical": 1}},
            {"key": "a", "score": 0.016129032, "ranks": {"lexical": 2}},
        ])
        self.assertEqual(reciprocal_rank_fusion({"lexical": []}), [])

    def test_rejects_invalid_k_empty_rankings_and_non_list(self):
        for bad_k in (0, -1):
            with self.subTest(k=bad_k):
                with self.assertRaises(ValueError):
                    reciprocal_rank_fusion({"lexical": ["a"]}, k=bad_k)
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion({})
        for ranking in (("a", "b"), "ab", None):
            with self.subTest(ranking=ranking):
                with self.assertRaises(ValueError):
                    reciprocal_rank_fusion({"lexical": ranking})
