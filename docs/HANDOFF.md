# Handoff: where LawIndex stands and how to continue

Written 25 September 2026 for the next agent. Read this first, then [PHASES.md](../PHASES.md). Everything here is verifiable in the repo. Where this file and the code disagree, trust the code and fix this file.

## What LawIndex is

A local research prototype that finds exact provisions of Indian central Acts and shows each with its verifiable official source. It is personal and non-commercial. Search is lexical only (SQLite FTS5 BM25). There is no AI answering, and nothing is deployed publicly. The vision is in [IDEA.md](../IDEA.md); the phase plan is in [PHASES.md](../PHASES.md).

The project directory is **not a git repository**. There is no version history to fall back on, so before overwriting or deleting anything, look at it first.

## Where the project is

| Phase | Status | Key record |
| --- | --- | --- |
| 0–2 | Closed | `docs/phase-0/`, `docs/phase-1/`, `docs/phase-2/PHASE2_GATE_AUDIT.md` |
| 3: coverage and lexical alpha | **Closed 23 September 2026**, with one recorded exception (P0-010), since resolved | `docs/phase-3/PHASE3_GATE_AUDIT.md` |
| 4: retrieval benchmark | **Closed 25 September 2026.** Targets agreed the same day | `docs/phase-4/PHASE4_GATE_AUDIT.md` |
| 5: semantic and hybrid retrieval | **Proposed, not started.** Waiting for the user to say begin | `docs/phase-5/PLAN.md` |

### The recorded decision

On 25 September 2026 the user agreed the release targets in [docs/phase-4/TARGETS.md](phase-4/TARGETS.md). Phase 4 is closed. Do not change those numbers to fit a later result. Phase 5 and the cheap lexical fixes below are not started; begin either only when the user says so.

## The corpus

- **1,504 searchable sections of 20 central Acts**, in `data/import/lawindex_offline.sqlite3`. The 20 Acts are listed in `docs/phase-3/INVENTORY.md`.
- 1,923 source-listed sections exist. The other **420 are quarantined** because their official HTML and PDF versions disagree, or the text could not be extracted. Every section has an explicit outcome on the coverage page (`#/coverage`, `/api/inventory`).
- 372 provisions were compared by eye against the source PDF. The other 1,132 were admitted under each Act's sampled review (366 sections sampled, 0 discrepancies) and are matched against the PDF automatically. All review is AI review; there has been no human or legal-expert review.
- Not indexed at all: schedules, rules, regulations and notifications, state laws, court judgments. Search shows a notice when a query reaches for these.

## Hard rules

1. **Permission.** The user reports ministry permission for **up to 20 Acts**, for personal, non-commercial use, recorded in `data/phase3/access-authorization.json`. It explicitly does **not** cover more than 20 Acts, associated instruments (rules, regulations, notifications), commercial use, or legal accuracy. Do not add Acts or instruments without a new, recorded permission. Schedules and the 420 quarantined sections of the 20 Acts are within permission.
2. **Search never admits text.** Text becomes searchable only through the canonical importer (`scripts/offline_importer.py`) and review records in `data/review/*.review.json`. `Snapshot` in `lawindex/search.py` re-validates every admitted provision on each request.
3. **Digest-bound files: never edit.** These files are bound by sha256 digests elsewhere, so editing them breaks verification or silently invalidates results:
   - `data/phase3/review-plans/*.json`;
   - review records;
   - `data/benchmark/queries.v1.jsonl`, `data/benchmark/judgments.v1.jsonl`, and anything in `data/benchmark/judging/`;
   - `data/benchmark/runs/baseline-lexical-v1.json`.

   To change the benchmark, create `queries.v2` / `judgments.v2` and a new baseline run.
4. **Do not tune ranking against the test split.** Tune on the dev split only. Report test-split numbers; never inspect test queries one by one while tuning. A ranking change is adopted only under the adoption rule in TARGETS.md.
5. **Say what things are.** Every provision states its review basis. The benchmark uses AI judgments and is not a legal-accuracy measure. Keep that honesty in anything new.
6. **No network fetching** of new sources, no public deployment and no commercial use. One recorded exception, from 25 September 2026: the user allowed downloading the BAAI/bge-small-en-v1.5 embedding weights, and installing `sentence-transformers` and PyTorch into `.venv/`, for Phase 5. That covers model weights and packages only, never legal sources. See `docs/phase-5/PLAN.md`.

## Code map

| Area | Files |
| --- | --- |
| Search and API | `lawindex/search.py` (`Snapshot`, query parsing, excerpts, coverage notices), `lawindex/retrieval.py` (`LexicalRetriever`, filters, per-Act cap), `lawindex/server.py`, `lawindex/coverage.py` |
| Web UI | `web/` (static; `app.js`, `styles.css`) |
| Import and review | `scripts/offline_importer.py`, `reviewed_html.py`, `sampled_agreement.py`, `sample_review_plan.py`, `record_sample_review.py`, `admit_sampled_batch.py`, `phase3_candidates.py`, `structural_store.py`, `ingestion_manifest.py` |
| Verification | `scripts/verify_offline_import.py` (28 checks), `scripts/verify_phase0.py`, `scripts/measure_search_latency.py` |
| Benchmark (Phase 4) | `lawindex/benchmark.py` (data contracts, split rule, corpus fingerprint), `lawindex/evaluation.py` (metrics), `scripts/run_benchmark.py`, `scripts/pool_candidates.py`, `scripts/judging_packets.py`, `scripts/show_provision.py`, `scripts/merge_judgments.py` |
| Phase 5 tooling (Wave 1) | `lawindex/adoption.py` (`--adoption` report), `lawindex/fusion.py` (reciprocal rank fusion, not yet wired into search), `scripts/analyze_notices.py` (weak-match diagnostic), `scripts/unjudged_packets.py` (packets for unjudged pairs, under `data/benchmark/judging-v2/`) |
| Tests | `tests/` (381 tests) |

## How to check everything still works

```bash
python3 -m unittest discover -s tests -q
```
About 3 minutes; 381 tests should pass.

```bash
python3 scripts/run_benchmark.py --compare data/benchmark/runs/baseline-lexical-v1.json --out /tmp/check.json
```
Should print `REPRODUCED`. Without `--out` it writes a new run file into `data/benchmark/runs/`.

```bash
python3 scripts/verify_offline_import.py
```
About 30 minutes; all 28 checks should pass. It runs full re-imports, so run it only after changing import or review code.

```bash
python3 scripts/show_provision.py dpdp-2023:6
```
Reads one admitted provision. `--act SLUG` lists an Act's sections; `--grep PATTERN` searches.

To run the server and UI, run `python3 -m lawindex.server --port 8000` and open `http://localhost:8000`.

## Phase 4 in brief

- 162 queries (92 dev, 70 test; the split is derived from a hash of the information need and is enforced by the validator). 3,557 graded judgments from two model judges (Sonnet 5 as judge A, Opus 5.5 as judge B), κ = 0.82, with 299 disagreements adjudicated by the main agent.
- Baseline, test split: nDCG@10 0.651, MRR 0.710. Strong on statutory wording (topic 0.80, filtered 0.84, broad discovery 0.88). Weak on ordinary language (0.53), acronyms (0.52) and terminology mismatch (0.46).
- Full results, failures and limits: [docs/phase-4/BASELINE.md](phase-4/BASELINE.md). Method: [BENCHMARK_PLAN.md](phase-4/BENCHMARK_PLAN.md) and [JUDGING_GUIDE.md](phase-4/JUDGING_GUIDE.md).

## What to do next

The targets are agreed. Nothing below has started. The proposed Phase 5 plan is [docs/phase-5/PLAN.md](phase-5/PLAN.md). Tasks scoped for delegated agents (Grok 4.7 high fast), in waves, are in [docs/phase-5/DELEGATED_TASKS.md](phase-5/DELEGATED_TASKS.md). In this order, when the user says to begin:

1. **Paired bootstrap comparison.** Done 25 September 2026. `python3 scripts/run_benchmark.py --baseline RUN --candidate RUN` reports, per split, the mean per-query nDCG@10 difference (candidate minus baseline) and a 95% interval (1,000 resamples, seed 0). It reads two run files and does not re-run search. Still required before any ranking change is adopted.
2. **Cheap lexical fixes, measured on dev.** Backlog items 2.7, 2.8, 2.10 and 2.11 in [EXPANSION_BACKLOG.md](EXPANSION_BACKLOG.md):
   - acronym aliases (RERA, DPDP, RTE, IT Act, CPA; only RTI, EPA and POSH have aliases today);
   - stop acronym citations being treated as unknown Act titles ("DPDP Act 2023");
   - recalibrate the `weak_match` notice (7 false positives);
   - a list of known central Act titles so unindexed Acts get a notice.

   Each change must keep the regression floors and be reported against the baseline.
3. **Phase 5: semantic and hybrid retrieval.** Proposed in [docs/phase-5/PLAN.md](phase-5/PLAN.md), not started. Whole-section vectors first, then hybrid fusion, under the same query contract. A new method will surface unjudged results, so check `judged@10` (flagged below 0.9) and judge the new pairs under JUDGING_GUIDE.md before comparing. Splitting long sections into passages is a later, separate experiment.

Longer-term items, including the coverage gaps the user explicitly wants worked on (schedules, the 420 quarantined sections, instruments, state laws, judgments), are in [docs/EXPANSION_BACKLOG.md](EXPANSION_BACKLOG.md). Keep that file current whenever a new gap or idea appears.

## How the user likes to work

- **Plain language.** Explain results simply, with numbers, not jargon. Say clearly what is done, what failed and what is pending.
- **Decisions belong to the user.** Targets, scope, closing a gate and anything touching permission are theirs to decide. Recommend, then ask.
- **Don't overclaim.** Verify before saying something is done, and report failures with evidence.
- **Keep parallel work small.** Running many parallel agents or jobs at once hit the user's usage limits and wasted work. Keep background work to about three jobs at a time, and have long jobs save progress incrementally.
- **Record decisions in the repo.** Update the phase docs, gate audits and backlog as work happens, not only in chat.
