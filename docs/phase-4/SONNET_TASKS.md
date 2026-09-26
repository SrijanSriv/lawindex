# Phase 4 implementation tasks delegated to Sonnet 5

The main agent owns the plan ([BENCHMARK_PLAN.md](BENCHMARK_PLAN.md)), the data contracts (`lawindex/benchmark.py`), the query set, adjudication and the gate. The two tasks below are implementation against those contracts. They touch disjoint files and can run in parallel.

## Rules for both tasks

- Read `docs/phase-4/BENCHMARK_PLAN.md` and `lawindex/benchmark.py` first. They are the specification. Do not edit either; if one is wrong or ambiguous, stop and report it with a concrete example rather than working around it.
- Edit only the files your task lists. Do not edit `lawindex/search.py`, `lawindex/retrieval.py`, `lawindex/server.py`, the importer, anything under `data/` except where your task says, existing tests, `web/`, `PHASES.md` or README.
- Do not change ranking behaviour. The benchmark measures the system as it is.
- No network access, no importer runs, no `--fresh`, no deployment.
- Standard library only (Python 3, `sqlite3`). Match the style of the surrounding code: small functions, docstrings where the reason is not obvious, no frameworks.
- Tests use `unittest`, live in `tests/`, and must not depend on the query set or judgments the main agent is still writing: build small in-memory fixtures. Loading the real `Snapshot()` in a test is allowed (it takes about a second) but keep it to one class-level load.
- Run only your own tests plus `python3 -m unittest tests.test_retrieval tests.test_search -q` as a regression check. The full suite takes about three minutes; do not run it repeatedly.
- Finish with a short report: files created, commands to run, test results with counts, any spec problem you found, and anything you did not do.

## T1: evaluation harness

**Files:** create `lawindex/evaluation.py`, `scripts/run_benchmark.py`, `tests/test_evaluation.py`.

### `lawindex/evaluation.py` (pure; no I/O except what callers pass in)

Metric functions. `ranking` is a list of provision keys in rank order; `grades` is `{key: grade}` for one query (judged pairs only; missing means unjudged).

- `dcg(gains)`: sum of `(2**g - 1) / log2(i + 2)` over positions `i` from 0.
- `ndcg_at_k(ranking, grades, k=10)`: DCG of the top k (unjudged gain 0) divided by the DCG of the top k of all judged grades sorted descending. `None` if the ideal DCG is 0.
- `mrr(ranking, grades, cutoff=20)`: `1/rank` of the first key with grade ≥ `RELEVANT` within `cutoff`, else 0.0.
- `recall_at_k(ranking, grades, k)`: relevant retrieved in top k / all relevant judged keys; `None` if none relevant.
- `precision_at_k(ranking, grades, k)`: relevant in top k / k (short rankings still divide by k).
- `success_at_k_best(ranking, grades, k=3)`: 1.0 if a key carrying the query's maximum judged grade (which must be ≥ `RELEVANT`) is in the top k, else 0.0; `None` if no judged key reaches `RELEVANT`.
- `judged_at_k(ranking, grades, k=10)`: share of the top `min(k, len(ranking))` that is judged; `None` for an empty ranking.
- `act_ranking(ranking, act_of)`: distinct Act slugs in order of first appearance (`act_of` maps key to slug).
- `doc_metrics(ranking, act_of, relevant_acts)`: `{"mrr_doc", "success_at_1_doc", "recall_at_3_doc"}` over `act_ranking`.
- `bootstrap_ci(values, resamples=1000, seed=0)`: 95% percentile interval of the mean using `random.Random(seed)`; `None` for an empty list. Values that are `None` are dropped before calling.
- `percentile(values, p)`: nearest-rank percentile, for latency.
- `evaluate_query(query, response, grades, records)`: one per-query row:
  - `id`, `category`, `scope`, `level`, `split`, `ranking` (keys from `response["results"]`), `notices` (codes from `response["notices"]`), `search_ms` (`response["trace"]["search_ms"]`).
  - Provision metrics when `level == "provision"` and the query has a judged key at grade ≥ 2: `ndcg_at_10`, `mrr`, `recall_at_10`, `recall_at_20`, `p_at_5`, `p_at_10`, `success_at_3`, `judged_at_10`, and `unjudged_in_top_10` (a list of keys). Otherwise these are `None` and `excluded_reason` says why (`"document_level"`, `"out_of_corpus"`, `"no_relevant_judged"`).
  - Document metrics for every non-`out_of_corpus` query: relevant Acts are `query["relevant_acts"]` for document queries, else the Acts of keys with grade ≥ 2. `None` if there are none.
  - Notice checks: `notice_hit` (every code in `expected_notices` present; `None` if none expected); `false_notice` for `in_corpus` queries (any `*_not_indexed` code or `weak_match` present), else `None`.
  - Round every float to 6 decimals so runs compare exactly.
- `aggregate(rows)`: means of every metric ignoring `None`, with the count used, for groups `overall`, `split:<s>`, `category:<c>`, `scope:<s>`; `bootstrap_ci` for `ndcg_at_10` and `mrr` in each group; `notice_recall` (mean of `notice_hit`) and `false_notice_rate` (mean of `false_notice`); latency `p50_ms` and `p95_ms` of `search_ms` for `overall` only. Include the list of excluded query ids per reason.

### `scripts/run_benchmark.py`

```
python3 scripts/run_benchmark.py [--queries PATH] [--judgments PATH] [--run-id ID] [--out PATH]
                                 [--rankings-only] [--compare RUN_JSON] [--split dev|test]
```

- Load `Snapshot()` once. Load and validate queries with `load_queries(path, act_slugs=set(snapshot.acts))`. Unless `--rankings-only`, load judgments with `read_jsonl` and `validate_judgments(..., records=snapshot.records, fingerprint=corpus_fingerprint(snapshot.records))`. A fingerprint mismatch is an error that says the corpus changed since judging.
- For each query (optionally only one split): `snapshot.search(query["query"], limit=20, filters=SearchFilters(**query["filters"]))`, timed with `time.perf_counter()` as `wall_ms` too. `evaluate_query` on the response.
- Write `{"manifest": ..., "queries": rows, "aggregate": aggregate(rows)}` to `--out` (default `data/benchmark/runs/<run_id>.json`; default run id `run-<UTC yyyymmddThhmmssZ>`). The manifest holds `run_id`, `created_at_utc`, `benchmark_plan: "docs/phase-4/BENCHMARK_PLAN.md"`, `queries_sha256`, `judgments_sha256` (or `null`), `corpus_fingerprint`, `provision_count`, `code_sha256` (a dict of sha256 per file for every `lawindex/*.py` plus `scripts/run_benchmark.py`, sorted), `method` (the trace method), `limit: 20`, `python`, `sqlite`, `split` (or `"all"`), `rankings_only`.
- Print a short human summary: per split and overall, n and nDCG@10, MRR, Recall@10, Success@3, MRR_doc, notice recall, false notice rate, p50/p95; then the ten worst queries by nDCG@10 in the dev split only. Never print per-query test-split rows (the test split is not inspected per query while tuning); the JSON still contains them.
- `--compare RUN_JSON`: after running, compare with the stored run. Equal means the same `corpus_fingerprint`, `queries_sha256`, `judgments_sha256`, and per query the same `ranking`, `notices` and every metric (ignore `search_ms`, `wall_ms`, `created_at_utc`, `run_id`, `code_sha256`). Print `REPRODUCED` and exit 0, or list each difference (at most 20 lines, then a count) and exit 1. Report code-digest differences as information, not failure.

### Tests (`tests/test_evaluation.py`)

Hand-computed expectations for every metric, including: ideal DCG from judged keys not retrieved; unjudged keys counting zero; `None` cases; `success_at_3` when the best grade is 2 not 3; `act_ranking` de-duplication; `bootstrap_ci` determinism; `aggregate` ignoring `None`; `evaluate_query` on a synthetic response for a document query, an out-of-corpus query and an in-corpus query with a false notice. One end-to-end test runs `scripts/run_benchmark.py --rankings-only` on a two-query temporary query file against the real snapshot, then runs it again with `--compare` and asserts exit 0 and `REPRODUCED`.

## T2: pooling, judging packets and merge

**Files:** create `scripts/pool_candidates.py`, `scripts/judging_packets.py`, `scripts/show_provision.py`, `scripts/merge_judgments.py`, `tests/test_benchmark_pool.py`. Outputs go under `data/benchmark/pools/` and `data/benchmark/judging/` only when the main agent runs the scripts; tests use temporary directories.

### `scripts/pool_candidates.py`

```
python3 scripts/pool_candidates.py [--queries PATH] [--out data/benchmark/pools/pool.v1.json]
```

- Load `Snapshot()` once and the queries via `load_queries`. Pool only queries with `level == "provision"` and `scope != "out_of_corpus"`.
- Methods and depths exactly as the plan's pool table. `system` is `snapshot.search(query, limit=20, filters=...)`. The other five build their own index from `snapshot.records` (never from the database directly):
  - Terms: lowercase `[^\W_]+` tokens of the query, minus `lawindex.search.STOPWORDS`, minus pure digits, de-duplicated in order. For `bm25_*`, match expression is the terms quoted and joined by `OR` (`AND` for `bm25_and`). If no terms remain, the method returns nothing.
  - `bm25_fields`, `bm25_body`, `bm25_heading`, `bm25_and`: one in-memory FTS5 table `(key UNINDEXED, title, heading, body, footnote)` with `tokenize='porter unicode61'`, built once for all queries, ranked by `bm25(search, 0, w_title, w_heading, w_body, w_footnote)` with weights `(4,3,1,0.5)`, `(0,0,1,0)`, `(1,5,0,0)`, `(4,3,1,0.5)` respectively. Ties broken by key.
  - `tfidf_unstemmed`: pure Python. Documents are heading + body tokenized as above (no stemming, no stopword removal beyond `STOPWORDS`). Weight `tf * log(N / df)`, with `tf` as the raw count; cosine similarity between query and document vectors; rank by similarity descending then key; drop zero-similarity documents.
  - Apply `SearchFilters(**query["filters"]).matches(record)` to every non-system method before the depth cut.
- Output: `{"manifest": {"corpus_fingerprint", "queries_sha256", "methods": {name: depth}, "created_at_utc"}, "pools": {query_id: {"candidates": [{"key", "found_by": {method: rank}}], "size": n}}}` with candidates sorted by key. Print pool-size statistics (min, median, max, total pairs).

### `scripts/show_provision.py`

`python3 scripts/show_provision.py KEY [KEY ...]` prints each admitted provision: key, Act title, section, heading, full body, footnote. `python3 scripts/show_provision.py --act SLUG` lists that Act's admitted sections (number and heading), for manual exploration. `--grep PATTERN [--act SLUG]` lists admitted provisions whose heading or body matches a case-insensitive regex, with a 160-character snippet. Unknown keys are an error.

### `scripts/judging_packets.py`

```
python3 scripts/judging_packets.py --judge A|B [--pool PATH] [--queries PATH] [--batch-size 8]
                                   [--out data/benchmark/judging/packets]
```

- Group pooled queries into batches of `--batch-size` in query-id order. For judge `X`, write `<out>/<X>/batch-NN.md` and `<out>/<X>/batch-NN.expected.json`.
- The markdown packet: a short header pointing to `docs/phase-4/JUDGING_GUIDE.md` (the main agent writes it); then per query: id, query, intent, filters if any, and each candidate as `### <key>` with Act title, section number, heading, body and footnote. Bodies longer than 6,000 characters are cut at 6,000 with the line `[Truncated. Read the rest with: python3 scripts/show_provision.py <key>]`. Candidate order is shuffled per query with `random.Random(f"{judge}|{query_id}")` so the two judges see different orders. Never include rank, score or method.
- `expected.json`: `{"judge", "batch", "corpus_fingerprint", "queries": {query_id: [keys]}}`.

### `scripts/merge_judgments.py`

Judge output files are `<judging>/raw/<X>/batch-NN.jsonl`, one object per line, either
`{"kind": "judgment", "query_id", "provision_key", "grade", "rationale", "source": "pool"|"manual"}` or
`{"kind": "unindexed_target", "query_id", "target", "rationale"}`.

```
python3 scripts/merge_judgments.py check --judge X --batch NN      # validate one output file
python3 scripts/merge_judgments.py merge                             # both judges complete
```

- `check`: every expected (query, key) pair judged exactly once with `source: pool`; grades 0–3 ints; non-empty rationale; at most five `manual` lines per query, each an admitted key not already in that query's pool and not repeated; `unindexed_target` targets non-empty. Print problems and exit 1, or print `OK n judgments, m manual, u unindexed` and exit 0.
- `merge`: requires every batch of both judges to pass `check`. For each pool pair: equal grades → `agreed`; both on the same side of 2 and one apart → the lower grade, `lower_of_adjacent`; otherwise → needs adjudication. Every `manual` pair (from either judge) needs adjudication, with the other judge's grade absent. Write:
  - `<judging>/agreement.json`: pair counts, exact agreement, within-one agreement, Cohen's kappa on binary relevance (grade ≥ 2) over pool pairs, each overall and per query category.
  - `<judging>/to_adjudicate.jsonl`: one line per pair needing adjudication with both grades and rationales (`null` where absent), sorted by query id then key.
  - `<judging>/unindexed_targets.json`: the union of unindexed targets per query with which judge named each.
  - If `<judging>/adjudication.jsonl` exists (lines `{"query_id", "provision_key", "grade", "rationale"}`) and covers every pair in `to_adjudicate.jsonl` exactly, write `data/benchmark/judgments.v1.jsonl` in the schema of `lawindex/benchmark.py` (sorted by query id then key; `reviewer_type: "ai_model"`; `corpus_fingerprint` from the packets; the rationale is the adjudication rationale, or judge A's for agreed and lower-of-adjacent pairs), then validate it with `validate_judgments`. Otherwise print how many pairs remain.

### Tests (`tests/test_benchmark_pool.py`)

Use a small fake records dict (a handful of provisions across two Acts) wherever the method does not need the live snapshot: the term extraction, each non-system method's ordering and filter application, TF-IDF on a hand-checked example, packet shuffling determinism and difference between judges, truncation, and every `check` and `merge` rule, including kappa on a hand-computed table, an incomplete adjudication, and a complete one producing a judgments file that passes `validate_judgments`.
