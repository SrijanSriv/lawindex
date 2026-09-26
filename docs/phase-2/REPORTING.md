# Ingestion journal report

`scripts/report_ingestion.py` is a read-only operator report over the Phase 2
`import_attempts` journal (see [ARCHITECTURE.md](ARCHITECTURE.md)) and the
current `data/review/*.review.json` inventory. It is the first item in
[ARCHITECTURE.md's remaining order of work](ARCHITECTURE.md#remaining-order-of-work)
("Build a read-only operator report over the implemented journal"), and only
that item. It does not migrate the schema, does not touch the importer, and
does not claim Phase 2 is complete.

## What it does and does not do

- Standard-library-only; no network, no subprocess, no schema migration.
- Opens the SQLite database strictly read-only, built from `Path.as_uri()`
  plus `?mode=ro` (not raw string interpolation, which would mis-handle a
  path containing `#` or `?`). A missing database file is reported as an
  error and is never created.
- Runs every query — the schema check and both the journal and canonical
  admission lookups — inside one explicit read transaction (`BEGIN` ...
  `ROLLBACK`), so the report reflects a single consistent database snapshot
  even if the importer is writing concurrently. Without this, two separate
  implicit reads could combine a journal row from before a write with a
  provisions row from after it — a combination that never existed together.
  The transaction is always rolled back, never committed.
- Validates both the required tables (`import_attempts`, `provisions`) and
  their required columns before querying; a database from an incompatible or
  older schema is reported as a diagnostic (exit `1`), not an unhandled
  traceback.
- Never writes to the database or to the review directory. The acceptance
  tests assert the database and review files are byte-identical before and
  after every run, including runs that fail.
- Review files are read as UTF-8; a file that is not valid UTF-8 is reported
  as a diagnostic naming the file, not an unhandled traceback.
- Does **not** reverify source bytes, re-run extraction, re-check reviewer
  sign-off, or make any legal-correctness or public-reuse-permission
  determination. It only reports what the journal and the current review
  inventory already say.
- A journal `succeeded` status, or a canonical `admitted` admission status,
  describes what a past import run recorded — it is not re-verified here and
  is not proof current readiness holds right now (a review record or manifest
  entry can be removed after a successful attempt; see
  `invalidate_stale_records` in `scripts/offline_importer.py`).

## CLI

```sh
python3 scripts/report_ingestion.py
python3 scripts/report_ingestion.py --db PATH --review-dir PATH --format json
```

| Flag | Default | Notes |
| --- | --- | --- |
| `--db` | `data/import/lawindex_offline.sqlite3` | Resolved relative to the repository root, not the current working directory. |
| `--review-dir` | `data/review` | Same resolution rule. Only `*.review.json` files are read as the current inventory. |
| `--format` | `text` | `json` emits the versioned shape documented below. |

## Exit codes

- `0`: the report rendered successfully. This is returned even when the
  report describes failed or quarantined imports — a successful *render* is
  distinct from the *content* being all-clear. Check `status_counts` in the
  JSON output (or the printed counts in text mode) to see whether anything
  failed.
- `1`: the report itself could not be trusted or rendered — a missing or
  corrupt database, a database missing the `import_attempts`/`provisions`
  tables (an older schema, from before the journal existed), a missing
  review directory, or a malformed/duplicate review record. A concise
  diagnostic goes to stderr. Nothing is fabricated in place of the missing
  data (no zero counts standing in for "unknown").

## JSON shape (`report_schema_version: 1`)

```json
{
  "report_schema_version": 1,
  "current_review_inventory_count": 4,
  "status_counts": {
    "not_attempted": 0,
    "succeeded": 4,
    "quarantined": 0,
    "failed": 0,
    "interrupted": 0,
    "running_or_interrupted": 0
  },
  "historical_only_count": 0,
  "rows": [
    {
      "provision_key": "rti-2005:6",
      "in_current_review": true,
      "latest_attempt": {
        "attempt_id": 3,
        "status": "succeeded",
        "display_status": "succeeded",
        "admission_status": "admitted",
        "started_at": "2026-09-21T06:21:08.319Z",
        "finished_at": "2026-09-21T06:21:08.323Z",
        "error_type": null,
        "attempt_count": 1
      },
      "canonical_admission_status": "admitted"
    }
  ],
  "limitations": ["..."]
}
```

Field notes:

- `rows` covers the **union** of current review-inventory provision keys and
  every provision key that ever has a row in `import_attempts`, sorted
  ascending by `provision_key` for determinism.
- `in_current_review`: whether a `*.review.json` file currently declares this
  key. A key with attempts but no current review file (`in_current_review:
  false`) is historical-only — a past success there must never be read as
  current admission.
- `latest_attempt` is chosen strictly by the greatest `attempt_id` for that
  provision key, never by `started_at`/`finished_at` (clock skew or
  concurrent commits make timestamp ordering unreliable; `attempt_id` is a
  monotonic `AUTOINCREMENT` primary key). A key with zero rows in
  `import_attempts` gets a synthetic `not_attempted` entry with
  `attempt_id: null`.
- `latest_attempt.status` preserves the raw journal value (including
  `running`). `latest_attempt.display_status` is the same value except
  `running` is rendered as `running_or_interrupted`: this report has no way
  to know whether the process that started that attempt is still alive, so
  it deliberately refuses to imply either "in progress" or "crashed".
  `status_counts` (and the text-format summary) use `display_status`; only
  the JSON `rows[].latest_attempt.status` field keeps the original `running`
  value.
- `latest_attempt.attempt_count` is the total number of attempts ever
  recorded for that key, not just whether the latest one succeeded.
- `canonical_admission_status` is the current `provisions.admission_status`
  for that key, independent of `latest_attempt.admission_status`. They can
  differ — for example after `invalidate_stale_records` marks a provision
  `invalidated_review_record_removed` even though its last journal attempt
  still reads `succeeded`/`admitted`. Present as `null` when no `provisions`
  row exists for that key (e.g. every attempt failed before a canonical row
  was ever written, or the key is historical-only and was later purged).
- `status_counts` is computed **only** over rows where
  `in_current_review` is true, bucketed by `display_status`
  (`not_attempted`, `succeeded`, `quarantined`, `failed`, `interrupted`,
  `running_or_interrupted`). The bucket values always sum to
  `current_review_inventory_count`.
- `historical_only_count` is the count of rows where `in_current_review` is
  false — kept as a separate figure, not folded into `status_counts`, so it
  can never be mistaken for current-inventory coverage.
- `limitations` is a fixed list of operator notices, including that the
  four ever-reviewed provisions are not full Act coverage and that public
  reuse/indexing permission from India Code is a separate, still-pending
  question (see `docs/phase-0/ACCESS_AND_REUSE.md`).

Bumping `report_schema_version` is required for any future change to the
meaning or presence of an existing field; purely additive optional fields may
be added without a bump, but should still be noted here.

## Review-inventory validation

Every `*.review.json` file in `--review-dir` is parsed and must contain a
non-empty string `provision_key`. Malformed JSON, a missing `provision_key`,
or two files declaring the same `provision_key` are all reported as a
top-level error (exit `1`) rather than silently dropping or merging records —
an unreliable inventory must not be presented as if it were a reliable one.

## Reproduce

```sh
python3 scripts/report_ingestion.py
python3 scripts/report_ingestion.py --format json
python3 -m unittest discover -s tests -v
```
