# Bounded task: display Phase 3 acquisition coverage and add a read-only operator report

Read `docs/phase-3/ACQUISITION_AND_CANDIDATES.md`, `lawindex/coverage.py`, `lawindex/server.py` and the existing `web/` coverage view. The main agent owns acquisition, candidate extraction, fidelity review and admission. Your task is presentation of the implemented contract, not interpretation of legal text.

Allowed edits: `web/app.js`, `web/styles.css`, a new `scripts/report_phase3_coverage.py`, a new `tests/test_phase3_coverage_report.py`, a new `docs/phase-3/COVERAGE_UI_VERIFICATION.md`, and relevant README usage links. Do not edit acquisition/candidate/coverage backend code, search/retrieval/server/schema/importer, existing tests/review records, PHASES, or any files under `data/`. Do not run `acquire_phase3.py`, the candidate generator, the importer, `--fresh`, network crawls, or a public deployment. Report backend defects with repros rather than fixing outside scope.

## Browser coverage page

Extend `#/coverage` to load `/api/inventory` as well as its existing live corpus information. Keep the existing searchable-provision links and filters working. Display separately: 20 selected Acts, captured Act count, searchable Act count, and searchable provision count. Derive every value from responses, never hardcode counts.

Show one row/card per selected Act: title, capture outcome, source-listed section count, comparison-review-pending count, quarantined count, live searchable provision count and full-Act coverage status. Null counts display “Unknown”; zero displays zero. Clearly explain that captured/matching text is not approved for search. Keep all returned limitations available. Comparison counts overlap historical admissions; do not add them to searchable counts or invent completion percentages. Quarantine does not by itself mean the law's wording is wrong.

The current real data has 20 captured Acts and 1,923 source-listed section records, 895 text-agreement candidates and 1,028 quarantines, but only four searchable provisions across two Acts. These are expectations for manual checks, not constants for code. No full Act is verified complete. Do not link unadmitted provisions into a reader or render raw candidate text. Show errors/unknowns visibly and retain all rows rather than hiding failed Acts.

Fetch races must not replace a newer route. Display inventory failure independently from the searchable-corpus panel: a failed inventory request must not manufacture zero coverage or erase successful corpus data. Support retry without altering source/DB files. Use textContent/DOM helpers, native accessible controls, readable mobile layout, keyboard focus, and no external assets/framework.

## Read-only operator CLI

Create `scripts/report_phase3_coverage.py` using `Snapshot` and `build_coverage` from the existing backend. Accept `--format text|json`, default text. No acquisition, extraction, database writes, subprocesses or network. Render the same semantics as the API, including limitations and unknowns. Catch expected missing/malformed-data errors with a clear stderr message and nonzero exit; avoid partial stdout on failure. Do not treat `data/phase3/coverage.json` as a live authority.

Add meaningful tests with small temporary fixtures or mocked report inputs: null versus zero, all rows preserved including failures, JSON/text consistency, source/candidate counts not mislabelled as searchable, clean unavailable-data diagnostics and no network/write path. Do not reproduce or reimplement backend validation.

## Verify

Run the full Python suite, `scripts/verify_offline_import.py`, and `scripts/evaluate_search.py`. Never run the importer. Check real browser desktop/mobile coverage, direct reload, retry/error handling (use isolated fixtures if needed), navigation back to searchable provisions, safe escaping, and keyboard controls. Hash the real DB before/after any CLI runs. Do not claim checks you did not perform.

Write the verification report with changed files, actual commands/results, browser checks and limitations. Finish with exact reproduction steps and any backend findings. Do not mark Phase 3 complete. Return the result for main-agent inspection.
