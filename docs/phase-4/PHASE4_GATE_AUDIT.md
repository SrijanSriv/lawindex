# Phase 4 gate audit

**Closed, 25 September 2026.** The user agreed the release targets in [TARGETS.md](TARGETS.md). Phase 4 is closed. No ranking change was made. Phase 5 is proposed in [the Phase 5 plan](../phase-5/PLAN.md) and has not started.

**Verdict, 24 September 2026: every exit criterion was met except the release targets, which were the user's decision.** That decision is now recorded. The findings below are the 24 September audit.

Exit gate, from [PHASES.md](../../PHASES.md): *a repeatable command evaluates a frozen corpus and query set, produces aggregate and per-query reports, and can reproduce the lexical baseline. Judgments, known gaps, splits, and release thresholds are documented.*

| Criterion | Evidence | Result |
| --- | --- | --- |
| A repeatable command evaluates a frozen corpus and query set | `scripts/run_benchmark.py`. Queries validated on load, split recomputed, judgments bound to the corpus fingerprint | **Met** |
| Aggregate and per-query reports | Run JSON has per-query rankings, notices, metrics and timings, plus aggregates by split, category and scope with bootstrap intervals | **Met** |
| Reproduces the lexical baseline | `--compare data/benchmark/runs/baseline-lexical-v1.json` prints `REPRODUCED` | **Met** |
| Judgments documented | [JUDGING_GUIDE.md](JUDGING_GUIDE.md), [BASELINE.md](BASELINE.md#judging): two judges, κ = 0.82, 299 adjudications with rationales, raw outputs retained | **Met** |
| Known gaps documented | [BASELINE.md, failures and limits](BASELINE.md#failures-found); [expansion backlog](../EXPANSION_BACKLOG.md) items 2.7–2.12 | **Met** |
| Splits documented | Derived by hash of the information need, validator-enforced; carried-over queries forced to dev | **Met** |
| Release thresholds documented | [TARGETS.md](TARGETS.md): agreed by the user, 25 September 2026 | **Met** |

## Roadmap work list

| Work item | Status |
| --- | --- |
| 100–200 representative queries across the listed types | 162 queries, 9 categories, including 15 out of corpus and 27 partial |
| Graded relevance with rationale, sources, reviewer and corpus snapshot | Every judgment has grade, rationale, source, resolution, both judges' grades, `reviewer_type` and corpus fingerprint |
| Legal-domain review where needed; model labels not authoritative | **Not done.** No human or legal reviewer was available. Disclosed everywhere; [backlog 4.1](../EXPANSION_BACKLOG.md) |
| Pool from several methods plus manual exploration; mark unjudged separately | 6 methods plus 160 manual additions; unjudged results counted as `judged@10` and never silently scored as judged |
| Dev and held-out test; paraphrases kept together | 92 / 70; 10 paraphrase pairs share a need and so a split |
| Document- and provision-level Recall, Precision, MRR, nDCG; passage mapping | All reported. There are no derived passages yet (Phase 5), so mapping is not needed |
| Out-of-corpus questions handled separately | Scored by notice recall and false notice rate, never by recall |
| Versions, timings and per-query rankings recorded | Corpus fingerprint, query and judgment sha256, per-file code sha256, method, Python and SQLite versions, per-query `search_ms` and `wall_ms`, p50 and p95 |
| Freeze a baseline; record targets before tuning | Baseline frozen before tuning. Targets agreed by the user on 25 September 2026 |

## Verification

- `python3 -m unittest discover -s tests -q`: **305 tests pass**: the 223 existing tests, plus 38 in `tests/test_evaluation.py` and 44 in `tests/test_benchmark_pool.py`.
- `python3 scripts/run_benchmark.py --compare data/benchmark/runs/baseline-lexical-v1.json`: `REPRODUCED`.
- Earlier on 25 September 2026, after the paired-bootstrap tests were added, the suite was **313 tests, OK**, and `--compare` still printed `REPRODUCED`. Closing the gate did not change search or ranking code and did not re-run those checks.
- `python3 scripts/merge_judgments.py merge`: judgments validate against the live corpus and fingerprint.
- No search, retrieval, importer or UI code changed in Phase 4.

## Process notes

- Two Sonnet 5 implementation tasks (T1 harness, T2 pooling and judging tools) were scoped in [SONNET_TASKS.md](SONNET_TASKS.md) and reviewed by the main agent before use. They flagged ambiguities; none needed a contract change.
- The first judging round ran 20 agents in parallel and hit the account's usage limit twice, losing partial work. The rest ran at most three at a time, with judges saving after every query. All 34 batches finished and validate.
