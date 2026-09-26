# Phase 3 first backend increment — verification

22 September 2026. This is not a Phase 3 closure record.

## Implemented

- Retrieval protocol and lexical implementation separated from admission/display orchestration.
- Exact intersecting Act/year/ministry/document-type filters with constraints applied before top-k and total count computed before truncation.
- Filter-only browsing, live-admitted option lists, nullable observed source metadata, bounded candidate traces.
- Personal/non-commercial 20-Act permission recorded from the user; proposed 20-Act inventory kept separate from admission input.

## Checks run

- `python3 -m unittest discover -s tests -q`: 139 tests pass.
- After updating the ingestion report's historical pending-permission wording, `python3 -m unittest tests.test_ingestion_report -q`: 23 tests pass.
- `python3 scripts/verify_offline_import.py`: all 26 checks pass.
- `python3 scripts/verify_phase0.py`: 16 original capture hashes and existing artifacts pass.
- `python3 scripts/evaluate_search.py`: all six development queries rank the expected provision first. Still a smoke set, not a benchmark.

Seven new retrieval tests cover post-filter top-k correctness and totals, missing metadata, intersecting constraints, filter-only browsing, source collection versus subject category, malformed inputs/limits, absence of unknown-Act fallback, and HTTP query parsing. Existing withdrawal/tamper/source/reviewer tests still pass through the refactored retrieval path.

No real import, `--fresh`, source-body acquisition, or admission expansion was performed. The source references for the ten new proposed Acts were located through official web search results; those references are discovery leads, not retained or reviewed source text. No schema migration was needed for derived metadata filters. SQLite remains the canonical store; there are no vectors or production-hosting changes.

The UI has not been modified or browser-verified for filters; that is the bounded agent handoff. Larger-corpus retrieval performance, phrase handling, exact Act-number syntax, generic extraction, and expanded coverage remain main-agent work.

## Acquisition and coverage increment — 22 September 2026

- Full suite: **149 tests pass**, including ten new bounded-acquisition/candidate/coverage tests. The known non-failing SQLite ResourceWarning appeared once.
- After a small candidate-CLI diagnostic/exit-code adjustment, the ten targeted pipeline tests pass again.
- All 26 importer checks, Phase 0 verification (16 original captures), and six search smoke queries pass. The real DB hash is unchanged across those verification commands; no real import or reset was run.
- Actual loopback `GET /api/inventory`: 200, 20 selected Acts, 20 captured Acts, four live searchable provisions.
- Every selected Act has a reconciled source SECTION listing and retained original PDF(s). The coverage report verifies materialized source records against captured HTTP body hashes.
- Candidate accounting: 1,923 source-listed records; 895 whitespace-only agreement candidates, 1,028 quarantines. Neither group is newly admitted or visually reviewed by this increment.
- Regression cases cover inventory limits/duplicates, host boundaries, incomplete HTTP-200 downloads, bounded retries, cache corruption, materialized metadata tampering, substring/ambiguous/punctuation alignment rejection, unknown markup, missing/failed Act counts, and inability of candidate counts to grant search admission.

See [acquisition contract](ACQUISITION_AND_CANDIDATES.md) and the [coverage presentation handoff](COVERAGE_AGENT_PROMPT.md). Phase 3 remains open; the main agent still owns fidelity review, the canonical admission bridge, expanded retrieval/navigation work and the final gate audit.

## Update — 22 September 2026, batch 1 and search work

- `python3 -m unittest discover -s tests -q`: 180 tests pass.
- `python3 scripts/verify_offline_import.py`: all 27 checks pass (new: search-side Snapshot serves every importer admission).
- `python3 scripts/offline_importer.py` against the working database: 12 documents, 10 admitted, 0 failed; backup at `data/import/lawindex_offline.sqlite3.pre-phase3-batch1.sqlite3`.
- `python3 scripts/measure_search_latency.py`: validation median 4.5 ms, search median 0.6 ms at 10 provisions.
- UI inspected in the local browser: phrase query results with context labels, provision navigation between admitted sections (including end states), no console errors.

## Update — 22 September 2026, sampled batch tooling

- `python3 -m unittest discover -s tests -q`: 203 tests pass.
- `python3 scripts/verify_offline_import.py`: all 28 checks pass (new: sampled admissions stay bound to their plan and never overclaim).
- RTI sampled batch imported: 12 documents, 34 admitted, 0 failed; `Snapshot` serves 34 with 0 exclusions.
- UI inspected: the provision page states the sampled basis, and unsampled results carry a "Text matched to source; not individually reviewed" badge.
- Corpus-size-dependent test expectations were made corpus-relative so later batches do not break them.

## Update — 22 September 2026, ingestion-manifest migration

- `python3 -m unittest discover -s tests -q`: 212 tests pass.
- `python3 scripts/verify_offline_import.py`: all 28 checks pass.
- `python3 scripts/verify_phase0.py`: passes again after being scoped to Phase 0 evidence (it had been failing since the first Phase 3 batch).
- `python3 scripts/build_phase0_artifacts.py`: 22 capture hashes, 8 PDFs, 22 manifest entries (20 candidates, 2 quarantine fixtures).
- Import: 22 documents, 76 admitted, 0 failed; `Snapshot` serves 76 with 0 exclusions across 4 Acts.
- `python3 scripts/measure_search_latency.py`: validation 25.9 ms median, search 3.4 ms median at 76 provisions.

## Update — 23 September 2026, all twenty Acts admitted

- `python3 -m unittest discover -s tests -q`: 213 tests pass in 188 s. At this corpus size, before the memoization fixes, the suite took about 25 minutes.
- `python3 scripts/verify_offline_import.py`: all 28 checks pass on the full corpus, including the sampled-admission binding check and the zero-silent-exclusion check.
- `python3 scripts/verify_phase0.py`: passes.
- Import into the working database: 22 documents, 1,504 admitted, 0 failed. `Snapshot` serves 1,504 provisions across 20 Acts with 0 exclusions: 372 individually compared, 1,132 admitted under their Act's sampled review.
- `python3 scripts/measure_search_latency.py`: snapshot validation 165 ms median and search 22 ms median per request, at 1,504 provisions.
- UI inspected in the local browser at full scale: search ranks Merchant Shipping results correctly and badges unsampled provisions, the Act filter lists all 20 Acts, the coverage page's live counts sum to 1,504, and there are no console errors.
- Earlier runs in this session failed because tests overlapped with admissions being written to the live database. The run above was made on a quiet tree after the last admission.

