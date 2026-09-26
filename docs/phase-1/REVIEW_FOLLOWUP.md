# Phase 1 follow-up review

Reviewed 21 September 2026. Implementation was inspected without modifying source, review baselines, backend, or UI. Ran all 15 backend tests successfully. Used a separate local server on port 8011 for focused browser checks. This was not a repeat of the entire mobile/error-state verification matrix.

## Findings to close before moving on

### 1. Explicit section-only lookup misses admitted provisions

Reproduced directly against `Snapshot.search`:

```text
section 6 -> []
s. 6 -> []
RTI section 6 -> [rti-2005:6]
```

`lawindex/search.py:215–236` sends the section label into full-text retrieval before applying the section filter. RTI section 6's body lacks the label token, so the candidate disappears. This is the backend defect correctly reported by the UI agent and originates in the backend handoff.

Fix structured reference lookup so section-only requests use provision metadata independently of whether labels appear in body text. Define behavior for remaining topic words explicitly. Preserve Act constraints and return no substitute for absent sections. Test `section 6`, `s. 6`, Act-qualified references, lettered sections, and unavailable references; keep accurate trace output.

### 2. Skip link is interpreted as an application route

The skip link in `web/index.html` targets `#main`. Activating it with Enter in the browser changed the page to **Page not found**. `web/app.js:95–104` treats `main` as an unknown route.

Keep the skip action separate from hash routing: move keyboard focus to a focusable main region without replacing the application route. Verify the search query/provision route remains unchanged and Tab continues into the main content.

### 3. PDF page footers remain inside admitted legal text

The RTI section 8 page visibly includes a standalone `10` between clause (i) and its continuation proviso. Inspection of retained `data/discovery/derived/rti-2005-page-10.png` confirms this is the PDF footer. The admitted Environment section 3 text likewise contains a standalone `4` at the page break; review its source page when fixing extraction.

The importer joins page text and removes page separators without distinguishing page footers (`scripts/offline_importer.py:130–145`). The UI correctly displays the admitted body; it did not introduce this problem. Previous successful digest checks preserved the reviewed output, including this missed artifact.

Fix at extraction/review level, with page-specific evidence and retained source mapping. Do not broadly strip numeric lines: RTI section 8 also contains an isolated amendment marker `1` that must survive. Preserve original files and prior review history, version the extraction change, inspect corrected passages and footnotes, and explicitly establish new reviewed output digests. Never merely adjust expected hashes to make a test pass.

## Confirmed strengths and limitations

- All 15 existing backend tests still pass; they do not cover the section-only lookup failure.
- Ordinary RTI section 8 search returns the expected result with exact-segment highlighting and conflict/footnote badges.
- Direct provision navigation renders the full admitted text, separate footnote, prominent RTI conflict, source links, and provenance details.
- UI rendering uses text nodes rather than upstream HTML. Search/view requests use cancellation and per-view sequence checks.
- The six development queries are covered by the passing backend smoke test; this is not general retrieval evaluation.
- The previous UI verification is manual, not an automated browser regression suite. Keep that distinction, and add focused regression coverage for the bugs found here.

## Recommended next step

Complete a small Phase 1 correction pass for these three findings, rerun importer/backend checks, and repeat the affected browser flows. Preserve the original UI verification as historical evidence and append the remediation results. Then close the local Phase 1 milestone.

Next, begin Phase 2 ingestion reliability over retained fixtures: generalizable boundaries/structure, resumable failure handling, and clear per-item outcomes. Keep new source acquisition dependent on permission. Do not add embeddings, generated answers, or widen the corpus merely to move past these correctness issues.
