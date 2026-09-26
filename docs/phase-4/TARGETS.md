# Release targets

Proposed 24 September 2026. **Agreed by the user, 25 September 2026.** Written from the [frozen lexical baseline](BASELINE.md) before any tuning, as PHASES.md requires. Later phases may not change these numbers to fit a result. They can be revised only with a recorded reason, before the run they are applied to.

All quality numbers are on the **test split** (70 queries) unless stated. Tuning looks only at dev.

## 1. Regression floors: what no change may break

| Measure (test split) | Baseline | Floor |
| --- | --- | --- |
| nDCG@10 | 0.651 | ≥ 0.63 |
| MRR | 0.710 | ≥ 0.69 |
| MRR, document level | 0.905 | ≥ 0.88 |
| Document-level queries (titles, citations), all splits | 13 of 13 right Act first | 13 of 13 |
| False notice rate, in corpus, all splits | 0.067 | ≤ 0.10 |
| Notice recall, out of corpus and partial, all splits | 0.684 | ≥ 0.68 |

The floors sit about 0.02 below baseline. The system is deterministic, so any drop is a real change in rankings, but the test split is small, and the floors allow for changes that trade one query against another.

## 2. Adoption rule: when a ranking change becomes the default

A change (new weights, semantic or hybrid retrieval, a reranker) becomes the default only if, on the test split:

1. **nDCG@10 improves by at least 0.03 absolute** over the current default, **and** a paired bootstrap on per-query nDCG@10 differences (1,000 resamples, seed 0) gives a 95% interval that excludes zero;
2. every regression floor above still holds;
3. no category with at least 8 scored queries (all splits) loses more than 0.05 nDCG@10;
4. judged@10 is at least 0.9 on both splits. If it is not, the unjudged pairs are judged under the [judging guide](JUDGING_GUIDE.md) before the comparison counts.

The paired bootstrap is available, added 25 September 2026:

```bash
python3 scripts/run_benchmark.py --baseline RUN --candidate RUN
```

It reads two run files and does not re-run search. For each split it reports the mean of the per-query nDCG@10 differences, candidate minus baseline, with a 95% interval from 1,000 resamples and seed 0. Queries without an nDCG@10 in both runs are left out. The command reports the interval. Adding `--adoption` also checks every condition above and every floor in section 1, and ends with `ALL CONDITIONS MET` or `NOT MET: …`. The floor for document-level queries is exactly 13 of 13, so a v2 query set needs a recorded update to that number. Whether a later change is adopted is still a decision under the rule above.

### Clarification for notice-only changes, 25 September 2026

The user decided this on 25 September 2026, before any notice-only change was measured. A change that only adds or alters notices, and leaves every ranking identical, cannot raise nDCG@10, so condition 1 above does not apply to it. It becomes the default if:

- every per-query ranking is unchanged from the current default;
- every regression floor in section 1 still holds;
- the false notice rate (in corpus, all splits) does not rise.

A change that alters any ranking is a ranking change and falls under the full rule above.

### Decision on G4 (acronym aliases), 25 September 2026

The aliases fell short of the rule: test gain +0.022, with an interval touching zero. The user chose to take them out. The change and its tests are kept in `docs/phase-5/candidates/g4-acronym-aliases/`. They will be re-measured together with the other lexical fixes, as one change, against the rule above.

## 3. Goals for Phase 5–6 (directions, not gates)

| Measure | Baseline | Goal |
| --- | --- | --- |
| nDCG@10, ordinary language + terminology mismatch + acronym (all splits) | 0.46–0.53 | ≥ 0.65 |
| Notice recall, out of corpus | 0.60 (15 queries) | ≥ 0.80 |
| False notice rate | 0.067 | ≤ 0.05 |

## 4. Latency

| Measure | Baseline | Ceiling |
| --- | --- | --- |
| Benchmark search p95, in process (`search_ms`) | 30.4 ms | ≤ 150 ms |
| End-to-end HTTP p95 (`measure_search_latency.py --http`) | 249 ms (Phase 3) | < 500 ms |

The in-process ceiling leaves room for a vector search and fusion step. The HTTP ceiling is the Phase 3 target and still applies.

## 5. Benchmark maintenance

- Changing the query set or judgments produces a new version (`queries.v2`, `judgments.v2`) and a new baseline run. Version 1 files are never edited, because run records bind their digests.
- A new corpus (for example, admitting held-back sections) changes the corpus fingerprint. Judgments are then revalidated: pairs for removed provisions are dropped, new provisions in the top 20 are judged, and the baseline is re-run before any comparison.
