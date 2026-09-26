# Local API contract — v1

Backend ready; frontend pending. Read [architecture and commands](ARCHITECTURE.md) first. Run `python3 -m lawindex.server` from the project root, then use `http://127.0.0.1:8000`. The `--port` option changes the local port. There is no authentication, CORS integration, CDN, or public hosting in this local prototype.

All data routes are GET-only and return JSON unless the route explicitly returns PDF. Errors have the shape `{"error":{"code":"not_found","message":"..."}}`. Response strings are **plain text, never trusted HTML**. All responses use `Cache-Control: no-store`.

## Endpoints

| GET route | Response | Frontend responsibility |
| --- | --- | --- |
| `/api/health` | `{status:"ok", scope:"local development"}` | Process liveness only; not a corpus-readiness guarantee |
| `/api/corpus` | Corpus object below | Coverage banner and list of available provisions |
| `/api/search?q=...&limit=10` | `{query, results, total, corpus, trace}` | Render results or a bounded-corpus empty state |
| `/api/provisions/{encoded-key}` | `{provision, corpus}` | Render exact text, notes, notices and source links |
| `/api/sources/{encoded-key}.pdf` | Hash-verified PDF bytes for that currently admitted provision | Open the API-supplied source URL; do not construct filesystem paths |

Use `encodeURIComponent(key)`. Example key: `rti-2005:6`. Example direct route: `/api/provisions/rti-2005%3A6`. Keys must come from API results/corpus, not a duplicated UI catalogue.

Search accepts one `q` and optional integer `limit` (1–20). Missing/blank query returns zero results. Maximum query length is 500 characters. Punctuation is not search syntax. Duplicate/unknown search parameters, invalid limits, and overlong queries return 400. No automatic answer generation.

## Corpus object

- `notice`: common scope and legal-effect qualification, ready for display.
- `provision_count`: number eligible **now**, not a hard-coded four.
- `acts`: array of `{slug, title, provisions:[{key, section_number, heading}]}`.
- `excluded_since_import_count`: count of database-admitted rows currently rejected by the live evidence check. Not the number of all unreviewed provisions in India Code.
- `public_use_permission`: currently `"pending"`.

Display partial Act coverage explicitly. If the count drops, update the UI; don't fill missing entries from cached results.

## Provision object

Both full detail and search results include:

| Field | Meaning |
| --- | --- |
| `key`, `act_slug` | Stable provision and Act identities |
| `act_title`, `section_number`, `heading` | Labels for navigation and display; section numbers are strings (`5A`) |
| `representation` | `pdf` or `structured_html`, describing the selected source; body is still plain text |
| `conflicts` | Array of `{id, classification, disposition, explanation}`; display relevant notices prominently |
| `source` | Source links and snapshot information, described below |
| `review` | `{type, independent_legal_expert:false}` |
| `coverage_note` | Explanation that full Act text is not indexed |

Full detail additionally includes:

- `body_text`: complete admitted text with its existing newlines, indentation, clause markers and amendment markers. Preserve these with a suitable text layout; do not reconstruct a hierarchy or change wording.
- `footnote_text`: exact footnote text, or null. Show separately, not as an AI explanation.

Search results omit the full body/footnote and add:

- `score`: lower SQLite FTS5 BM25 values rank first. Keep this out of the ordinary user flow.
- `has_footnote`: boolean.
- `excerpt`: `{text, start, end, offset_unit, segments, omitted_before, omitted_after}`.

### Safe excerpts and highlighting

`excerpt.text` is exactly `body_text[start:end]` in **Unicode code points**, not UTF-8 byte or JavaScript UTF-16 offsets. UI code should use `segments` instead of recreating offsets:

```js
for (const segment of result.excerpt.segments) {
  const node = document.createElement(segment.match ? 'mark' : 'span');
  node.textContent = segment.text;
  excerptElement.append(node);
}
```

Concatenating segment text reproduces the excerpt exactly. Add a separate ellipsis before/after when the corresponding omission flag is true. Never pass API text to `innerHTML`. No highlight is not an error: matching can occur through stemming, title/alias, or footnote text.

### Source object

- `act_url`: original India Code Act page.
- `viewer_url`: original India Code PDF viewer. Remote availability is not guaranteed.
- `local_pdf_url`: same-origin verified retained PDF with `#page=N` for the provision's first PDF file page.
- `pdf_download_url`: same PDF without a page fragment.
- `pdf_page_from`, `pdf_page_to`: verified **file page numbers**, one-based; not inferred printed labels.
- `pdf_sha256`, `text_source_sha256`, `body_text_sha256`: provenance fingerprints for an optional details panel.
- `fetched_at`: source PDF capture timestamp, not effective date.
- `source_stated_modified_date`: raw source metadata date, possibly null. Label “Source-stated modification date”; never label “currently in force” or infer a legal timeline.

The PDF can contain unreviewed sections beyond the slice. Label the link “Source PDF — only listed provisions reviewed.” Full-PDF access for verification is not a claim that its full text is indexed.

## Query trace

`trace` contains `method`, normalized `terms`, `match_expression`, `act_filters`, `section_filter`, ranked `candidates:[{key,score}]`, `final_order`, `score_note`, `validation_ms`, and `search_ms`.

Use this only in an optional collapsed developer panel. It explains actual retrieval, not legal applicability. The service does not persist queries or send analytics. `total` counts current matching eligible provisions before the response limit; there is no pagination API in this slice.

## Errors and changed content

| Status/code | Meaning | UI action |
| --- | --- | --- |
| 400 / `invalid_query` | Invalid search input | Show the supplied message and preserve the editable query |
| 404 / `not_found` | Unknown or no-longer-admitted provision/PDF/resource | Remove any previously displayed text for that route; offer current coverage/search |
| 503 / `data_unavailable` | Database or required evidence cannot be loaded | Clear stale results/detail; show an unavailable state with retry |
| 403 / `local_only` | Host is not localhost/127.0.0.1 | Use the documented local URL |

Network failures must also clear or explicitly hide stale content. Cancel old search requests or use request sequence IDs so a slow older response cannot replace a newer query. Use `fetch(..., {cache:'no-store'})`; no service worker or local-storage cache of provisions. Previously rendered pages are not automatically pushed updates: refetch on navigation and when the page regains focus, and clear displayed content when validation fails.

## Static UI contract

The server serves only files under `web/` with `.html`, `.css`, `.js`, `.svg`, or `.ico` extensions. `/` serves `web/index.html` when it exists. No directory listings or project/data-file serving. Until the interface is built, `/` correctly returns 404 while API routes work.

Use `web/index.html`, `web/app.js`, and `web/styles.css` with hash routing (for example `/#/provisions/rti-2005%3A6`). Scripts/styles must be external files: CSP disallows inline scripts/styles and remote dependencies. Open source PDFs as ordinary links; embedded viewer work is unnecessary.
