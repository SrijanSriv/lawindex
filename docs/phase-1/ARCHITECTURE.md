# Phase 1 backend decision and handoff

Status: data/search API implemented; interface pending. Local-only, four reviewed provisions, English. Public-use permission remains pending. This is not full Phase 1 completion.

## Decision

Keep the existing SQLite database as the importer-owned store for this bounded slice. Use Python 3.11+ standard-library HTTP handling and SQLite FTS5 for retrieval. There are no pip or npm dependencies and therefore no package lockfile. Python must include SQLite FTS5; Poppler remains an importer prerequisite.

This is an explicit, bounded deviation from the roadmap's proposed PostgreSQL setup. A server database and migration layer would add operation and translation work without improving this four-row experiment. Reconsider PostgreSQL before multi-user deployment, larger corpus ingestion, or persistent vector search. Preserve provision keys, review digests, and the API semantics during any migration.

## Responsibilities

| Component | Owns |
| --- | --- |
| `scripts/offline_importer.py` | Source extraction, review enforcement, writing the canonical local SQLite database |
| `lawindex/search.py` | Read-only eligibility revalidation, source mapping, ephemeral lexical index, exact excerpts |
| `lawindex/server.py` | Loopback HTTP routes, JSON errors, allowlisted static files and admitted PDF bytes |
| `web/` | Future interface; no ingestion, admission, or ranking decisions |

The server never imports automatically or changes review records. Run the importer explicitly. Start with `python3 -m lawindex.server`; it binds only to `127.0.0.1`. The standard-library server is a development service, not a public production deployment.

## Keeping withdrawn content out of search

Every data request opens a read-only database connection and reads one joined document/provision snapshot. It checks candidate scope, database admission, current review presence/status, expected extracted-text digests, extraction-version label, exact original source bytes, PDF anchor mapping, and referenced conflict evidence. Missing or inconsistent per-provision evidence excludes that provision. Missing/malformed top-level evidence or database produces HTTP 503. There is no fallback to last-known-good content.

Search, direct provision access, and the PDF route all use this same admission boundary. A request uses the PDF bytes it actually hash-checked, rather than reopening a path after validation. Thus removal of a review or a changed source takes effect on the next request even if the importer has not yet rerun. Actual reimport withdrawal/restoration is also covered by tests.

Only eligible records populate a private in-memory FTS5 table for that search request. There is no persistent search index or refresh command to forget. Reimporting canonical data changes the next request's results; shutting down discards the temporary index. Each response has `Cache-Control: no-store`.

This trades performance for simplicity and correctness on four provisions: files are rehashed and the tiny index is rebuilt per request. It is not a scaling design. Requests already underway represent their acquired snapshot; revocation cannot erase text previously seen by a browser. A future interface must clear stale views when a new request reports withdrawal/failure. Concurrent evidence-file editing is not a supported publishing workflow; finish edits/imports before claiming a stable snapshot.

## Retrieval method

The named method is `sqlite-fts5-bm25-v1`. SQLite FTS5 supplies BM25, with column weights: title/aliases 4, heading 3, body 1, footnote 0.5. Lower returned scores rank first; they are not probabilities or legal confidence. The tokenizer uses English Porter stemming over Unicode tokenization. [SQLite FTS5 documentation](https://www.sqlite.org/fts5.html).

Input is limited to 500 characters and 40 distinct searchable terms. Punctuation is treated as separators; a documented code-level stopword list drops common grammatical words. Terms are quoted individually and combined with OR, then passed as a SQL parameter. Users are not entering raw SQL or FTS operators.

Recognized Act aliases (`RTI`, `Environment`, `EPA`) or an exact full title constrain the Act; explicit `section 6`/`s. 5A` references constrain the provision label. An unavailable explicit reference returns no results, never a substitution. Other questions use lexical matching. There are no query-specific answers, synonym expansion, embeddings, or generated responses.

Excerpts are exact body-text slices. Matching literal words are supplied as plain-text highlight segments; stemming can retrieve a result without an exact highlighted word. Body excerpts do not claim to show footnote-only matches. Full notes remain available on provision pages. Search normalization never changes displayed text.

## Verification and limitations

Run:

```sh
python3 scripts/build_phase0_artifacts.py
python3 scripts/verify_phase0.py
python3 scripts/offline_importer.py --fresh
python3 scripts/verify_offline_import.py
python3 -m unittest discover -s tests -v
python3 scripts/evaluate_search.py
python3 -m lawindex.server
```

`--fresh` rebuilds generated output. Tests mutate only temporary copies, including persistent-database imports and live HTTP requests. API tests cover query handling, exact excerpts, notes/conflicts, source tampering, review withdrawal/restoration, direct-route exclusion, and arbitrary-path denial.

The six existing development questions currently place their expected provision first. See [recorded results](DEV_RESULTS.md). That is a smoke result over four provisions and provides no evidence of broad recall or performance on unseen queries.

No browser interface has been implemented or visually verified in this task. The next agent owns it under [the fixed API contract](API_CONTRACT.md). Do not declare Phase 1 complete until its end-to-end browser flow is verified.
