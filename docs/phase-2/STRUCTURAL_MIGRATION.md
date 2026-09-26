# Structural storage v1

Implemented 21 September 2026. This closes the structural schema migration for the bounded four-provision slice. It does not close all of Phase 2 or establish support for parsing every legal structure.

## What changed

The database now separates retained sources, extraction results, stable provision identities, text versions, review decisions, and exact passages. Old versions are immutable. A small `current_versions` table selects which reviewed version is currently available; withdrawing a review or starting revalidation clears that selection without erasing history.

Existing URLs such as `rti-2005:8` remain aliases. Search now obtains body and footnote text from the structural version, after checking it against the live review, reviewer, source bytes, scope, conflicts, and compatibility projection. A missing or inconsistent version is excluded; search cannot silently fall back to the old text table. Requests read one SQLite transaction.

## Tables

| Table | Role |
| --- | --- |
| `documents` | Existing document registry; `act_slug` remains the stable local document identifier. Existing metadata/permission behavior is preserved. |
| `source_blobs` | SHA-256 and length of retained bytes. Private copies live at `data/import/source-blobs/<sha256>.body`. |
| `source_snapshots` | Capture observation: document, representation, blob hash, source URL, known capture time, original path, and complete capture metadata. Different observations can reference identical bytes. |
| `extractions` | Source snapshot, extraction method version, configuration and digest, output digests, and verified-output status. Failed/quarantined attempts stay in `import_attempts`; they do not create approved text versions. |
| `structural_nodes` | Stable internal UUID for a provision identity, independent of its displayed number. |
| `provision_aliases` | Existing public provision key to internal node. Aliases cannot be reassigned. |
| `node_versions` | Immutable text, label, heading, kind, parent version, sibling position, extraction reference, and source/PDF anchors. |
| `version_footnotes` | Separately labeled footnote text, digest, and anchor attached to a particular version. |
| `version_admissions` | Exact review and reviewer records and hashes, bound to one node version. |
| `passages` | Exact body or footnote slices, Unicode code-point offsets, and strategy version. Current strategy is `whole-section-v1`. |
| `current_versions` | Revocable public-key → version/admission selection. |
| `instrument_relationships` | Separate documents connected by a named relationship and supporting source snapshot/anchor. Empty for the current corpus. |
| `structural_schema` | Explicit schema version, currently 1; unknown versions are refused. |

`provisions`, `review_decisions`, and `excerpts` remain importer-maintained compatibility projections for existing reports/checks. They are written in the SAME per-item transaction as structural promotion. The search reader requires agreement and obtains text from `node_versions`/`version_footnotes`; these projections are not independent writable sources of truth. They may be retired through a later versioned migration once remaining consumers move.

## Admission and identity rules

- DDL alone does not backfill old rows as approved. The ordinary importer re-runs its source and expected-output checks against retained evidence, then promotes each accepted provision.
- Promotion independently checks source hashes, text digests, review admission, and record/review agreement. It stores the review and reviewer as immutable evidence; changing either requires another import and admission record.
- New source bytes cannot inherit the approval for old bytes. Repeated imports of identical inputs reuse the same immutable rows. Attempt history intentionally grows.
- Internal node UUIDs are assigned once when an explicitly reviewed public key first enters this database. Reimports retain them. Restoring the database retains them; deliberately discarding the database with `--fresh` also discards those identities and history. Public aliases remain stable across rebuilds.
- Automatic renumbering reconciliation is not implemented. A differently labeled public key is not automatically the same legal provision. Future alias/identity mappings require explicit evidence and a dedicated migration/workflow.
- Review snapshots are AI review records, not new legal-expert certifications. Capture time is not a legal effective date.

## Hierarchy and passages

The schema supports chapters, sections, subsections, clauses, schedules, tables, and unknown kinds. A parent must already exist in the same extraction. Document/source bindings must agree; self-parenting, repeated node ancestry, duplicate sibling positions, and history updates/deletions are rejected. Foreign keys are enabled on every importer connection. Other direct writers are unsupported.

The actual backfill contains four section nodes with null parents and null sibling positions: surrounding hierarchy/order has not been separately modeled or reviewed. Nested clause markers remain preserved in the full reviewed section text. No chapter, clause, schedule, table, or rules relationship is fabricated.

Passage insertions must exactly match their body's or footnote's stored slice. The current whole-section passages preserve all qualifications; body and footnotes are separate. Synthetic tests exercise hierarchy, relationship evidence, and Unicode offsets, but do not establish legal parsing fidelity for real schedules or tables. That work remains part of Phase 2.

## Upgrade and recovery

Run the existing importer without `--fresh`:

```sh
python3 scripts/offline_importer.py
python3 scripts/report_ingestion.py
```

The importer acquires its usual single-writer lock. Before its first structural upgrade of an on-disk database, SQLite's backup API creates a uniquely named sibling file matching `*.pre-structure-v1-*.sqlite3`. The migration runs DDL and its version marker in one transaction; any failure rolls it back. The backup contains the prior database, including its import journal. Subsequent migrations at the same supported version do not create another backup.

Backfilling is the normal restartable per-provision import AFTER schema installation. An interrupted backfill may leave the schema installed and only some current versions populated. Rerun the same import; do not reset the database. Old-schema databases are refused by the new reader until migrated. Running imports may temporarily reduce available results because queued provisions are revoked before revalidation, as in the first Phase 2 increment.

A blob is written atomically before the referencing transaction commits and is never overwritten. A failed item may leave an unreferenced private blob. No garbage collection is implemented. A corrupt existing blob causes a failure rather than being silently replaced. Preserve the database, retained discovery/review files, and the `source-blobs` directory together for a full backup. SQLite backup files alone do not contain raw PDF bytes.

### Restore drill / rollback

The automated migration test restores a backup into a separate database using SQLite's backup API, checks integrity, and verifies the legacy rows and schema. To inspect a real backup safely, use its absolute path and a NEW destination:

```python
from pathlib import Path
import sqlite3

backup = Path('/absolute/path/to/selected.pre-structure-v1-backup.sqlite3')
restored = Path('/absolute/path/to/new-restored.sqlite3')
if restored.exists():
    raise RuntimeError('Choose a new destination; do not overwrite a live database')
source = sqlite3.connect(backup.as_uri() + '?mode=ro', uri=True)
target = sqlite3.connect(restored)
try:
    source.backup(target)
    assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
finally:
    source.close()
    target.close()
```

An operational rollback must stop the server and importer, preserve the failed/current database for diagnosis, and deliberately select the restored database. A pre-structural backup needs compatible older reader code, or can be upgraded again with the current importer. Do not point the new reader at the legacy backup and expect an automatic fallback. Restoration does not establish corpus access permission.

## Validation

`tests/test_structural_store.py` covers transactional migration failure, backup restoration, unsupported versions, revalidation of legacy rows, idempotence, changed-source history, review revision, invalid admission, hierarchy/scope constraints, exact Unicode passages, footnotes, and relationship evidence. Search tests cover missing-current-version exclusion, reviewer changes, immutable history, and the existing HTTP/search/source-link contract.

Run:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/verify_offline_import.py
python3 scripts/evaluate_search.py
```

The four admitted sections and their original text/PDF anchors remain the scope. Remaining work includes reviewed real hierarchy/schedule fixtures, skip-completed job design, and acquisition behavior after the access decision.

### Verification recorded for this implementation

- 60 unit/integration tests pass, including 11 structural/migration tests and 3 additional search admission tests.
- All 26 importer regressions and all 6 development-query smoke cases pass; these remain a tiny development set, not a retrieval-quality benchmark.
- Phase 0 verification confirms all 16 original capture hashes are unchanged.
- Every row in the five legacy canonical tables exactly matches the pre-migration database backup after the upgrade/reimport.
- The migrated real database contains 3 retained blobs/snapshot observations, 4 extractions, 4 nodes/aliases/versions/admissions/current selections, 2 separate footnotes, and 6 exact passages. There are no inferred instrument relationships.
- SQLite integrity and foreign-key checks pass, and all three archived blob hashes and lengths verify.
- The pre-migration backup was retained at `data/import/lawindex_offline.sqlite3.pre-structure-v1-sbmx7rfw.sqlite3`; future upgrades create their own unique backup names. No `--fresh` reset was used for this upgrade.

## Subsequent bounded extension

The counts and null-parent backfill above describe the initial migration. The later [queue and structure increment](QUEUE_AND_STRUCTURE.md) adds 19 contextual child versions to the current Environment Act section 3 extraction, retains the earlier root version as history, and implements opt-in verified resume. Children have no public aliases or independent search admission. The two RTI schedule fixtures explicitly refuse unsafe structural splitting; positive schedule parsing remains open.
