# Interface implementation boundary

The interface is not implemented yet. Build `index.html`, `app.js`, and `styles.css`
here using browser JavaScript and CSS; no framework or Node build step is required.
The existing Python server serves these files and the API on the same origin.

Read [the API contract](../docs/phase-1/API_CONTRACT.md) and
[the interface task](../docs/phase-1/UI_AGENT_PROMPT.md) before working.

Use hash routes (`/#/provisions/rti-2005%3A6`) so navigation needs no server changes.
Use external scripts/styles, text nodes for API strings, and API-supplied excerpt
segments for highlighting. No inline script/style or CDN dependencies. Source PDFs
are available through the API; do not copy source artifacts into this directory.
