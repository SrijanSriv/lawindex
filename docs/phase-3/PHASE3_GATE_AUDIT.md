# Phase 3 gate audit — 23 September 2026

**Closed, 23 September 2026.** The user accepted the recommendation and moved to Phase 4. Phase 3 is closed with one recorded exception: seed query P0-010 ranks its unjudged target fifth. It is carried into the Phase 4 judged benchmark, where ranking changes must be shown on held-out judged queries rather than tuned against this smoke set.

**Verdict (re-audit, end of 23 September 2026): every exit criterion is met except one retrieval-smoke case.** The user agreed the coverage and latency targets. Both blocking gaps are fixed: uncovered queries now carry notices, and one long Act can no longer dominate a generic query. The one miss is seed query P0-010, which ranks its target fifth; the recommendation is below. Closure is the user's decision; see [Re-audit](#re-audit--23-september-2026) at the end. The first-pass findings follow as they were recorded.

**First-pass verdict: Phase 3 gate not yet closed.** The corpus and review work is complete and verified. Three items stand between it and a usable internal alpha:

1. The coverage and latency targets have not been agreed. That decision belongs to the user.
2. Queries outside the corpus return plausible-looking noise with no warning that they are not covered.
3. One long Act can dominate results for queries that name no Act, which the roadmap explicitly asks to prevent.

None of these is a fidelity problem. No known text corruption is served.

This audit uses the exit gate and work list in [PHASES.md](../../PHASES.md). It does not approve public deployment, commercial use, legal-expert accuracy, schedules or associated instruments in search, or legally current consolidated text.

## Exit gate, with evidence

| Exit criterion | Evidence | Status |
| --- | --- | --- |
| Every item in the declared manifest has an explicit outcome | All 20 inventory Acts are captured and in the corpus manifest. All 1,923 source-listed sections have a recorded outcome: 1,503 aligned and admitted, and 420 quarantined, each with a reason. `rti-2005:8` is quarantined as a candidate but stays admitted through its earlier individual PDF-extracted review, which gives 1,504 searchable. Kerala and RTI Rules keep their quarantine-fixture outcomes. Schedules and associated instruments are not enumerated per Act (see N1). | **Pass at section level** |
| Agreed coverage targets pass | 1,504 / 1,923 source sections searchable (78.2%), ranging by Act from 29% (Competition) to 100% (Repealing and Amending). No target has been agreed; the roadmap asked for targets to be frozen after measurement. | **Open (B3): user decision** |
| Sample extraction audits pass | Deterministic risk-weighted plans for all 20 Acts: 366 sections compared whole against rendered PDF pages, **0 discrepancies**, and every Act batch admitted. The sample covers every normalization stratum an Act uses and every length band, weighted toward risk: 16% of sections under 300 characters sampled, 24% at 300–1,000, 31% at 1,000–3,000 and 43% over 3,000. With zero discrepancies in 366, the rule of three puts the 95% upper bound on the per-section discrepancy rate at about 0.8%. That bound applies within the sampled strata; unsampled sections are lower-risk by construction, since no footnote or page-break skip is involved. | **Pass** |
| No known severe text-corruption issue remains hidden | Known representation conflicts (Copyright s.6, IT s.12 and others) are quarantined and absent from search. Merchant Shipping ss.191 and 197, which carry corrigenda, are quarantined. RTI-001 is shown to users as a source conflict. The remaining surprise is Education ss.21, 24 and 29: the source prints Rajasthan state-amendment text inside these central sections, faithfully reproduced but not flagged in the UI (see N3). That is not corruption, but a reader could misread it. | **Pass, with N3 disclosure gap** |
| Seed-query report, navigation, filters and coverage statement support a useful internal alpha | Seed queries (below): of 18 in-scope text queries, 15 rank the target section first, 17 in the top 3, and none miss the top 10. Source-linked navigation, metadata filters and the coverage page work at full scale in the browser. But out-of-scope and uncovered queries get no "not covered" signal (B1), and one long Act can take most of the top 10 (B2). | **Not yet (B1, B2)** |

## Roadmap work checklist

| Phase 3 work item | Status |
| --- | --- |
| Discovery manifest with discovered, fetched, parsed, indexed, excluded and failed counts against the declared inventory | Done for sections: `/api/inventory`, the coverage page and `report_phase3_coverage.py` show per-Act captured, exact/typographic candidates, quarantined with reasons, and live searchable counts. Schedules and associated instruments are not counted (N1). |
| Ingest in batches and audit samples across document types and lengths | Done: 20 Act batches, each gated by its own sampled review. See the length bands above. |
| Associated instruments only where justified; keep missing ones visible | None added, which is correct. Visibility is partial: a limitation note covers other-language PDFs, but rules and regulations are not reported per Act (N1). |
| Lexical retrieval for titles, Act numbers, years, sections, phrases and mixed topics | Done: title, alias and cited-title matching, `Act N of YYYY`, year citations including title-year mismatches, section lookup, and stemmed phrase constraints. The cited-title fix (no fallback to another Act of the same year) is recorded in ARCHITECTURE.md. |
| Metadata filters; missing metadata never a known category | Done: year, ministry and document type. Nulls never match a concrete filter. Options come from the live admitted corpus. |
| Excerpts with context retaining qualifications; identify heading matches | Excerpts report their sub-section and proviso from the provision's own markers. Heading-caused ranking is **not** identified separately (N2). |
| Chapter/section navigation, schedules, surrounding context, stable deep links; group passages; stop one long Act overwhelming results | Previous/next navigation within admitted sections, stable `#/provisions/<key>` links, and PDF page anchors are done. One provision is one passage, so grouping holds trivially. Schedules are excluded from search (Phase 2 decision). **Per-Act domination is not prevented (B2).** |
| Retriever boundary: query, filters, candidate limit, scored candidates, trace | Done (`lawindex/retrieval.py`). |
| Measure end-to-end latency; document failure categories | Latency measured at 1,504 provisions: validation 165 ms and search 22 ms median per request. Failure categories are documented below. No latency target has been agreed (B3). |

## Seed-query report

The smoke set is unjudged: 24 seed queries from Phase 0 and 6 development queries. It is not a retrieval benchmark (that is Phase 4). Ranks were taken on the full 1,504-provision corpus; a hint such as "6(2)" counts as a hit on section 6.

| Category | Queries | Result |
| --- | --- | --- |
| Exact title, section lookup, Act citation | P0-001, 002, 007, 019 | All rank 1 |
| Topic, terminology, ordinary language, acronym, title terms | P0-003 to 005, 008 to 017 | 11 rank 1; P0-003 and P0-009 rank 2; P0-010 rank 5 |
| Source conflict (RTI s.8(1)(j)) | P0-006 | Rank 1, with the RTI-001 conflict shown |
| Schedule discovery (Repealing and Amending) | P0-018 | Rank 1, because the enactments are listed in the sections |
| Schedule lookup (RTI First Schedule oath) | P0-020 | No hit; schedules are not in search, and nothing tells the user |
| Deferred instrument (RTI Rules fee) | P0-021 | No hit; returns RTI Act sections with no "rules not covered" notice |
| Partial coverage (environmental clearance) | P0-022 | Environment Act at rank 3 |
| Other jurisdiction, other document type | P0-023, P0-024 | 269 and 445 unrelated results; no "not covered" notice |

Development queries: DEV-001 and DEV-003 to DEV-006 rank 1. **DEV-002 has dropped to rank 2** on the full corpus, behind RTI s.9. The unit test pins the legacy four-provision fixture, so it does not catch this (N4).

**Failure categories observed:** a *coverage miss* (schedules, rules, other jurisdictions, case law) presented as if answerable, which is the most important for alpha usability; *ranking displacement* by a related section of the same Act (DEV-002, P0-009, P0-010); and *single-Act concentration* on generic queries (B2). No *bad extraction* was found in the served text, and the *query parsing* fault found (the cited-title fallback) is fixed.

## Findings

### Blocking the gate

- **B1. No "not covered" signal.** Queries about schedules, rules, other jurisdictions or judgments return confident-looking lexical matches. Minimum fix: a persistent scope statement beside every result list (the 20 Acts; sections only; no schedules, rules, case law or state law), plus a specific notice when the query names something outside that scope.
- **B2. A long Act can dominate.** Examples: Merchant Shipping takes 7 of the top 10 for "definitions" and 6 of 10 for "power to make rules". Fix: when a query names no Act, cap each Act's share of the returned page, then fill in rank order. `total` and the trace must still report every match.
- **B3. Coverage and latency targets not agreed.** This is the user's decision. Proposal below.

### Non-blocking, to fix or record

- **N1.** The coverage report does not enumerate schedules or associated instruments per Act.
- **N2.** Ranking caused by a heading match is not identified separately in results or trace.
- **N3.** Education ss.21, 24 and 29 carry Rajasthan state-amendment text in their bodies with no UI note.
- **N4.** DEV-002 is rank 2 on the full corpus. The dev-query test should also run on the live corpus, reporting ranks rather than pinning a four-provision fixture.
- **N5. Correction.** The Education review notes and earlier docs said five sections carry state-amendment text (ss.8, 16, 21, 24, 29). Only ss.21, 24 and 29 are admitted; ss.8 and 16 are quarantined. The Education review plan is digest-bound to its admissions, so it is left unchanged and corrected here.
- **N6.** Per-request validation costs 165 ms locally. A public deployment would need a validated persistent index built once per import (recorded in ARCHITECTURE.md).

## Proposed targets for agreement (B3)

Measured values are in brackets.

- **Coverage:** every section of every inventory Act has an explicit, visible outcome [met: 1,923 / 1,923]. At least 75% of source-listed sections searchable overall [78.2%]. Any Act below 50% shows its quarantine reasons prominently on the coverage page [Competition 29%, Copyright 39%, IT 42%]. The alternative is a hard per-Act floor, such as 50%. That would require resolving the HTML/PDF conflicts in those three Acts, probably by reviewed PDF-only extraction, which is substantial work.
- **Fidelity:** zero discrepancies in each Act's sampled review [met: 0 of 366].
- **Latency:** loopback search request p95 under 500 ms at the current corpus size [validation 165 ms plus search 22 ms, median].
- **Retrieval smoke:** every in-scope seed query has its target in the top 3 [17 of 18: P0-010 is rank 5], and every out-of-scope seed query shows a "not covered" notice [0 of 4].

## Verification run

Final code, quiet tree, 23 September 2026:

- `python3 -m unittest discover -s tests -q`: **213 tests pass** (188 s).
- `python3 scripts/verify_offline_import.py`: **all 28 checks pass**, including sampled-admission binding and zero silent exclusions.
- `python3 scripts/verify_phase0.py`: passes; the 16 original Phase 0 capture hashes are unchanged.
- `Snapshot`: 1,504 served, 0 excluded, 20 Acts; 372 individually compared, 1,132 under their Act's sample.
- `python3 scripts/evaluate_search.py`: 5 of 6 development queries rank 1 and DEV-002 ranks 2 (N4).
- Database `integrity_check` ok; foreign-key check clean.
- Browser check at full scale: search, "not individually reviewed" badges, Act filter (20 Acts), coverage page (live counts sum to 1,504), no console errors.

## Handoffs

The UI and coverage-UI handoffs were accepted earlier at the four-provision scale ([UI_VERIFICATION](UI_VERIFICATION.md), [COVERAGE_UI_VERIFICATION](COVERAGE_UI_VERIFICATION.md)). They were re-inspected in the browser at 1,504 provisions for this audit. No other handoffs are outstanding. All fidelity reviews in Phase 3 were done by an AI agent and are disclosed as such; none is independent legal-expert review.

## Re-audit — 23 September 2026

The user accepted the proposed targets and asked for B1 and B2 to be fixed.

### B1 fixed: uncovered queries are named

Every search response now carries a `scope` statement: the provision and Act counts, and what is never included (schedules, rules and regulations, state laws, court judgments, held-back sections). The page shows it beside every result list. It also carries `notices`, shown above the results; notices never hide results. Coverage is not only about the 20-Act limit, so each way a query can reach outside the index has its own notice:

| Notice | When |
| --- | --- |
| `act_not_indexed` | A cited Act title matches no indexed Act |
| `schedules_not_indexed` | The query mentions a schedule |
| `instruments_not_indexed` | The query cites rules or regulations ("RTI Rules", "rules, 2012") |
| `case_law_not_indexed` | The query mentions judgments, case law, precedents or rulings |
| `state_law_not_indexed` | The query names a state or union territory |
| `weak_match` | Even the best result holds fewer than half the query's words (question words ignored, an Act's own aliases credited, light suffix stemming) |

On the seed set, none of the 19 queries whose answer is in the index gets a notice, and all 5 that reach outside it do (P0-020 to P0-024). P0-006 is answered at rank 1 with its source conflict shown, so it correctly has no notice.

### B2 fixed: one Act no longer takes over a generic query

When a query names no Act, no single Act may take more than `max(2, ⌈0.3 × limit⌉)` places on the page (3 of 10), counting only *competitive* results: those scoring at least 60% of the best. A focused question keeps its Act's strong results; "seafarer wages abandoned" still returns ten Merchant Shipping sections, not weak matches from other Acts. `total` still counts every match. The page offers the close matches the cap held back as a search within that Act ("More close matches in: The Merchant Shipping Act, 2025 (5)"). The trace records `diversity.per_act_cap`, `diversity.applied` (true only when the cap changed the page) and the competitive share.

Examples: "power to make rules" went from 6 of 10 Merchant Shipping to at most 3 of 10 across 6 Acts; "appeal against order", 3 of 10 across 7 Acts. "definitions" still shows 6 of 10 from Merchant Shipping, because only 16 sections match at all and 7 of those are Merchant Shipping definitions sections.

A first version capped every result regardless of score. That let weak matches from other Acts displace strong Merchant Shipping results for the seafarer query, so it was replaced by the competitive-score version before review.

### B3: agreed targets, measured

| Target (agreed) | Measured | Result |
| --- | --- | --- |
| Every section of every inventory Act has an explicit, visible outcome | 1,923 / 1,923 | **Met** |
| At least 75% of source-listed sections searchable overall | 78.2% (1,504 / 1,923) | **Met** |
| Acts under 50% searchable show their quarantine reasons prominently | Competition (29%), Copyright (39%) and IT (42%) are flagged on the coverage page with the reasons open; other Acts keep them collapsed | **Met** |
| Zero discrepancies in each Act's sampled review | 0 of 366 | **Met** |
| Search request p95 under 500 ms at current size | 249 ms end to end (50 loopback requests; median 195 ms): `measure_search_latency.py --http` | **Met** |
| Every in-scope seed query has its target in the top 3 | 17 of 18 | **Not met: P0-010** |
| Every out-of-scope seed query shows a "not covered" notice | 5 of 5 | **Met** |

**P0-010** ("consent for processing digital personal data", unjudged target DPDP s.6 "Consent.") ranks s.6 fifth. Ahead of it are DPDP ss.4 (grounds for processing), 9 (children's data), 11 (right to access information) and 5 (notice), all sections about consent-based processing in the right Act. Tuning the ranker to move one unjudged smoke query would be overfitting to the development set, which the Phase 4 plan exists to prevent.

**Recommendation:** close the gate with P0-010 as a recorded exception, carried into the Phase 4 judged benchmark ([expansion backlog](../EXPANSION_BACKLOG.md) item 2.1). The alternative is to keep the gate open until ranking work, measured on judged queries, moves it.

### Other first-pass items

N1 (schedules and instruments on the coverage page), N2 (heading-match identification), N3 (the state-amendment note), N4 (live-corpus dev-query report) and N6 (a persistent index before public use) are carried in the [expansion backlog](../EXPANSION_BACKLOG.md), along with the five coverage gaps. N5 (the state-amendment count) is corrected in the docs.

### Verification after the fixes

- `python3 -m unittest discover -s tests -q`: **223 tests pass**, including 10 new tests in `tests/test_coverage_signals.py`.
- `python3 scripts/verify_offline_import.py`: **all 28 checks pass**.
- `python3 scripts/verify_phase0.py`: passes.
- Database `integrity_check` ok; foreign keys clean; 1,504 current versions.
- Browser: out-of-scope notices and the scope statement render above results. The "More close matches" link opens that Act's search (103 results, no cap inside a named Act). The coverage page flags exactly the three Acts under 50%. No console errors.
