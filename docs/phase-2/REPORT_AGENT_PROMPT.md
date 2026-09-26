# Agent task: read-only ingestion status report

Work in the LawIndex repository. Implement a small offline operator report for the Phase 2 ingestion journal. Read `docs/phase-2/ARCHITECTURE.md`, `scripts/offline_importer.py`, `tests/test_ingestion.py`, and the root README first. This is an operational reporting task, not the Phase 2 structural migration.

## Allowed changes

Create `scripts/report_ingestion.py`, `tests/test_ingestion_report.py`, and `docs/phase-2/REPORTING.md`. Add a link and usage commands to the root README. Do not modify the importer, search API, web UI, existing tests, schema, source captures, review/conflict decisions, or corpus inventory. If a correctness defect blocks this task, report a minimal reproduction rather than expanding scope.

## Deliverable

A standard-library-only CLI:

```
python3 scripts/report_ingestion.py
python3 scripts/report_ingestion.py --db PATH --review-dir PATH --format json
```

Default database `data/import/lawindex_offline.sqlite3`, review directory `data/review`, default format human-readable text; alternative `json`. Resolve defaults relative to repository, not current working directory. Open SQLite in read-only mode; a missing DB must never create one. No network, subprocess imports, schema migration, mutations, or automatic retries.

The report must show:

- The union of current `*.review.json` provision keys and historically attempted keys. Validate required provision keys and reject duplicates or malformed JSON clearly.
- Current-review membership separately from journal status: historical success for a removed review must not look like current admission.
- Latest attempt per provision by greatest `attempt_id`, never timestamp ordering; status, admission outcome, start/end, exception class, and attempt count. Keys with no attempts are `not_attempted`.
- Current canonical admission status separately, if a provision row exists; journal `succeeded` must not be presented as proof of current readiness. Do not claim to reverify source bytes, reviews, legal correctness, or permission.
- Deterministically sorted provision rows, outcome counts over the current review inventory, and separate historical-only count. Counts sum to the declared current inventory. Show a running attempt as `running_or_interrupted` in display with an explanation that the report cannot know whether its owner is alive; retain original `running` in JSON.
- A clear notice that four reviewed provisions do not represent full Act coverage, and public reuse permission remains separate.

Use a versioned JSON shape documented in REPORTING.md, containing inventory count, status counts, historical-only count, rows, and limitations. Do not dump legal text, arbitrary error payloads, or review evidence into the report. SQL parameterize values and use fixed table names. An older database without `import_attempts`, missing/corrupt DB, or malformed reviews gets a concise diagnostic and nonzero exit, not fabricated zero counts. A successfully rendered report returns zero even when it describes failed imports; document this distinction.

## Acceptance tests

Use synthetic temporary SQLite databases/review JSON, not modifications to real fixtures. Cover: missing DB does not create a file; unsupported schema; current item without attempt; latest attempt tie on timestamps ordered by ID; failed then succeeded history; historical-only removed review; running ambiguity; admission status differing from latest attempt; malformed/duplicate reviews; valid JSON and deterministic ordering/counts. Verify DB bytes and review files are unchanged after reporting, including on failures. Prefer behavioral assertions over exact prose snapshots.

Run `python3 -m unittest discover -s tests -v`, `python3 scripts/verify_offline_import.py`, and `python3 scripts/evaluate_search.py`. Do not rebuild the real DB with `--fresh`, since that erases the attempt journal. Finish with changed files, reproduction commands, test results, and remaining limitations. Do not mark Phase 2 complete.
