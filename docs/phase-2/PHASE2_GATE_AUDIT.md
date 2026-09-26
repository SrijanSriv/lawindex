# Phase 2 gate audit — 21 September 2026

**Verdict: bounded offline Phase 2 technical gate closed, 21 September 2026. Independent schedule layout review, private viewer verification, and the final main-agent audit pass within the scope below.**

This audit concerns the bounded offline corpus established in Phases 0–1. It does not approve acquisition, public deployment, full-Act coverage, generic legal parsing, or legally current consolidated text. The four reviewed sections remain the searchable corpus; the 19 Environment Act child ranges remain contextual only. The new schedule models are private, non-search-admitted review artifacts.

## Exit criteria, with evidence

| Original exit criterion | Current evidence | Status |
| --- | --- | --- |
| Two identical imports have identical canonical output and no duplicates | Existing idempotence regressions; immutable structural-history tests; fresh full import and verified resume exercised on the real DB, with all five compatibility tables unchanged | Pass |
| An interrupted run resumes | Persistent interruption/reopen tests; only committed successes are skipped; pending/failed work re-runs | Pass |
| A source-change fixture creates a traceable update | Source-hash history, changed-source invalidation, new-reviewed-source version tests; prior snapshots/reviews remain immutable | Pass |
| Extraction failures are visible and do not become searchable text | Failure isolation, job/attempt states, revoked current versions, expected-digest checks, missing-data behavior, read-only reports, and search admission tests | Pass |
| Representative clauses survive parsing correctly | Environment Act section 3: 19 exact nested ranges, full clause (iv) proviso and subsection (3) continuation retained; boundaries visually reviewed against retained pages 4–5 | Pass within stated profile |
| Representative schedules survive parsing correctly | Positive positioned-word model of RTI pages 23–24; every word accounted for; alternatives, brackets, omissions, and footnote links explicit; 10 focused tests pass | Pass for the reviewed fixture and verified private viewer |
| Source links remain usable and source-bound | Existing search/PDF endpoint tests; exact schedule capture/hash/page references and word coordinates; original PDF required as visual reference | Pass for search and private viewer |

Schedule acceptance is backed by a separate AI review, not merely implementation-generated expected hashes.

## Roadmap work checklist

| Phase 2 work item | What is demonstrated / what remains outside this slice |
| --- | --- |
| Restartable stages | Retained captures separate acquisition from extraction; versioned extraction, normalization, structural storage, admission, and derived passages commit per item. Whole-item reprocessing is deliberate; there is no separate persisted job for every internal function. |
| Concurrency, timeout, retry, cache, queue | One cooperating writer is the concurrency bound; extraction timeouts and explicit retries are tested. `--resume` validates full dependencies and stored outputs. Network concurrency/backoff is not exercised because new acquisition remains outside permitted scope. |
| Idempotence | Canonical rows and immutable history reuse tested; attempt history intentionally grows on actual reprocessing, not on skips. |
| Separate documents/snapshots/provisions/passages | Structural migration, foreign keys, versioned rows, parent relationships, aliases, exact passage slices, private content-addressed source copies. |
| Associated instruments | Schema requires separate documents and evidenced relationships; synthetic constraint tests pass. No positive RTI Rules import is claimed: its scanned text remains excluded. |
| Exact source versus normalized search | Reviewed display text and footnotes are retained separately; FTS is derived. Schedule representation preserves words/positions instead of inventing linear prose. |
| Versioned parsers and retained artifacts | Parser versions/configuration and review digests are bound; changed output fails closed. Local snapshots suffice to reparse without a crawl. |
| Renumbering/identity | Existing public aliases are retained and cannot be reassigned by ordinary upsert. Automatic identity reconciliation is unsupported; uncertain new versions require explicit review. Contextual child identity is scoped to a root version, not inferred across renumbering. |
| Quarantine | Known disagreements, missing/changed sources, wrong digests, OCR, and unsafe plain-text schedule splitting stay excluded. The current schedule representation has a digest-bound independent AI review and never auto-admits into search; changed baselines require a new review. |
| Source status/dates | Existing conflict records and scope flags preserved; no inference of historical legal effect or public reuse rights from capture metadata. |
| Difficult fixtures / OCR decision | Real nested clauses, amendment markers, oath alternatives, and numbered footnotes are covered. OCR is still deliberately excluded. Generic tables/multilingual parsing remain future expansion work. |

These are explicit limitations, not claims that network ingestion or arbitrary legal documents have been validated. Phase 3 expands coverage; Phase 5 adds vector experiments; production hosting/migration remain separate work. The pending India Code reply governs any permitted acquisition/use beyond the retained offline fixtures.

## Verification run

- `python3 -m unittest discover -s tests -q`: **110 tests pass**. The suite emitted one non-failing SQLite `ResourceWarning`; this is not an assertion failure or evidence that source/DB bytes changed.
- `python3 scripts/verify_offline_import.py`: **26 checks pass**.
- `python3 scripts/verify_phase0.py`: **16 original capture hashes unchanged**, existing reports/manifest/query fixtures pass.
- `python3 scripts/evaluate_search.py`: **6 development queries pass**, still a smoke set rather than a retrieval benchmark.
- `python3 scripts/report_structure.py --format json`: current four roots and 19 contextual children reported successfully.
- `python3 scripts/schedule_layout.py`: deterministic candidate emitted with `needs_independent_review`, `search_admitted=false`.
- Full import followed by `--resume`: four roots admitted, four skipped on resume, no new attempts on the skipped run, all five compatibility tables unchanged, foreign-key check clean. No `--fresh` reset.

## Handoffs and closure

The separate review agent completed the digest-bound source review. The implementation agent delivered the private viewer; the main agent inspected it, corrected presentation defects, verified the browser behavior, and reran the gate checks. Both handoffs are complete. The reviewed model/profile/source/parser and independent acceptance record are unchanged by the viewer corrections.

The gate is closed only for the bounded offline technical slice. Schedule search admission, broader source acquisition, public release, generic parsing, network ingestion, and legal-expert review are not enabled by closure.

## Independent review follow-up — 21 September 2026

The separate AI reviewer accepted artifact `a111a35d9a490fe6a2f789c41e21648c4a4e565333db0d7d153fdbe671544288`, bound to the retained PDF, profile, parser version, and pages 23–24. The main agent reproduced `python3 scripts/schedule_layout.py --review data/review/structure/rti-schedule-independent-review.json`: exit 0, `layout_reviewed_not_search_admitted`, `search_admitted=false`. This verifies the current binding; it is not another independent visual review or legal-expert certification.

The seven advisory observations are non-blocking. Carry O1 (graphical details need the original PDF) and O5 (note 6's affected span includes superscript 7) into viewer verification. O2 confirms that some semantic mistakes are caught by the reviewed baseline hash, so changing that baseline requires renewed independent review. O3 remains a disclosed validation limitation: the acceptance helper checks reviewer identity and declared independence, but does not enforce the `type` and `independent_legal_expert` fields. The actual accepted record supplies both and explicitly discloses an AI, non-legal-expert review; do not infer credentials from the acceptance status. O4 and O6 limit the parser to the reviewed fixture and compatible extraction layout; O7 concerns private artifact file permissions only.

No parser, profile, accepted review, source, or database was changed in this follow-up. The earlier full-suite results above remain historical verification results, not a claim of a new full-suite run. At this intermediate follow-up the viewer handoff and final audit were still pending; they are completed below.

## Final viewer audit and closure — 21 September 2026

The main agent found and fixed two fidelity defects in the delivered viewer: footnote highlighting expanded exact affected-word ranges to whole containing entries (notably note 3 / `[Frontier]`), and the unnumbered omitted block was presented after entry 27 rather than between 21 and 22. Three new regression tests cover exact highlighting (including note 6 covering marker 7), omission order, and honest reviewer disclosure. The viewer also removes an incorrect “competent authorities” heading and duplicate automatic serial numbers, presents the oath alternatives between separate shared-context blocks, and uses an explicit readable light palette.

Rebuilt with the real independent review: `layout_reviewed_not_search_admitted`, `search_admitted=false`. Browser verification used a temporary loopback-only server serving only the generated viewer directory. Both PNGs loaded, the accepted banner and AI/non-expert disclosure appeared, note 3 highlighted only its marker/`[Frontier]`/footnote without shading the containing entry, and keyboard activation of note 6 included marker 7 and toggled cleanly off. Both PDF page links were correct and the copied PDF was byte-identical. No full accessibility audit is claimed.

Final checks: **132 unit tests pass**, **26 importer checks pass**, Phase 0 verification passes with **16 original hashes**, and all **6 development queries rank their expected provision first**. The structure report returns four roots and 19 contextual children. The unit suite still emits the previously noted non-failing SQLite resource warning. Database, retained PDF, layout profile, and independent review hashes are unchanged across this audit; no real import or `--fresh` reset was run. Earlier full-import/resume evidence and current interruption/history/idempotence tests cover the ingestion criteria.

No blocking Phase 2 finding remains within the declared scope. The India Code access decision is still a separate dependency for expanding acquisition/use. The four reviewed root sections remain the searchable corpus; schedule artifacts remain private and excluded from search.
