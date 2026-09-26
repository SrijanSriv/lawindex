# Phase 3 UI verification — metadata filters

Scope of this increment: `web/index.html`, `web/app.js`, `web/styles.css`, and this
report. No files under `lawindex/`, `scripts/`, `tests/`, `data/` were changed; the
importer was never run and no `--fresh` reset was performed. Phase 3 is not being
marked complete by this report.

## Commands run

```bash
python3 -m unittest discover -s tests -q
```
Result: `Ran 139 tests in 14.610s` — `OK`.

```bash
python3 scripts/verify_offline_import.py
```
Result: `ALL 26 OFFLINE IMPORT CHECKS PASSED`.

```bash
python3 scripts/evaluate_search.py
```
Result: ran to completion, printing the existing dev-query trace output (six smoke
queries, unchanged expectations/ordering). Neither script wrote to the real database;
both are read-only against the existing `data/import/lawindex_offline.sqlite3`
snapshot (confirmed by reading their source before running them).

None of the three commands touch `web/`, so they only confirm the backend the UI
was built against is unchanged and still passing — they do not exercise the UI
itself. The UI was exercised separately in a real browser (below).

## Browser checks

Server under test: `python3 -m lawindex.server --port 8791`, bound to
`127.0.0.1` only (the server itself enforces this via its `Host` check). Driven with
the in-app browser pane against `http://127.0.0.1:8791/`.

All of the following were actually performed, not just read from source:

- **Filter population**: `/api/corpus` loaded and the Act/Year/Ministry/Document type
  selects populated correctly — Act options from `corpus.acts` (slug → title),
  the other three from `corpus.filter_options`. Confirmed via the accessibility tree.
- **`year=2005` filter-only search** (`#/?year=2005`, no query): returned exactly the
  two RTI provisions (section 6 and section 8), nothing from Environment. Confirmed
  via rendered page text.
- **`act=environment-1986` + `q=RTI section 6`**: returned zero results (the act
  filter and the query's inferred Act conflict, per `lawindex/retrieval.py`'s
  intersection semantics) — confirmed as "No matches among the 4 currently available
  provision(s)".
- **Filter intersection / filter-only browsing**: exercised generally through the
  above and through combined `q` + `ministry` searches (see result-link check below).
- **Unknown filter values are not silently dropped/broadened**: navigated to
  `#/?act=fake-act&ministry=Nope`. Both selects kept the bookmarked value selected,
  labelled "(not currently searchable)", with an inline warning per field and a
  "Clear <field>" button. The search still ran (not silently widened) and correctly
  returned zero results. Clicking "Clear Act" removed only that filter (`#/?ministry=Nope`
  afterwards), leaving the ministry warning in place — confirmed via
  `window.location.hash` and re-read of the page.
- **Malformed value case**: `#/?year=05` (fails the backend's exactly-four-digits
  rule) — the select still kept "05" selected with the same unavailable-value warning,
  and the search request surfaced the backend's actual 400 message ("year must contain
  exactly four ASCII digits.") instead of a broadened or invented result set.
- **Reset**: "Clear all" from a populated search reset the query input, all four
  selects, and navigated to `#/`, reproducing the original empty-search idle message
  ("Enter a query above, choose filters, or browse the current coverage list.").
- **Reload / direct navigation restores query + filters**: `#/?year=1986` was loaded
  via `location.reload()` (a genuine full document reload, not an SPA transition).
  **This surfaced a real defect during verification** (see "Defect found and fixed"
  below); after the fix, reload correctly restored the Year=1986 selection and reran
  the filter-only search, returning the two Environment provisions.
- **Back/forward**: navigated `#/` → `#/?year=2005` → browser back; the hash and
  rendered view correctly returned to `#/`.
- **Ministry values are correctly URL-encoded**: a result link for a search with
  `ministry=Ministry of Personnel, Public Grievances and Pensions` rendered as
  `#/provisions/rti-2005%3A8?q=exemption&ministry=Ministry+of+Personnel%2C+Public+Grievances+and+Pensions`
  — confirmed via `find`, i.e. produced by `URLSearchParams`, not hand-built.
- **Provision detail / back-link preservation**: opened
  `#/provisions/rti-2005%3A8?q=exemption&ministry=...` directly; the "← Back to
  search" link's `href` exactly reproduced `#/?q=exemption&ministry=...` (read from
  the DOM, not assumed).
- **RTI §8 conflict + footnote**: confirmed still rendered — "Source conflict" box
  with `RTI-001 — substantive_text (selected_with_disclosed_conflict)` and its
  explanation, plus the footnote box with the amendment text. Metadata line
  ("Act year: 2005 (the source's recorded year — not a commencement date). Ministry:
  ...  Document type: ACT.") also rendered on the same page.
- **Environment §5A source link**: confirmed the Source PDF link resolves to
  `/api/sources/environment-1986%3A5A.pdf#page=5`, matching the admitted anchor.
- **Coverage view / permission plain language**: `#/coverage` renders the real
  `corpus.notice` string, the real `provision_count`/act list, and the permission
  line as "Ministry permission reported for up to 20 Acts for this personal,
  non-commercial project." — not the raw code
  `personal_noncommercial_20_acts_user_reported`, and without claiming 20 Acts are
  indexed or that the ministry email was verified. Each Act section also shows its
  metadata line (year/ministry/document type, "Not recorded" where null — not
  observed in this corpus since both Acts have all three fields populated).
- **`<mark>` segments / no `innerHTML`**: confirmed via `document.querySelectorAll('.result-excerpt mark')`
  that the match highlighting still renders as real `<mark>` elements with the exact
  matched text as `textContent`. Also confirmed by `grep -n innerHTML web/app.js` that
  the string appears nowhere except in a comment — all DOM construction goes through
  the existing `el()`/`textContent` helper, including the new metadata lines and
  filter-warning text.
- **Network failure recovery**: stopped the server, submitted a search — got the
  existing "Could not reach the local server." panel with a Retry button; restarted
  the server and clicked Retry — the search then completed successfully.
- **503 (data unavailable) path**: not exercised end-to-end in the browser this
  session, because doing so would require making `data/` or the database
  unavailable, which is outside this task's allowed changes. The code path itself
  (`error.status === 503` → `renderUnavailable`) is unchanged from the
  already-shipped implementation and was not touched by this increment except to
  thread `filters` through the retry closure.
- **Keyboard / focus**: added `select` to the existing `:focus-visible` outline rule
  (previously only `a`/`button`/`input`/`main`), so the four new filter selects get
  the same visible focus ring as the rest of the form. Not walked with a physical
  keyboard tab sequence this session; native `<label for>`/`<select>` pairing and
  the existing tab order (input → selects → Search → Clear all) were used, which
  are standard, keyboard-operable controls.
- **Mobile layout**: emulated a 375×812 viewport. The filter row stacks to one
  column, selects are full width, "Search"/"Clear all" stack and go full width, and
  there is no horizontal overflow. Screenshots taken at the top of the form and
  scrolled to the filters/buttons.

## Defect found and fixed (in this increment, before handoff)

**Symptom**: on a genuine hard reload (`location.reload()`) of a URL like
`#/?year=1986`, the page incorrectly fell back to the empty-search idle state
instead of restoring the Year filter and re-running the search.

**Cause**: `renderSearchView` computed whether to auto-run a search by reading the
`<select>` elements' *current* values after calling `refreshOptions(initialFilters)`.
`refreshOptions` originally returned immediately if `latestCorpus` was not yet
loaded (`if (!latestCorpus) return;`), which is normal right after a hard reload,
since `/api/corpus` is fetched asynchronously and has not resolved yet. That left
every select at "All", so `currentFilters()` read back all-empty values, and the
view showed the idle message and never searched.

**Fix**: `refreshOptions` no longer bails out when `latestCorpus` is unset — it
falls back to empty option lists per field so the route's filter values are still
applied to each select (marked as a temporary "not currently searchable" option
until the real corpus data arrives and reconciles them). Separately, the
run-search-or-show-idle decision on mount now reads directly from the parsed route
(`initialQuery`/`initialFilters`) instead of reading it back out of the DOM, so it
is correct regardless of `/api/corpus` timing. Verified by reproducing the failure,
applying the fix, and reloading again — now Year=1986 restores correctly and the
select shows a clean "1986" option (no leftover "not currently searchable" tag)
once `/api/corpus` resolves.

## Changed files

- [web/index.html](../../web/index.html) — footer text updated to remove the stale
  "permission... pending" claim (contradicted by the corpus notice/permission
  record) and link to Coverage instead.
- [web/app.js](../../web/app.js) — added the four filter `<select>`s, route/query
  persistence via `URLSearchParams`, unknown-filter retention with per-field clear,
  a "Clear all" reset, readable metadata lines (with "Not recorded" for null and an
  explicit "not a commencement date" note on Act year), plain-language permission
  rendering, and preserved race protection (`searchSeq`/`AbortController` for search,
  the existing corpus-fetch abort pattern extended to also refresh filter options
  without disturbing the active route).
- [web/styles.css](../../web/styles.css) — styles for the filter row/fields, filter
  hint/warning text, reset button, and metadata line; added `select` to the
  `:focus-visible` rule; added a mobile (`max-width: 30rem`) stacking rule for the
  new filter controls.
- `docs/phase-3/UI_VERIFICATION.md` — this report.

## Reproduction commands

```bash
python3 -m unittest discover -s tests -q
python3 scripts/verify_offline_import.py
python3 scripts/evaluate_search.py
python3 -m lawindex.server --port 8791
# then open http://127.0.0.1:8791/ in a browser and exercise the routes listed above,
# e.g. http://127.0.0.1:8791/#/?year=2005 or http://127.0.0.1:8791/#/coverage
```

## Limitations / unresolved issues

- The 503 (`data_unavailable`) UI path was not exercised live this session (see
  above) — only read-verified against the unchanged existing code. If it needs a
  live check, it requires making the database or evidence unavailable, which is
  outside this task's allowed changes and should be done deliberately, separately,
  and restored afterward.
- Keyboard operation was verified structurally (native controls, correct
  `label for`/`id` pairing, `:focus-visible` extended to `select`) but not walked
  with an actual physical Tab-key sequence in this session.
- No backend defects were found. The backend's documented behavior (empty query +
  filter browses in key order; unknown filter values match nothing rather than
  erroring; malformed `year` is a 400) all matched what was observed.

## Main-agent handoff inspection — 22 September 2026

Accepted for the bounded metadata-filter task. Inspected route parsing, initial filter restoration before corpus options load, unknown-value retention, query serialization, response sequence/abort guards, metadata display, and text-only rendering. No blocking defect found in this increment.

Independently reran the full unit suite: 139 tests pass. Browser checks against the real loopback API reproduced a full reload of `#/?year=1986`, with the year restored and both Environment provisions returned. A keyboard Tab action from Act year moved focus to Ministry. Clear all returned to the idle state. A bookmarked `year=05` stayed constrained and displayed the backend's 400 diagnostic.

Also tested the previously unexercised 503 screen using a temporary project copy containing only `web/`, with no database or evidence, served on a separate loopback port. The page showed coverage unavailable and the data-unavailable Retry panel while retaining the year constraint. No real source or database file was moved or edited. This check verifies the failure screen, not a newly performed end-to-end 503 recovery test. Request-race protection was code-inspected; no artificial delayed-response race was injected during this inspection. This remains a bounded manual check, not a full accessibility audit.

Phase 3 itself remains open. The next main-agent work is source identity resolution, bounded acquisition and coverage reconciliation, followed by candidate extraction and independent batch review. The UI handoff requires no further agent edits at this point.
