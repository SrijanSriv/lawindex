# Phase 1 UI verification

Status: browser interface implemented in `web/index.html`, `web/app.js`, `web/styles.css` against the fixed [API contract](API_CONTRACT.md). Verified in the built-in Claude Code browser pane (a real Chromium-based browser, not a headless assertion run) on 21 September 2026. This is a manual verification record, not an automated test suite.

**Update, 21 September 2026 (later the same day):** a follow-up review ([REVIEW_FOLLOWUP.md](REVIEW_FOLLOWUP.md)) found three issues in the pass recorded below, plus a low-contrast badge noted separately. All four are now fixed — see [Remediation (2026-09-21)](#remediation-2026-09-21) at the end of this document. The original pass below is left unmodified as historical evidence of what was checked and found at the time.

## Startup used for verification

```sh
python3 -m unittest discover -s tests -v      # 15 tests, all pass
python3 scripts/evaluate_search.py            # smoke run, all 6 dev queries rank first
python3 -m lawindex.server                    # http://127.0.0.1:8000/
```

`data/import/lawindex_offline.sqlite3` already existed from a prior offline import, so `scripts/offline_importer.py --fresh` was not rerun for this pass.

## What was tested and the actual result

| Check | Result |
| --- | --- |
| Load `/` fresh | Loads `index.html`/`app.js`/`styles.css` over the same origin; no console errors. |
| Search view initial render | Heading, purpose text, labelled query input, submit button, idle hint, and a live coverage banner (`4 provisions currently available across 2 Acts`) all render from `/api/corpus`. |
| Query submission via mouse | Typing "exemption" and clicking **Search** updates the hash to `#/?q=exemption` and renders 1 result (RTI s.8) with a `<mark>`-highlighted excerpt built from `excerpt.segments`, an omission ellipsis, a "Source conflict recorded" badge, and a "Has footnote" badge. |
| Query submission via keyboard (Enter) | Confirmed the search `<form>` submits on Enter inside the text field (verified by dispatching a real keystroke through `type`, which the browser tool's synthetic `key: Return`/`Enter` action does **not** reliably deliver as a native keydown in this pane — see Limitations). Hash updated to `#/?q=section 6` and the app re-rendered correctly. |
| Multi-term highlighting | Query "green tribunal" against Environment s.5A highlights both "Green" and "Tribunal" as separate non-adjacent `<mark>` spans, matching the `segments` array exactly — no `innerHTML` used anywhere (confirmed by reading the rendered `<mark>` node's `outerHTML`, which contains only the plain matched word). |
| No-match empty state | Query "nonexistentqueryxyz" shows "No matches among the 4 currently available provision(s) for…" with a link to Coverage — no error styling. |
| RTI section 8 — conflict + footnote | Direct route `#/provisions/rti-2005%3A8` (including a cold reload, see below) renders the RTI-001 conflict prominently in a labelled, non-hidden box above the body text, the full body text with original clause markers, indentation and the `[(j) …]` amendment bracket preserved, and the footnote in its own separate "Footnote" section — not merged into the body and not hidden in a generic footer. |
| Environment s.5A — clause markers | `#/provisions/environment-1986%3A5A` renders the leading `1\n     [5A. Appeal to National Green Tribunal.—…]` amendment bracket and its footnote exactly as returned by the API, with newlines preserved via a `white-space: pre-wrap` block fed by `textContent`. |
| Source verification | Both provisions' Source section links to the same-origin `local_pdf_url` (`/api/sources/<key>.pdf#page=N`, confirmed served as `application/pdf`, 200 OK, correct byte size), a full-PDF download link, the original India Code Act and PDF-viewer links, and the "Source PDF — only listed provisions reviewed." label plus the full-PDF caveat sentence from the contract. `fetched_at` and `source_stated_modified_date` are shown in the collapsed developer panel with the contract's exact labels, not as an inferred legal date. |
| Coverage navigation | `#/coverage` lists both Acts and all 4 provisions read live from `/api/corpus` (no hard-coded UI catalogue), states the partial-coverage notice, `excluded_since_import_count`, and `public_use_permission: pending`, and links back to Search. |
| Direct-route reload | Loading `#/provisions/rti-2005%3A8` as a fresh navigation (not a client-side transition) renders the full page correctly — hash routing survives a cold load. |
| Back-navigation preserving query | A search-result link to a provision carries `?q=<query>` in its hash; the provision page's "← Back to search" link returns to `#/?q=<query>`, restoring the original query. |
| Mobile viewport (375×812) | Search, results, and Coverage views reflow to a single column, the search button becomes full-width, and body text remains readable without horizontal scrolling. |
| Dark mode | The pane's OS-level dark color scheme was active throughout testing; the `prefers-color-scheme: dark` palette in `styles.css` rendered correctly with adequate contrast — this was incidental coverage, not a separate manual toggle. |
| 404 / withdrawn provision | `#/provisions/rti-2005%3A99` (never-admitted key) clears the view and shows "Provision not found… may have been withdrawn…" with a link to Coverage. No stale text is left behind. |
| 503 / data unavailable (search) | Temporarily moved `data/import/lawindex_offline.sqlite3` aside while a search was in flight. The results region cleared and showed "The local database or required evidence is currently unavailable." with a **Retry** button; the coverage banner simultaneously switched to its unavailable variant. Restoring the file and clicking **Retry** re-ran the search and produced normal results again. |
| 503 / data unavailable (provision, focus-triggered refetch) | Loaded Environment s.5A successfully, then moved the database file aside and dispatched a `focus` event (simulating the tab regaining focus) without any navigation. The previously-rendered full provision text was cleared and replaced by the unavailable state — confirming the contract's "clear displayed content when validation fails" and "refetch on focus" requirements are both honored, not just refetch-on-navigate. Restoring the database and clicking Retry brought the full provision back. |
| Network failure (server stopped) | Stopped `lawindex.server` entirely and reloaded a search route from the browser's cached shell. Both the coverage banner and the search results region showed a "Could not reach the local server" state with Retry, instead of leaving prior content looking current. Restarting the server and clicking Retry recovered fully. |
| 400 / invalid query | Forced a >500-character query via the hash (bypassing the input's `maxlength`) and confirmed the API's `invalid_query` message ("Query must contain at most 500 characters.") is displayed and the query text remains in the editable input field. |
| Stale-request race | Fired two hash changes in rapid succession (`q=environment` then `q=exemption`, ~10ms apart) via script; only the later query's single result was rendered, confirming the sequence-number guard discards the earlier in-flight response. |
| Console errors | No uncaught JavaScript exceptions were logged at any point. The only console entries were the browser's own network-status log lines for the 400/404/503/connection-refused responses that were deliberately triggered above — expected side effects of testing error handling, not application bugs. |

## A backend behavior discovered during this verification (not modified)

Per the interface task's boundary, backend code, ranking, and admission rules were not touched. While testing query submission I found and want to flag a reproducible gap in the backend's explicit-section-reference handling:

- `GET /api/search?q=section%206` (or `q=s.%206`) returns **zero results**, even though `rti-2005:6` is currently admitted and is exactly the provision that reference names.
- Cause (from reading `lawindex/search.py`, not modified): `query_terms()` strips the word "section" as a stopword, leaving the bare digit `"6"` as the only search term. That term is used both as (a) the required FTS5 `MATCH` expression and (b) the input to the section-number filter. RTI section 6's admitted `body_text` (see `GET /api/provisions/rti-2005%3A6`) begins `"(1) A person, who desires…"` — it does not contain the literal numeral `6` anywhere the FTS index tokenizes — so the FTS candidate set is already empty before the section filter is applied, and the fallback for an empty-candidates-with-no-terms case (`if not candidates and not terms`) never triggers because `terms` is non-empty (`["6"]`).
- This does not reproduce for Environment (Protection) Act sections 3 and 5A, only because their reviewed body text happens to start with `"3. Power of…"` / `"…[5A. Appeal…"` — i.e. it is a data-shape coincidence, not a property of the matching logic. `q=RTI%20section%206` (which adds the `rti` alias term) does work, so an explicit-section query only fails when it has no other lexical term to anchor a false-seeming "match".
- No workaround was added in the UI for this — the UI displays exactly what `/api/search` returns (a correct, contract-compliant empty state for a 0-result response). Fixing it would mean changing `lawindex/search.py`'s query-term/section-filter interaction, which is out of this task's boundary.

## Limitations of this verification

- Verification was manual, exploratory browser testing in one browser engine (the Claude Code built-in pane, Chromium-based) at two viewport sizes. It is not a cross-browser (Safari/Firefox) or automated regression suite.
- The browser pane's synthetic `key` action for `Return`/`Enter` did not reliably dispatch a native keydown recognized by the page (confirmed via an instrumented listener: `e.key` came back as an empty string). This is a tool limitation, not a UI defect — real character input via `type` (including a literal newline) did trigger the form's native submit-on-Enter behavior correctly, and screen readers/real keyboards send proper key events.
- Full keyboard-only navigation was exercised for the search form and route links; a complete screen-reader pass (e.g. with VoiceOver/NVDA) was not performed.
- The 400/503/network-failure states were exercised through direct hash manipulation and a temporarily-moved database file, not through dedicated test fixtures, per the task's instruction not to mutate original evidence — no reviewed data files were altered, and the database file was restored immediately after each check (backend regression tests were rerun afterward and still pass: 15/15).
- No visual design review beyond basic contrast/readability was performed (no accessibility scanner, no automated Lighthouse/axe run).

## Acceptance

All Phase 1 UI acceptance checks named in [UI_AGENT_PROMPT.md](UI_AGENT_PROMPT.md) — query submission, keyboard use, narrow viewport, no-matches, direct-route reload, back navigation, RTI s.8 conflict/footnote, Environment s.5A, verified PDF page links, delayed/failed responses, and withdrawn-provision behavior — passed as described above. Phase 1 status in [PHASES.md](../../PHASES.md) has been updated accordingly, without altering later-phase scope.

## Remediation (2026-09-21)

A follow-up review ([REVIEW_FOLLOWUP.md](REVIEW_FOLLOWUP.md)) found three issues in the pass above, plus a separately-reported low-contrast badge. All four are fixed, with regression coverage added, and rechecked in the browser below.

### 1. Section-only search (`lawindex/search.py`)

**Finding:** `q=section 6` (and `q=s. 6`) returned zero results for the admitted `rti-2005:6`, while `q=RTI section 6` worked. Root cause: the bare digit left after stripping the word "section" was used both to detect the section reference *and* as a required FTS5 lexical match term — but `rti-2005:6`'s reviewed body text never repeats its own section number (`"(1) A person, who desires..."`), unlike `rti-2005:8` (`"8. Exemption..."`), so the two behaved inconsistently for reasons unrelated to the query's actual intent.

**Fix:** `Snapshot.search()` now separates a detected section reference from the remaining "topic" terms. When no topic terms remain (a pure section-only query), the candidate set is resolved directly from provision metadata (`section_number`, plus any Act filter), independent of body text. When topic terms remain (e.g. `"RTI section 6"` → topic term `"rti"`), lexical matching proceeds as before and the section reference still narrows the result set afterward as a hard constraint, never a substitution.

**Regression coverage:** `tests/test_search.py::test_section_only_lookup_uses_metadata_independent_of_body_text` — covers `section 6`, `s. 6`, `section 5A`, `s. 3`, an Act-qualified reference to a section that belongs to a *different* Act (`EPA section 6` → no results, no fallback to `rti-2005:6`), an unavailable section number with and without an Act qualifier, and asserts the trace's `match_expression` is empty for a pure section-only query so the trace stays honest about what was actually matched lexically.

**Rechecked in browser:** `#/?q=section%206` now renders "1 result for 'section 6'" with the RTI section 6 excerpt, confirmed via the live API (`/api/search?q=section%206` → `rti-2005:6`) and the browser pane.

### 2. Skip link changing the route (`web/index.html`, `web/app.js`)

**Finding:** the "Skip to main content" link used `href="#main"`. Because the app treats every hash change as a route, activating it was handled by the router (which does not recognize `main` as a route) and rendered "Page not found" instead of moving focus.

**Fix:** `<main>` now has `tabindex="-1"` so it is a valid programmatic focus target, and `web/app.js` attaches a `click` handler to the skip link that calls `event.preventDefault()` and `mainEl.focus()` directly — the hash is never touched, so no `hashchange` fires and the router never runs. Added a `main:focus-visible` outline rule to `web/styles.css` so the jump is visually confirmable.

**Rechecked in browser:** focused the skip link (it becomes visible on focus, per its existing CSS) from both the search route (`#/`) and a provision route (`#/provisions/rti-2005%3A8`), clicked it, and confirmed in both cases `window.location.hash` was unchanged and `document.activeElement` became `<main>`. No automated test covers this (it is DOM/focus behavior, not covered by the Python test suite); it was rechecked manually in the same browser pane used for the original verification pass.

### 3. PDF page-footer digit inside admitted body text (`scripts/offline_importer.py`)

**Finding:** RTI section 8's admitted body text contained a standalone `10` between clause (i) and its continuation proviso; Environment section 3's contained a standalone `4` inside the sub-section (2) enumerated list. Both are the retained PDF's own printed page-number footer (confirmed against `data/discovery/derived/rti-2005-page-10.png` and `-environment-1986-page-04.png`), which `pdftotext -layout` renders as a lone, heavily right-indented digit line at the very end of each page. Both affected provisions span a page boundary (RTI s.8: pages 10–11; Environment s.3: pages 4–5), so the donor page's trailing footer digit landed in the middle of the joined body text. `environment-1986:5A` (single page, body ends before the page's footer) and `rti-2005:6` (structured-HTML representation, not PDF-extracted) were unaffected.

**Fix:** added `scripts/offline_importer.py:strip_page_footers()`, applied to each PDF's per-page text immediately after `pdftotext_layout()` and before pages are joined. It removes a page's trailing line only when that line is digits-only **and** textually equal to the page's own 1-based position in the extracted PDF — an exact, verifiable identity a real in-body number (such as RTI section 8's own amendment-marker digit `1` before `[(j) information which relates to personal information;]`, which is never the last line of a page) will not coincidentally share. Bumped `EXTRACTION_METHOD_VERSION` from `offline-importer-v1` to `offline-importer-v2` so this behavior change is versioned, not silent (per the existing safeguard in `docs/phase-0/INSPECTION_FOLLOWUP.md` Finding 1). Updated all four review records' `extraction_method_version` field accordingly, and re-established `expected_output` digests for the two affected provisions (`rti-2005:8`, `environment-1986:3`) after re-running the fixed extraction against the same retained source bytes and re-checking the corrected text against the same page renders those records already cite. The other two provisions' digests are unchanged (confirmed byte-identical, not merely assumed). Full disclosure, root cause, and before/after digests: `data/review/reviewer-remediation-2.json`.

**Regression coverage:** `scripts/verify_offline_import.py::check_pdf_page_footers_stripped_not_legal_digits` (new, 26th check) — unit-level coverage of `strip_page_footers()` against engineered fixtures (a true footer, a standalone marker digit that is *not* the page's own footer, and a trailing digit that doesn't match the page's position), plus an end-to-end check against the real admitted database confirming no residual footer line in `rti-2005:8`/`environment-1986:3` and that RTI section 8's amendment marker survives unchanged.

**Rechecked:** re-ran `python3 scripts/offline_importer.py --fresh`, `python3 scripts/verify_offline_import.py` (26/26 pass), `python3 -m unittest discover -s tests -v` (16/16 pass, including the new section-lookup test), and `python3 scripts/evaluate_search.py` (all 6 dev queries still rank first). In the browser, loaded `#/provisions/rti-2005%3A8` and confirmed via `get_page_text` that "other officers:" is immediately followed by the "Provided that the decisions of Council of Ministers..." proviso with no intervening `10`, and that the `1\n[(j) information which relates to personal information;]` amendment marker is intact.

### 4. "Has footnote" badge low contrast (`web/styles.css`)

**Finding:** `.badge--footnote` used a hardcoded light background (`#eef1e8`) with no explicit text color, so it inherited the ambient (theme-dependent) text color. In dark mode this put near-white text on a near-white background, making the badge effectively unreadable — unlike `.badge--conflict`, which already used theme-aware CSS custom properties.

**Fix:** added a theme-aware `--color-info-bg`/`--color-info-border` token pair (light and dark variants, alongside the existing warning/danger tokens) and pointed `.badge--footnote` at them with an explicit `color: var(--color-text)`, matching the pattern already used for the conflict badge.

**Rechecked in browser:** confirmed the badge renders with clear, readable contrast in both the pane's dark color scheme (its default) and with `prefers-color-scheme: light` forced via `resize_window`.

### Full regression status after remediation

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -v` | 16/16 pass (15 original + 1 new) |
| `python3 scripts/verify_offline_import.py` | 26/26 pass (25 original + 1 new) |
| `python3 scripts/evaluate_search.py` | 6/6 dev queries rank expected provision first |
| Browser recheck of all three functional fixes + the badge | Confirmed in the same built-in browser pane used for the original pass |

No backend defect remains open from this review cycle. The manual-verification limitations noted in the original pass above (single browser engine, no automated UI regression suite, no full screen-reader pass) still apply to this remediation's browser rechecks.
