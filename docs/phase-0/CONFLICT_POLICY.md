# Decision: source conflicts and text admission

**Status: accepted policy, 20 September 2026.** This closes the conflict-handling design question in [source-discovery section 4](SOURCE_DISCOVERY.md#4-structured-text-exists-but-its-fidelity-needs-verification). It does not certify unreviewed text, implement the importer, or close the overall Phase 0 ingestion-readiness gate.

## 1. Decision

**Preserve every observed representation; select a reviewed reference snapshot for retrieval; disclose material disagreements; never silently merge competing texts.**

For the initial English corpus, use structured text when its wording and structure have been checked against the linked, retained PDF. When a substantive conflict exists, the default candidate for the searchable provision is the **visually reviewed PDF snapshot**, including its relevant footnotes and context. Admit it only after extraction and source mapping pass review. If that cannot be done reliably, hold the affected provision out of search.

This is an editorial choice for a snapshot search engine. A PDF's format, government hosting, or later displayed date does **not** establish that it is legally authoritative or currently operative. Label it “selected reference snapshot,” never “authoritative/current law” on those grounds. A verified source declaration of authority can be recorded with its scope, but we have not established one that resolves the RTI mismatch.

Do not automatically apply amendments, infer commencement, or reconstruct a legally effective version. If establishing legal effect becomes a product requirement, it needs a separate evidence and review workflow.

## 2. Why these patterns fit—and their limits

- **Separate identity, version, and format.** Akoma Ntoso distinguishes a work, its expressions, and their manifestations. HTML and PDF can be manifestations of the same expression; a disagreement does not prove two legitimate legal versions. Preserve them as source representations with an unresolved version relationship until evidence supports a mapping. We adopt that distinction without requiring a complete Akoma Ntoso implementation. [OASIS vocabulary](https://docs.oasis-open.org/legaldocml/akn-core/v1.0/akn-core-v1.0-part1-vocabulary.html).
- **Expose editorial state.** The UK legislation data model includes version information and outstanding unapplied changes. Borrow explicit processing/status labels; do not infer that our importer knows all outstanding Indian amendments. [Official legislation data documentation](https://legislation.github.io/data-documentation/api/overview.html).
- **Separate consolidated reference text from legal effect.** EU guidance distinguishes consolidation from adopting a new legal act. That is a useful product distinction, not a rule that establishes the authority of an Indian PDF. [EUR-Lex guidance, paragraphs 20–22](https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX%3A52015XG0324%2801%29).
- **Use OCR confidence as a review signal.** EasyOCR's documented output includes text boxes, text, and confidence; it is not a universal per-character correctness guarantee. Scores vary by engine and output mode. A high score cannot itself admit legal text. [EasyOCR tutorial](https://jaided.ai/easyocr/tutorial/).

We do not need commercial redlining software or an LLM adjudicator to make this decision. The first implementation should combine deterministic comparison with manual review of the small admitted slice.

## 3. Data and provenance contract

Keep the original HTML/JSON and PDF unchanged. A derived text record must identify its parent Act/provision, source URL, capture time, exact source hash, extraction method/version, language, and source-stated snapshot date when available. Record unknown dates as unknown.

Each conflict record must contain:

| Field | Required meaning |
| --- | --- |
| Issue ID and scope | Stable issue ID; affected document, provision, field, or anchor |
| Observations | Every competing value/text and its source representation/hash/location |
| Classification | Formatting-only, substantive text, metadata, anchor, OCR, or acquisition/completeness problem |
| Selected representation/value | Explicit choice and rationale, or null when unresolved |
| Review evidence | Reviewer identity, actual review time, checked scope, and evidence locations; never fabricate a completed review |
| Disposition | Review pending, selected with disclosed conflict, verified equivalent, or excluded |
| Admission | Whether the specific representation is eligible for search, independently of access/reuse permission |
| Recheck trigger | Changed content/hash, parser output, identity, or relevant source evidence |

Keep these axes separate: **policy decided**, **fidelity reviewed**, **legal effect established**, and **access permitted**. One cannot substitute for another.

The searchable unit must reference one coherent provision representation. Do not repair section 8 by splicing the PDF's clause (j) into otherwise unreviewed HTML and presenting the result as an unchanged source. Prefer the entire reviewed PDF-derived section 8, with its clause structure and notes. Other sections may use reviewed structured text, but document views must disclose mixed source representations and must not present the assembled document as one publisher-issued version.

## 4. Comparison and admission workflow

1. **Check identity and completeness first.** Confirm the instrument, language, provision label, source hashes, completed pagination, and available context. Wrong-document comparisons and failed fetches are not text disagreements.
2. **Align by legal structure.** Match sections and clauses, keeping labels as strings; treat footnotes, tables, schedules, and chapter headings as distinct structures. Ambiguous alignment requires review.
3. **Make a comparison-only normalized copy.** Normalize line endings and repeated layout whitespace. Remove headers, watermarks, or line-wrap hyphens only with explicit, tested rules and retained source mapping. Do not discard punctuation, negation, numbers, provision markers, or amendment notes. Never display the normalized comparison copy as an exact quotation.
4. **Classify differences.** Exact agreement or known layout-only differences can pass that comparison check. Any unexplained word, number, punctuation, clause, footnote, or order change needs review. Similarity scores can prioritize work; no percentage threshold automatically makes a difference legally immaterial.
5. **Review against the rendered reference.** A discrepancy can originate in PDF extraction rather than the source. Check the relevant page image, boundaries, notes, and continuation pages before selecting the PDF-derived provision. Record whether the source disagreement remains or the extraction was corrected.
6. **Admit only the reviewed scope.** For the first slice, review every provision actually admitted against the reference, including its boundaries and notes. We can start with a small subset; unreviewed sections do not inherit approval from one inspected page. Report partial Act coverage explicitly.
7. **Revalidate on change.** Source or derived-text changes invalidate the affected approval and index entry until checked again. Preserve earlier snapshots and decisions; never silently overwrite them.

Whole-file equality is not required. Unexplained material differences must not reach search without an explicit selected representation and a visible conflict notice. If the issue is isolated to a field or provision, hold that scope; quarantine the entire instrument when identity or boundaries cannot be trusted.

## 5. Disposition of the observed fixtures

| Issue | Accepted decision | What is still required |
| --- | --- | --- |
| **RTI-001: section 8(1)(j)** | Retain HTML and PDF. Select the retained PDF, whose cover states 18 November 2025, as the reference candidate for **whole section 8**. Keep the conflicting HTML out of normal retrieval; retain it as comparison evidence. | Extract and visually verify the complete section, its notes and anchors, then record admission. Existing inspection proves the mismatch, not full-section readiness. Do not determine current legal effect from this choice. |
| **RTI-002: section 6 page hint** | Preserve source hint `7`. Use PDF file page `9` for the inspected retained file, bound to its exact hash. Store printed page labels separately. | The importer must encode and validate that mapping; do not infer a universal +2 offset for other sections or later PDFs. |
| **KERALA-001: enactment date** | Preserve listing `25 August 2026` and detail `14 August 2026` as conflicting observations. Canonical enactment date stays null; do not guess, average, or prefer the later date. Keep this fixture outside the initial ten-Act slice. | **Update, second-pass investigation, 20 September 2026: resolved.** Retained-PDF evidence (the Act's own printed assent-date bracket, cross-calibrated against the identical convention in the RTI Act's PDF) resolves the canonical enactment date to `14-08-2026`; `25 August 2026` is explained as this Act's "as on"/commencement-notification date, not a competing enactment claim. Both raw observations still preserved. One residual gap remains disclosed (the live listing UI's exact field mapping was not independently re-captured). This does **not** lift the fixture's exclusion from the searchable slice. See [KERALA-001.json](../../data/review/conflicts/KERALA-001.json). |
| **UI-001: loading/missing fields** | A loading state, failed request, or untraversed page is unknown, not an empty collection. Only a completed source response plus relevant completeness checks may establish zero. | Implement explicit acquisition states and count/pagination checks; do not freeze transient UI emptiness into metadata. |
| **RTI Rules, 2012: faulty OCR** | Preserve the scanned file and raw OCR; keep rule text excluded. Retain reviewed parent metadata and source link. New OCR remains outside the first slice. | If OCR enters scope later, record engine/version and available scores; review extracted provisions against page images before admission. Missing scores mean unknown confidence. **Update, second-pass assessment, 20 September 2026:** six concrete error types now catalogued (digit/letter confusion, clause-marker corruption, a missing clause marker, word-merge errors, failure on handwritten annotations, failure on non-Latin script) with explicit acceptance criteria — see [RTI_RULES_OCR_ASSESSMENT.md](RTI_RULES_OCR_ASSESSMENT.md). No OCR work started; exclusion unchanged. |

These are accepted **dispositions**, not claims that the external sources have been corrected. Kerala and scanned rules can remain excluded without blocking the text-only first slice. RTI section 8 can also remain held while other reviewed provisions proceed.

## 6. OCR, excerpts, and user-visible treatment

Do not select an arbitrary confidence cutoff such as 0.95 now. If an OCR engine is introduced, calibrate review routing on our own annotated scans, retaining scores at their actual granularity. Low confidence, malformed numbering, or suspicious text routes to review; high confidence does not bypass first-slice visual verification. The existing PDF text layer has no established confidence data for us to trust.

For each search excerpt, verify its text against the admitted display text and preserve a mapping to the reviewed representation. Check provision identity, boundaries, and the exact PDF/page anchor independently. Display normalization or omitted text must be explicit; never label reconstructed wording as a verbatim quote. A functioning link is insufficient.

The future interface should show, where applicable:

> **Source disagreement:** this result uses the reviewed India Code PDF snapshot labelled 18 November 2025. The portal's structured text differs. Current legal effect has not been established by LawIndex. View the reference PDF and conflict details.

For partial coverage, state which provisions are excluded or unreviewed. For Kerala metadata, show “Enactment date unresolved” with both attributed observations, rather than a clean-looking chosen date. No definitive generated answer may erase a conflict; claim-level answer verification is separate later work.

## 7. Closure and implementation handoff

**Closed now:** deciding how to represent disagreements, select a reference, handle dates and anchors, and exclude uncertain OCR. The fixture dispositions above exercise the policy at the decision level.

**Update, 20 September 2026: implemented and demonstrated, then critically audited and broadened in a second pass.** `scripts/offline_importer.py` and its regression suite `scripts/verify_offline_import.py` implement the records and comparison/review path for RTI Act sections 6/8 and, since the second pass, Environment (Protection) Act sections 3/5A, and demonstrate on retained fixtures that:

- RTI's substantive mismatch is flagged and cannot silently select the HTML. (Verified — the excluded HTML wording never appears in admitted text.)
- Layout-only differences do not alter displayed source text or erase amendment notes. (Verified — the section 8 footnote is preserved distinctly from the body; the Environment Act's section 5A amendment-insertion marker and footnote are likewise preserved.)
- Both Acts' PDF anchors remain bound to their retained PDF hashes. (Verified.)
- Both Kerala date observations survive; the canonical date is now resolved from an explicit, evidenced conflict-record resolution rather than staying unknown by default — and a synthetic fixture proves the same mechanism still yields an unknown canonical date when a conflict is genuinely unresolved. (Verified.)
- OCR and incomplete acquisition cannot be auto-admitted. (Verified — both the RTI Rules OCR text and a simulated hash-mismatched source are excluded/invalidated rather than admitted.)
- A source/extraction change invalidates the affected approval, and every excerpt resolves to its selected representation. (Verified — a simulated changed PDF hash invalidates section 8's admission without duplicating rows, and restoring the real bytes re-admits it; a changed extraction-method version and a declared-but-missing footnote each independently invalidate admission too; an excerpt is shown to resolve exactly to a byte-offset slice of its admitted source text.)
- The watermark-stripping normalization cannot silently corrupt legitimate text. (Verified against a second document's 65 real matches, plus constructed near-misses that must NOT be stripped.)
- A second-pass audit of the importer itself found and fixed real defects — including a global reviewer mis-attribution that would have silently credited the wrong reviewer for the Environment Act provisions — each now covered by its own regression check. See the [readiness manifest](READINESS_MANIFEST.md#second-pass-defect-review-of-the-importer-itself) for the full list.

See the [readiness manifest](READINESS_MANIFEST.md) for the full scope statement. This closes the acceptance-check items above **only for the four listed provisions across two Acts**; every other provision in the ten-Act candidate corpus remains unreviewed and unadmitted, and this implementation work does not reopen or change the policy decided above. Source-access permission remains an independent gate; the user has reported requesting access for 20 Acts, with a reply not yet reported. An [access-response checklist](ACCESS_RESPONSE_CHECKLIST.md) is now ready for when that reply arrives. See [access status](ACCESS_AND_REUSE.md#access-request-status).

**Update, 20 September 2026 (remediation pass): two gaps closed.** An independent review and a follow-up inspection (see [INDEPENDENT_REVIEW.md](INDEPENDENT_REVIEW.md) and [INSPECTION_FOLLOWUP.md](INSPECTION_FOLLOWUP.md), both preserved as historical reports) found that "a source/extraction change invalidates the affected approval" above held for byte-level and version-label changes but not for a change in the extracted output itself under an unchanged source hash and unchanged version label, and that a manifest entry restored after removal kept a stale removal flag. Both are now fixed in `scripts/offline_importer.py` — admission is bound to `expected_output` digests recorded on each review record (established during this remediation pass, not claimed to predate it), and manifest restoration explicitly clears the removal flag — with new regression coverage. See the [readiness manifest's remediation section](READINESS_MANIFEST.md#remediation-2026-09-20-binding-admission-to-reviewed-output-and-fixing-manifest-restoration-state) for the full account. This does not change the policy decided above or the four-provision scope.
