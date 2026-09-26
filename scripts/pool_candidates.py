#!/usr/bin/env python3
"""Pool candidates for provision-level benchmark queries from several retrieval
methods, per docs/phase-4/BENCHMARK_PLAN.md ("Pool").

Read-only: builds a disposable in-memory FTS5 index and a pure-Python TF-IDF
index from snapshot.records; never queries the on-disk database directly and
never changes ranking behaviour.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawindex.benchmark import QUERIES, corpus_fingerprint, load_queries, sha256_hex  # noqa: E402
from lawindex.retrieval import SearchFilters  # noqa: E402
from lawindex.search import STOPWORDS, TOKEN, Snapshot  # noqa: E402

DEFAULT_POOL = ROOT / "data/benchmark/pools/pool.v1.json"

# Method -> pool depth, exactly the plan's pool table.
METHOD_DEPTHS = {
    "system": 20,
    "bm25_fields": 10,
    "bm25_body": 10,
    "bm25_heading": 10,
    "bm25_and": 10,
    "tfidf_unstemmed": 10,
}
BM25_METHODS = ("bm25_fields", "bm25_body", "bm25_heading", "bm25_and")
# bm25(search, 0, w_title, w_heading, w_body, w_footnote); argument 0 is the
# UNINDEXED key column.
BM25_WEIGHTS = {
    "bm25_fields": (4, 3, 1, 0.5),
    "bm25_body": (0, 0, 1, 0),
    "bm25_heading": (1, 5, 0, 0),
    "bm25_and": (4, 3, 1, 0.5),
}


def extract_terms(query_text: str) -> list[str]:
    """Lowercase [^\\W_]+ tokens minus STOPWORDS minus pure digits, de-duplicated in order."""
    tokens = (t.lower() for t in TOKEN.findall(query_text))
    return list(dict.fromkeys(t for t in tokens if t not in STOPWORDS and not t.isdigit()))


def build_search_index(records: dict) -> sqlite3.Connection:
    """One disposable in-memory FTS5 table, shared by all four bm25_* methods."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE search USING fts5(key UNINDEXED, title, heading, body, footnote, "
                 "tokenize='porter unicode61')")
    conn.executemany("INSERT INTO search VALUES (?,?,?,?,?)",
                      [(key, r["act_title"], r["heading"], r["body_text"], r["footnote_text"] or "")
                       for key, r in records.items()])
    return conn


def bm25_rank(conn: sqlite3.Connection, terms: list[str], method: str) -> list[str]:
    """All matches for `method`, best first, ties broken by key. Unfiltered, uncut."""
    if not terms:
        return []
    join = " AND " if method == "bm25_and" else " OR "
    match_expression = join.join(f'"{t}"' for t in terms)
    w = BM25_WEIGHTS[method]
    sql = f"SELECT key, bm25(search,0,{w[0]},{w[1]},{w[2]},{w[3]}) FROM search WHERE search MATCH ? ORDER BY 2,1"
    return [key for key, _score in conn.execute(sql, (match_expression,))]


def tfidf_rank(records: dict, terms: list[str]) -> list[str]:
    """Pure-Python TF-IDF cosine over heading + body, no stemming. Ties broken by key;
    zero-similarity documents are dropped."""
    if not terms:
        return []
    doc_tokens = {key: [t.lower() for t in TOKEN.findall(r["heading"] + " " + r["body_text"])
                         if t.lower() not in STOPWORDS]
                  for key, r in records.items()}
    total_docs = len(records)
    document_frequency: dict[str, int] = {}
    for tokens in doc_tokens.values():
        for term in set(tokens):
            document_frequency[term] = document_frequency.get(term, 0) + 1

    def idf(term: str):
        df = document_frequency.get(term, 0)
        return math.log(total_docs / df) if df else None

    # `terms` is already de-duplicated, so the query's raw term count is 1 per term.
    query_weight = {term: weight for term in dict.fromkeys(terms)
                    if (weight := idf(term)) is not None}
    query_norm = math.sqrt(sum(w * w for w in query_weight.values()))
    scored = []
    if query_norm:
        for key, tokens in doc_tokens.items():
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            dot = document_norm_sq = 0.0
            for term, count in counts.items():
                weight = idf(term)
                if weight is None:
                    continue
                term_weight = count * weight
                document_norm_sq += term_weight * term_weight
                if term in query_weight:
                    dot += term_weight * query_weight[term]
            if dot > 0:
                similarity = dot / (query_norm * math.sqrt(document_norm_sq))
                scored.append((key, similarity))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [key for key, _similarity in scored]


def apply_filters(keys: list[str], records: dict, filters: SearchFilters, depth: int) -> list[str]:
    """SearchFilters applied before the depth cut, per the plan."""
    return [key for key in keys if filters.matches(records[key])][:depth]


def pool_query(snapshot: Snapshot, conn: sqlite3.Connection, query: dict) -> dict[str, dict[str, int]]:
    """{key: {method: rank}} for one query, across all six methods."""
    filters = SearchFilters(**query["filters"])
    found_by: dict[str, dict[str, int]] = {}

    def record_ranks(method: str, keys: list[str]):
        for rank, key in enumerate(keys, 1):
            found_by.setdefault(key, {})[method] = rank

    system_response = snapshot.search(query["query"], limit=METHOD_DEPTHS["system"], filters=filters)
    record_ranks("system", [r["key"] for r in system_response["results"]])

    terms = extract_terms(query["query"])
    for method in BM25_METHODS:
        ranked = apply_filters(bm25_rank(conn, terms, method), snapshot.records, filters, METHOD_DEPTHS[method])
        record_ranks(method, ranked)

    tfidf_ranked = apply_filters(tfidf_rank(snapshot.records, terms), snapshot.records, filters,
                                  METHOD_DEPTHS["tfidf_unstemmed"])
    record_ranks("tfidf_unstemmed", tfidf_ranked)
    return found_by


def build_pool(snapshot: Snapshot, queries: list[dict]) -> dict:
    conn = build_search_index(snapshot.records)
    try:
        pools = {}
        for query in queries:
            if query["level"] != "provision" or query["scope"] == "out_of_corpus":
                continue
            found_by = pool_query(snapshot, conn, query)
            candidates = [{"key": key, "found_by": found_by[key]} for key in sorted(found_by)]
            pools[query["id"]] = {"candidates": candidates, "size": len(candidates)}
        return pools
    finally:
        conn.close()


def print_statistics(pools: dict) -> None:
    sizes = [entry["size"] for entry in pools.values()]
    if not sizes:
        print("No queries pooled.")
        return
    print(f"Pooled {len(sizes)} queries: min={min(sizes)} median={statistics.median(sizes):.1f} "
          f"max={max(sizes)} total_pairs={sum(sizes)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, default=QUERIES)
    parser.add_argument("--out", type=Path, default=DEFAULT_POOL)
    args = parser.parse_args()

    snapshot = Snapshot()
    queries = load_queries(args.queries, act_slugs=set(snapshot.acts))
    pools = build_pool(snapshot, queries)
    manifest = {
        "corpus_fingerprint": corpus_fingerprint(snapshot.records),
        "queries_sha256": sha256_hex(args.queries.read_bytes()),
        "methods": dict(METHOD_DEPTHS),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"manifest": manifest, "pools": pools}, indent=2, ensure_ascii=False) + "\n")
    print_statistics(pools)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
