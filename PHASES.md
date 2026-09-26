# LawIndex — Phases and Milestones

This is the proposed execution plan for the vision in [IDEA.md](IDEA.md). Phase 0's bounded offline technical slice is complete; source access remains separately pending. Phase 1's data/search backend and browser interface are both implemented, tested, and browser-verified for the bounded four-provision slice. Phase 2’s bounded offline technical gate is closed. Phase 3 is closed (23 September 2026) over 1,504 reviewed sections of 20 Acts, with one recorded ranking exception. Phase 4, the retrieval benchmark, is closed (25 September 2026); see its [gate audit](docs/phase-4/PHASE4_GATE_AUDIT.md).

Current evidence and remaining gates are recorded in the [Phase 0 overview](docs/phase-0/README.md). The source has migrated to `indiacode.gov.in`. The [conflict-handling policy](docs/phase-0/CONFLICT_POLICY.md) is implemented for four reviewed provisions across two Acts. The user has requested access to 20 Acts from India Code; no reply or permission has yet been reported.

The sequence is deliberate: discover the source, build a small end-to-end search engine, make its ingestion reliable, establish a useful lexical baseline, then improve retrieval through controlled experiments. AI answers and additional jurisdictions are later decisions.

## How we will use this plan

- Work toward one milestone's exit gate at a time. A gate describes working evidence, not just code that exists.
- Keep the first vertical slice small enough to inspect manually. It should not wait for a full-corpus crawl, embeddings, or a polished frontend.
- Start evaluation and provenance in that first slice; deepen them as coverage grows.
- Record assumptions and significant architecture decisions with their evidence. Proposed sample sizes and candidate counts below are starting points, not frozen requirements.
- At each milestone, record what shipped, how it was verified, known limitations, and the next unresolved question.
- Do not assign calendar deadlines until source discovery and a working slice reveal the actual effort.

## Sequence at a glance

| Phase | Milestone | Completion evidence |
| --- | --- | --- |
| 0 | Source discovery and scope | Verified source inventory, sample artifacts, bounded first corpus |
| 1 | First working search engine | Query → exact provision → source on a small sample |
| 2 | Reliable ingestion and canonical structure | Repeatable imports, stable identities, explicit failures |
| 3 | Central-legislation lexical alpha | Declared inventory coverage, usable document navigation |
| 4 | Retrieval benchmark | Reviewed 100–200-query dataset and reproducible baseline |
| 5 | Semantic and hybrid experiments | Comparable lexical, vector, and hybrid reports |
| 6 | Reranking and structural improvements | Measured quality gains with acceptable latency and cost |
| 7 | Public India beta | Deployed, bounded, observable search with recovery procedures |
| 8 | Maintained search service | Scheduled refreshes, change detection, regression checks |
| 9 | Optional grounded answers | Evidence-supported answers that can be disabled independently |
| 10 | Evidence-led expansion | One justified new corpus, source, or interface at a time |

Phases 5–6 are experiments: a negative result is a valid outcome, and lexical search may remain the default. Public beta does not require an LLM or every experimental retrieval component. Maintenance is essential; answers and expansion are optional.

## Phase 0 — Discover India Code and bound the first corpus

**Objective:** replace assumptions about the source with an inspected ingestion plan.

**Status — first discovery pass complete; offline import/verification implemented and strengthened across two second-pass rounds, covering a bounded four-provision slice over two Acts; exit gate not fully met.** Inspected 11 Act metadata records, retained 16 HTTP captures including five PDFs, selected 10 Act candidates plus two quarantine fixtures, and drafted 24 seed queries. Documented current collection/section pagination, real metadata keys, source identifiers, scan quality, and representation discrepancies. RTI Act sections 6 and 8, plus Environment (Protection) Act sections 3 and 5A, are now visually reviewed, admitted, hash-anchored, and covered by a passing offline importer and regression suite (run `scripts/verify_offline_import.py` for the current check count) — see the [readiness manifest](docs/phase-0/READINESS_MANIFEST.md). A second-pass audit also found and fixed several importer defects (see the manifest's "second-pass defect review" section), resolved the Kerala enactment-date conflict from retained PDF evidence (see [KERALA-001](data/review/conflicts/KERALA-001.json) — canonical date now 14-08-2026, Act still quarantined), catalogued concrete RTI Rules OCR error types with deferred acceptance criteria (see [RTI_RULES_OCR_ASSESSMENT.md](docs/phase-0/RTI_RULES_OCR_ASSESSMENT.md)), and prepared an [access-response checklist](docs/phase-0/ACCESS_RESPONSE_CHECKLIST.md) for when India Code replies. A subsequent independent review and follow-up inspection ([INDEPENDENT_REVIEW.md](docs/phase-0/INDEPENDENT_REVIEW.md), [INSPECTION_FOLLOWUP.md](docs/phase-0/INSPECTION_FOLLOWUP.md)) found and a remediation pass then fixed two gaps in the change-invalidation mechanism — see the readiness manifest's "Remediation" section. The remaining candidate corpus is not text-reviewed, alternate-language fixtures were not acquired, and automated ingestion/public reuse is unresolved. See [source findings](docs/phase-0/SOURCE_DISCOVERY.md), [metadata matrix](docs/phase-0/METADATA_MATRIX.md), [corpus scope](docs/phase-0/CORPUS.md), and [access findings](docs/phase-0/ACCESS_AND_REUSE.md).

### Work

- Inspect how central legislation is listed, identified, paginated, and linked to detail pages, provision text, PDFs, and associated instruments.
- **Decision complete:** preserve conflicting representations, select reviewed reference snapshots, disclose disagreements, and exclude unreviewed text under the [conflict policy](docs/phase-0/CONFLICT_POLICY.md). This does not certify the candidate corpus.
- Review source access and reuse conditions, crawler guidance, and practical request limits. Prefer a documented export or API if an appropriate one exists; do not assume one is available.
- Save a representative sample of source pages and files. Include straightforward Acts and difficult examples: long documents, schedules, missing metadata, amendments, alternate languages, and associated instruments where found.
- Distinguish structured HTML, text PDFs, and scanned material. Establish whether OCR is needed for the first slice or can be deferred with an explicit coverage exclusion.
- Create a metadata availability matrix showing source field, example value, extraction method, reliability, and missing-value handling.
- Identify source identifiers and distinguish duplicate representations from separate instruments or versions.
- Select an initial slice of roughly 10–20 Acts, adjusted to observed complexity. Declare its language scope and whether associated instruments are included.
- Draft 15–25 seed search questions spanning exact titles, section lookups, topics, ordinary-language wording, and questions outside the sample's coverage.

### Deliverables

A source-discovery note, representative fixtures, metadata matrix, first-corpus manifest, and seed queries. Include unresolved questions about source completeness and legal status representation. A bounded offline importer, its regression suite, and a [readiness manifest](docs/phase-0/READINESS_MANIFEST.md) now demonstrate the accepted conflict policy against four reviewed provisions.

### Exit gate

We can explain where each first-slice document comes from, how to extract it, which fields are actually available, and which cases will be excluded or quarantined. No unverified claim of complete central-legislation coverage.

## Phase 1 — Build the first working search engine

**Objective:** deliver the smallest useful end-to-end product.

**Status: complete for the bounded slice, backend and browser interface, including a follow-up correction pass.** Implemented a loopback Python JSON/PDF API, SQLite FTS5 BM25 search, live admission revalidation, source anchors, exact excerpt segments, and query traces. A plain HTML/CSS/JS browser interface (`web/`) implementing search, provision, and coverage views was built against the fixed API contract and manually verified in a real browser — query submission, keyboard submission, mobile layout, direct-route reload, back-navigation with preserved query, RTI s.8's conflict and footnote, Environment s.5A, verified source-PDF links, 400/404/503/network-failure states, and stale-request-race handling all pass. A subsequent review ([REVIEW_FOLLOWUP.md](docs/phase-1/REVIEW_FOLLOWUP.md)) found and this project then fixed three issues: (1) explicit section-only queries (e.g. "section 6") now resolve from provision metadata rather than requiring the section digit to appear in body text; (2) the skip-link no longer changes the hash route when activated; (3) a PDF page-number footer digit that had leaked into RTI s.8 and Environment s.3's admitted body text at a page boundary is now stripped at extraction, with re-established review digests (`offline-importer-v2`) — see [UI verification record](docs/phase-1/UI_VERIFICATION.md#remediation-2026-09-21) for full detail and regression coverage. All 26 importer checks and 16 API/search tests pass; all six development targets ranked first in the recorded smoke run. See [architecture](docs/phase-1/ARCHITECTURE.md), [API contract](docs/phase-1/API_CONTRACT.md), [results](docs/phase-1/DEV_RESULTS.md), and [interface task](docs/phase-1/UI_AGENT_PROMPT.md).

**Store decision:** retain the existing SQLite store for this four-provision local slice rather than introducing PostgreSQL immediately. The importer remains its sole writer; each request constructs a disposable FTS5 index from currently eligible rows. This is a documented bounded deviation from the initial proposal, to be reconsidered for larger ingestion or deployment.

### Work

- Set up a minimal application and repeatable local startup. SQLite is selected for the bounded slice as described above; the frontend needs only search, results, and a provision view.
- Import the Phase 0 sample, retain source artifacts and content hashes, and store titles, available metadata, source URLs, and section-level text.
- Establish stable document and provision identifiers immediately. Preserve chapter and section labels where available, without blocking the slice on perfect subsection parsing.
- Implement and name the lexical baseline accurately. The current slice uses SQLite FTS5's BM25 ranking with English stemming, field weights, and explicit Act/provision filters. PostgreSQL's built-in full-text ranking, if considered later, is a distinct method.
- Return document title, provision label, faithful excerpt, internal section link, and government-source link.
- Let users move from a result to the full provision and its parent document. Long provisions can initially be searched as whole units rather than introducing arbitrary chunking prematurely.
- Capture a query trace with configuration, candidate IDs and scores, final result IDs, and timings.
- Run the seed queries and manually judge whether the expected provision is retrievable. Retain results as the first baseline.

### Exit gate

From a clean setup, we can import the declared sample, search it, read exact relevant provisions, and open their original sources. Empty results and missing fields behave clearly. This is the **first product milestone**; it does not need full corpus coverage or semantic search.

## Phase 2 — Make ingestion and document structure dependable

**Bounded offline technical gate closed, 21 September 2026:** first offline reliability increment implemented; see [architecture and target schema](docs/phase-2/ARCHITECTURE.md). Per-provision transactions, attempt history, timeout, failure isolation, and conservative restart recovery are implemented. The bounded structural schema migration and reader cutover are now implemented; see [migration and recovery](docs/phase-2/STRUCTURAL_MIGRATION.md). Verified skip-completed recovery and a reviewed 19-node Environment Act clause profile are implemented; see [queue and structure](docs/phase-2/QUEUE_AND_STRUCTURE.md). Two real RTI schedule layouts have negative/quarantine fixtures. A positive positioned-word model for both RTI schedules is now implemented with hash-bound profiles and regression tests. Independent schedule layout review, private viewer verification, and the final main-agent audit pass; see the [Phase 2 gate audit](docs/phase-2/PHASE2_GATE_AUDIT.md) for evidence, viewer corrections, and explicit scope limits. Schedules remain private and not search-admitted; network ingestion and broader acquisition remain outside this gate.

**Objective:** ensure increasing coverage does not multiply silent errors.

### Work

- Separate discovery, fetching, extraction, normalization, storage, passage generation, and indexing into restartable steps.
- Add bounded concurrency, timeouts, backoff, retry limits, caching, and a resumable work queue. Persist per-item outcomes so a failed batch can resume without refetching successful items.
- Make imports idempotent. Importing unchanged input twice must not create duplicate documents, provisions, or index entries.
- Represent documents, source snapshots, hierarchical provisions, and derived passages separately. Provisions need parent references, display labels, ordering, and stable internal anchors.
- Model associated rules and regulations as distinct instruments with explicit parent relationships when supported by source evidence.
- Preserve source text alongside normalized search text. Track passage-to-provision mapping and offsets or equivalent anchors so snippets can be verified. Do not present reconstructed PDF reading order as more certain than extraction supports.
- Version parsers and passage strategies. Keep source artifacts sufficient to reparse without another crawl.
- Handle renumbering or changed structure explicitly: unchanged provisions should keep links; uncertain identity matches should be flagged rather than silently reassigned.
- Quarantine broken, empty, or suspicious extractions. Check hierarchy, ordering, duplicate labels, text lengths, source mappings, and required fields.
- Preserve explicit source status and dates without inferring current legal effect. Snapshot history does not itself establish a historical legal timeline.
- Add parser regression fixtures for ordinary and difficult documents. Decide whether OCR is needed now; if so, preserve extraction method and review uncertain output.

### Exit gate

Two imports of the same fixtures yield the same canonical output and no duplicates. An interrupted run resumes. A source-change fixture creates a traceable update. Known extraction failures are visible and do not silently become searchable text. Representative clauses, schedules, and source links survive parsing correctly.

## Phase 3 — Expand coverage and ship a usable lexical alpha

**Gate audit, 23 September 2026:** all 20 Acts admitted (1,504 searchable provisions; 366 sections sampled, 0 discrepancies). The targets are agreed, uncovered queries are now named, and no single Act dominates a generic query. Every exit criterion is met except one unjudged seed query (P0-010, rank 5). **Closed 23 September 2026** by the user's decision, with P0-010 recorded as an exception carried into the Phase 4 benchmark. See the [Phase 3 gate audit](docs/phase-3/PHASE3_GATE_AUDIT.md).

**In progress, 22 September 2026:** the user reports ministry approval for any 20 Acts for the personal, non-commercial project. A [proposed inventory](docs/phase-3/INVENTORY.md) and [architecture / ownership plan](docs/phase-3/ARCHITECTURE.md) are recorded. The main agent implemented a retriever boundary, exact metadata filters, and live-admitted filter options with regression tests. The bounded filter UI is implemented and accepted; see [UI verification](docs/phase-3/UI_VERIFICATION.md). All 20 selected Acts have now been captured, with 1,923 source-listed section records and conservative comparison outcomes; see [acquisition and candidates](docs/phase-3/ACQUISITION_AND_CANDIDATES.md). No new Act text is admitted; the four-provision slice remains the search corpus. The coverage presentation and read-only report are implemented and accepted; see [verification](docs/phase-3/COVERAGE_UI_VERIFICATION.md). Fidelity review, canonical admission of expanded text, richer query handling and the final Phase 3 gate remain open.

**Objective:** turn the sample into useful search over a declared central-legislation inventory.

### Work

- Build a complete discovery manifest for the selected source scope, with discovered, fetched, parsed, indexed, excluded, and failed counts. Report those against the declared inventory, not against all Indian law.
- Ingest in batches and audit samples across document types and lengths before expanding further.
- Add associated instruments only where source discovery and parser support justify them. Keep missing rules, regulations, languages, and PDFs visible in the coverage report.
- Improve lexical retrieval for exact Act titles, Act numbers, years, section references, phrases, and mixed topic queries. Use field weights and normalization carefully; preserve legally meaningful numbers and punctuation in display text.
- Add available metadata filters, initially document type and year or ministry where sufficiently populated. Missing metadata must not misleadingly behave like a known category.
- Generate excerpts from matched provisions with enough context to retain qualifications and exceptions. Identify headings separately when a title match caused a result to rank.
- Add chapter/section navigation, schedules, surrounding context, and stable deep links. Group multiple passages from one provision and prevent one long Act from overwhelming results.
- Define simple boundaries for interchangeable retrievers: query, filters, candidate limit, scored candidates, and trace metadata. Keep shared result IDs consistent across strategies.
- Measure end-to-end latency and document common failure categories: missing corpus, bad extraction, query parsing, retrieval miss, or ranking error.

### Exit gate

Every item in the declared manifest has an explicit outcome. Agreed coverage targets and sample extraction audits pass, and no known severe text-corruption issue remains hidden. The seed-query report, source-linked navigation, filters, and coverage statement support a useful internal alpha.

## Phase 4 — Establish a credible retrieval benchmark

**Closed, 25 September 2026.** The user agreed the release targets. 162 queries (92 dev / 70 test) with 3,557 graded AI judgments from two independent model judges (κ = 0.82) and main-agent adjudication. The lexical baseline is frozen and reproduces exactly: test nDCG@10 0.651, MRR 0.710. Search is strong on statutory wording and weak on ordinary language, acronyms and terminology gaps (nDCG@10 0.46–0.53). See the [gate audit](docs/phase-4/PHASE4_GATE_AUDIT.md), [baseline](docs/phase-4/BASELINE.md) and [targets](docs/phase-4/TARGETS.md). Phase 5 is proposed and has not started; see [docs/phase-5/PLAN.md](docs/phase-5/PLAN.md).

**Objective:** make retrieval decisions reproducible and harder to fool ourselves about.

### Work

- Expand seed queries to roughly 100–200 representative questions: exact titles, citations, topic searches, terminology mismatches, broad discovery questions, narrow provisions, filters, and out-of-corpus requests.
- Annotate relevant documents and provisions, with graded relevance where useful. Store judgment rationale, source references, reviewer information, and the corpus snapshot used.
- Review ambiguous questions carefully and obtain legal-domain review where needed. Model-suggested labels may help draft judgments but are not authoritative ground truth.
- Pool candidates from multiple methods and manual source exploration to reduce bias toward the first search system. Mark unjudged results separately from judged-irrelevant results; document incomplete judgments.
- Separate a development set for tuning from a held-out test set. Keep paraphrases of the same information need in one split to reduce leakage.
- Report document-level and provision-level Recall@k, Precision@k, MRR, and nDCG. Map derived passage IDs back to canonical provisions so overlapping chunks do not inflate scores.
- Treat out-of-corpus questions separately; they do not have ordinary relevant-document recall. Evaluate whether results and coverage messaging avoid implying completeness.
- Record corpus, parser, chunking, index, model, code, and configuration versions with each run. Include stage timings, end-to-end p50/p95 latency, and per-query rankings.
- Freeze an initial lexical baseline and agree concrete quality, coverage, and latency targets using observed results. Record numerical targets before the next tuning cycle.

### Exit gate

A repeatable command evaluates a frozen corpus and query set, produces aggregate and per-query reports, and can reproduce the lexical baseline. Judgments, known gaps, splits, and release thresholds are documented.

## Phase 5 — Add semantic retrieval and measure hybrid search

**Objective:** test whether semantic similarity improves queries that use different wording from the legislation.

### Work

- Create structure-aware passages: preserve short provisions intact; split long ones at subsection or clause boundaries where possible, with a fallback for oversized blocks.
- Preserve exact display text and offsets separately from any title, heading, or contextual text added for embedding. Assign passage-strategy versions.
- Add a replaceable embedding pipeline with batched, resumable indexing and model/version tracking. PostgreSQL with a vector extension is a candidate first implementation, subject to deployment fit.
- Recompute embeddings only when input or model changes. Prevent querying an index with an incompatible model or mixing incompatible vectors.
- Expose lexical-only, vector-only, and hybrid modes under the same query/filter contract.
- Start hybrid fusion with an explicit method such as reciprocal rank fusion. Raw lexical and vector scores are not automatically comparable.
- Make candidate counts configurable; lexical top 25 plus vector top 25 is an experiment starting point. Deduplicate overlapping representations of the same provision before final presentation.
- Apply corpus and metadata filters consistently. Record how approximate vector filtering affects available candidates and recall.
- Compare methods using Phase 4's benchmark, including query-category regressions, index size, build time, and query cost.

### Exit gate

All three retrieval modes produce comparable, traceable runs on the same corpus. We have a documented decision about whether hybrid search improves relevant-provision retrieval enough to become the default. Semantic infrastructure is not a required default if evidence is weak.

## Phase 6 — Improve ranking and use legislative structure

**Objective:** improve the first page of results without obscuring how they were selected.

### Work

- Measure candidate recall before adding a reranker. A reranker cannot recover a provision missing from its input candidates.
- Add an optional reranker over merged candidates, with configurable input size, timeout, latency budget, and fallback to the prior ranking.
- Compare retrieval with and without reranking. Preserve original retrieval scores, fusion ranks, and reranker outputs in traces.
- Experiment separately with passage length, overlap, parent headings, document-first retrieval, passage-first retrieval, and document/provision grouping.
- Evaluate bounded query expansion for abbreviations and terminology mismatches. Keep the original query and expanded terms visible in debugging; check for changed intent and degraded exact citations.
- Resolve explicit cross-references where reliable identifiers exist. Distinguish a linked reference from a claim that it answers the user's question.
- Prevent repeated overlapping passages from crowding out other relevant instruments. Show additional matches within a document as secondary navigation where useful.
- Introduce an internal comparison view that shows candidate sets, scores, final ranking, and timings side by side.

### Exit gate

Each retained change has a benchmark comparison, understood regressions, and an acceptable latency/cost impact. Held-out performance confirms the chosen configuration after tuning. Disable experiments that do not justify their complexity.

## Phase 7 — Launch the public India beta

**Objective:** make the search engine available with an honest scope and dependable operation.

### Work

- Deploy the selected retrieval configuration at `india.lawindex.live` and choose whether `lawindex.live` is a landing page or entry redirect.
- Refine a responsive search/results/provision interface. Prioritize readable passages, keyboard navigation, filters, useful empty states, and source links.
- Display coverage, excluded categories, source-check times, and available document status/version information. Avoid presenting the corpus as exhaustive or claiming historical applicability without evidence.
- Explain matches using actual highlighted terms or retrieval-method labels. A semantic match should not receive fabricated keyword highlights.
- Establish query and candidate limits, pagination, timeouts, input validation, rate limits, and safe rendering of imported content.
- Run representative load checks and enforce the agreed p95 latency target. Report test corpus size, request load, and cache conditions.
- Add health checks and operational metrics for search errors, latency, index availability, and ingestion failures. Set a deliberate query-log retention policy and keep credentials and unnecessary personal information out of logs.
- Test database/artifact backup restoration, index rebuilds, and rollback to a known good parser/index configuration.
- Publish a concise project/scope description, choose the code license, and document any source reuse constraints before exposing exports.
- Provide a way to report a bad result, incorrect extraction, or broken source link with enough identifiers to investigate.

### Exit gate

Users can complete the full search-to-source path on the live site. Previously agreed quality, coverage, and latency gates pass. There are no known severe source-fidelity issues in launch scope, and deployment rollback and restoration have been exercised. Search works without generation.

## Phase 8 — Keep the corpus current and the service trustworthy

**Objective:** make LawIndex sustainable after its first successful crawl.

### Work

- Schedule discovery and refresh jobs at a source-appropriate cadence. Use hashes and conditional requests where supported to avoid unnecessary work.
- Distinguish newly discovered, changed, unchanged, unavailable, and removed source items. A disappearing page is not evidence that an Act was repealed.
- Keep last attempted and last successful fetch times separate. Establish freshness targets and alerts against successful checks.
- Reparse and reindex changed documents incrementally, retaining snapshots and update lineage. Publish updates coherently so users do not see mismatched text and indexes.
- Monitor parser drift, extraction anomalies, broken source links, inventory changes, and stale indexes.
- Run parser checks and retrieval regression evaluations before material ingestion, model, or ranking changes. Rejudge benchmark items when source changes invalidate them; preserve old benchmark versions.
- Maintain a short recovery runbook and regular backup checks. Inspect operating cost as corpus and traffic grow.
- Turn real search failures into reviewed evaluation cases without casually changing held-out test data or retaining unnecessary user information.

### Exit gate

An automated refresh cycle has completed successfully; a controlled source-change and failed-fetch exercise demonstrate correct update behavior and alerts. Freshness, coverage, and retrieval regression reports are inspectable. Maintenance continues after this milestone.

## Phase 9 — Consider optional answers grounded in retrieved passages

**Objective:** help users synthesize evidence after search itself is demonstrably useful.

**Entry condition:** the search quality gates pass, refreshes are reliable, and observed user needs justify an answer feature.

### Work

- Place generation after retrieval and any reranking. Supply retrieved passages with explicit document and provision identifiers.
- Require source support for every substantive legal claim. A valid citation link alone is insufficient; the cited passage must support the claim.
- Preserve source qualifications, uncertainty, and corpus limitations. If supporting material is inadequate or conflicting, decline to synthesize a definitive answer and show the available evidence.
- Treat imported source text as evidence, not as instructions for the model.
- Evaluate citation correctness, claim support, omitted qualifications, appropriate abstention, latency, and cost using separately reviewed answer cases.
- Keep results prominently accessible and make generation optional and independently disableable. Generation failure must not break search.

### Exit gate

Reviewed answer evaluations meet agreed thresholds and demonstrate appropriate behavior on unsupported and out-of-corpus questions. Disable the feature if it fails these checks. Shipping this phase is not required for LawIndex's search mission.

## Phase 10 — Expand only after the India foundation works

Concrete candidate expansions and known gaps are tracked in the [expansion backlog](docs/EXPANSION_BACKLOG.md). It lists the five ways a query can fall outside the index, with evidence and prerequisites. Expanding past 20 Acts or into associated instruments needs new permission first.

**Objective:** apply a proven system to one justified expansion at a time.

Possible directions include additional official sources for missing central instruments, state legislation, government orders, judgments, a developer API, and other jurisdictions. These are alternatives to prioritize, not a commitment to build them all.

For each proposed expansion:

1. Establish user demand and the gap it addresses.
2. Audit source coverage, structure, update behavior, and reuse conditions.
3. Define corpus boundaries and jurisdiction-specific metadata.
4. Build a small verified slice and a representative benchmark.
5. Confirm quality and maintenance capacity before broad ingestion or public launch.

Use additional subdomains only when an actual corpus needs them. Judgments and historical legal research will require new modeling and evaluation decisions; do not assume they behave like present-source legislation. Public APIs need deliberate versioning, usage limits, and export policies.

## Decisions we should keep explicit

| Decision | Initial direction | Evidence that can change it |
| --- | --- | --- |
| First corpus | Small verified slice of India Code central legislation | Source discovery and extraction quality |
| Initial language | Declare after inspecting the source sample | Availability, parser support, language-specific evaluation |
| Structured storage | PostgreSQL | Demonstrated operational or scale limitation |
| Lexical baseline | PostgreSQL full-text search | Measured need for BM25 or another engine |
| Passage boundaries | Legal structural units first | Recall, context fidelity, and long-provision behavior |
| Vector infrastructure | Prefer a small PostgreSQL-compatible setup | Corpus size, filter behavior, latency, deployment fit |
| Default retrieval | Lexical until another method proves better | Reviewed benchmark and held-out results |
| Numerical release targets | Set after the first credible baseline, before tuning | User needs and observed quality/latency tradeoffs |
| Historical/legal status claims | Only what source evidence supports | Reliable authoritative history and explicit modeling |
| AI answers | Optional, after dependable search | User need and claim-support evaluation |

## Immediate next milestone

**Current handoff, 25 September 2026:** Phase 4 is closed. The user agreed the release targets the same day. The next work is proposed in [docs/phase-5/PLAN.md](docs/phase-5/PLAN.md) and in [docs/HANDOFF.md](docs/HANDOFF.md), and has not started. Lexical search remains the default until a later change meets the adoption rule in [docs/phase-4/TARGETS.md](docs/phase-4/TARGETS.md).

**Earlier handoff, 21 September 2026:** Phase 1's local interface is implemented and browser-verified (see [UI_VERIFICATION.md](docs/phase-1/UI_VERIFICATION.md)) against the completed local data/search API, closing the Phase 1 exit gate for the bounded four-provision slice. A follow-up review ([REVIEW_FOLLOWUP.md](docs/phase-1/REVIEW_FOLLOWUP.md)) found three issues, all now fixed in a bounded correction pass with regression coverage: the section-only query gap in `lawindex/search.py`, the skip-link changing the hash route in `web/`, and a PDF page-footer digit leaking into `rti-2005:8`/`environment-1986:3` body text in `scripts/offline_importer.py` (re-extracted under `offline-importer-v2`, with new review digests disclosed in `data/review/reviewer-remediation-2.json`). All 26 importer checks and 16 API/search tests pass. Phase 1 is closed for this bounded slice.

The bounded Phase 0 offline technical gate is complete for four provisions across two Acts. The user's 20-Act access request remains separately pending; use the [reply-review checklist](docs/phase-0/ACCESS_RESPONSE_CHECKLIST.md) when the response arrives. Phase 2’s bounded offline technical gate is now closed, including reliability, structural migration, schedule layout review, and private viewer verification; see its gate audit for the retained scope limitations. OCR and alternate languages remain excluded. Do not deploy publicly or widen acquisition while the relevant permission is unresolved.
