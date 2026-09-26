# Reviewed clause structure report

`scripts/report_structure.py` is a read-only inspector over the reviewed
contextual clause tree written by `scripts/structural_store.py` and
`scripts/clause_structure.py` (see
[STRUCTURAL_MIGRATION.md](STRUCTURAL_MIGRATION.md) and
[QUEUE_AND_STRUCTURE.md](QUEUE_AND_STRUCTURE.md)). It is the bounded task
described in [STRUCTURE_AGENT_PROMPT.md](STRUCTURE_AGENT_PROMPT.md), and
only that task: it does not touch the importer, the parser, admission, or
search.

## What it does and does not do

- Standard-library-only; no network, no subprocess, no schema migration,
  no write of any kind.
- Opens the SQLite database strictly read-only, from
  `Path.resolve().as_uri() + "?mode=ro"` (never raw string interpolation,
  which mishandles a path containing `#`, `?`, or spaces). A missing
  database file is reported as an error and is never created.
- Runs every read inside one explicit SQLite read transaction (`BEGIN` ...
  `ROLLBACK`), so the report reflects a single consistent snapshot even if
  the importer is writing concurrently under WAL mode. The transaction is
  always rolled back, never committed.
- Reports **only current roots**, joined strictly through
  `current_versions`. A historical `node_versions` row belonging to the
  same document as a current root is never treated as one of that root's
  children — children are always looked up by the current root's own
  `extraction_id`, never by document or node identity alone.
- For each current root: its public provision key, root version id,
  display label, heading, enclosing PDF page range, total contextual child
  count, and a nested tree of children ordered by sibling ordinal (never by
  label text — `(2)` sorts before `(10)`). Each tree node shows kind,
  display label, sibling position, root character offsets, and text
  length. **It never prints legal body or footnote text**, for the root or
  for any child.
- A root section with no reviewed structure profile is still shown, with
  `contextual_child_count: 0` and an explicit `no reviewed child
  structure` label — never silently omitted, and never confused with an
  unchecked/missing count.
- Before rendering anything, it validates the whole tree for each root:
  every parent exists inside that root's own extraction, there are no
  cycles, no duplicate sibling positions under one parent, and no orphan
  descendants; every descendant's stored root-offset anchor names the
  current root (both `root_version_id` and `mandatory_context_version_id`),
  its offsets fall strictly inside the root's actual text, and its stored
  text is the exact code-point slice of the root text at those offsets. A
  violation of any of these — or an unsupported/missing structural schema —
  produces one concise diagnostic on stderr and a nonzero exit, with no
  traceback and no partial report on stdout. Most of these malformed
  shapes are already rejected by `structural_store`'s own insert-time
  triggers; this validation is defense-in-depth against a database that was
  edited outside that API.
- Includes a versioned, deterministic JSON form (`--format json`) with the
  same information, `sort_keys=True` so byte-identical input produces
  byte-identical output.
- Never writes to the database. Tests assert the database is byte-identical
  before and after every run, including runs that fail.

## What it deliberately does not claim

- Contextual children are annotations of a reviewed root section, not
  independently admitted or independently searchable provisions.
- This report checks stored relationships and stored text slices only. It
  does not re-verify live source bytes, legal accuracy, reviewer
  independence, or corpus reuse permission.
- The current search corpus remains the reviewed root sections themselves;
  contextual children add no new searchable provisions.
- RTI schedule pages are explicitly excluded from structural parsing (see
  [QUEUE_AND_STRUCTURE.md](QUEUE_AND_STRUCTURE.md)). The absence of rows in
  this report is not evidence that a schedule was parsed — it never infers
  a parsed schedule from an absent row, and it never reads a path out of
  database content to go looking for one.

## CLI

```sh
python3 scripts/report_structure.py
python3 scripts/report_structure.py --db PATH --format json
```

`--db` defaults to the repository's existing
`data/import/lawindex_offline.sqlite3`; `--format` defaults to `text`.

## Tests

`tests/test_structure_report.py` uses only small synthetic fixtures built
in temporary directories — none of it is real legislative text or a real
reviewed boundary profile. It covers: current-vs-historical roots (a
historical version's children never leak into the current root), nested
ordering with numeric and lettered labels, no-profile roots, exact Unicode
code-point offsets (including a multi-code-point character), incorrect
stored offsets/text, a wrong root anchor, missing-parent/cycle/duplicate-
sibling rejection (exercised directly against the validation function,
since the storage layer's triggers already forbid constructing these
through the normal write path), a malformed/missing/unsupported schema,
filenames containing `#`, `?`, and spaces, a missing database that is
never created, deterministic JSON across repeated runs, unchanged database
bytes after both success and failure, and one consistent read snapshot
against a concurrent WAL writer holding an uncommitted transaction.
