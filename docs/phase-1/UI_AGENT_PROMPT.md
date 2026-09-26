# Prompt for the interface agent

Work in `/Users/srijansrivastava/randoms/lawindex`. Implement the local Phase 1 interface against the backend already built. Complete the UI, browser checks, and startup documentation. Do not redesign the backend or ingestion pipeline.

Read `IDEA.md`, `docs/phase-0/README.md`, `docs/phase-1/ARCHITECTURE.md`, and **`docs/phase-1/API_CONTRACT.md`** first. The contract is the implementation boundary. Inspect actual API responses before writing the interface.

## Fixed decisions

- Python/SQLite backend is implemented and tested. Use it unchanged.
- Browser JavaScript and CSS in `web/index.html`, `web/app.js`, and `web/styles.css`; no framework, Node build, CDN, or new service.
- Same-origin JSON API and hash routing. Start with `python3 -m lawindex.server`.
- Four reviewed provisions across two Acts, with dynamic coverage read from the API. No corpus expansion, source fetching, messages, public deployment, analytics, generated answers, or semantic search.

## Build

1. **Search view:** product name, concise purpose, query input and submit button, current partial-corpus notice, accessible loading/error/empty states, and results using API titles, section labels, exact excerpts, and omission markers.
2. **Provision view:** Act title, section heading, full text preserving newlines and clause markers, separate footnotes, conflict notices, reviewed-source labels, and source links. Display no invented hierarchy, adjacent provisions, legal interpretation, or current-law claims.
3. **Coverage navigation:** list the actually available provisions from `/api/corpus`; explain that whole Acts are not indexed. Link back to search without losing the query where practical.
4. **Source verification:** use the supplied local PDF/page link and original India Code links. Explain that the source PDF contains material beyond the reviewed slice. Show source dates with their exact meaning from the contract.
5. **Optional developer details:** collapsed query trace/provenance panel. Keep scores and hashes out of the main reading flow.

Use semantic HTML, labels, visible focus states, keyboard navigation, readable legal text, and responsive layout. Make it feel like a restrained search/documentation product. Do not turn long provisions into decorative cards or truncate the full text. No image generation or icon package is needed.

## Correctness requirements

- Use `textContent`/text nodes for all API text. Use API excerpt segments with `<mark>` for highlighting. Never render upstream text through `innerHTML`.
- Every result/provision must show applicable source-conflict information. Do not hide RTI section 8's conflict behind a generic footer.
- Fetch current data on navigation and focus restoration. No service worker or persisted source-text cache. A withdrawn provision returning 404 must clear old detail text. Errors/503 must not leave old content looking current.
- Prevent stale request races with cancellation or a sequence check.
- Respect external-file script/style CSP; do not weaken server headers.
- Keep UI routing separate from API routing. Build keys/links from API data; do not hard-code the four provisions into the UI.

## Boundaries

Edit `web/` and UI-specific documentation/tests. Add frontend-only files where needed, but do not modify `lawindex/`, `scripts/offline_importer.py`, reviewed evidence, admission rules, expected text digests, ranking, or existing backend tests. If an actual backend defect blocks you, report a precise reproduction; do not silently work around it by duplicating backend logic in the browser.

## Verification

Run the backend regression checks with `python3 -m unittest discover -s tests -v` and the development search run with `python3 scripts/evaluate_search.py`. If no generated database exists, use the documented offline import commands first.

Start the application and inspect it in a browser. Test query submission, keyboard use, a narrow viewport, no matches, direct hash-route reload, back navigation, RTI section 8 conflict and footnote display, Environment section 5A, and the verified PDF page links. Test delayed/failed responses and withdrawn-provision behavior using temporary fixtures or mocked network responses; never mutate original evidence just to exercise the UI. Check for console errors. If browser tooling is unavailable, state the limitation explicitly.

Do not claim broad relevance quality from six development questions. Do not mark Phase 1 complete until the browser flow has actually been verified. Preserve the pending source-access condition separately.

Update the root README with the working UI URL/startup steps. Add `docs/phase-1/UI_VERIFICATION.md` recording what was tested, actual results, and limitations. If all acceptance checks pass, update Phase 1 status accurately in `PHASES.md` without altering later scope.

Proceed autonomously. Finish with the files changed, exact startup commands, verification results, and any remaining issue. Do not deploy.
