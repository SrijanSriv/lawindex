# LawIndex expansion backlog

Started 23 September 2026. This is the running list of what LawIndex could do next, in one place. Phase plans say what each phase must deliver. This file collects the concrete gaps and ideas that surfaced during the work, so none depends on someone remembering a report. Add to it whenever a gap is found; move an item into a phase plan when it is scheduled.

Each item says what is missing, the evidence, what closing it would take, what must come first, and where it fits in [PHASES.md](../PHASES.md).

**Permission comes first.** The reported ministry permission ([access-authorization.json](../data/phase3/access-authorization.json)) covers up to 20 chosen Acts, for personal, non-commercial use. It explicitly does **not** cover more than 20 Acts, associated instruments (rules, regulations, notifications), commercial use, or the legal accuracy of extracted text. Items marked **needs permission** must not begin until the user has that permission and it is recorded.

## 1. Coverage: why a query can go unanswered

Today's search covers 1,504 sections of 20 central Acts. The Phase 3 gate audit found five separate reasons a query can fall outside it. Covering more Acts closes only the first. Search now names each case in a notice beside the results (`act_not_indexed`, `schedules_not_indexed`, `instruments_not_indexed`, `state_law_not_indexed`, `case_law_not_indexed`, plus `weak_match`).

| # | Gap | Evidence | What closing it would take | First | Fits |
|---|---|---|---|---|---|
| 1.1 | **Acts outside the 20** (e.g. the National Green Tribunal Act) | Seed query "National Green Tribunal Act, 2010"; `act_not_indexed` | The same pipeline as Phase 3: capture, candidate extraction, typographic tier, sampled review, admission. Per Act, that has been roughly 2–40 sections of visual review. Either swap Acts within the 20 or expand past it. | **Needs permission** to exceed 20 Acts. Choose Acts by observed user need. | Phase 3 method; Phase 10 at scale |
| 1.2 | **Schedules of the included Acts** (e.g. the RTI oath forms, the Repealing and Amending lists) | Seed P0-020; `schedules_not_indexed`. Schedules were excluded from search in Phase 2. | Generalize the Phase 2 positioned-word schedule model ([SCHEDULE_LAYOUT.md](phase-2/SCHEDULE_LAYOUT.md)), which so far handles one reviewed RTI fixture, to other schedule shapes (tables, lists, forms). Add a schedule admission path with its own review, and a display that keeps layout rather than inventing prose. Count schedules per Act in the coverage report. | Nothing new; schedules are part of the permitted Acts. | Phase 6 (legislative structure) |
| 1.3 | **Rules, regulations and notifications** made under the Acts (e.g. RTI Rules, 2012) | Seed P0-021; `instruments_not_indexed`. RTI Rules are a scanned PDF with defective OCR ([RTI_RULES_OCR_ASSESSMENT.md](phase-0/RTI_RULES_OCR_ASSESSMENT.md)). | Discover each Act's linked instruments. Decide on OCR (re-OCR plus review, or text sources only). The schema already separates instruments and records their relationships (Phase 2). Show them as separate, linked documents, never merged into the Act. | **Needs permission**: associated instruments are explicitly not covered. OCR decision. | Phase 10 ("missing central instruments") |
| 1.4 | **State laws** (e.g. UP rent control) | Seed P0-023; `state_law_not_indexed` | A different source family and jurisdiction metadata: state as a first-class field and filter, no mixing with central law. Start with one state and a verified slice. | Source audit and reuse terms for the chosen state. | Phase 10 |
| 1.5 | **Court judgments** | Seed P0-024; `case_law_not_indexed` | New modeling: citations, benches, dates, and whether a judgment is still good law. It cannot reuse the provision model. Evaluate separately. | A source with clear reuse terms; a decision that the product should include case law at all. | Phase 10 (flagged there as needing new modeling) |
| 1.6 | **The 420 held-back sections of the 20 Acts** | [ACQUISITION_AND_CANDIDATES.md](phase-3/ACQUISITION_AND_CANDIDATES.md): 180 body disagreements, 114 start absent, 111 footnote reworded, 14 empty HTML bodies, 1 table | Three separate jobs: (a) 111 bodies that agree while the footnote wording differs: admit the body with a recorded footnote conflict; (b) genuine HTML/PDF disagreements, concentrated in Competition (29% searchable), Copyright (39%) and IT (42%): a reviewed PDF-only extraction path with the conflict recorded, as `rti-2005:8` already has; (c) empty bodies and the table: PDF extraction plus review. | Nothing new; within the permitted Acts. | Phase 3 method (coverage) |
| 1.7 | **Best answers that v2 judging found outside the admitted text** | Phase 5 judge B, 25 September 2026: IT Act s.43, 66 and 66E; RTE Act s.3; FCRA s.11 and 12; Legal Services Authorities Act s.12; Arbitration Act s.8; Contract Act s.176; Food Security Act s.4 and Second Schedule; DPDP Schedule (penalty amounts) | Confirm which are held-back sections (1.6) and which are schedules (1.2). Prioritize these sections when doing 1.6, because real queries need them. | Nothing new; within the permitted Acts. | With 1.6 and 1.2 |

## 2. Search quality

| # | Item | Evidence | What it would take | Fits |
|---|---|---|---|---|
| 2.1 | Ranking displacements inside the right Act | DEV-002 is rank 2 behind RTI s.9; P0-009 rank 2; P0-010 rank 5 ([gate audit](phase-3/PHASE3_GATE_AUDIT.md)). Judged benchmark, 24 September 2026: P0-010 scores nDCG@10 0.90 because the judges graded s.4 a direct answer too ([baseline](phase-4/BASELINE.md#the-phase-3-exception)) | Benchmark exists now; field weights and proximity measured against [targets](phase-4/TARGETS.md) | Phase 5–6 |
| 2.2 | Lowercase citations carry no title signal | "national green tribunal act, 2010" falls back to the year constraint (see ARCHITECTURE.md, cited titles) | Match cited words against a list of known central Act titles, including unindexed ones, instead of relying on capitals | Phase 3 follow-up |
| 2.3 | Heading-caused ranking not identified | Audit N2 | Report which fields matched per result (FTS5 match info) and show "matched heading" | Phase 6 |
| 2.4 | Dev-query test pins a four-provision fixture | Audit N4 | Done in Phase 4: `scripts/run_benchmark.py` reports ranks for all 162 queries on the live corpus | Done |
| 2.5 | Weak-match and notice heuristics are hand-written | `coverage_notices` in `lawindex/search.py` | Replace with measured detection once the benchmark has out-of-scope cases | Phase 4–5 |
| 2.6 | Semantic retrieval for plain-language questions | Lexical only today | Hybrid retrieval, measured against lexical | Phase 5 |
| 2.7 | Acronym citations read as unknown Act titles | "DPDP Act 2023 …" shows `act_not_indexed` for an indexed Act (benchmark B-045) | Resolve cited titles against known acronyms and aliases before declaring an Act unindexed | Phase 5–6 |
| 2.8 | Unknown acronym plus section number returns nothing | "RERA section 18" gets zero results (B-038) | Aliases for common Act acronyms (RERA, DPDP, RTE, IT Act, CPA); today only RTI, EPA and POSH have aliases. Measure on dev | Phase 5–6 |
| 2.9 | Terminology gaps | "non-compete" never meets "restraint of trade" (B-117; 0 of 31 pooled candidates relevant); ordinary language nDCG@10 0.53, terminology 0.46 | Semantic or hybrid retrieval, or a reviewed synonym list; judged against [targets](phase-4/TARGETS.md) | Phase 5 |
| 2.10 | `weak_match` fires on plain questions | 7 in-corpus queries flagged, e.g. "someone found my lost wallet, what are their duties". Measured 25 September 2026 with `scripts/analyze_notices.py`, on the dev split: at the current rule (share below 0.5, at least 3 words) it flags 6 in-corpus and 6 out-of-corpus or partial queries. At 0.4 it is 2 and 2; at 0.6, 11 and 12. **Changing the threshold trades false notices for missed notices about one for one**, so a threshold alone cannot fix this. | A different signal, such as known Act titles (2.11) or a vector-similarity score in Phase 5. Choose on dev, and check notice recall stays ≥ 0.68 | Phase 5–6 |
| 2.11 | Out-of-corpus queries without a cited Act and year get no notice | GST, Income Tax s.80C, BNS 2023 ("Sanhita", not "Act"), divorce, anticipatory bail, trademark: notice recall 0.60 | A list of known central Act titles (also closes 2.2), and measured weak-match detection | Phase 5–6 |
| 2.12 | Held-back sections are invisible in search | 47 benchmark queries have an unindexed target (74 in all), e.g. Contract ss.11, 25, 73; IT ss.43, 66; FCRA ss.3, 11, 12 | Tell the user when a cited or likely section exists but is held back; admitting them is item 1.6 | Phase 5–6 (notice), Phase 3 method (admission) |

## 3. Presentation

| # | Item | Evidence | What it would take |
|---|---|---|---|
| 3.1 | State-amendment text inside central sections not flagged | Education ss.21, 24, 29 carry Rajasthan amendment blocks (audit N3) | Detect "STATE AMENDMENT" blocks and show a note, or render them as separate labelled parts |
| 3.2 | Coverage page omits schedules and instruments | Audit N1 | Per-Act counts of schedules and linked instruments, each shown as "not indexed" until 1.2 and 1.3 land |
| 3.4 | Merged heading in one admitted section | `consumer-protection-2019:83` has the heading "Product liability action 84. Liability of product manufacturer.", which looks like two headings run together. Reported by v2 judge B, 25 September 2026 | Check it against the source PDF. Any fix goes through the importer and a new review record, never a direct edit |
| 3.3 | Languages | Hindi PDFs are retained but not parsed | Hindi text extraction, review and a language filter; never silently mix languages |

## 4. Trust, currency and operations

| # | Item | Evidence | What it would take | Fits |
|---|---|---|---|---|
| 4.1 | Only AI review so far | Every review record discloses AI, non-expert review; 1,132 provisions were matched automatically but not individually compared | Independent human or legal-expert review, at least of a sample; a separate AI review pass is a cheaper interim step | Before any public release |
| 4.2 | Current legal effect not established | No commencement/amendment timeline | Amendment and commencement tracking per provision | Phase 6 / 8 |
| 4.3 | Source refresh | Captures are one-off (21–22 September 2026) | Scheduled refresh with change detection; revocation already works | Phase 8 |
| 4.4 | Per-request validation cost | 165 ms median at 1,504 provisions ([ARCHITECTURE.md](phase-3/ARCHITECTURE.md)) | A validated persistent index built once per import, before any public deployment | Phase 7 |
| 4.5 | Verifier runtime | `verify_offline_import.py` takes about 30 minutes at full size (many full re-imports) | Share imports across checks where independence isn't needed | Maintenance |
| 4.6 | Commercial use | Not permitted | Separate licence | Only if ever needed |
