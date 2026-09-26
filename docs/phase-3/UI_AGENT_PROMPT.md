# Bounded Phase 3 task: metadata filters in the existing search UI

Implement the filter UI against the already-tested Phase 3 backend. Read `docs/phase-3/ARCHITECTURE.md`, `web/index.html`, `web/app.js`, `web/styles.css`, and the current API responses first. Preserve the existing search/detail/coverage flow and visual style; no framework or build system.

Allowed changes: `web/index.html`, `web/app.js`, `web/styles.css`, and a new `docs/phase-3/UI_VERIFICATION.md`. You may add UI startup/usage instructions to README. Do not change `lawindex/`, `scripts/`, `tests/`, `data/`, the permission record, existing reviews or source bytes. Do not run the importer or `--fresh`, acquire corpus data, publish, or mark Phase 3 complete. Report backend defects with exact repros instead of fixing across this boundary.

## Deliver

Add labelled native selects for Act, Act year, ministry, and document type. Populate Act values/titles from `/api/corpus`'s `acts`; other choices come from `filter_options`. Omit empty filters from API requests. “All” means no constraint. Explain that choices cover only currently searchable provisions, not the proposed 20-Act inventory. Do not create fictional counts or show unreviewed Acts as searchable.

Use `URLSearchParams` for query construction. Persist query and all selected filters in the existing hash route. Direct reload, back/forward navigation and returning from a provision must restore both query and filters. A filter-only submission is supported by the backend; an empty query with no filters must retain the existing empty-search experience. Provide a clear/reset action. Do not silently drop an unknown filter from a bookmarked route and then show broader results: retain it as an unavailable selection with a way to clear it, or explicitly explain the invalid value without running a broadened search.

Display nullable metadata with readable labels. The source's Act year is not a commencement date. Null is “Not recorded,” not zero or another inferred value. `document_type` is ACT, not the source's subject category. Keep links, warnings, conflicts, footnotes, exact `<mark>` segments and source-PDF navigation working. Never use extracted text as `innerHTML`.

Use the actual corpus notice and render the permission code `personal_noncommercial_20_acts_user_reported` in plain language: “Ministry permission reported for up to 20 Acts for this personal, non-commercial project.” Do not say we have indexed 20 Acts or verified the original email. The active searchable corpus is still four provisions.

Retain race protection: stale search responses and stale corpus-option loads must not overwrite a newer route or filter state. Preserve selected route filters when corpus options refresh. Support 400/503/network failure with clean recovery, keyboard operation, visible focus, and narrow/mobile layouts. No full redesign or new analytics.

## Verification and report

Run `python3 -m unittest discover -s tests -q`, `python3 scripts/verify_offline_import.py`, and `python3 scripts/evaluate_search.py`. These must not modify the real database. Test in a real browser against `python3 -m lawindex.server`, bound to loopback.

Check: year 2005 yields only RTI; Act=Environment plus query “RTI section 6” yields no results; filters intersect; filter-only browsing works; reset restores the empty-search state; bookmarked unknown values are not silently broadened; selection survives detail/back and reload; ministry values are correctly URL-encoded; disabled/unavailable corpus data never generates invented choices; old responses cannot replace current results; 400/503/network states recover; keyboard and mobile layout remain usable. Check existing RTI §8 conflict/footnote and Environment §5A source link.

Write `UI_VERIFICATION.md` with actual commands, outcomes, browser checks, limitations and any defects. Do not claim checks you did not perform. Finish with changed files, reproduction commands and unresolved issues. The main agent will inspect your implementation before accepting the handoff.
