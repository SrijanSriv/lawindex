# Bounded acquisition and candidate comparison

22 September 2026. The main agent selected the proposed 20 Acts under the user's authorization and captured their current India Code records. The ministry approval is recorded from the user for the personal, non-commercial project; this record does not claim we inspected the email.

## What is complete

`scripts/acquire_phase3.py` accepts only members of `data/phase3/inventory.v1.json`, enforces the 20-Act cap and distinct identities, and resolves exact central Act titles. It retains metadata, every page of the source SECTION listing, and original PDF bitstreams. It checks section counts, UUID uniqueness and parent Act identity. It does not crawl linked rules/notifications. Original bundles include separately retained language files; retaining them does not admit or parse all languages.

All 20 Acts were captured successfully. There are **1,923 source-listed SECTION records**. This is not a claim of 1,923 complete legal provisions: portal records and legal structures are different inventories, and schedules still require explicit reconciliation.

Requests are sequential, spaced at least two seconds apart, limited to three attempts for transient failures, with 15-second connection and 40-second transfer timeouts and a 50 MiB response bound. URLs must use the exact HTTPS India Code API host/path. Redirects are refused rather than followed to an unvalidated destination. Acquisition failures are explicit and return nonzero. A writer lock prevents cooperating concurrent capture runs.

Bodies are stored by SHA-256 in `data/phase3/acquisition/blobs/`; immutable observation records and Act-history records preserve evidence. Latest receipts and per-Act materializations are atomic. Cached responses are reused only after status, curl completion and body-hash verification. Cache corruption fails closed. Re-running the command reuses this capture batch; it is not a source-refresh service. Fresh refresh/version selection is future work.

`verify_acquisition` independently reconstructs the materialized Act/section data from retained HTTP bodies and checks declared PDFs against captured bitstreams. Editing a materialized Act JSON is insufficient to change the source-backed inventory. No changes were made to the original Phase 0 captures or canonical importer input.

## Candidates are not admissions

`scripts/phase3_candidates.py` creates review candidates only. Its versioned HTML parser accepts a small explicit set of presentation tags, retains amendment-marker text and footnotes, and rejects tables/unknown tags. It selects an apparent English PDF by filename as an initial heuristic; language identity still requires review.

It compares the entire extracted HTML body to a unique PDF occurrence, allowing whitespace folding only. It preserves punctuation, word spelling, numbers and markers in the comparison. Footnote text must also align within the body's PDF pages. Page mappings are derived from actual PDF page boundaries, not source page-number hints. The existing watermark/footer cleanup is reused as a candidate-stage heuristic; its applicability to new documents needs visual review. The comparison does not prove that HTML omitted no boundary text, that headings are correct, or that graphical relationships survived. It never grants admission.

Current outcomes: **895 agreement-review-pending**, **1,028 quarantined**. A quarantine may indicate formatting, parser limitations, ambiguous alignment, unsupported markup, or a substantive conflict; it is not automatically a legal-text discrepancy. Existing RTI §8 remains admitted through its separately reviewed PDF path despite this candidate comparator rejecting the conflicting HTML. Old admissions and new candidates are independent records.

Every new candidate has `search_admitted=false`. At the time of this increment the four reviewed provisions remained the search corpus and no new review record, schema migration, canonical import, or `--fresh` reset was performed; the first six-section batch was admitted later the same day (see [ARCHITECTURE.md](ARCHITECTURE.md)).

## Coverage API

`GET /api/inventory` returns the selected inventory and capture/comparison bookkeeping. It reads data without modifying it and uses `Snapshot` for live searchable counts. Top-level inventory errors return 503. Per-Act missing/invalid/stale evidence remains a visible row with a diagnostic and unknown counts. A broken row is not silently dropped.

Fields:

- `schema_version`, `inventory_id`, `inventory_sha256`.
- `selected_act_count`, `captured_act_count`, `searchable_act_count`, `searchable_provision_count`.
- `rows`: `slug`, `title`, `acquisition_status`, nullable `source_section_count`/`pdf_count`, `candidate_status`, nullable `agreement_review_pending_count`/`quarantined_count`, `searchable_provision_count`, `full_act_coverage_verified` (currently false), and nullable `diagnostic`.
- `limitations`: required explanatory statements for reporting clients.

Candidate counts are bookkeeping checked against the acquisition version and parser version, not a fresh extraction or independent fidelity assessment. Null means unknown; zero is a known zero. Pending candidate counts can overlap with previously admitted provisions and must not be summed with searchable counts. Do not compute a completion percentage by adding these columns. Snapshot review withdrawal affects searchable counts even when acquisition still reports success.

The stored `data/phase3/coverage.json` is a point-in-time report. Use the API or `build_coverage(root, Snapshot(root))` for live reporting.

## Reproduce

```sh
python3 scripts/acquire_phase3.py
python3 scripts/phase3_candidates.py
python3 -m unittest tests.test_phase3_pipeline -q
python3 -m lawindex.server
# GET http://127.0.0.1:8000/api/inventory
```

The acquisition command is the only command here that may contact the source on a cache miss. Candidate generation is offline. Neither writes the canonical database. Do not delete cached source evidence as a shortcut to refresh.

## Remaining correctness work — main agent

1. Review candidate boundaries, headings, markers, footnotes and language against rendered PDF pages; investigate discrepancy groups without weakening equality checks to inflate coverage.
2. ~~Implement a reviewed-candidate admission bridge through the sole canonical writer~~ — done 22 September 2026 (`scripts/reviewed_html.py`, first batch of six sections; see [ARCHITECTURE.md](ARCHITECTURE.md)). Candidate JSON is still never served directly.
3. Reconcile full per-Act section/schedule coverage, then establish explicit alpha coverage targets. Do not describe the current ten-section product as an expanded alpha.
4. ~~Improve citation/phrase handling, source-neighbour navigation~~ and measure latency — done 22 September 2026; ranking on the expanded corpus remains to be evaluated once the corpus is large enough to measure.
5. Audit the reporting/UI handoff and run the Phase 3 exit checks. Phase 3 remains open.

The user asked the main agent to handle critical work and hand off lower-risk work; the coverage UI/read-only report are that handoff. No independent-review claim has been manufactured.

## Typographic equivalence tier — 22 September 2026

Parser version `phase3-html-pdf-agreement-v2`. The exact tier (whitespace folding only, status `agreement_review_pending`) is unchanged and still yields 896 candidates. A second tier, status `typographic_agreement_review_pending`, applies an ordered, cumulative list of normalizations to **both** the HTML body and the PDF text and records on each candidate the minimal level it needed (`normalizations`, `normalization_level`, `agreement`). Whole-body unique alignment is still required; nothing here admits.

| Level | Tolerates | Never tolerates |
|---|---|---|
| `dash` | `--`, `---`, en/em dash variants, and a single hyphen directly after `, : ; .` | compound-word hyphens |
| `quote` | curly vs straight quotes | |
| `ellipsis` | `…` vs `...` | |
| `marker` | footnote/amendment reference numbers glued to a word or before `[`, asterisk marks; footnote-line numbers in footnote comparison only | stand-alone numbers ("section 5", "2005") |
| `hyphen` | line-break and compound hyphenation between letters | digits ("2-3" is not "23") |
| `punct-space` | whitespace before closing punctuation / after opening bracket or dash | |
| `dash-drop` | a list-introducing em-dash one side omits | |
| `case` | letter case | |
| `quote-drop` | quote marks around a defined term one side omits | |
| `bracket-drop` | editorial amendment brackets `[ ]` placed differently | |
| `space-drop` | spacing inside words; bodies under 25 characters are refused and word-boundary checks are replaced by whole-PDF uniqueness | |
| `footnote-block-skip` | a PDF footnote block at a page break splitting the body; each skipped run must be the entire rest of a page, start like a footnote, and is recorded in `pdf_page_break_gaps` | any other interleaved text |

A footnote is compared on its body's pages with its own minimal level; the candidate's level is the larger of the two. A body that aligns while its footnote text differs is quarantined with reason `body aligned but footnote text differs from the PDF footnote` (111 cases: the portal's per-section footnotes are frequently reworded, e.g. "ibid." resolved differently). Every quarantined candidate whose body was parsed carries a `divergence` diagnostic (first differing context after all normalizations) for reviewers.

Result on the 20 captured Acts (1,923 source-listed sections): 896 exact + 607 typographic = **1,503 aligned (78%)**, 420 quarantined. Quarantine reasons: 180 body not uniquely aligned (real punctuation, wording, numbering or bracket differences between the representations, e.g. "Commercial Court" vs "Appellate Board" in Copyright s.6, "acknowledgment"/"acknowledgement" in IT s.12, an extra comma in Competition s.16), 114 section start absent (mostly the same class, diagnosed at the exact tier), 111 footnote reworded, 14 empty HTML bodies, 1 HTML table. Per-Act alignment ranges from 29% (Competition) to 99–100% (Disabilities, Repealing and Amending); the three heavily amended Acts (Competition, Copyright, IT) carry most of the real conflicts, and their retained PDFs are current (w.e.f. dates into 2024–2026), so these are representation conflicts, not stale PDFs.

`/api/inventory` rows now carry `typographic_agreement_review_pending_count` and `quarantine_reasons`; the coverage UI and `scripts/report_phase3_coverage.py` show both. The v1 candidate files were replaced; regeneration takes about five minutes and is offline. Tests: `tests/test_typographic_tier.py`.

## Sampled review and batch admission — 22 September 2026

Admitting 1,503 aligned candidates one visual review at a time was not going to happen, and admitting them on text agreement alone would have broken the project's rule that agreement never admits. The chosen middle is per-Act sampled visual review with full automated checks on every provision.

**Plan** — `scripts/sample_review_plan.py --act <slug> [--render]` writes `data/phase3/review-plans/<slug>.json`. Selection is deterministic (`seed = sha256(planner_version|act_slug|candidates_sha256)`), so re-running cannot re-roll a sample until an easy one appears. It selects every aligned candidate with a footnote or a page-break footnote gap (the cases whole-body character agreement cannot police), then, from the rest, `max(2, 10%)` of each stratum, a stratum being the most tolerant normalization level that candidate needed. Every normalization class an Act actually uses is therefore looked at. The plan carries the whole aligned population with its output digests, so it is complete evidence of what a passing review authorizes. Across the 20 Acts this is 370 sections of review for 1,503 provisions.

**Review** — the reviewer compares each selected section whole against its rendered pages, then `scripts/record_sample_review.py` stamps the outcomes. Coverage is enforced: outcomes must cover exactly `selected_keys`, each needs a decision and a note, and one `discrepancy` sets the Act decision to `act_batch_rejected`, which authorizes nothing. A recorded review is never silently replaced.

**Admission** — `scripts/admit_sampled_batch.py --act <slug> [--write]` materializes the retained captures into `data/discovery/` (bytes, URL, status and `fetched_at_utc` all from the retained receipt), then writes one review record per aligned candidate with its own expected-output digests, the recorded normalization level, and the plan reference. Every record is verified through `offline_importer.build_provision_record` before anything is written, and existing records are never overwritten, so individually reviewed provisions keep their stronger record. The importer remains the only writer.

**Import-time proof** — extraction method `phase3-sampled-agreement-v1` (`scripts/sampled_agreement.py`) re-proves, on every import: capture bytes and Act/section identity (shared with the individually reviewed path via `reviewed_html.source_fields`); that the body still aligns at exactly the recorded normalization level, on the recorded pages, with the recorded page-break gap count, and that the recorded level is a genuine prefix of the ladder; and that an unchanged, completed, passing plan lists this provision with these digests. A changed plan, a withdrawn or rejected review, a dropped or failed outcome, an overstated normalization level or a mis-set `visually_reviewed` flag each stop admission.

**Honesty** — `lawindex/search.py` derives each provision's review basis from its own record. A provision admitted under a sample is served as "matched against the source PDF automatically; N of M provisions of this Act were also compared by eye, but not this one", carries a result badge saying so, and can never be presented as individually reviewed. The reviewer record discloses the sampling.

**First batch** — RTI 2005: 27 aligned, 10 selected (4 mandatory, 6 stratified), all verified equivalent against the rendered pages; 24 new records written (3 provisions already had individual records). The searchable corpus is now 34 provisions across 3 Acts. Plans exist for all 20 Acts; the other 19 await rendering and review. Tests: `tests/test_sampled_batch.py`; verifier check `check_sampled_admission_is_bound_to_its_plan_and_never_overclaims`.

**~~Blocked~~ — resolved 22 September 2026.** Those 10 Acts were absent from `data/discovery/corpus-manifest.json`; the ingestion-manifest migration added them (see [ARCHITECTURE.md](ARCHITECTURE.md)). All 20 Acts are now admissible, and the National Food Security Act, 2013 was admitted as the first newly unblocked batch.

## All twenty Acts admitted — 22-23 September 2026

Every one of the 20 authorized Acts went through the sampled review. 366 sections were compared by eye against their rendered PDF pages. **No discrepancy was found**, so no Act batch was rejected. 1,503 aligned candidates were admitted, plus `rti-2005:8`, which keeps its earlier individual PDF-extracted record. That gives **1,504 searchable provisions across all 20 Acts**. The 420 quarantined candidates stay out of search.

| Act | Aligned & admitted | Reviewed by eye |
|---|---:|---:|
| Merchant Shipping 2025 | 311 | 39 |
| Indian Contract 1872 | 200 | 36 |
| OSH Code 2020 | 134 | 18 |
| Mental Healthcare 2017 | 111 | 20 |
| Consumer Protection 2019 | 104 | 15 |
| Rights of Persons with Disabilities 2016 | 101 | 20 |
| Real Estate 2016 | 82 | 22 |
| Arbitration and Conciliation 1996 | 69 | 24 |
| Information Technology 2000 | 53 | 27 |
| FCRA 2010 | 51 | 20 |
| National Food Security 2013 | 42 | 7 |
| Copyright 1957 | 41 | 25 |
| DPDP 2023 | 40 | 11 |
| Right of Children to Education 2009 | 31 | 12 |
| Competition 2002 | 28 | 21 |
| RTI 2005 | 27 | 10 |
| POSH 2013 | 26 | 8 |
| Legal Services Authorities 1987 | 25 | 16 |
| Environment (Protection) 1986 | 23 | 13 |
| Repealing and Amending 2023 | 4 | 2 |
| **Total** | **1,503** | **366** |

**What the review found.** None of it blocked admission. It is recorded in each plan's outcome notes.

- **Page-break footnote skips.** Every one belonged to a neighbouring section's footnote, never to the section being admitted.
- **Amendment material in section bodies.** Some bodies carry text the source prints inside the section. Environment s.16 includes the inserted "CHAPTER IIIA" heading. Education 2009 prints Rajasthan state-amendment blocks inside ss.21, 24 and 29, so those admitted provisions include that state material. Earlier notes also listed ss.8 and 16; those two are quarantined and not searchable (see [PHASE3_GATE_AUDIT.md](PHASE3_GATE_AUDIT.md) N5). Several substituted sections carry their own number and heading, as the PDF prints them.
- **Spacing defects in the PDFs.** Legal Services and Contract Act PDFs drop spaces around cross-references and clause letters ("section3A", "(a)A", "s. 65,ibid"). Those provisions needed the `space-drop` level; the wording itself is identical.
- **Amendment brackets.** The two representations of heavily amended Acts (IT, Competition, Copyright, Arbitration) place amendment brackets differently. That is what `bracket-drop` exists for.
- **Wording disagreements.** Copyright s.6 reads "Commercial Court" in the HTML but "Appellate Board" in the PDF. Conflicts like this remain quarantined and unadmitted.

**Disclosure.** 372 of the 1,504 provisions have been individually compared: the 10 earlier individual reviews plus 362 sampled sections (four of the 366 sampled sections, RTI ss.6 and 9 and Environment ss.3 and 5A, already had individual records, which they keep). The other 1,132 have not been individually compared. Each unsampled provision is served as matched to the source automatically and not individually reviewed, with its Act's sample size stated. No legal-expert review has taken place, and no provision's current legal effect has been established.

