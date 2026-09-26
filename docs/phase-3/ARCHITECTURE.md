# Phase 3 — lexical alpha architecture and ownership

Started 22 September 2026 after the bounded Phase 2 gate closed. This phase is in progress. The ministry has approved use of up to 20 Acts for the personal, non-commercial project according to the user, who can choose the Acts. See [authorization](../../data/phase3/access-authorization.json) and [proposed inventory](INVENTORY.md). Do not continue reporting that the ministry has not replied. We have not inspected the original email or established any commercial-use right.

## Decisions

Keep the canonical SQLite store and the existing single-writer importer. Acquisition, candidate extraction, fidelity review, and search admission remain separate steps. Permission permits project use; it does not make extracted wording correct. Do not relax source hashes, review-output digests, immutable history, conflicts, or current-version validation to expand faster.

The proposal contains 20 Acts, not 20 complete searchable Acts. Freeze identities and source-listed section/schedule inventories before claiming coverage. Start with RTI and Environment, then expand in small batches with explicit excluded/failed outcomes. Reuse retained bytes where appropriate. Fetching must respect the selected Act set, one outstanding request, a conservative two-second minimum spacing, bounded retries/timeouts, content-addressed retention, and explicit redirect/host validation. These are project defaults, not ministry-specified limits. Do not discover/crawl every linked subordinate instrument automatically.

The Phase 0 discovery manifest is historical evidence and existing importer input. The new inventory lives separately in `data/phase3/inventory.v1.json`; it is not an admission shortcut. The main agent owns the eventual ingestion-manifest migration and generic provision extraction, including identity resolution between the current portal and legacy official references.

## Implemented in this increment

`lawindex/retrieval.py` defines immutable `SearchFilters`, `RetrievalRequest`, `Candidate`, and `RetrievalResult`, plus a `Retriever` protocol and the lexical implementation. Input records have already passed `Snapshot`'s live admission checks. A retriever cannot authorize a new provision or supply display text. Its output is canonical provision IDs and scores; display/excerpts come from the admitted snapshot.

All explicit filters and inferred Act/section constraints intersect. There is no fallback to an unrelated Act or section. Apply constraints before cutting to `limit`; `total` counts all matching provisions, not the returned subset. Ties use canonical keys. Build BM25 statistics over the whole admitted snapshot so selecting a filter does not change the corpus used for term frequency statistics. The trace includes effective explicit filters, method, total candidate count, and candidate limit. Candidate details are now bounded to returned candidates, rather than an unbounded full ranking dump.

Metadata comes from observed source fields, not inferred from titles: `year` is the source manifest's Act year, `ministry` is its ministry, and `document_type` is `collection_observed` (currently `ACT`). The source's `type` field such as “Social” is a subject category and must not become document type. Missing or malformed values stay null and do not match a concrete filter. No claim of current legal effect follows from these metadata labels.

`/api/corpus` lists options only for live admitted records; proposed or quarantined Acts do not appear as searchable filter options. Explicit unknown filter values produce an empty result. Empty query plus at least one filter browses matching admitted provisions in key order; empty query without filters still returns no results. Existing section lookup, lexical weighting, exact excerpts, source links and revocation remain intact.

## API contract for the UI agent

`GET /api/search?q=...&limit=10&act=rti-2005&year=2005&ministry=...&document_type=ACT`

Every parameter is optional and may occur at most once. Omit unused filters; sending an empty filter is a 400. Unknown parameter names or duplicate parameters are 400. Limit is 1–20. Year is exactly four ASCII digits. Other filters are non-empty strings of at most 200 characters. Comparison is exact, case-insensitive, without fuzzy matching or fallback. URL-encode all values using `URLSearchParams`.

Response preserves `query`, `results`, `total`, `corpus`, and `trace`. Every result and provision has `metadata: {year, ministry, document_type}`, whose values may be null. Every `corpus.acts` item adds the same metadata. Act options are `corpus.acts` using slug as value and title as label. `corpus.filter_options` provides arrays `year`, `ministry`, and `document_type`. These options describe the whole currently admitted corpus, not cascading query-specific facets. Do not invent per-option counts.

The permission status is `personal_noncommercial_20_acts_user_reported`; it records the user's account of the grant. The application is still a loopback development server, not a production deployment. The searchable corpus was four provisions when this contract was written; see the batch-1 section below for the current ten.

## Work remaining, in order

1. **Main agent:** resolve the proposed Act identities, implement the bounded capture/inventory path and coverage reconciliation; exercise failures and inventory limits. First expanded batch on RTI/Environment before any broad crawl.
2. **Main agent:** generic section candidates, exact source anchors, conflict decisions and batch review packages; never generate an independent acceptance on behalf of a reviewer.
3. **Separate review agent, after a batch exists:** source comparison and adversarial admission checks with a precise digest-bound brief.
4. **UI handoff completed and accepted:** metadata-filter controls, readable source metadata, route preservation and error states against the implemented contract. See [UI_VERIFICATION.md](UI_VERIFICATION.md). The original [brief](UI_AGENT_PROMPT.md) is retained for context.
5. **Main agent:** phrase/Act-number/year query parsing, larger-corpus ranking behavior, surrounding-source navigation, snippet qualification context, and persistent-index design if measured latency requires it. The current per-request FTS rebuild is a correctness-preserving baseline, not a scalability claim. No vectors until the evaluation phase justifies them.
6. **Main agent:** freeze coverage and latency targets after the first expanded batch measurement, inspect all handoffs, and run the final Phase 3 gate audit. Six development queries remain smoke checks, not a retrieval benchmark.

Phase 3 is not closed by the filter UI. It requires an explicit outcome for every selected Act, reviewed expansion, honest provision-level coverage, source-linked navigation, metadata filters, and an evaluated internal alpha. Generic schedule search, OCR, legal timelines, a production server, and commercial use are not implied by this increment.

## Acquisition increment — 22 September 2026

The 20-Act proposal is now selected, all 20 identities resolved and captured, and conservative candidate extraction is implemented. See [acquisition and candidate contract](ACQUISITION_AND_CANDIDATES.md). There are 1,923 source-listed SECTION records; 895 text-agreement candidates remain review-pending and 1,028 are quarantined. No new text is admitted. `/api/inventory` supplies the tested coverage contract. The next lower-risk handoff is [coverage UI/operator reporting](COVERAGE_AGENT_PROMPT.md); fidelity review and the canonical admission bridge remain with the main agent.

## Coverage handoff accepted — 22 September 2026

The coverage UI and read-only operator report are implemented and inspected; see [verification](COVERAGE_UI_VERIFICATION.md). The full suite passes 162 tests. No further reporting-agent work is required for this handoff. The next main-agent work remains fidelity review and the canonical admission bridge; captured/comparison candidates remain outside search.

## First expanded batch admitted — 22 September 2026

Six reviewed sections joined the searchable corpus through the canonical importer: RTI ss.3 and 9, Environment Act ss.4 and 8, and POSH Act ss.9 and 10. Ten provisions across three Acts are now live. The path is `scripts/reviewed_html.py` (extraction method `phase3-reviewed-html-v1`): it re-verifies capture hashes, Act UUID/act_id, section item UUID, number, heading and collection, then requires the HTML body to occur uniquely at exactly the reviewed PDF page range. Agreement alone never admits; each `data/review/*.review.json` carries the reviewer reference, the visual-comparison evidence renders with their digests, and the expected output digest that the importer and `Snapshot` both enforce. The reviewer record `data/review/reviewer-phase3-batch1.json` is disclosed as AI self-review, not independent legal review. Legacy provisions keep `offline-importer-v2`; `import_attempts` records the method per attempt.

Two defects were found while landing it. The batch's capture metadata lacked `fetched_at_utc`, so the importer admitted all ten but search silently served four; the field is now copied from the matching acquisition receipt (same URL and hash), and `verify_offline_import.py` gained a check that a fresh import is served in full by `Snapshot` with zero exclusions. Browsing order for empty queries was lexicographic on key (`10` before `9`); it is now Act, then natural section order.

## Query parsing, excerpt context and neighbour navigation — 22 September 2026

Roadmap item 5, implemented in `lawindex/search.py` and `lawindex/retrieval.py`:

- **Quoted phrases** (`"give any reason"`, curly quotes accepted, at most five) are FTS5 phrase constraints intersected with every other constraint before the top-k cut. They also enter the ranking expression; ranking never relaxes them. Quoted text is literal: `"section 6"` is a phrase, not a section reference.
- **Citations** are parsed only outside quotes and are removed before topic terms are taken: `Act 22 of 2005` / `No. 22 of 2005` constrains on the manifest's `act_number` and year; `Act, 2005`, `Act of 2005`, `2005 Act` constrain on year. A bare year is ordinary text. There is no fallback: `National Green Tribunal Act, 2010` returns nothing rather than provisions whose text mentions 2010, and the trace's `citation` field says why. Explicit `year` filters intersect with parsed years.
- **Act titles** are matched from the manifest with or without the leading "The" and the trailing year, whole words only, before citation stripping. `ALIASES` remains for short forms (RTI, EPA, POSH). A word inside a title selects nothing.
- **Excerpt context**: each excerpt reports `context: {subsection, proviso}` read from the provision's own markers (`(n)` at a line start or after the heading's ".—"; "Provided [further] that" at a line start). Cross-references such as "sub-section (1)" never count. The response's `excerpt_context_note` states that this locates the excerpt and is not a separate structural admission. The excerpt window anchors on the first literal phrase occurrence when there is one.
- **Navigation**: `GET /api/provisions/<key>` adds `navigation` with the admitted provisions of that Act in section order, `previous`/`next` (null at the ends), the manifest's source-listed section count, and a note that movement is between admitted provisions only. The UI renders this under the source section; `corpus.acts[].provisions` is likewise in section order. `results[].act_number` is additive.
- **Latency** (`scripts/measure_search_latency.py`, 20 rounds, 10 provisions, this machine): snapshot validation median 4.5 ms (p95 5.6 ms) per request; search after validation median 0.6 ms (p95 1.1 ms). No persistent index is justified at this size. Validation cost is roughly linear in admitted provisions and captures; re-measure after each batch and decide at the point it approaches interactive limits, not before.

Tests: `tests/test_query_navigation.py` and `tests/test_reviewed_html.py`; the suite is 180 tests and the verifier 27 checks. Remaining from item 5: ranking behaviour needs a larger corpus to evaluate; the six development queries remain smoke checks. Item 6 (freeze targets, inspect handoffs, gate audit) is still open.

## Typographic equivalence tier — 22 September 2026

Candidate alignment now has two tiers, both requiring whole-body unique agreement with the retained PDF: exact (896) and typographic (607), the latter with an enumerated, symmetric normalization ladder recorded per candidate. 1,503 of 1,923 source-listed sections align; 420 are quarantined with per-candidate divergence diagnostics, of which 111 are bodies that align while the footnote is reworded. Details and the ladder are in [ACQUISITION_AND_CANDIDATES.md](ACQUISITION_AND_CANDIDATES.md). No candidate is admitted by either tier; the review standard for admitting aligned candidates at scale is an open decision for the user (per-section visual review, per-Act sampled visual review with automated checks, or automated-only), and the disclosure label must follow whichever is chosen.

## Sampled review admission — 22 September 2026

Review standard for expanded coverage, chosen by the user: per-Act sampled visual review over full automated checks. A deterministic plan selects every risk-flagged aligned candidate plus a stratified sample of the rest; a passing review authorizes that Act's aligned candidates for admission through the canonical importer under review class `text_agreement_sampled_visual`, one record per provision, each re-proved at import time against the plan. Search states per provision whether it was individually compared. Contract, tooling and the first batch (RTI, 34 provisions now searchable) are in [ACQUISITION_AND_CANDIDATES.md](ACQUISITION_AND_CANDIDATES.md). Half the inventory is blocked on the ingestion-manifest migration.

## Ingestion-manifest migration — 22 September 2026

`data/discovery/corpus-manifest.json` is now schema 2 with 22 records: the 12 original Phase 0 records, unchanged, plus 10 derived from the retained Phase 3 item captures (`scripts/ingestion_manifest.py`, composed by `build_phase0_artifacts.py`, which remains the manifest's single writer). This unblocks the half of the 20-Act inventory that `admit_sampled_batch` was refusing.

Every derived field is read out of hash-bound HTTP bytes rather than re-transcribed, and a field the item API does not supply is null rather than invented: `last_modified_display` is a rendered-page-only field and is null for these Acts, as are `notification_present` and `linked_counts`. Each record carries `record_basis` and `record_evidence`.

Two facts are now explicit instead of latent:

- **Mixed date formats.** The Act Details pages print `DD-MM-YYYY`; the item API returns `YYYY-MM-DD`. `enact_date_raw` keeps each source's own string and every record now carries `enact_date_raw_format`; `verify_phase0.py` checks the two agree. Nothing parses these strings today, so no value changed — the label exists so nothing starts assuming one format later.
- **Title year vs recorded year.** The Competition Act, 2002 is Act No. 12 of 2003, so its manifest `year` is 2003 while its title says 2002. A cited year in a query now matches either the recorded year or the year in the Act's own title (`title_year`), so both citations find it. The explicit `year` filter stays strict on recorded metadata, as its contract documents.

`verify_phase0.py` was broken and unnoticed: it asserted a fixed 16 captures and 12 manifest records, and the first Phase 3 batch had already materialized captures into `data/discovery/`. It is not in the test suite, so nothing caught it. It now verifies every capture's bytes but scopes its counts to the Phase 0 subset, and additionally checks the date-format labelling.

**Proven end to end** on a newly unblocked Act: the National Food Security Act, 2013 (42 aligned, 7 sampled across 4 strata, all verified equivalent, 42 provisions admitted). The searchable corpus is 76 provisions across 4 Acts. Fixing this also surfaced that section listings are paginated at `size=100`, so an Act over 100 sections has several listing captures; `admit_sampled_batch` now materializes each page and binds every provision to the capture that actually holds its section item.

**Latency signal.** Snapshot validation is now 25.9 ms median at 76 provisions across 4 Acts, up from 7.7 ms at 34 across 3. It is paid once per HTTP request and grows faster than provision count, because each Act adds capture hashing on top of per-provision structural revalidation. This is the measurement the persistent-index decision was waiting for: re-measure after the next few batches and decide before it reaches interactive limits.

## Full corpus admitted, and the cost of re-proving it — 23 September 2026

All 20 authorized Acts passed their sampled review: 1,504 provisions are searchable, 366 of them compared by eye. The table and the review findings are in [ACQUISITION_AND_CANDIDATES.md](ACQUISITION_AND_CANDIDATES.md).

At that size the per-provision re-proof exposed repeated work. None of it was verification; it was the same pure computation redone for every provision of an Act:

| Cost at 1,504 provisions | Before | After |
|---|---:|---:|
| Full `import_all` | over 10 min | about 20 s |
| Snapshot validation per HTTP request (median) | 245 ms | 165 ms |
| Search after validation (median) | 22 ms | 22 ms |

The fixes are memos keyed by content, so none of them removes a check:

- `offline_importer.pdftotext_layout` and the new `clean_pdf_pages` are memoized by the SHA-256 of the exact PDF bytes. Before, every provision re-ran `pdftotext` on its whole Act PDF, 311 times for Merchant Shipping. Derived text files on disk are still never trusted.
- `phase3_candidates.normalized_pages` / `compacted_pages` memoize a page tuple's normalization per level.
- `reviewed_html._listing_items` indexes a section-listing capture by the digest the caller has just verified against those bytes, and decodes each item afresh for each caller.
- `Snapshot` reads and canonicalizes each reviewer file once per snapshot, which means once per request, never across requests. It also builds each Act's title patterns once instead of once per provision.

What remains is mostly SHA-256: roughly 33 digests per provision per import. That cost is deliberate. The queue, the record builder, the extraction method, promotion and the snapshot writer each re-prove the bytes they are handed, and the independence of those checks is worth more than the seconds.

Per-request validation still grows with the corpus. 165 ms is fine for a loopback development server; a public deployment would need a validated, persistent index built once per import instead of once per request. The earlier plan named that decision; this measurement is the evidence for it.

## Cited titles no longer fall back to another Act of the same year — 23 September 2026

With the whole corpus admitted, "National Green Tribunal Act, 2010" began returning FCRA s.24. The FCRA is also a 2010 Act, and its s.24 mentions "tribunal". That broke the documented rule that citations never fall back to an unrelated Act; the rule had only held because no 2010 Act was admitted.

A capitalised name written immediately before "Act, YEAR" is now a **cited title**. Connector words (of, and, the, to, for, in, on, at, with) and a parenthesised part, as in "(Protection)" or "(Regulation)", may sit inside it, and it starts at its first capitalised word. If no admitted Act matches the query by title or alias, the answer is empty rather than every Act of that year. The trace reports `citation.cited_title` and `citation.cited_title_unmatched`. With no capitalised name ("Act, 2013", "appeal procedure Act, 2005") the year alone constrains, as before.

Known limits: a lowercase citation ("national green tribunal act, 2010") carries no title signal and falls back to the year constraint. A capitalised word that is not a title ("Appeal Act, 2005") is read as one and returns nothing. Both fail toward saying less.

Two query tests had assumptions the full corpus broke; they are now written against the corpus as it stands. "Provided further that" no longer puts POSH s.9 in the top 20, so that test filters to POSH. The phrase "three months" legitimately matches "three month's wages" because FTS5 phrases are stemmed, so that test checks tokens rather than a literal substring.

