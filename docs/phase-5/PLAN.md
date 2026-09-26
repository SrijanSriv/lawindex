# Phase 5 plan: does different wording find the right section?

**Proposed 25 September 2026. Not started.** Waiting for the user to say begin. Lexical search stays the default until a result meets the adoption rule in [TARGETS.md](../phase-4/TARGETS.md).

The question, from the [baseline](../phase-4/BASELINE.md): search is strong when the query uses the statute's own words (topic 0.80, filtered 0.84, broad discovery 0.88) and weak when it does not (ordinary language 0.53, acronyms 0.52, terminology mismatch 0.46). Phase 5 tests whether a vector index, and a hybrid of vector and lexical, closes that gap. A negative result is a valid outcome.

## Before this phase

Four small lexical and notice fixes are already listed, and they should come first. They match failures the baseline measured, and an embedding will not fix them:

1. Acronym aliases (RERA, DPDP, RTE, IT Act, CPA). Today only RTI, EPA and POSH have aliases. "RERA section 18" returns nothing.
2. Stop an acronym citation such as "DPDP Act 2023" being reported as an unknown Act when that Act is indexed.
3. Recalibrate the `weak_match` notice (7 false positives on in-corpus queries).
4. A list of known central Act titles, so an unindexed Act gets a notice instead of a confident-looking result.

Each one is measured on the dev split only, reported against the frozen baseline with the paired bootstrap, and adopted only under the rule in TARGETS.md. They are backlog items 2.7, 2.8, 2.10 and 2.11. They are not started.

## What Phase 5 will not do

- No new Acts, rules, schedules or judgments, and no network fetching of sources.
- No public deployment. Embeddings, if used, are computed locally.
- No change to the v1 benchmark files. New judgments, if a method surfaces unjudged provisions, go in a new version.
- No tuning on the test split, and no reading of test queries one by one while tuning.
- Search still admits text only through the importer and review records.

## The experiment, in order

One change at a time, so a gain can be attributed.

1. **Whole-section vectors.** Search today indexes each admitted section as one unit (`whole-section-v1`). The first vector index uses those same 1,504 sections, not a new chunking. The text embedded is the section text already admitted. Title and heading may be added for the vector only, and that extra text is stored apart from the display text. A passage hit always maps back to its provision, so overlapping pieces cannot inflate nDCG.
2. **A replaceable local pipeline.** Record the model name and version with every run. Rebuild vectors only when the text or the model changes. Refuse to query an index with a different model. The corpus is 1,504 sections and the app is local SQLite, so the index can be a local file or a SQLite extension. PostgreSQL is the roadmap's candidate for a later deployment, not for this experiment.
3. **Three modes, one contract.** Lexical, vector and hybrid answer the same query, filters and limit. Lexical stays the default. Hybrid uses reciprocal rank fusion of the lexical top 20 and the vector top 20. The retriever's current ceiling is 20, so 20 and 20 is the starting point; raising it is a separate measured change. Raw lexical and vector scores are not mixed. Duplicate provisions collapse to one result before the page is shown. Filters apply to both sides.
4. **Compare on the benchmark.** Each mode writes a run file. Report dev and test, by category, plus index size, build time and query time (the in-process ceiling is 150 ms). If `judged@10` is below 0.9 on either split, stop and judge the new pairs under the [judging guide](../phase-4/JUDGING_GUIDE.md) before the comparison counts.
5. **Passages later, on their own.** Splitting long sections at subsection or clause boundaries is a different change. Reviewed clause structure exists for a sample, not for all 1,504 sections. Do not mix it into the first hybrid comparison. Short sections would stay whole; unknown boundaries would stay explicit.

Tune fusion weights, if at all, on the dev split only.

## The mode contract (started 25 September 2026)

The user approved starting the structural work. Two modules exist, with tests in `tests/test_vectors_and_modes.py`. Neither is used by search yet.

- **`lawindex/vectors.py`, the vector index.**
  - An index is bound to three things: a named model and version, the passage strategy (`whole-section-v1`), and the corpus fingerprint used by the benchmark.
  - `check` refuses an index built with a different model, for a different corpus, or from changed text. Mixed vectors can never be queried.
  - `build` re-embeds only records whose text or model changed. It reports progress after each batch, so a long build can save and resume.
  - The embedded text is the Act title, heading and body. The displayed text is unchanged.
  - Storage is one JSON file with float32 vectors, and search is exact cosine over every eligible record. It is pure standard library.
  - Measured on the live 1,504 sections with random vectors: 17 ms per query at 384 dimensions and 32 ms at 768, plus 7 ms for `check`. Lexical search is about 30 ms. Both together fit the 150 ms in-process ceiling, before the model's own time to embed the query.
- **`lawindex/modes.py`, the modes.**
  - Modes are `lexical` (the default), `vector` and `hybrid`.
  - `fuse` combines only the ranks of the two sides, never their scores: reciprocal rank fusion with k = 60 over the top 20 from each side.
  - The trace records each result's rank on each side.

Still to do, in the main agent's hands:

1. **Filters.** Move the eligibility logic out of `LexicalRetriever.retrieve` into a shared function, so filters, section and citation constraints apply identically in every mode.
2. **Plumbing.** Add `mode` to `Snapshot.search`, the API and `scripts/run_benchmark.py`, recorded in the trace and the run manifest. Vector and hybrid return a clear "no vector index" error until an index exists; they never fall back to lexical silently.
3. **The per-Act cap in hybrid.** The cap's "competitive" test compares scores. Fusion scores are on a different scale, so whether to cap by rank instead is decided on the dev split.
4. **A real model.** Decided by the user on 25 September 2026: **BAAI/bge-small-en-v1.5**, with 384 dimensions.

**Built, 25 September 2026.**
- `.venv/bin/python scripts/build_vectors.py` wrote `data/index/vectors-bge-small-en-v1.5.json`: 1,504 sections, 384 dimensions, 3.3 MB, 63 s on CPU.
- Model id `BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`.
- A rebuild with nothing changed took 0.0 s, re-embedding nothing, and the index reloads offline.
- Query embedding takes about 20 ms and vector search about 17 ms.
- Informal check with the main agent's own wording, not benchmark queries: "agreement stopping someone from working for a competitor" ranks Contract Act s.27 (restraint of trade) second.
- Noise to handle: sections whose whole text is "Repealed." appear in vector results. Lexical search never surfaces them.

**Recorded exception, 25 September 2026.** The user permitted a one-time network download of this model's weights, and installing `sentence-transformers` and PyTorch into a project virtual environment (`.venv/`). The exception covers model weights and Python packages only. It does not cover any legal source, Act or instrument. The model runs locally. The core app and the test suite stay standard-library only; the embedding code imports the model lazily, and only when an index is built or queried.

## First measurement, 25 September 2026 (provisional: not yet judged)

The modes are wired in. `Snapshot.search(..., mode=...)` is available, the API takes `mode=` (the server loads vectors with `--vectors`), and the benchmark runner takes `--mode`. Lexical is still the default, and a lexical run still reproduces the baseline exactly.

The configuration was fixed before any run and nothing was tuned: bge-small-en-v1.5 over whole sections, and RRF with k = 60 over the lexical top 20 and the vector top 20. The runs are `data/benchmark/runs/vector-bge-small-v1.json` and `data/benchmark/runs/hybrid-bge-small-rrf-v1.json`. Only split-level totals and dev-split detail were looked at.

| Test split | Lexical baseline | Vector | Hybrid |
| --- | --- | --- | --- |
| nDCG@10 | 0.651 | 0.727 | 0.708 |
| Paired gain, 95% interval | — | +0.076 [+0.022, +0.138] | +0.057 [+0.027, +0.094] |
| MRR | 0.710 | 0.829 | 0.785 |
| judged@10, dev / test | 1.00 / 1.00 | 0.71 / 0.69 | 0.92 / 0.89 |
| Search p95, in process | 30 ms | 51 ms | 73 ms |

- **Adoption check for hybrid:** every condition passes except judged@10 on the test split (0.89, below 0.9). All floors hold and no category loses.
- **Vector:** broad discovery drops by 0.055 and judged@10 is about 0.7. Its numbers mean little until the new pairs are judged.
- **Why nothing is decided:** unjudged results count as zero gain, so these numbers are not final. Under TARGETS.md the comparison does not count until the unjudged pairs are judged. Judging the new pairs also changes the ideal ranking for some queries, so the lexical baseline has to be re-run against the new judgments before comparing.
- **Pairs to judge:** 120 for hybrid (56 dev, 64 test), or 374 to cover vector too (`scripts/unjudged_packets.py`).
- **Judging, decided by the user on 25 September 2026:** judge all 374 pairs. Judge A is Grok 4.7 high fast and judge B is Opus 5.5, two different model families as in Phase 4 (Sonnet 5, the Phase 4 judge A, is no longer available). Both use `docs/phase-4/JUDGING_GUIDE.md` and blind packets in `data/benchmark/judging-v2/`, and the main agent adjudicates disagreements. The result will be `data/benchmark/judgments.v2.jsonl`: the v1 judgments plus the new pairs. v1 files are untouched. `merge_judgments.py merge` must be run with `--judging data/benchmark/judging-v2 --out` pointing at a v2 path, never at its default, which is the v1 file. Then the lexical baseline is re-run against v2 as `baseline-lexical-v2`, and all three modes are compared against v2.
- **Judge B, batches 01–07:** 180 pool pairs and 119 manual additions, and every batch passes `check`. Every one of the 119 manual additions was a pair already judged in v1, and 109 of them (92%) got the same grade as v1. That is an independent consistency check on v1. **Merge rule:** a manual pair that is already in v1 keeps its v1 grade, and only pairs new to v1 are adjudicated.
- **Judge B, batches 08–13:** done, and every batch passes `check`. Judge B is complete (13 of 13).

  In batch 12, several cross-Act queries have more fully answering sections than the limit of five manual additions allows, so some likely grade-3 sections stay unjudged. The best answers judge B found outside the admitted text include IT Act s.43, 66 and 66E, RTE Act s.3, FCRA s.11 and 12, the DPDP Schedule, and the Food Security Act s.4 and Second Schedule. These are coverage gaps, not ranking faults.
- **Judge A:** batches 01–07 are done and pass `check`. Batches 08–13 started on 25 September 2026.
- **Still open:** how the per-Act cap should work on fusion scores. The cap currently uses the same score-share test for every mode.

## When a mode becomes the default

Only under [TARGETS.md](../phase-4/TARGETS.md): on the test split, nDCG@10 up by at least 0.03, the paired bootstrap 95% interval excluding zero, every regression floor held, no category of 8 or more scored queries down by more than 0.05, and `judged@10` at least 0.9. The comparison command is:

```bash
python3 scripts/run_benchmark.py --baseline RUN --candidate RUN
```

If hybrid does not clear that bar, lexical remains the default and the plan says so.

## Exit

Lexical, vector and hybrid each have a traceable run on the same corpus. There is a written decision on whether hybrid becomes the default. The aims in TARGETS.md (ordinary language, terminology and acronyms toward 0.65) are directions, not the exit gate.
