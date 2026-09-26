# Lexical baseline, 24 September 2026

The first measured run of LawIndex's search against the Phase 4 benchmark. It is frozen as [`data/benchmark/runs/baseline-lexical-v1.json`](../../data/benchmark/runs/baseline-lexical-v1.json), and a fresh run reproduces it exactly:

```
python3 scripts/run_benchmark.py --compare data/benchmark/runs/baseline-lexical-v1.json
```

prints `REPRODUCED`: identical corpus fingerprint, query and judgment digests, rankings, notices and metrics.

**What these numbers are.** A development benchmark with AI judgments over 1,504 admitted sections of 20 central Acts. They measure how well search finds the provisions two model judges considered relevant. They are not a measure of legal accuracy, and no human or legal expert has reviewed the judgments (see [the plan](BENCHMARK_PLAN.md#honest-limits-stated-up-front)).

## What was built

| Piece | Where | Who |
| --- | --- | --- |
| Plan, data contracts, split rule, corpus fingerprint | [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md), `lawindex/benchmark.py` | Main agent |
| 162 queries over 152 information needs | `data/benchmark/queries.v1.jsonl` | Main agent |
| Judging guide | [JUDGING_GUIDE.md](JUDGING_GUIDE.md) | Main agent |
| Metrics, runner, reproducibility check | `lawindex/evaluation.py`, `scripts/run_benchmark.py`, `tests/test_evaluation.py` (38 tests) | Sonnet 5, task T1 |
| Pooling, packets, provision viewer, merge and agreement | `scripts/pool_candidates.py`, `judging_packets.py`, `show_provision.py`, `merge_judgments.py`, `tests/test_benchmark_pool.py` (44 tests) | Sonnet 5, task T2 |
| 34 judging batches | `data/benchmark/judging/raw/` | Sonnet 5 (judge A), Opus 5.5 (judge B) |
| Adjudication of 299 pairs | `data/benchmark/judging/adjudication.jsonl` | Main agent |

The main agent reviewed both Sonnet implementations against the task specs before relying on them. Neither changed search or ranking code.

## The query set

| | Count |
| --- | --- |
| Queries | 162 (26 carried over from Phase 0 and Phase 1, 136 new) |
| Information needs | 152 (10 needs have two paraphrases each) |
| Split | 92 dev, 70 test. Test is assigned by hash of the need and contains only new queries |
| Scope | 120 in corpus, 27 partial, 15 out of corpus |
| Level | 149 provision, 13 document (title and citation lookups) |

Categories: ordinary language 37, topic 36, terminology mismatch 21, out of corpus 18, citation 15, exact title 10, acronym 9, broad discovery 8, filtered 8.

## Judging

- **Pool:** 3,397 query–provision pairs over 134 queries (median 25 per query). Every alternative method found candidates the live system never returned: heading-only BM25 added 393 unique candidates, TF-IDF 303, body-only BM25 85.
- **Manual exploration:** judges added 160 provisions the pool missed and named 74 unindexed targets across 47 queries: held-back sections, schedules, rules and other Acts.
- **Agreement** on the 3,397 pooled pairs: 86.2% identical grades, 99.9% within one grade, **Cohen's κ = 0.82** on relevant vs not relevant.
- **Resolution:** 2,928 agreed; 330 one grade apart on the same side of the relevance line, where the lower grade was taken; 299 adjudicated by the main agent. Of those, 260 were read against the text: 139 relevance disagreements, 1 manual addition that both judges added but graded on opposite sides, and 120 manual additions from one judge. The other 39 were manual additions both judges found independently and graded on the same side, where the lower grade was taken.
- **Result:** 3,557 judgments: 205 grade 3, 326 grade 2, 511 grade 1, 2,515 grade 0. Of the 134 pooled queries, 126 have at least one relevant admitted provision. The other 8 are all partial-coverage queries whose answer is held back or not indexed. They are coverage gaps, not retrieval misses, and are excluded from provision metrics.
- **judged@10 = 1.00** on both splits for the baseline run. Every result in the top 10 has a judgment.

## Baseline results

Limit 20. Provision metrics use grade ≥ 2 as relevant. 95% bootstrap intervals are in brackets.

| | Overall | Dev | **Test** |
| --- | --- | --- | --- |
| nDCG@10 | 0.648 [0.59, 0.70] | 0.644 [0.57, 0.71] | **0.651 [0.57, 0.73]** |
| MRR | 0.737 [0.67, 0.80] | 0.761 [0.67, 0.85] | **0.710 [0.61, 0.80]** |
| Recall@10 | 0.631 | 0.638 | 0.623 |
| Success@3 (best-graded answer in top 3) | 0.738 | 0.761 | 0.712 |
| MRR, document level | 0.918 | 0.928 | 0.905 |
| Notice recall (out of corpus and partial) | 0.684 (n=19) | 0.750 (n=12) | 0.571 (n=7) |
| False notice rate (in corpus) | 0.067 (n=120) | 0.092 (n=65) | 0.036 (n=55) |
| Search p50 / p95, in process | 25.6 / 30.4 ms | | |

By category (all splits):

| Category | n scored | nDCG@10 | MRR | Success@3 |
| --- | --- | --- | --- | --- |
| broad discovery | 8 | 0.878 | 1.000 | 0.875 |
| filtered | 8 | 0.839 | 0.875 | 1.000 |
| topic | 34 | 0.801 | 0.951 | 0.912 |
| citation | 9 | 0.746 | 0.815 | 0.889 |
| ordinary language | 37 | 0.528 | 0.577 | 0.595 |
| acronym | 8 | 0.523 | 0.604 | 0.625 |
| terminology mismatch | 20 | 0.461 | 0.552 | 0.550 |

All 13 document-level queries (titles and citations such as "Act 12 of 2003") find the right Act first.

**Reading it.** Search works well when the query uses the statute's own words: topics, filters, citations, cross-Act discovery. It is weak when people use their own words: ordinary-language questions, acronyms and different terminology score 0.46 to 0.53. That gap is the question Phase 5, semantic retrieval, exists to test.

## Failures found

Recorded in the [expansion backlog](../EXPANSION_BACKLOG.md), item 2.7 onward. None was fixed in this phase: the baseline measures the system as it was.

1. **Acronym citations are read as unknown Act titles.** "DPDP Act 2023 obligations of data fiduciary" shows *act_not_indexed* for an Act that is indexed.
2. **Unknown acronyms plus a section number return nothing.** "RERA section 18" returns zero results: the section filter holds, but "rera" matches no text. The judges had to find RERA s.18 by hand.
3. **Terminology gaps.** "non-compete clause validity": none of the 31 pooled candidates was relevant, and the answer, Contract Act s.27 on agreements in restraint of trade, was found only by manual search. Similar misses: "pawn shop rights", "deregistering a ship", "hacking punishment".
4. **The weak-match notice fires on plain questions.** 7 in-corpus queries get a false *weak_match*, for example "someone found my lost wallet, what are their duties" and "punishment for fake ads".
5. **Out-of-corpus queries without a cited Act, or without a year, get no notice.** "GST registration threshold", "Income Tax Act section 80C deduction", "Bharatiya Nyaya Sanhita, 2023 punishment for murder" (a Sanhita, not an "Act"), "divorce by mutual consent", "anticipatory bail" and "trademark infringement remedies" all return confident-looking statutory results with no warning.
6. **Unindexed material answers or completes 47 queries.** Judges named 74 unindexed targets (held-back sections, schedules, rules, other Acts). The held-back sections named most often are in the Contract Act (ss.11, 25, 73, 74, 176), the IT Act (ss.43, 66, 66E, 70B), the FCRA (ss.3, 11, 12), Copyright s.52 and POSH s.4. Search gives no sign that a section exists but is held back. This quantifies [backlog item 1.6](../EXPANSION_BACKLOG.md).

## The Phase 3 exception

P0-010, "consent for processing digital personal data" (query B-010), scores nDCG@10 = 0.90, MRR = 1.0 and Success@3 = 1.0 under the judged benchmark. Both judges independently graded DPDP s.4 (grounds for processing, ranked first) a 3, a direct answer, alongside s.6 (Consent, ranked fifth). The Phase 3 check failed because its single heading-based target (s.6) was too narrow, not because search failed the user. That supports the Phase 3 decision not to tune ranking to the smoke set.

## Known limits of this benchmark

- AI judgments only; κ is agreement between two models, not correctness. A human review of a sample is [backlog item 4.1](../EXPANSION_BACKLOG.md).
- The main agent wrote the queries and adjudicated disagreements while knowing the system. It did not look at system rankings while adjudicating (adjudication sheets carry no rank or method).
- Paraphrase pairs share one intent, but a paraphrase that names a section ("section 69A website blocking orders") reads as a citation, so judges reasonably graded some provisions differently across the pair. The adjudicated grades stand as they are; future paraphrases should keep the same query form.
- Small categories have wide intervals. Acronym and filtered have 8 or 9 scored queries each, and the test split has only 7 notice queries.
- Pools are drawn from lexical methods. A future semantic method may retrieve relevant provisions that nobody judged. Runs report judged@10 and are flagged below 0.9, which is the signal to judge the new pairs before comparing.
