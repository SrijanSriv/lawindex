# Follow-up inspection of agent work

Inspected 20 September 2026. This is an implementation/status inspection, not an independent legal-expert review. Original source artifacts, implementation files, and the working database were not modified. All reproduction and adversarial checks ran in a temporary copy. No network requests were made.

## Confirmed progress

- The importer handles a bounded four-provision slice: RTI sections 6 and 8, and Environment Act sections 3 and 5A.
- Review records, two versions of development queries, conflict records, OCR assessment, and an access-response checklist exist.
- The Kerala conflict record now selects 14 August 2026 with retained-PDF evidence and a disclosed uncertainty about the listing's field mapping. The Act remains excluded. This inspection did not independently adjudicate the legal meaning of those dates.
- The independent review predates a subsequent stale-record invalidation fix. Removal of a review record and removal of a manifest entry now have dedicated checks. The earlier report should be read as a historical review, not an exact description of current code.
- All four documented commands passed in a temporary copy:

```sh
python3 scripts/build_phase0_artifacts.py
python3 scripts/verify_phase0.py
python3 scripts/offline_importer.py --fresh
python3 scripts/verify_offline_import.py
```

The import reported 12 documents, 4 admitted provisions, and 4 conflicts. **All 21 offline import checks passed**, rather than the 19 still described in README/readiness documentation.

## Finding 1 — bind admission to the reviewed extracted text

Priority: high for trusting repeated extraction. Location: `scripts/offline_importer.py`, `build_provision_record`, particularly lines 258–273 at inspection time.

The importer verifies source bytes and a manually maintained extraction-version label. It then calculates hashes of newly extracted body and footnote text, but does not compare them with expected hashes attested by the review record. The calculated hash describes this run; it does not establish that the reviewer saw this output.

Reproduced in isolation by wrapping `strip_watermark` to replace `information which relates to personal information` with `UNREVIEWED REPLACEMENT`, leaving the original PDF bytes and extraction-version label unchanged, and reimporting into the same database:

```text
RTI section 8 status: admitted
Replacement present in admitted body: True
```

This models an unversioned extraction change. Different extraction-tool behavior can likewise change output without changing the manually declared label. The existing version-change test only proves behavior when that label is explicitly changed.

Recommended fix: store approved body and footnote digests (or immutable approved text) in each review record and compare freshly extracted output before admission. Mismatches must invalidate the provision and remove its excerpts. Establish initial expected hashes from verified text, not by automatically accepting whatever a failed run produced. Add an existing-database regression with unchanged source bytes/version but changed extraction output.

No claim is made that today's four provision texts are corrupt; this is a gap in the promised change-detection guarantee.

## Finding 2 — restored manifest entries retain their removal flag

Priority: medium. Location: `scripts/offline_importer.py`, the document upsert in `import_all`, around line 462 at inspection time.

`invalidate_stale_records` sets `documents.removed_from_manifest = 1` when an Act disappears. The document upsert does not reset this column when the Act returns.

Reproduced using an existing database:

1. Import the original manifest.
2. Import with Environment Act removed from the manifest.
3. Restore the original manifest and import again.

```text
After removal: removed_from_manifest = 1
After restoration: removed_from_manifest = 1
Environment provisions after restoration: admitted, admitted
```

This leaves contradictory state. The readiness exporter also does not expose the removal flag, so it does not clearly communicate document retraction.

Recommended fix: explicitly reset the flag for current manifest entries and represent/filter removed documents consistently in readiness output. Add remove-and-restore coverage, not only removal coverage.

## Documentation/evidence follow-ups

- Update suite counts to 21, or avoid fixed counts that become stale.
- Preserve the independent review as historical evidence and add a dated remediation status rather than silently rewriting its original findings.
- The page-10 RTI PNG remains absent. The original review record describes a page-10 visual inspection but lists no retained page-10 image. The PDF is available for reproducible regeneration, so this is an evidence-packaging limitation, not proof the inspection did not occur. Clarify transient-render handling or retain a regenerated render with its actual generation provenance.

## Assessment

Substantial offline preparation is complete and the checked-in suite passes. The prior review-record removal defect has been addressed. Fix and test the two remaining state/admission issues before declaring the importer dependable across changes. These are bounded engineering corrections; they do not require further source acquisition or expansion of Phase 0's corpus.

India Code permission remains separately pending. OCR and other provisions remain excluded. This inspection did not repeat the prior agent's full page-by-page visual review, run a retriever, or establish current legal effect.

## Remediation note, 2026-09-20 (added after this report; original findings above are unmodified)

Both findings in this report are now fixed:

- **Finding 1 (bind admission to reviewed extracted text):** each of the four review records now carries an
  `expected_output` block (`body_text_sha256`, and `footnote_text_sha256` or the explicit sentinel
  `"no-footnote-expected"`), established during this remediation session — not claimed to have existed
  during the original review — by re-running the current extraction against the same retained bytes each
  record already binds to and cross-checking the result against that record's own evidence.
  `build_provision_record` in `scripts/offline_importer.py` now compares freshly extracted output against
  these digests before admission; a mismatch invalidates the provision
  (`invalidated_body_text_changed` / `invalidated_footnote_text_changed`) and removes its excerpt, and a
  missing baseline refuses admission (`invalidated_missing_expected_digest`) rather than defaulting to
  admitted. This exact repro from this report (wrapping extraction to replace section 8's clause-(j)
  wording while leaving source bytes and the version label untouched) now yields
  `invalidated_body_text_changed` with no replacement text in the admitted body, instead of silently staying
  `admitted`.
- **Finding 2 (restored manifest entries retain their removal flag):** the document upsert in `import_all`
  now explicitly sets `removed_from_manifest = 0` for every act slug present in the current manifest, and
  `build_readiness_manifest` now exposes `documents_removed_from_manifest` explicitly. This exact repro from
  this report (import → remove Environment Act from the manifest → restore → reimport) now yields
  `removed_from_manifest = 0` after restoration, instead of staying stuck at `1`.

New regression checks in `scripts/verify_offline_import.py` cover both: `check_changed_body_text_invalidates_via_digest_mismatch`,
`check_changed_footnote_wording_invalidates_via_digest_mismatch`, `check_missing_expected_digest_prevents_admission`,
and `check_manifest_removal_and_restoration_round_trip`. The documentation/evidence follow-ups are also
addressed: the page-10 RTI PNG has been regenerated and retained at
`data/discovery/derived/rti-2005-page-10.png` with its own generation provenance in
`data/review/reviewer-remediation.json` (it confirms today's page content; it does not retroactively prove
the original session's inspection occurred), and README/PHASES/CONFLICT_POLICY/SOURCE_DISCOVERY no longer
hardcode a specific check count. See `docs/phase-0/READINESS_MANIFEST.md`'s "Remediation, 2026-09-20"
section for the full, authoritative account. This note does not alter any finding above.
