# Phase 2: dependable ingestion and legal structure

Status: reliability increment, operator report, bounded structural migration, verified resume queue, and reviewed contextual clause profile implemented; Phase 2 is not complete. See [STRUCTURAL_MIGRATION.md](STRUCTURAL_MIGRATION.md) for the implemented schema, upgrade, and rollback contract.

## Purpose and boundaries

Phase 1 proves a local search-to-source path over four reviewed provisions. Phase 2 must make that path safe to extend without treating successful extraction as approval. Continue offline on retained evidence. India Code's 20-Act access request remains pending and separate from technical readiness. No new acquisition, OCR admission, public deployment, embeddings, or coverage expansion is authorized by this design.

Keep SQLite for this bounded local implementation. PostgreSQL remains a possible later deployment choice, not a prerequisite for modeling the data correctly. The importer is the sole canonical writer; the search API remains read-only and independently validates live evidence.

## Implemented reliability contract

`scripts/offline_importer.py` now persists `import_attempts` alongside the existing canonical tables. Each attempt records its provision key, UTC start/end times, review JSON digest, parser version, actual hashes of input bytes successfully loaded, outcome, admission status, and exception class on an expected failure. It records metadata, not a second copy of legal text.

Outcomes:

| Status | Meaning |
| --- | --- |
| running | Attempt started; completion has not been committed. A stopped process may leave this status behind. |
| succeeded | Extraction passed the existing admission checks and canonical output committed. |
| quarantined | Checks completed but admission was refused. This is not an infrastructure error. |
| failed | Loading, parsing, review-field access, or another expected input/tool operation failed. |
| interrupted | A later run found an unfinished attempt from its predecessor. |

The newer `import_jobs` queue now persists pending jobs for current review items; see [QUEUE_AND_STRUCTURE.md](QUEUE_AND_STRUCTURE.md). The attempt journal alone still does not enumerate every pending item. An existing canonical row awaiting processing is marked `pending_revalidation`; an item that has never been attempted may have no canonical row. A report must derive such items from the current review inventory rather than pretend the journal is the whole inventory.

Transaction boundaries:

1. Acquire a nonblocking advisory sidecar lock for the database, including before CLI `--fresh` deletion. This is a single cooperating writer design on macOS/Linux (`fcntl`); direct SQLite writers are outside this contract.
2. Load the global inventory/reviews/conflicts. Duplicate review keys fail explicitly. Invalid global JSON fails the run; it is not interpreted as an empty inventory or permission to delete records.
3. Commit document/conflict metadata, removed-record invalidation, and revocation of old text for provisions queued for revalidation. Old excerpts are deleted too.
4. Commit an attempt start and observed input hashes. Extract with a 60-second `pdftotext` timeout.
5. Commit canonical provision, review decision, excerpt, and terminal attempt state together. On an expected exception, roll back that item's partial writes and commit a failed attempt with revoked text; continue other items.
6. An unexpected programming error or interruption escapes. Prior successful items remain committed. The CLI returns nonzero if any expected item failures occurred.

Restart using the normal import command against the SAME database. It safely reprocesses all current reviews and retains attempt history. The default still revalidates every item. The newer `--resume` option skips completed items only after fresh dependency and stored-output verification; no admission is reused based solely on an attempt status. Do not use `--fresh` to recover; it intentionally erases the database and journal. The JSON readiness file is an end-of-run export and may be stale after interruption; the database is the operational state.

Parser output and review digests are unchanged by this operational work, so the extraction version remains v2. Raw source files and review approvals are unchanged. Canonical output remains idempotent; attempt history intentionally grows on every run. Repeated expected failures are retried only when the operator reruns, not in a tight automatic loop.

## Structural schema design

The journal and structural model are separate. The following design is now implemented for four reviewed section nodes, with the concrete tables and limitations documented in [STRUCTURAL_MIGRATION.md](STRUCTURAL_MIGRATION.md). Real clause/schedule parsing and evidence-backed renumbering remain outstanding.

| Entity | Identity and relationships | Required evidence / rules |
| --- | --- | --- |
| Document/instrument | Stable document ID; retain existing `act_slug` as a unique alias | Title, jurisdiction, language/status observations with provenance; rules are distinct documents, never sections of their parent Act. |
| Source snapshot | Stable snapshot ID; document FK; capture observation referencing immutable blob hash | Representation, source URL, capture time when known, byte hash, retained local location. Same bytes can have multiple acquisition observations; a blob hash alone is not the observation's identity. Unknown timestamps stay null. |
| Extraction | ID; snapshot FK; parser version and configuration digest | Output hashes, method, diagnostic outcome. Never overwrite an earlier extraction as though its text had been reviewed. |
| Structural node | Internal stable node ID; document FK | Identity must not be derived solely from a display number. Keep current public provision keys as aliases so existing links survive. |
| Node version | Node FK; extraction FK; nullable parent-version FK within that extraction; sibling ordinal | Kind (chapter/section/subsection/clause/schedule/etc.), display label, heading, exact text and source anchors. Parentage must be acyclic and within one document/snapshot tree. Unknown structure stays explicit; don't invent headings or clause boundaries. |
| Review/admission | Node-version FK; evidence and reviewer reference | Bind the exact source, parser, body and footnote digests. Approval belongs to a version, not every future version of a section number. |
| Passage | ID; admitted node-version FK; strategy version; start/end offsets | Text must exactly equal the referenced display-text slice. Footnotes remain distinguishable. Search normalization belongs in a separate derived field. |
| Instrument relationship | From/to document FK; relation type; evidence snapshot/anchor | Such as rules-made-under; create only with supporting evidence, not matching titles. |

Footnotes need explicit attachment to the relevant node version and anchors; do not flatten them into unlabeled body text. Tables and schedules need dedicated retained fixtures before choosing cell-level modeling. Store current source observations without inferring enactment, commencement, amendment effectiveness, or repeal from capture chronology.

### Migration and identity rules

Implemented: structural schema v1 has transactional DDL, SQLite backup/restore tests, and revalidated backfill of only the four reviewed sections and their observed snapshots. Existing tables remain compatibility projections, written atomically with structural records. The reader now requires structural versions and projection agreement; it has no legacy-text fallback. Removing the remaining projections is a future migration, not a second independent editing workflow. No chapters or child nodes were inferred from visual numbering.

A renumbered provision is not automatically the same node. Retain old snapshot versions; require evidence-backed identity mapping or an unresolved mapping record. A new snapshot begins unreviewed. Changed bytes never inherit approval. No exact historical legal applicability is claimed.

Before adding partial-clause search, define offsets in the same Python Unicode-code-point convention as Phase 1, verify exact slices, and prove that neighboring qualifications and amendment markers are preserved. Clause, table, schedule, and rule fixtures remain outstanding; the present two-Act sample does not validate them.

## Remaining order of work

1. Completed: read-only operator report, including URI, snapshot consistency, and diagnostic fixes.
2. Completed for the bounded slice: structural schema migration, immutable source/text/review history, preserved public aliases, backup/restore tests, and reader cutover.
3. Implemented for Environment Act section 3: 19 reviewed contextual child ranges; real RTI schedule negative fixtures remain quarantined. A positive schedule layout model is implemented; independent review and private viewer verification are complete, documented in [PHASE2_GATE_AUDIT.md](PHASE2_GATE_AUDIT.md).
4. Implemented: opt-in `--resume`, durable per-provision jobs, broad input fingerprinting and per-provision output graph/blob checks. Code/tool/review/source/conflict/inventory changes prevent reuse. See [QUEUE_AND_STRUCTURE.md](QUEUE_AND_STRUCTURE.md).
5. Design acquisition jobs/backoff/rate limits after the access reply establishes permitted methods and scope.

## Verification of this increment

`tests/test_ingestion.py` checks persistent-database interruption/reopen/retry, missing-source isolation and recovery, changed-source hash history, extraction timeout recovery, and the single-writer lock. The existing importer regression suite protects all prior fidelity and admission rules. The search tests and development-query smoke evaluation must also continue to pass. These tests alone do not establish closure; the completed bounded gate audit additionally records independent schedule review and viewer verification.
