"""Retrieval modes that share one query contract: lexical, vector and hybrid.

Lexical is the default. Vector and hybrid need a vector index built for the
live corpus and a named embedding model; without one they are unavailable,
never silently lexical. Every mode applies the same eligibility (filters,
section and citation constraints, quoted phrases) before ranking, and the
same per-Act cap after it.
"""
from __future__ import annotations

from dataclasses import replace

from . import vectors
from .fusion import reciprocal_rank_fusion
from .retrieval import (Candidate, LexicalRetriever, browse_order, check_limit, eligible_keys, is_browse,
                        page_result)

MODES = ("lexical", "vector", "hybrid")
DEFAULT_MODE = "lexical"
RRF_K = 60
DEPTH = 20


def parse_mode(value) -> str:
    mode = DEFAULT_MODE if value is None else value
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}.")
    return mode


def fuse(lexical: list[Candidate], vector: list[Candidate], depth: int = DEPTH, k: int = RRF_K):
    """Hybrid candidates: reciprocal rank fusion of each side's top `depth`.

    Raw BM25 and cosine scores are never compared; only ranks are. Each
    candidate's score is its fusion score, higher first. Returns the fused
    candidates and, per key, the rank it held on each side, for the trace.
    """
    if depth < 1:
        raise ValueError("depth must be at least 1")
    fused = reciprocal_rank_fusion({"lexical": [c.key for c in lexical[:depth]],
                                    "vector": [c.key for c in vector[:depth]]}, k=k)
    return [Candidate(row["key"], row["score"]) for row in fused], {row["key"]: row["ranks"] for row in fused}


class VectorRetriever:
    """Cosine similarity over the eligible admitted records, top DEPTH."""

    def __init__(self, index: vectors.VectorIndex, query_vector, aliases):
        self.index, self.query_vector, self.aliases = index, query_vector, aliases
        self.method = f"vector-cosine-v1:{index.model}"

    def candidates(self, records, request) -> list[Candidate]:
        eligible = eligible_keys(records, request)
        if request.phrases:
            eligible &= LexicalRetriever(self.aliases).phrase_eligible(records, request.phrases)
        return vectors.search(self.index, self.query_vector, eligible, DEPTH)

    def retrieve(self, records, request):
        check_limit(request.limit)
        if not request.match_expression:
            # A pure citation or filter lookup has nothing to rank by meaning.
            ranked = browse_order(records, eligible_keys(records, request)) if is_browse(request) else []
            return page_result(ranked, records, request, self.method)
        return page_result(self.candidates(records, request), records, request, self.method)


class HybridRetriever:
    """Reciprocal rank fusion of the lexical and vector top DEPTH."""

    def __init__(self, index: vectors.VectorIndex, query_vector, aliases):
        self.lexical = LexicalRetriever(aliases)
        self.vector = VectorRetriever(index, query_vector, aliases)
        self.method = f"hybrid-rrf-k{RRF_K}-v1:{index.model}"
        self.side_ranks: dict = {}

    def retrieve(self, records, request):
        check_limit(request.limit)
        if not request.match_expression:
            ranked = browse_order(records, eligible_keys(records, request)) if is_browse(request) else []
            return page_result(ranked, records, request, self.method)
        lexical = self.lexical.retrieve(records, replace(request, limit=DEPTH, per_act_cap=None))
        fused, self.side_ranks = fuse(list(lexical.candidates), self.vector.candidates(records, request))
        return page_result(fused, records, request, self.method)
