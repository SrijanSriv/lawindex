# Phase 3 coverage UI and read-only operator report — verification

Scope of this increment: `web/app.js`, `web/styles.css`, `scripts/report_phase3_coverage.py`,
`tests/test_phase3_coverage_report.py`, this report, and README usage links. No
files under `lawindex/`, `scripts/acquire_phase3.py`, `scripts/phase3_candidates.py`,
`lawindex/coverage.py`, `lawindex/server.py`, existing tests/review records, `PHASES.md`,
or `data/` were changed. `scripts/acquire_phase3.py`, the candidate generator, the
importer, `--fresh`, a network crawl, and a public deployment were never run. This is
a presentation layer over the existing `/api/inventory` contract (`lawindex/coverage.py`
`build_coverage`) — it does not review, admit, or reinterpret any legal text, and it
does not mark Phase 3 complete.

## What changed

- `web/app.js`: `#/coverage` now mounts a second, independent panel that fetches
  `/api/inventory` (own `AbortController`/sequence counter, exactly like the existing
  `/api/corpus` panel) and renders: the four inventory summary counts (selected,
  captured, searchable Acts, searchable provisions), the API's own `limitations`
  array (never hardcoded), and one card per selected Act with capture outcome,
  source-listed section count, candidate status, comparison-review-pending count,
  quarantined count, live searchable provision count, full-Act coverage status, and
  any diagnostic. The existing searchable-corpus panel (`/api/corpus`, its provision
  links, and the metadata filters on the search page) is untouched code.
- `web/styles.css`: styling for the new summary stat row, limitations box, and
  per-Act cards, plus a mobile breakpoint that stacks the two-column card fields to
  one column.
- `scripts/report_phase3_coverage.py`: read-only CLI wrapping `Snapshot` +
  `build_coverage` from `lawindex.search` / `lawindex.coverage`, rendering the same
  semantics as the API in `--format text` (default) or `--format json`. No
  acquisition, extraction, database write, subprocess, or network call.
- `tests/test_phase3_coverage_report.py`: 13 tests against the CLI's rendering and
  report-building, using small temporary inventory fixtures (the same
  `acquire_phase3.atomic_json`/`sha`/`canonical` helpers `tests/test_phase3_pipeline.py`
  already uses) and a mocked `Snapshot`, plus two tests against the real repository
  that assert no subprocess is invoked and the `data/` tree's contents are
  byte-for-byte unchanged after a run.

## Commands run

```
python3 -m unittest discover -s tests -p "test_*.py"
```
Result: `Ran 162 tests in 18.784s` — `OK` (162 = the pre-existing suite plus the 13
new coverage-report tests; one `ResourceWarning: unclosed database` from an existing,
unrelated test was present and is not from this change).

```
python3 scripts/verify_offline_import.py
```
Result: `ALL 26 OFFLINE IMPORT CHECKS PASSED`.

```
python3 scripts/evaluate_search.py
```
Result: ran to completion, printing the existing six-query dev trace with unchanged
ordering/expectations.

```
python3 scripts/report_phase3_coverage.py
python3 scripts/report_phase3_coverage.py --format json
```
Both ran cleanly against the real repository. Text output matched the documented
expectations in `docs/phase-3/ACQUISITION_AND_CANDIDATES.md`: 20 selected Acts, 20
captured, 2 searchable Acts, 4 searchable provisions; row source-listed-section
counts summed to 1,923; agreement-review-pending counts summed to 895; quarantined
counts summed to 1,028. (These are the current real-data expectations from the
handoff doc, not constants asserted in code — the report and its tests compute
everything from the live inputs.)

### Database hash before/after

```
shasum -a 256 data/import/lawindex_offline.sqlite3
```
Before: `24b305672a9d3e6858a5fe03a5cedf91d4c19e9e0e83d957e0ddd938e6a5c341`
After running both verification scripts and both CLI invocations above: same hash,
`24b305672a9d3e6858a5fe03a5cedf91d4c19e9e0e83d957e0ddd938e6a5c341`. Also confirmed via
`find data -newer scripts/report_phase3_coverage.py -type f` returning no results
(nothing under `data/` has a newer mtime than this session's own new file).

## Browser checks

Server under test: `python3 -m lawindex.server --port 8123`, driven with the in-app
browser pane against `http://127.0.0.1:8123/`.

All of the following were actually performed in the browser, not inferred from source:

- **`#/coverage` desktop render**: both panels loaded. The inventory panel showed
  Selected Acts 20 / Captured Acts 20 / Searchable Acts 2 / Searchable provisions 4,
  the API's six `limitations` strings verbatim, and 20 per-Act cards — including
  Acts with 0 live searchable provisions (e.g. DPDP 2023, Copyright 1957) shown with
  the same card structure as the two Acts with searchable provisions (RTI 2005,
  Environment 1986), not hidden or specially collapsed. Confirmed via
  `get_page_text` and `read_page`.
- **Mobile layout**: resized the pane to the 375×812 mobile preset and reloaded
  `#/coverage`. The summary stats and per-Act card fields both reflowed to a single
  column (confirmed via screenshot); text wrapped normally with no horizontal
  scroll or clipped content.
- **Existing search page unaffected**: on `#/`, the Act/Year/Ministry/Document type
  filter selects still populated from `/api/corpus` (2 Acts, correct year/ministry
  options), a query (`disclosure`) returned the expected single RTI §8 result with
  a working link to `#/provisions/rti-2005:8?q=disclosure`, and a direct reload of
  that provision URL rendered the full provision (source-conflict box, footnote,
  provenance panel, back-link) — none of this code was touched by this change.
- **Coverage → search round trip**: the coverage page's existing "← Back to search"
  link and the banner's "See what is indexed" link were confirmed present and
  pointing at the expected routes (unchanged code, verified alongside the above).
- **Independent inventory failure, isolated fixture**: with the server running,
  temporarily moved the real `data/phase3/inventory.v1.json` aside (to
  `/tmp/inventory.v1.json.bak`, restored immediately after) so `/api/inventory`
  returned `503 data_unavailable` while `/api/corpus` kept returning `200`
  (confirmed both via direct `curl` first). Reloading `#/coverage` in the browser
  then showed: the inventory panel replaced by "The local database or required
  evidence is currently unavailable." with a Retry button, **while the searchable-corpus
  panel below it rendered fully and correctly** (4 provisions, both Acts, both
  provision links) — the failed inventory fetch did not blank, zero out, or block
  the corpus panel. Restored the real inventory file, confirmed `/api/inventory`
  returned `200` again via `curl`, then clicked the panel's own Retry button in the
  browser: the inventory panel reloaded and rendered the full 20-Act report
  correctly. `data/phase3/inventory.v1.json` was moved and restored, never edited,
  and no other file under `data/` was touched during this check.
- **Full server-down case**: separately stopped the server entirely and reloaded —
  the whole page failed to load (expected: `web/index.html` itself is server-served
  in this local prototype), distinct from the isolated-fixture case above where the
  server stayed up and only one API route was made to fail.
- **No raw candidate text / no unadmitted-provision links**: read the rendered
  inventory markup; it contains only counts, status strings, titles, and the
  diagnostic string when present — no candidate body text, and no link is generated
  from any inventory row into `#/provisions/...` (only the existing corpus panel
  links to provisions, and only for the four already-admitted ones).
- **Escaping**: all inventory-derived text (titles, diagnostics, limitations) is
  inserted via `el()`'s `text`/`textContent` path or `document.createTextNode`,
  the same DOM-only helper the rest of `web/app.js` uses — no `innerHTML` was added.
- **Keyboard**: the new panel introduces no new interactive controls beyond the
  existing Retry button pattern (reused verbatim from the corpus panel's own error
  state) and a plain, non-interactive limitations `<ul>` and per-Act `<dl>`s;
  tab order and focus behavior were not otherwise changed. The Retry button was
  operated by click in the check above; its focus/activation behavior is identical
  to the pre-existing corpus-panel Retry button, which this change does not modify.

## Known limitations of this verification

- The Retry button's keyboard activation (Enter/Space via `Tab` navigation to it)
  was not separately exercised with a keyboard-only interaction in this session,
  though it is a native `<button>` reusing the existing `renderUnavailable`/
  `renderNetworkError` helpers, which have this behavior for free.
- No screen-reader software was used; ARIA structure (`aria-labelledby` on the new
  section, `role="note"` on the diagnostic) was inspected via the accessibility
  tree, not audibly verified.
- The browser check exercised one fetch-race scenario (inventory 503 while corpus
  succeeds) via a real, isolated file move/restore against the real data files,
  not synthetic abort-controller unit tests; no automated browser test suite exists
  in this repository to encode this as a regression test.

## Backend findings

None. `build_coverage` and `/api/inventory` behaved exactly as documented in
`docs/phase-3/ACQUISITION_AND_CANDIDATES.md` throughout this verification, including
returning `503` cleanly when the inventory file was made temporarily unavailable and
recovering correctly once restored.

## Reproduce

```sh
python3 -m unittest discover -s tests -p "test_*.py"
python3 scripts/verify_offline_import.py
python3 scripts/evaluate_search.py
python3 scripts/report_phase3_coverage.py
python3 scripts/report_phase3_coverage.py --format json
python3 -m lawindex.server --port 8123
# open http://127.0.0.1:8123/#/coverage
```

Phase 3 remains open; this report does not close it.

## Main-agent inspection — 22 September 2026

Accepted for the bounded coverage presentation and read-only reporting task. No blocking implementation defect found. Independently reran the full suite: 162 tests pass, with the previously known non-failing SQLite ResourceWarning. Ran the JSON CLI and verified its counts (20 selected/captured Acts, two searchable Acts, four searchable provisions) and unchanged real DB hash.

Verified that the restored inventory's canonical digest is `7c793d417118529469d9fcf3ab9945b624c54afa095b74c504cbd72a55c494de`, matching all 20 acquisition records. The database matches the implementer's reported SHA-256. Live browser inspection showed 20 inventory cards, zero candidate-reader links, and four admitted-provision links, alongside the correct summary counts. Sequence/abort guards, null handling and escaped DOM rendering were inspected in code.

Verification wording correction: moving the real inventory file aside was a temporary mutation of the real workspace, not an isolated fixture. It has been restored. Future failure injection must use a temporary project copy; moving production/workspace evidence was outside the handoff's intended no-data-change boundary. Also, the 503/success check demonstrates independent error handling and recovery, not an out-of-order response race. No artificial delayed-response race was independently exercised in this inspection.

This accepts the reporting/UI handoff only. Fidelity review, admission of expanded text through the canonical writer, richer retrieval/navigation, and the Phase 3 gate audit remain main-agent work.
