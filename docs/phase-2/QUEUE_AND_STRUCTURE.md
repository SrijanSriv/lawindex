# Safe resume and bounded clause structure

Implemented offline, 21 September 2026. These are correctness-sensitive additions to the existing four-section prototype, not broader legal coverage or a completed generic legal parser.

## Restarting an import

```sh
python3 scripts/offline_importer.py
python3 scripts/offline_importer.py --resume
```

The default command still re-extracts/revalidates every reviewed item. `--resume` may skip an item only if its durable job and referenced attempt both succeeded, all input dependencies have the same freshly computed fingerprint, and the current stored output graph and private source blobs match its checkpoint. The summary's `provisions_skipped` counts reused successes; `provisions_admitted` includes them. Skipping does not fabricate a new extraction attempt or refresh its timestamp.

`import_jobs` stores pending/running/succeeded/quarantined/failed/removed state, input and output fingerprints, and the last attempt ID. `import_queue_schema` versions this additive schema. Existing databases get these tables without discarding their journal. The importer lock covers queue planning and processing. Pending work is persisted and revoked before processing; successful output and its checkpoint commit together. Interruption leaves completed successes reusable and unfinished work retryable on the next explicit invocation.

The input fingerprint includes retained capture bytes and metadata, manifest, review and conflict records (including excluded observations), explicitly referenced reviewer files and capture body paths, structural profiles, Python code, Python/SQLite runtime information, locale, and the `pdftotext` executable/version. It uses content hashes, not modification times. Inputs intentionally invalidate together for this small corpus. One changed input can reprocess all four provisions; selective dependency scheduling is an optimization we have not implemented.

Output fingerprints are per provision: compatibility rows, document, alias, current version/admission, source snapshots, extraction/configuration, footnotes, passages, the associated hierarchy, and the archived source bytes. Changed/missing output prevents skipping. Historical attempts are retained; quarantined/failed items are retried only when the operator explicitly reruns the importer. Unavailable fingerprint dependencies disable reuse and let the ordinary per-item failure handling run.

The report CLI still describes actual attempts. On a skipped import, its latest attempt remains the original completed one. It does not claim that extraction ran again. `--fresh` destroys checkpoints and history and is not a recovery command.

## Reviewed clause profile

The Environment (Protection) Act, 1986 section 3 now has a narrowly scoped, versioned boundary profile at `data/review/structure/environment-1986-section-3.json`. It was checked against rendered retained-PDF pages 4 and 5 by this AI agent. This is disclosed as agent boundary review, not independent legal-expert review; elapsed review time was not separately instrumented.

The parser accepts only the exact source hash and reviewed full-text hash. Each marker anchor must occur once; paths must be unique and in source order; parents must precede children; sibling ranges cannot overlap; children must remain within parents. It makes 19 contextual child nodes:

- Subsections (1), (2), and (3).
- Clauses (i) through (xiv) inside subsection (2).
- Clauses (a) and (b) inside clause (2)(i).

Clause (iv) includes its entire proviso. Subsection (3) includes its continuation on page 5 and stops at the section boundary. Every child is an exact Unicode-code-point slice of the reviewed root section. Its source anchor includes the root version, start/end offsets, profile hash, and mandatory root-context version. PDF page ranges remain the enclosing section's verified range, not a claim of more precise child coordinates.

Child nodes do not receive public aliases, standalone passages, independent admission records, or search entries. Section-level search is unchanged. The complete profile is retained in the extraction configuration; child versions are immutable. Contextual identities are scoped to their root version; no automatic cross-version renumbering match is inferred. A changed profile/source/text must be reprocessed and reviewed rather than silently applying old boundaries.

This is a profile-driven parser for a verified shape, not a regex that infers arbitrary legislation from numbering. The root section's normal admission checks remain in force. A present but invalid profile fails that item's import rather than emitting unverified structure.

## Real schedule fixtures and exclusions

Retained RTI PDF pages 23 and 24 were rendered and inspected, then recorded in `data/review/structure/rti-schedule-quarantine.json` as negative fixtures:

- First Schedule: the oath has vertically stacked alternatives (“swear…” / “solemnly affirm”). Flattened text does not encode that choice reliably. Outcome: `quarantined_structure`, reason `stacked_oath_alternatives`.
- Second Schedule: amendment superscripts/brackets, omitted entries, and footnotes repeat numbering used by the main list. Outcome: `quarantined_structure`, reason `amendment_markers_and_footnote_numbering`.

Both fixtures bind the retained PDF hash, page number, and exact cleaned extraction hash. They produce no child nodes or admitted schedule text. Other schedules return `unsupported_structure`; recognition is not approval. The private visual evidence is under `data/import/structure-review/` and is not a source release.

The parser's safe refusal is tested. Correct positive parsing/display of these schedules is STILL OPEN, and the full Phase 2 gate is not closed by negative fixtures. In particular, we have not invented a flattening rule that would misrepresent the oath or detach amendment notes.

## Checks and remaining work

`tests/test_import_queue.py` covers unchanged skips without new attempts, persistent interruption/reopen, failed-job retry, source changes, review withdrawal/removal, stored-text changes, missing archives, and dependency invalidation including code/tool/reviewer changes. `tests/test_clause_structure.py` covers exact child ranges, proviso preservation, bad profiles, changed-source refusal, schedule quarantine, and the absence of independent child search admission.

Run the standard full tests, importer regressions, Phase 0 hash verification, and search smoke evaluation. No new fetches, OCR, permissions, public deployment, or source publication were performed.

The supporting agent can now build the read-only structure inspector described in [STRUCTURE_AGENT_PROMPT.md](STRUCTURE_AGENT_PROMPT.md). Further architecture work includes positive layout-preserving schedule representation, evidence-backed identity mapping, and source acquisition policy after India Code replies.

### Verification for this increment

All 74 unit/integration tests, 26 importer regression checks, and 6 development queries pass. Phase 0 verification confirms the 16 original capture hashes are unchanged. The real database passes integrity/foreign-key checks and contains four current searchable roots, four successful jobs, and 19 current contextual children. A full import followed by `--resume` reports four admitted roots and four skipped successes, without new attempts on the second run. No `--fresh` reset was used.

## Subsequent schedule implementation

The plain-text quarantine decisions above are preserved. A separate positive, source-position-preserving schedule parser now exists; see [SCHEDULE_LAYOUT.md](SCHEDULE_LAYOUT.md). Its model keeps oath alternatives and amendment/footnote relationships explicit. Independent AI acceptance and private viewer verification are complete; [PHASE2_GATE_AUDIT.md](PHASE2_GATE_AUDIT.md) is the current closure checklist.
