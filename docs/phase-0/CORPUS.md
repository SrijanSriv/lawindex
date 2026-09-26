# Phase 0 — first corpus and exclusions

The proposed first searchable corpus is **10 Indian central Acts, in English**, from the current India Code portal. This is a deliberately varied engineering sample, not a representative coverage claim for all Indian law.

The user has requested access to **20 Acts** from India Code; permission is pending. That request does not expand or approve this initial ten-Act candidate manifest. Conflict dispositions are now decided in the [accepted policy](CONFLICT_POLICY.md); individual text admission remains pending for all provisions except a bounded slice — RTI Act, 2005 sections 6 and 8, plus (added in a second pass) Environment (Protection) Act, 1986 sections 3 and 5A — reviewed and admitted offline. See the [readiness manifest](READINESS_MANIFEST.md). Technical admission of this slice does **not** mean it, or any other part of the corpus, is cleared for public indexing.

All 11 inspected Act records were reached through the central collection or its search results, and all display `CENTRAL` in their detail metadata. The [manifest](../../data/discovery/corpus-manifest.json) preserves source UUIDs, Act IDs, titles, dates, PDF references, observed fields, rationale, and review status. **Nothing is imported or approved for public indexing yet.**

## Ten candidates for Phase 1

| Candidate | Why include it | Current verification limit |
| --- | --- | --- |
| Right to Information Act, 2005 | Plain-language retrieval, chapters, schedules, footnotes, staged commencement | Metadata, first 10 structured sections and PDF retained; **sections 6 and 8 reviewed, hash-anchored, and technically admitted** (see [readiness manifest](READINESS_MANIFEST.md)); the other 29 sections, schedules, and chapters remain unreviewed |
| Environment (Protection) Act, 1986 | Environmental searches, section 5A, many linked instruments | Metadata and PDF retained; **sections 3 and 5A reviewed, hash-anchored, and technically admitted, PDF-only** (no structured text was ever retained for this Act, so cross-representation comparison is not possible — see [readiness manifest](READINESS_MANIFEST.md)); all other sections and chapters remain unreviewed |
| Copyright Act, 1957 | Older amended Act and larger section inventory | Metadata and file reference verified; PDF not retained |
| Digital Personal Data Protection Act, 2023 | Recent terminology, missing department/enforcement metadata | Metadata and file reference verified; PDF not retained |
| Mental Healthcare Act, 2017 | Rights terminology and later commencement | Metadata and file reference verified; section count not verified |
| Sexual Harassment of Women at Workplace Act, 2013 | Common acronym versus long official title | Full official title in manifest; metadata/file reference verified |
| Foreign Contribution (Regulation) Act, 2010 | Acronym queries and different linked instrument kinds | Metadata/file reference verified; subordinate texts outside first slice |
| Occupational Safety, Health and Working Conditions Code, 2020 | A Code classified as ACT, distinct enactment/enforcement dates | Metadata/file reference verified; full text review pending |
| Repealing and Amending Act, 2023 | Cross-instrument changes and missing metadata | Metadata/file reference verified; not automatically applied to other Acts |
| Merchant Shipping Act, 2025 | 125-page stress case with contents and amendment notes | Metadata and PDF retained; full structure verification pending |

These are candidates for a reviewed importer, not 10 verified complete text snapshots. Start Phase 1 with one or two reviewed documents/provisions, then admit the remaining candidates after their extraction checks. Use the PDF references in the manifest to acquire the remaining files only once the source-access decision is settled.

## Two additional fixtures held out of the index

- **Kerala (Alteration of Name) Act, 2026:** retained six-page PDF and metadata; conflicting listing/detail dates and sparse metadata. **Update:** the date conflict is now investigated and the canonical enactment date resolved to 14-08-2026 from retained-PDF evidence (see [KERALA-001](../../data/review/conflicts/KERALA-001.json)); this Act still stays excluded from the searchable slice regardless of that resolution.
- **RTI Rules, 2012:** retained four-page scanned PDF with defective existing OCR. Keep its parent relation and source link; defer searchable rule text until reviewed. **Update:** six concrete error types are now catalogued with acceptance criteria for future OCR work — see [RTI_RULES_OCR_ASSESSMENT.md](RTI_RULES_OCR_ASSESSMENT.md). No OCR work performed; exclusion unchanged.

The conflicting raw RTI section 8 HTML stays out of retrieval even though the RTI Act remains a corpus candidate. The selected PDF-derived whole section must pass extraction and visual review before admission, with the source disagreement disclosed. Holding a passage does not mean declaring the Act unavailable in all representations.

## Scope boundaries

- Index admitted Act text, its provisions, and verified schedules. Do not index summaries as if they were statutory provisions.
- Retain associated-instrument links and metadata, but do not recursively import all rules, notifications, regulations, or amendments. Environment's displayed linked counts alone would expand this tiny slice by well over a thousand source records.
- Exclude state law, judgments, tax sources linked from other domains, historical as-of reconstruction, and unverified alternate-language text.
- Defer new OCR processing. Existing OCR still needs quality review.
- Treat the sample as a retained source snapshot, never as a promise of currently operative or comprehensive law.

## Seed-query policy

[seed-queries.jsonl](../../data/discovery/seed-queries.jsonl) contains 24 queries covering exact titles, citations, headings, everyday terminology, filters, known source conflicts, and unavailable scope.

Each query records intent, expected corpus behavior, candidate targets, and judgment status. Section hints are marked as heading-observed, text-inspected, or unjudged. They are not legal conclusions or a scored benchmark. Questions outside the corpus should trigger a coverage limitation, not necessarily an empty results list: related text can still be useful.

Keep all these Phase 0 queries in the development/smoke set. The independent held-out benchmark comes in Phase 4. Before computing retrieval quality, review the passages in the exact selected snapshot, record graded judgments, and explicitly separate unjudged results from irrelevant ones.
