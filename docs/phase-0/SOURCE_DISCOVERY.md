# Phase 0 — India Code source discovery

Inspected on **20 September 2026**. This report describes observed source behavior, not a determination of the current legal effect of any provision.

**Status: the first discovery pass is complete; a bounded offline import/verification pass has been implemented, self-audited, and broadened across two sessions; the overall ingestion-readiness gate remains open.** We have a bounded candidate corpus, real source fixtures, an extraction plan, and seed queries. RTI Act sections 6/8 and Environment (Protection) Act sections 3/5A are now reviewed, admitted, and hash-anchored by an offline importer — see the [readiness manifest](READINESS_MANIFEST.md). A second pass also fixed several importer defects, resolved the Kerala date conflict from retained evidence, catalogued RTI Rules OCR error types, and prepared an access-response checklist. We have not completed a full corpus import, resolved source reuse conditions, or certified the remaining candidate documents' text.

## Deliverables

- [Metadata matrix](METADATA_MATRIX.md): observed fields, reliability limits, and normalization decisions.
- [First corpus](CORPUS.md): 10 candidate Acts and two additional quarantine fixtures.
- [Access and reuse findings](ACCESS_AND_REUSE.md): published conditions and the decision needed before bulk ingestion/public reuse.
- [Accepted conflict policy](CONFLICT_POLICY.md): reference selection, review, exclusions, and dispositions for the observed issues.
- [Machine-readable manifest](../../data/discovery/corpus-manifest.json).
- [Offline import readiness manifest](READINESS_MANIFEST.md): what is reviewed, admitted, excluded, and still pending for the bounded four-provision slice across two Acts, plus the offline importer (`scripts/offline_importer.py`) and its regression suite (`scripts/verify_offline_import.py`).
- [RTI Rules OCR assessment](RTI_RULES_OCR_ASSESSMENT.md): six concrete observed error types and acceptance criteria for any future OCR work, without starting that work.
- [Access-response checklist](ACCESS_RESPONSE_CHECKLIST.md): what to check when India Code replies to the pending 20-Act request. No follow-up sent.
- [24 seed queries](../../data/discovery/seed-queries.jsonl), with review status and candidate targets rather than invented relevance judgments.
- [Capture index](../../data/discovery/capture-index.json): 16 raw HTTP captures, their URLs, timestamps, response types, statuses, byte counts, and SHA-256 hashes.
- [PDF diagnostics](../../data/discovery/pdf-report.json) and [structured-data diagnostics](../../data/discovery/structured-report.json).

## 1. The source has migrated

The [old homepage](https://www.indiacode.nic.in/) displays a migration notice pointing to [indiacode.gov.in](https://indiacode.gov.in/). A tested old Act URL and old search route returned 404 during discovery. Historical search-engine results still show old DSpace handles and state-hosted copies; those are discovery leads, not proof that a URL remains usable or represents the central source record.

The new frontend is a client-rendered application. The homepage, central collection, terms, and copyright paths all returned the same 6,762-byte application shell in our direct captures. **HTTP 200 plus an HTML document is not proof that legislation or policy text was fetched.** The policy findings below were read from the rendered browser page, not inferred from those shells.

The site's delivered configuration identifies a backend base URL of `https://indiacode.gov.in/server`. The browser uses public DSpace-style HAL JSON endpoints under `/server/api`. A bounded item response and a section-list response were retained for schema discovery. We found a working interface used by the site; we did **not** establish a documented, supported third-party bulk API contract.

## 2. Discovery, collections, and pagination

The homepage links [Central Laws](https://indiacode.gov.in/collections/69a0c1fb-7b22-4481-b16a-1dc59b5d02e6) to a collection UUID. The rendered listing reported **847 Act records** during this visit. This is an observed collection count, not a count of all Indian central law or a completeness guarantee.

The interface displayed 10 results per page. Navigating an RTI phrase search verified page transitions through 22 results. Observed frontend parameters include `spc.page`, `spc.rpp`, `spc.sf`, `spc.sd`, `query`, and metadata filters such as `f.title=Environment,contains`. UI page numbering starts at 1; the sampled backend page numbering starts at 0.

The default date-descending sort can place title matches far below more recent documents containing the phrase. Unquoted `Right to Information` returned 485 matches; the quoted phrase returned 22. A title-field filter for `Environment` returned one Act. These are source-discovery observations, not LawIndex relevance scores.

For sections, the browser requested:

```text
/server/api/discover/search/objects
  ?sort=dc.identifier.order_number,ASC
  &page=0&size=10
  &f.identifier_collection=SECTION,equals
  &f.act_id=AC_CEN_26_36_00004_200522_1517807322955,equals
```

In the retained response, records are at `_embedded.searchResult._embedded.objects[*]._embedded.indexableObject`. Pagination metadata reports 31 RTI sections across four pages. The response supplies `next` and `last` links. A future importer should follow returned pagination and reconcile counts; Phase 0 fetched only the first 10 sections, not all 31.

## 3. Identity and relationships

For RTI, these identifiers coexist:

| Identifier | Observed value | Intended treatment |
| --- | --- | --- |
| Act item UUID | `37520cf3-5c3f-4c0b-aa4a-5985e6f522bf` | Source-record identity, namespaced to the source |
| Handle | `123456789/496169` | Retain as a source alias; do not equate to old handles |
| Act identifier | `AC_CEN_26_36_00004_200522_1517807322955` | Join sections and associated source records |
| Given ID | `2005-22` | Retain as source metadata |
| Legal citation | Act 22 of 2005 | Searchable citation, insufficient alone as a global record key |
| PDF bitstream UUID | `78f68a27-8902-4081-8d53-a3932264ca52` | File identity, separate from document identity |
| Section 6 item UUID | `822280bc-89b4-4a39-aa10-72163b7c22f6` | Source provision identity |
| Section 6 label | `6` | Display/citation label, separate from ordering |

The RTI item contains a `dc.identifier.uri` value pointing at `http://test1.indiacode.nic.in/...`. Do not blindly promote that value to the public source URL or follow it. Retain the value for provenance and use the verified public Act/PDF URLs.

The Environment Act exposes a section labelled `5A`. Labels must be strings, and ordering must use a separate field. Do not sort section labels lexicographically or assume the displayed record count equals the highest section number.

Subordinate instruments have their own `/items/{uuid}` records. The inspected RTI Rules, 2012 record displays `Act Year = 2005` and `Act Number = 22`: these describe the **parent Act**, not the rule's year and number. Its publication date is separately displayed as 31 July 2012.

## 4. Structured text exists, but its fidelity needs verification

**Decision closed; implementation and text admission pending.** The [accepted conflict policy](CONFLICT_POLICY.md) preserves all representations, uses a visually reviewed PDF snapshot as the initial fallback for substantive conflicts, and discloses disagreements. This is a reference-selection policy, not a declaration that PDFs establish current legal effect. The original observations below remain evidence; their handling is now decided.

The sampled section records contain HTML in `dc.identifier.section_page_note`, with amendment notes in `dc.identifier.section_footnote`. Preserve both. The HTML uses paragraph-like breaks, separators, inline spans, italics, and superscripts. The frontend expands section text inline; its section links use `javascript:void(0)`, so a link-only crawler would miss provision content.

Subsections and clauses exist within the section HTML, rather than as demonstrated independent child records. No chapter metadata field appeared in the sampled RTI item/10-section key union. Chapter headings are present in the PDF. A complete chapter hierarchy is therefore an extraction task, not a verified property of the JSON schema.

### RTI-001 — structured text and PDF disagree

Section 8(1)(j) in the captured structured response includes the longer public-activity/privacy wording. In the linked PDF, page 11 contains the shorter personal-information wording and an amendment footnote. The PDF cover identifies its text as being as of 18 November 2025.

This is a confirmed representation mismatch. We are **not** resolving current legal applicability from it. **Accepted disposition:** select the retained PDF as the reference candidate for the whole of section 8, preserve the conflicting HTML as evidence, and disclose the conflict. **Update, 20 September 2026:** the complete section, its amendment footnote, and its PDF anchor have now been extracted and visually verified — see [`data/review/rti-2005-section-8.review.json`](../../data/review/rti-2005-section-8.review.json) and the [readiness manifest](READINESS_MANIFEST.md). Section 8 is technically admitted for this offline slice; it is still not publicly indexed pending the access decision. Never splice the two texts into a purported unchanged source. See [conflict policy](CONFLICT_POLICY.md).

Evidence: [structured response](../../data/discovery/rti-sections-page-0.body), [linked PDF capture](../../data/discovery/rti-2005-pdf.body), and the original [PDF viewer](https://indiacode.gov.in/pdf-viewer/37520cf3-5c3f-4c0b-aa4a-5985e6f522bf/78f68a27-8902-4081-8d53-a3932264ca52). The offline report script verifies the retained discrepancy.

### RTI-002 — page references are not interchangeable

RTI section 6's structured metadata reports page `7`; the corresponding provision begins on PDF page `9` in the linked file. Store source-provided page references separately from independently verified PDF page anchors. A new PDF cover or arrangement of sections can invalidate assumed offsets. **Update:** the offline importer now binds section 6 to the independently verified PDF page 9 anchor, keeps the raw `7` hint as separate metadata, and does not generalize a fixed offset to any other provision.

### KERALA-001 — listing and detail dates disagree

The central collection listed the Kerala (Alteration of Name) Act, 2026 with 25 August 2026 under its enactment-date column. Its Act Details page displayed 14 August 2026. **Original disposition:** retain both observations, leave the canonical enactment date unknown, and keep this additional fixture outside the first searchable slice. **Update, second-pass investigation, 20 September 2026:** retained-PDF evidence now resolves which date concept each observation represents. The Kerala PDF's own preamble page prints "ACT NO. 18 OF 2026 [14th August, 2026.]" in exactly the position where the RTI PDF prints its own enactment date (independently confirmed against RTI's known `enact_date_raw`), and its cover prints "[As on the 25th August, 2026]" in exactly the position where the RTI PDF's cover prints its own last-modified date. A section 1(2) footnote independently confirms 25 August 2026 is also this Act's commencement-notification date. The canonical enactment date is now recorded as 14-08-2026 with this evidence trail; the Act still stays outside the searchable slice regardless. See [KERALA-001.json](../../data/review/conflicts/KERALA-001.json) for the full investigation, including the one residual gap it discloses (the live listing UI's exact field mapping was never independently re-captured). It also lacks several metadata fields populated on the other sample Acts.

### UI-001 — loading states look like missing data

Several pages briefly displayed no sections or no files while still loading. RTI Rules later exposed its file normally. Do not convert an initial empty browser state into a durable “no file” or “zero sections” fact. Unknown counts in the observation file mean not verified after loading, not zero.

## 5. PDF, scans, OCR, and language

| Retained reference file | Pages | Observed format | Initial use |
| --- | ---: | --- | --- |
| RTI Act, 2005 | 25 | Text PDF, amendment notes and schedules | Structured/PDF comparison; section boundary fixture |
| Environment (Protection) Act, 1986 | 13 | Text PDF | Environmental query and lettered-section fixture |
| Merchant Shipping Act, 2025 | 125 | Text PDF | Long-document, contents, and amendment-note fixture |
| Kerala (Alteration of Name) Act, 2026 | 6 | Text PDF | Short document with metadata conflict; quarantine |
| RTI Rules, 2012 | 4 | Scan with an existing OCR layer | OCR-quality and parent-instrument fixture; quarantine text |

`pdfinfo` and `pdftotext -layout` ran successfully on all five files. RTI PDF pages 9 and 11 and RTI Rules page 1 were also rendered and visually inspected. This was targeted layout/fidelity inspection, not a page-by-page review of all 173 pages.

The RTI Rules file identifies scanning/OCR software in its metadata. Its extracted text contains errors such as distorted words and list markers despite producing thousands of characters. **Extractable text is not evidence of accurate text.** Watermarks also produce stray text fragments in several files (the offline importer's watermark-stripping rule handles this specific artifact for admitted PDF text; it is not an OCR-quality fix). **Update, second-pass assessment, 20 September 2026:** the RTI Rules errors are now catalogued concretely, not just described generally — six distinct error types with page-1 examples (digit/letter confusion, clause-marker corruption, a missing clause marker, word-merge errors, total failure on handwritten annotations, total failure on non-Latin script) — with explicit acceptance criteria for any future OCR work. See [RTI_RULES_OCR_ASSESSMENT.md](RTI_RULES_OCR_ASSESSMENT.md). No OCR work was performed; the rule text remains excluded.

Decision: start with **English**, defer OCR-dependent searchable content, and preserve original files unchanged. No new OCR engine is required for the first text-only slice. Scanned rules can remain source-linked metadata until reviewed. No authoritative alternate-language version was verified or retained in this pass; the site's language switch is not sufficient evidence of a parallel legal text. Hindi and other languages are explicitly outside the first index.

## 6. Proposed ingestion contract for Phase 1

Once source access/reuse is resolved:

1. Begin with explicit manifest entries, not recursive crawling of every linked instrument.
2. Retain original responses/files with status, source URL, fetch time, content type, and checksum. Reject application shells, error responses, and partial downloads as document content.
3. Store source UUIDs, legal citation, parent Act ID, and representation hashes separately. Preserve all metadata values and their language/place attributes before normalization.
4. Fetch section pages completely and compare enumerated counts with the reported total. Use parent ID and collection type to prevent mixing instruments.
5. Preserve raw section HTML and footnotes; produce safely rendered text with structural boundaries. Keep source summaries and legislative-history commentary out of the exact statutory-passage index.
6. Follow the [accepted conflict policy](CONFLICT_POLICY.md): compare aligned provisions, classify differences, and visually review every provision actually admitted in the first small slice against its reference snapshot. Start with partial coverage if needed. Source-linked PDFs are a fidelity reference, not a blanket assertion of current law.
7. Hold conflicts without an approved representation, uncertain OCR, incomplete page traversal, missing provenance, or unverified parentage. A reviewed selected snapshot may be indexed with a disclosed source disagreement; the external disagreement need not have been corrected. Show the chosen source/date and partial-coverage limits.
8. Build LawIndex provision anchors independently of the source's expandable UI and unverified page fields. Derive PDF anchors against the exact retained PDF hash.

Prefer the source's structured interface if an acceptable access arrangement can be established. PDF extraction is needed for verification and some representation conflicts, not as an excuse to discard available structure.

## 7. What remains unresolved

| Item | Current state | Resolution needed |
| --- | --- | --- |
| Automated access and redistribution | User reports emailing India Code for access to 20 Acts; reply/permission not reported | Record the response and exact permitted uses/interface; request more scope separately; see access note |
| Full metadata/schema coverage | One raw Act and 10 raw section records; 11 rendered Act metadata records | Extend reviewed fixtures when the access route is settled |
| Corpus completeness | UI count observed; no full enumeration performed | Complete bounded inventory reconciliation in later ingestion work |
| Conflict-handling decision | **Closed:** reference-selection policy and fixture dispositions accepted; review/admission checks now implemented and passing for RTI sections 6 and 8 | Extend the same checks to the remaining candidate Acts |
| Text fidelity and admission | RTI sections 6 and 8 extracted, visually reviewed, and admitted with hash-bound anchors; other Acts' comparisons pending | Extend visual review to the other 29 RTI sections and the other nine candidate Acts |
| Chapter hierarchy | Visible in PDFs; not found in sampled section metadata | Derive and verify chapter membership |
| Alternate-language fixtures | Not acquired | Keep outside first corpus; investigate separately if needed |
| Production API guarantees and rate limits | Not established | Obtain an agreed interface and request budget; do not infer from frontend config |
| Historical/current legal effect | Not established | Preserve source claims; do not offer as-of legal answers |

## 8. Phase 0 completion assessment

The source's live organization, identity scheme, representative extraction paths, metadata variability, five sample files, seed questions, and proposed exclusions are documented. **The conflict-handling policy decision is closed and is now implemented and verified for a bounded two-provision slice** (RTI Act sections 6 and 8; see the [readiness manifest](READINESS_MANIFEST.md)). **The original exit gate is not fully closed:** a user-sent access request for 20 Acts is pending, the permitted uses remain unconfirmed, and only 2 of the ~180+ provisions across the 10 candidates are certified full-text-ready.

An offline importer now operates on the retained, explicitly labelled fixtures, with conflict handling built in from the start (`scripts/offline_importer.py`, `scripts/verify_offline_import.py`). Expansion of source fetching, review of the remaining candidates, and public publication all require further deliberate steps — visual review effort for the former, a source-access decision for the latter. This report does not start either action or imply that permission has been obtained.
