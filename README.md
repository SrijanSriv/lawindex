# LawIndex

An open search engine for public law, starting with Indian legislation. Retrieval quality, exact provisions, and source traceability come first.

- [Phase 2 gate audit and remaining owners](docs/phase-2/PHASE2_GATE_AUDIT.md)
- [RTI schedule layout model and review contract](docs/phase-2/SCHEDULE_LAYOUT.md)
- [Private local schedule review viewer](docs/phase-2/SCHEDULE_VIEWER.md)
- [Safe resume and reviewed clause structure](docs/phase-2/QUEUE_AND_STRUCTURE.md)
- [Bounded structure-report agent task](docs/phase-2/STRUCTURE_AGENT_PROMPT.md)
- [Structural schema migration and recovery](docs/phase-2/STRUCTURAL_MIGRATION.md)
- [Phase 2 architecture and reliability contract](docs/phase-2/ARCHITECTURE.md)
- [Phase 2 bounded reporting task](docs/phase-2/REPORT_AGENT_PROMPT.md)
- [Ingestion journal report](docs/phase-2/REPORTING.md)
- [Reviewed clause structure report](docs/phase-2/STRUCTURE_REPORTING.md)
- [Project idea and north star](IDEA.md)
- [Milestone plan](PHASES.md)
- [Market research and existing systems](MARKET_RESEARCH.md)
- [Phase 0 explained — start here](docs/phase-0/README.md)
- [Phase 1 backend architecture and startup](docs/phase-1/ARCHITECTURE.md)
- [Frontend API contract](docs/phase-1/API_CONTRACT.md)
- [Interface agent task](docs/phase-1/UI_AGENT_PROMPT.md)
- [UI browser verification](docs/phase-1/UI_VERIFICATION.md)
- [Phase 0 discovery report](docs/phase-0/SOURCE_DISCOVERY.md)
- [Metadata matrix](docs/phase-0/METADATA_MATRIX.md)
- [First corpus](docs/phase-0/CORPUS.md)
- [Source access/reuse findings](docs/phase-0/ACCESS_AND_REUSE.md)
- [Accepted source-conflict policy](docs/phase-0/CONFLICT_POLICY.md)
- [Offline import readiness manifest](docs/phase-0/READINESS_MANIFEST.md)
- [RTI Rules OCR assessment](docs/phase-0/RTI_RULES_OCR_ASSESSMENT.md)
- [Access-response checklist](docs/phase-0/ACCESS_RESPONSE_CHECKLIST.md)
- [Independent review (historical)](docs/phase-0/INDEPENDENT_REVIEW.md)
- [Follow-up inspection (historical)](docs/phase-0/INSPECTION_FOLLOWUP.md)

## Current state

Phase 2 imports retain per-provision attempt history, isolate failures, and support verified skip-completed recovery with `python3 scripts/offline_importer.py --resume`. Environment Act section 3 has 19 reviewed contextual child ranges; standalone search remains limited to four sections. Plain-text splitting of two RTI schedules remains quarantined. A separate position-preserving schedule model is implemented and awaiting independent review and private viewer verification; it adds no searchable provisions. Do not use `--fresh` for recovery: it deletes that history. The structural schema migration is implemented for the four reviewed sections: source snapshots, immutable versions/reviews, exact passages, and stable public aliases now back search. The full Phase 2 gate remains open; see the [migration and recovery guide](docs/phase-2/STRUCTURAL_MIGRATION.md).

Phase 0's bounded offline technical work is complete. Phase 1's read-only data/search API and its browser interface are both implemented and browser-verified for the bounded four-provision slice — see [UI_VERIFICATION.md](docs/phase-1/UI_VERIFICATION.md) for what was tested. The user has emailed India Code requesting access to 20 Acts; a reply and permitted uses remain pending. Bulk ingestion/public reuse is not cleared and the ten-Act candidate corpus is not fully reviewed.

A bounded offline importer now implements the accepted conflict policy end to end for a four-provision slice across two Acts: RTI Act, 2005 sections 6 and 8, plus (added in a second pass) Environment (Protection) Act, 1986 sections 3 and 5A, are reviewed, hash-anchored, and technically admitted, with known conflicts (RTI-001, RTI-002, KERALA-001, OCR-001) handled exactly as the policy specifies — KERALA-001's enactment date is now resolved from retained-PDF evidence, and OCR-001 has a documented catalogue of concrete error types. A second-pass self-audit found and fixed several importer defects; a later independent review and follow-up inspection found two more (admission was not bound to reviewed extracted-text digests, and a removed-then-restored manifest entry kept a stale removal flag), both now fixed and regression-tested — see [INDEPENDENT_REVIEW.md](docs/phase-0/INDEPENDENT_REVIEW.md) and [INSPECTION_FOLLOWUP.md](docs/phase-0/INSPECTION_FOLLOWUP.md) for the historical findings and the readiness manifest's "Remediation" section for the fixes. See the [readiness manifest](docs/phase-0/READINESS_MANIFEST.md) for exactly what is reviewed, admitted, excluded, and still pending. This is a technical-readiness result, independent of India Code's access decision — it does not make any content publicly indexable.

Retained local evidence includes 16 HTTP captures, five PDFs, 11 Act metadata observations, a 12-entry manifest (10 candidates and two quarantine fixtures), and 24 seed queries. Raw evidence is not a licensed corpus release.

## Reproduce the offline checks

Requires Python 3 and Poppler's `pdfinfo`, `pdftotext`, and `pdftoppm` on PATH. No Python packages or network requests are needed:

```sh
python3 scripts/build_phase0_artifacts.py
python3 scripts/verify_phase0.py
python3 scripts/offline_importer.py --fresh
python3 scripts/verify_offline_import.py
```

The first command verifies original capture hashes and regenerates derived PDF reports and the corpus manifest from retained observations. The second checks cross-file consistency and query references. The third runs the offline importer against `data/discovery/` fixtures and `data/review/` decisions, producing `data/import/lawindex_offline.sqlite3` and `data/import/readiness_manifest.json`. The fourth runs its regression suite (RTI mismatch handling, hash-bound anchors, conflicting-metadata resolution, OCR exclusion, incomplete-source invalidation, idempotence across every table, changed-source/changed-extraction-method/changed-extracted-text invalidation via reviewed-output digests, footnote-consistency and footnote-wording checks, watermark-rule safety against false positives, excerpt-to-source mapping, reviewer attribution, dev-query honesty, and existing-database record-removal/restoration round trips) — run `python3 scripts/verify_offline_import.py` directly for the current check count and full list; it changes as gaps are found and closed, most recently in the [readiness manifest's remediation note](docs/phase-0/READINESS_MANIFEST.md#remediation-2026-09-20-binding-admission-to-reviewed-output-and-fixing-manifest-restoration-state).

`scripts/discovery_fetch.py` is the bounded capture helper used during discovery. It is not a scheduled crawler or production importer. See the access note before expanding source requests.

### Ingestion journal report

A read-only operator report over the `import_attempts` journal and the current review inventory — see [REPORTING.md](docs/phase-2/REPORTING.md) for the full JSON shape and what it does and does not verify:

```sh
python3 scripts/report_ingestion.py
python3 scripts/report_ingestion.py --db PATH --review-dir PATH --format json
```

It opens the database read-only and never creates or modifies it or the review files; a missing database is reported as an error, not silently created.

### Reviewed clause structure report

A read-only inspector over the reviewed contextual clause tree (Environment Act section 3's 19 contextual children) — see [STRUCTURE_REPORTING.md](docs/phase-2/STRUCTURE_REPORTING.md) for the full JSON shape, the validation it performs, and what it does not verify:

```sh
python3 scripts/report_structure.py
python3 scripts/report_structure.py --db PATH --format json
```

It opens the database read-only and never creates, migrates, or modifies it; children are contextual annotations, not independently searchable provisions, and legal body/footnote text is never printed.

## Run the local Phase 1 app (API + browser UI)

After the offline import above, use Python 3.11+ with SQLite FTS5 support:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/evaluate_search.py
python3 -m lawindex.server
```

Then open **http://127.0.0.1:8000/** in a browser for the search interface, or hit the API directly: [current coverage](http://127.0.0.1:8000/api/corpus), [an example search](http://127.0.0.1:8000/api/search?q=RTI%20section%206). No additional Python or Node packages are required — the UI in `web/` is plain HTML/CSS/JS served by the same process, with no build step. The backend is loopback-only; do not deploy it publicly.

The UI (`web/index.html`, `web/app.js`, `web/styles.css`) implements a search view, a provision view (full text, footnotes, conflict notices, source links), and a coverage/navigation view against the [API contract](docs/phase-1/API_CONTRACT.md), using hash routes (e.g. `http://127.0.0.1:8000/#/provisions/rti-2005%3A6`). It was manually verified in a real browser — see [UI_VERIFICATION.md](docs/phase-1/UI_VERIFICATION.md) for the exact checks and results, including a 2026-09-21 [remediation pass](docs/phase-1/UI_VERIFICATION.md#remediation-2026-09-21) that fixed three review-flagged issues (explicit section-only search resolving from metadata, the skip link no longer changing the app route, and a PDF page-footer digit no longer leaking into RTI s.8/Environment s.3 body text) plus a low-contrast footnote badge, all with regression coverage.

Search is SQLite FTS5 BM25 over eligible provisions, with live evidence validation and exact excerpts. All six existing development queries ranked their expected provision first; this is a four-provision smoke result, not a general retrieval benchmark. See [actual results](docs/phase-1/DEV_RESULTS.md).

## Build the private schedule review candidate

```sh
python3 scripts/schedule_layout.py
```

The command prints the exact artifact path and review status. See the [layout contract](docs/phase-2/SCHEDULE_LAYOUT.md) and [closure audit](docs/phase-2/PHASE2_GATE_AUDIT.md). Artifacts stay under ignored `data/import/`; generation does not grant search admission or public reuse permission.

To look at that candidate against the retained PDF pages, render the private local viewer:

```sh
python3 scripts/render_schedule_review.py --artifact data/import/schedules/<digest>.json --output-dir data/import/schedule-viewer
```

Open the printed `index.html` directly from disk. See [the viewer's own contract](docs/phase-2/SCHEDULE_VIEWER.md) for what it does and does not do; it never grants search admission, never claims a reviewer accepted anything it did not actually accept, and never touches the database or importer.

### Phase 2 status

The bounded offline Phase 2 technical gate is closed; see the [final audit](docs/phase-2/PHASE2_GATE_AUDIT.md). The four reviewed sections remain searchable. Schedules have a separate AI layout review and verified private viewer, but remain excluded from search. India Code access/reuse permission remains a separate pending dependency.

To render the viewer with the accepted review, include `--review data/review/structure/rti-schedule-independent-review.json` in the viewer command above. Omitting it deliberately produces a pending-review view.

### Phase 3 in progress — 22 September 2026

The user reports ministry permission to choose and use up to 20 Acts for this personal, non-commercial project, superseding the earlier pending-access status. See the [proposed inventory](docs/phase-3/INVENTORY.md) and [architecture](docs/phase-3/ARCHITECTURE.md). The searchable corpus is 1,504 provisions across all 20 authorized Acts, as of 23 September 2026. 372 have been compared by eye against the source PDF: ten individual reviews plus 362 sections from the Acts' sampled reviews (366 sections were sampled, four of which were already individually reviewed). The other 1,132 were admitted under their Act's sampled review and are matched whole against the source PDF automatically. Each provision states its own basis in search. 420 source sections whose HTML and PDF disagree remain quarantined, so no Act has full coverage. What could come next, including the five coverage gaps, is tracked in the [expansion backlog](docs/EXPANSION_BACKLOG.md).

The API now supports `act`, `year`, `ministry`, and `document_type` filters, combined with `q` and `limit`. For example, `/api/search?year=2005&limit=10` browses admitted RTI provisions. Options are returned in `/api/corpus`. The filter controls are implemented and the main agent has accepted the bounded UI handoff; see [UI verification](docs/phase-3/UI_VERIFICATION.md). Corpus expansion remains in progress.

### Phase 4 retrieval benchmark

The benchmark is 162 queries with graded AI judgments, split into dev and held-out test. The lexical baseline is frozen and reproducible; see the [baseline report](docs/phase-4/BASELINE.md), [proposed targets](docs/phase-4/TARGETS.md) and [plan](docs/phase-4/BENCHMARK_PLAN.md).

```
python3 scripts/run_benchmark.py --compare data/benchmark/runs/baseline-lexical-v1.json
```

### Phase 3 source acquisition and coverage

All 20 selected Acts now have retained source records and PDFs. Candidate comparison remains separate from search admission: the searchable corpus is still four reviewed provisions. See [acquisition details and commands](docs/phase-3/ACQUISITION_AND_CANDIDATES.md). The live coverage contract is available at `/api/inventory`; the coverage UI and read-only reporting command are implemented and accepted (see [verification](docs/phase-3/COVERAGE_UI_VERIFICATION.md)). Phase 3 remains open.

The `#/coverage` browser view now renders this same `/api/inventory` contract — selected/captured/searchable Act counts, searchable provision count, and one row per selected Act with capture outcome, source-listed section count, comparison-review-pending/quarantined counts, live searchable provisions, and full-Act coverage status — alongside the existing live searchable-corpus panel. A read-only operator CLI renders identical semantics from the terminal:

```sh
python3 scripts/report_phase3_coverage.py
python3 scripts/report_phase3_coverage.py --format json
```

It performs no acquisition, extraction, database write, subprocess, or network access. See [coverage UI verification](docs/phase-3/COVERAGE_UI_VERIFICATION.md) for what was checked and known limitations.
