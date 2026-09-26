# Phase 4 plan: a retrieval benchmark we can trust

Started 23 September 2026. Owner of this plan, the query set, the judging protocol, adjudication and the gate: the main agent. Implementation tasks delegated to Sonnet 5 are scoped in [SONNET_TASKS.md](SONNET_TASKS.md).

## What Phase 4 must produce

The exit gate in [PHASES.md](../../PHASES.md): *a repeatable command evaluates a frozen corpus and query set, produces aggregate and per-query reports, and can reproduce the lexical baseline. Judgments, known gaps, splits, and release thresholds are documented.*

Concretely:

1. **A query set** of about 150 queries across 20 Acts, each with a stated information need, a category, a scope expectation and a split.
2. **Graded judgments** for provision-level queries, pooled from several retrieval methods plus manual exploration, judged blind by two independent model judges, with disagreements adjudicated and agreement reported.
3. **An evaluation command** that runs the live search system over the query set and reports document- and provision-level metrics, per query and in aggregate, per category and per split, with latency and a full version manifest.
4. **A frozen lexical baseline**: a stored run that the command reproduces exactly (identical rankings and metrics).
5. **Recorded targets** for quality, coverage and latency, set from the baseline before any tuning.

What Phase 4 does not do: change ranking. Ranking work (including the P0-010 exception carried from Phase 3) is Phase 5–6, and must be measured on the test split this phase creates.

## Honest limits, stated up front

- **No human or legal-expert judgments.** Every judgment is made by an AI model. PHASES.md says model labels "are not authoritative ground truth". They are recorded as `reviewer_type: ai_model`, and the benchmark is described as a *development benchmark with AI judgments*, not a legal-accuracy benchmark. Human review of a sample is recorded in the [expansion backlog](../EXPANSION_BACKLOG.md) (item 4.1).
- **Author bias.** The query author (the main agent) knows the system and the corpus. To reduce the bias, queries are written from knowledge of the law and of how people ask, not from section headings, and roughly a third deliberately use wording the statute does not use. Pooling from methods other than the live system reduces bias toward the current ranker.
- **Correlated judges.** Two model judges are less independent than two people. We use two different models (Sonnet 5 and Opus 5.5) and report their agreement.
- **Judged against the admitted corpus only.** Judgments cover the 1,504 admitted provisions. When the best answer is a held-back section, the query records it as a known unindexed target; it counts as a coverage gap, not a retrieval miss.

## Query set

File: `data/benchmark/queries.v1.jsonl`, one JSON object per line.

| Field | Meaning |
| --- | --- |
| `id` | `B-001` … |
| `info_need` | `N-001` …; paraphrases of the same need share one. Splits are assigned per need, so paraphrases never straddle dev and test. |
| `query` | What the user types. |
| `intent` | One or two sentences describing what the user wants. Judges judge against this, not only the words. |
| `category` | One of the categories below. |
| `level` | `provision` (judged per provision) or `document` (the right Act is the answer; no provision judging). |
| `scope` | `in_corpus` (the answer is among admitted provisions), `partial` (some relevant text is admitted, but a key provision is held back or lives in an instrument we don't index), or `out_of_corpus` (nothing indexed answers it). |
| `relevant_acts` | For `document` queries: the Act slugs that answer it. Otherwise omitted. |
| `known_unindexed_targets` | Keys of held-back sections that would answer it (e.g. `copyright-1957:52`), or names of unindexed material ("RTI Rules, 2012"). |
| `expected_notices` | For `out_of_corpus` and `partial`: the notice codes a correct response shows (see `coverage_notices` in `lawindex/search.py`). |
| `filters` | `{}` or a `SearchFilters` dict (`act`, `year`, `ministry`, `document_type`). |
| `split` | `dev` or `test`. |
| `origin` | `authored`, or `seed:P0-0xx` / `dev:DEV-00x` when carried over. |
| `notes` | Optional. |

### Categories and target counts

| Category | Count | Example |
| --- | --- | --- |
| `exact_title` | 10 | "Consumer Protection Act 2019" |
| `citation` | 12 | "section 27 Contract Act", "Act 22 of 2005" |
| `topic` | 30 | "limitation of shipowner liability for maritime claims" |
| `ordinary_language` | 30 | "can my landlord's builder take money before signing an agreement" |
| `terminology_mismatch` | 20 | "time limit to file consumer case" (statute: "limitation period") |
| `acronym` | 8 | "ICC composition POSH" |
| `broad_discovery` | 8 | "penalties for companies" |
| `filtered` | 8 | "power to make rules" with `year=2016` |
| `out_of_corpus` | 16 | "GST registration threshold", "UP rent control", "Maneka Gandhi judgment" |
| Carried over | 30 | the 24 Phase 0 seeds and 6 dev queries, recategorized into the categories above |

### Splits

Split is a function of `info_need`, not a choice: `test` when `int(sha256("lawindex-bench-v1|" + info_need), 16) % 100 < 50`, else `dev`. Carried-over seed and dev queries are always `dev`, because the system was developed against them. The validator recomputes every split and rejects a file where one was edited. Tuning in later phases may look at dev only; test is reported, never inspected per query while tuning.

## Judging

### Grades

| Grade | Name | Meaning |
| --- | --- | --- |
| 3 | Answers | States the rule, right, duty, procedure or definition the user asked about. A user could stop here. |
| 2 | Relevant | Substantially needed to answer: a qualification, exception, companion procedure, the body that decides, or the penalty for the rule asked about. |
| 1 | Marginal | On the topic but does not help answer (uses the words, a definitions list that mentions the term, a rule-making power on the subject). |
| 0 | Not relevant | Off topic, or the right words in the wrong sense. |

Binary relevance for precision, recall and MRR is grade ≥ 2.

### Pool

For each `provision`-level query, `scripts/pool_candidates.py` takes the union of:

| Method | Depth | Why |
| --- | --- | --- |
| `system`: the live `Snapshot.search`, limit 20 | 20 | What users see |
| `bm25_fields`: FTS5 porter, weights title 4 / heading 3 / body 1 / footnote 0.5, OR of terms, no per-Act cap, no Act selection | 10 | Production scoring without the query-parsing layer |
| `bm25_body`: body only | 10 | Removes heading bias (the P0-010 failure mode) |
| `bm25_heading`: heading 5, title 1 | 10 | Finds sections whose heading names the topic |
| `bm25_and`: all terms required | 10 | Precision-oriented |
| `tfidf_unstemmed`: pure-Python TF-IDF cosine over heading + body, no stemming | 10 | A different scoring family |

Filters apply to every method. Then **manual exploration**: each judge may add up to five admitted provisions per query that the pool missed, found by reading the Act's section list or grepping the corpus (`source: manual`), and may name held-back sections that would answer it.

### Protocol

- Judges see the query, its intent and each pooled provision's Act, section, heading, full text and footnote, in a per-judge shuffled order, with no rank, score or method.
- Two judges per pair: **A** (Sonnet 5) and **B** (Opus 5.5), in separate agents that never see each other's output.
- Each judgment has a one-sentence rationale.
- Merge: identical grades are final. Grades on the same side of the relevance line (both ≥ 2 or both < 2) that differ by one take the **lower** grade. Every pair where one judge says ≥ 2 and the other < 2 is adjudicated by the main agent, reading the text, with a rationale. Manual additions by either judge are adjudicated.
- Manual additions that both judges found independently and graded on the same side of the relevance line take the lower grade, like adjacent pool pairs. All other manual additions are read by the main agent. (Added during adjudication, 24 September 2026; 39 pairs.)
- Reported: exact agreement, within-one agreement, and Cohen's kappa on binary relevance, overall and per category.
- Unjudged results in a later run are counted and reported as `judged@10`; for scoring they are treated as not relevant. A run whose `judged@10` falls below 0.9 on either split is flagged as needing more judging before its numbers are compared.

File: `data/benchmark/judgments.v1.jsonl`, one line per (query, provision): `query_id`, `provision_key`, `grade`, `rationale`, `source` (`pool` or `manual`), `resolution` (`agreed`, `lower_of_adjacent`, `adjudicated`), `grades` (`{"A": g, "B": g}` where present), `reviewer_type: "ai_model"`, `corpus_fingerprint`. Raw judge outputs stay in `data/benchmark/judging/`.

## Metrics

Per `provision`-level query, over the returned ranking (limit 20):

- **nDCG@10** (primary), gain `2^grade − 1`, ideal ranking from all judged admitted provisions for the query.
- **MRR**: reciprocal rank of the first grade-≥2 result within 20; 0 if none.
- **Recall@10, Recall@20**: share of grade-≥2 judged provisions retrieved.
- **P@5, P@10** at grade ≥ 2.
- **Success@3**: a result with the query's highest judged grade is in the top 3. This is the judged form of the Phase 3 "answer in top 3" check.
- **judged@10**: share of the top 10 that has a judgment.

Document level (every in-scope query): collapse the ranking to distinct Acts in order of first appearance. Relevant Acts are `relevant_acts` for document queries, or Acts with a grade-≥2 provision. Report **MRR_doc**, **Success@1_doc**, **Recall@3_doc**.

Out of corpus and partial: **notice recall** (the response carries every code in `expected_notices`). Over `in_corpus` queries: **false notice rate** (any `*_not_indexed` notice, or `weak_match`, shown).

Aggregates are means over queries, reported overall, per split, per category and per scope, with 95% bootstrap intervals (1,000 resamples, seed 0) for nDCG@10 and MRR. Queries with no grade-≥2 judged admitted provision are excluded from provision metrics and listed.

Latency: per-query `search_ms` from the trace and wall-clock time; p50 and p95.

## Run records and reproducibility

`scripts/run_benchmark.py` writes `data/benchmark/runs/<run_id>.json` with a manifest and per-query rows. The manifest records:

- `corpus_fingerprint`: sha256 over the sorted admitted provisions' keys, Act titles and the sha256 of heading, body and footnote text. The live corpus is validated on load, as in search.
- sha256 of the query file and judgment file.
- sha256 of each file in `lawindex/` and of `scripts/run_benchmark.py`.
- method name, Python and SQLite versions, limit, and time.

`--compare <run>` exits non-zero unless the fingerprints and every per-query ranking and metric match (timings excluded), and says what differs. The baseline is `data/benchmark/runs/baseline-lexical-v1.json`; the gate requires that a fresh run reproduces it.

## Targets

Recorded in `docs/phase-4/TARGETS.md` after the baseline run and before any tuning. Draft structure (numbers decided from observed results):

- Quality: test-split nDCG@10 and MRR floors that later changes must not fall below, and the improvement a ranking change must show on the test split, beyond its bootstrap interval, to be adopted.
- Coverage: notice recall on out-of-corpus queries; false notice rate ceiling.
- Latency: p95 ceiling for the benchmark run.

## Sequence

1. Plan and task scopes (this document, [SONNET_TASKS.md](SONNET_TASKS.md)). Main agent.
2. In parallel: evaluation harness (Sonnet, task T1); pooling, judging packets and merge tools (Sonnet, task T2); query set (main agent).
3. Pool, build packets, run judges A and B.
4. Merge, adjudicate disagreements and manual additions, report agreement.
5. Baseline run; reproduce it; write targets; gate audit.
