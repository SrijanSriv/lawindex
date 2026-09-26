# Independent review of Phase 0 offline technical-readiness work

**Reviewer:** a separate agent session (Claude Sonnet 5), acting as an independent reviewer of the
implementation agent's Phase 0 offline importer and its second-pass self-audit. Not an independent
legal-expert review; a software/provenance/source-fidelity review only.

**Reviewed:** commit-less working tree at `/Users/srijansrivastava/randoms/lawindex` as of 2026-09-20.

**Method:** read every Phase 0 doc, review record, and conflict record; read `scripts/offline_importer.py`
and `scripts/verify_offline_import.py` line by line; independently recomputed source-file hashes;
independently re-ran `pdftotext -layout` against the retained PDF bytes (outside the importer) and diffed
the result against what review records and admitted `body_text` claim; reproduced all four documented
commands from a clean copy of the tree in an isolated scratch directory; wrote and ran adversarial checks
against copies of the tree in `/private/tmp/.../scratchpad/review/` (never against the real
`data/import/lawindex_offline.sqlite3` or any file under the project directory) to probe the
existing-database update path, missing/malformed inputs, and record retraction/removal, none of which the
checked-in regression suite exercises. No network requests were made; no India Code content was fetched;
no messages were sent; nothing under the project directory was modified by this review.

## Scope actually covered

- RTI Act, 2005 sections 6 and 8, and Environment (Protection) Act, 1986 sections 3 and 5A — the entire
  admitted slice — against the exact retained PDF bytes.
- The watermark-stripping rule, its regression coverage, and its false-positive risk.
- The conflict-policy compliance claims for RTI-001, RTI-002, KERALA-001, and OCR-001.
- Provenance/anchor claims (hashes, PDF page ranges, printed-page vs. file-page distinctions).
- Admission-invalidation behavior, **including the existing-database update path** (not just `--fresh`
  imports), which the task specifically called out as under-tested.
- Import behavior on missing/malformed inputs and interrupted/failed runs.
- Regression-test quality: which of the 19 checks exercise real behavior vs. which guarantees remain
  untested.
- Cross-document consistency (README, PHASES, CONFLICT_POLICY, READINESS_MANIFEST, CORPUS,
  ACCESS_AND_REUSE) and a check for invented metrics or overclaiming.

## Commands run and results (all reproduced from a clean copy in an isolated scratch directory)

```
python3 scripts/build_phase0_artifacts.py
python3 scripts/verify_phase0.py
python3 scripts/offline_importer.py --fresh
python3 scripts/verify_offline_import.py
```

All four ran exactly as documented: the artifact builder reported 16 hashes / 5 PDFs / 12 manifest
entries / 24 seed queries; `verify_phase0.py` passed; the importer produced
`{"documents": 12, "provisions_admitted": 4, "conflicts": 4}`; and all 19 regression checks in
`verify_offline_import.py` passed. **The claim that the checked-in test suite passes is confirmed.** Per
the review brief, this is treated as necessary, not sufficient, evidence — see the findings below for what
the suite does not cover.

Independent hash recomputation (`shasum -a 256`) confirmed both retained PDFs match their declared hashes
exactly: `rti-2005-pdf.body` → `c1ef189e...cfb2f5`, `environment-1986-pdf.body` → `d9712743...576fdc9169`.

Independent re-extraction (`pdftotext -layout` run directly on the retained PDF bytes, outside the
importer) confirmed, byte-for-byte against the claims in the review records:
- RTI section 8's admitted body text correctly preserves the amendment-bracketed clause (j)
  (`1\n[(j) information which relates to personal information;]`), the two provisos, subsections (2)–(3),
  and stops exactly before "9. Grounds for rejection...". The excluded HTML wording never appears.
- RTI section 8's PDF page 10 (independently re-extracted by this review, since no retained render of it
  exists — see Finding 2) genuinely contains clauses (a)–(i) as the review record claims.
- Environment Act section 3's admitted text correctly preserves the nested (i)/(a)/(b) structure, the
  (iv) proviso, and correctly continues subsection (3) onto PDF page 5 before stopping at "4. Appointment
  of officers...".
- The watermark regex's claimed "65 real matches" against `environment-1986.txt` was independently
  recomputed and confirmed to be exactly 65.

No source-fidelity defect was found in the four admitted provisions' actual text, boundaries, footnotes,
or anchors. This is the strongest part of the submission and the claims about it hold up under independent
re-derivation.

## Findings, ordered by severity

### Finding 1 (blocker for Phase 1 readiness as a general mechanism, not for the current four-provision slice) — Admission invalidation does not hold on an existing database when a review record is removed or a manifest entry is dropped

**What I did:** In an isolated copy of the repo, ran `offline_importer.py` against a **persistent** (file,
not in-memory) SQLite database — mirroring how the manifest/database in `data/import/` is actually
regenerated and how Phase 1+ would use this database over time, not fresh every time. Then:

1. Removed `data/review/rti-2005-section-8.review.json` (simulating a reviewer retracting an approval, or
   an operator deleting a record because it was found to be wrong) and re-ran `import_all(conn)` against
   the *same* existing database file (no `--fresh`).
2. Separately, removed the `rti-rules-2012` entry from `data/discovery/corpus-manifest.json` (simulating a
   document being dropped from the candidate corpus) and re-ran the same way.

**Observed behavior:**

```
stats after retracting review record (existing db, not fresh): {'documents': 12, 'provisions_admitted': 3, 'conflicts': 4}
rti-2005:8 row after retraction still present as: admitted | body_text present: True
admitted count after retraction (existing db): 4
```

The function's own return value correctly reports `provisions_admitted: 3` (it only iterates over the 3
review records it can still see), but the **database itself still contains 4 admitted rows**, including
the full `body_text` for `rti-2005:8` whose review record no longer exists anywhere in the tree.
Regenerating the readiness manifest from that same database (`build_readiness_manifest(conn)`) reproduces
the same problem: it lists `rti-2005:8` as `admitted` even though nothing in `data/review/` any longer
attests to that admission.

The document-level case reproduces identically: removing `rti-rules-2012` from the manifest and re-running
against the existing database leaves 1 stale row for it in the `documents` table.

**Root cause:** `import_all` in `scripts/offline_importer.py:361-489` only ever `upsert`s rows for records
it currently sees in `data/review/` and `data/discovery/corpus-manifest.json`. It never computes the set
of provision keys / act slugs that exist in the database but are no longer backed by a current review
record or manifest entry, and never deletes or invalidates them. `import_all` and
`build_readiness_manifest` are effectively insert/update-only over an ever-growing set of historical rows.

**Impact:** This directly contradicts the guarantee the project's own documentation claims. The conflict
policy states (`docs/phase-0/CONFLICT_POLICY.md:53`): *"Revalidate on change. Source or derived-text
changes invalidate the affected approval and index entry until checked again."* The readiness manifest
states (`docs/phase-0/READINESS_MANIFEST.md:92`): *"A source/extraction change invalidates the affected
approval, and every excerpt resolves to its selected representation."* Both are demonstrated true for
**byte-level** changes (tampered PDF bytes, bumped extraction-method version, a missing declared footnote —
all correctly invalidate, per checks #9, #15, #16 in `verify_offline_import.py`), but false for the
**removal of the review record itself** — the most natural way an approval would actually be retracted in
a real workflow (a reviewer decides a prior approval was wrong and pulls the record; an Act is dropped from
scope). The regression suite's idempotence check (`check_idempotence`) only proves that importing the
*same* fixtures twice is stable — it never imports, removes a record, and re-imports, so it cannot catch
this. This is exactly the "existing-database update path" the review brief asked to be tested separately
from fresh imports, and it fails.

**Reproduction:**
```sh
cp -r data/review /tmp/scratch/data-review-orig   # or work in an isolated copy of the whole tree
cd /tmp/scratch/isolated-repo
python3 -c "
import sys; sys.path.insert(0,'scripts')
import offline_importer as oi, sqlite3
conn = sqlite3.connect('test.sqlite3')
oi.import_all(conn)  # first import: 4 admitted
"
rm data/review/rti-2005-section-8.review.json
python3 -c "
import sys; sys.path.insert(0,'scripts')
import offline_importer as oi, sqlite3
conn = sqlite3.connect('test.sqlite3')
print(oi.import_all(conn))
print(conn.execute(\"SELECT admission_status FROM provisions WHERE provision_key='rti-2005:8'\").fetchone())
"
# -> admission_status still 'admitted', body_text still populated
```

**Recommended fix:** At the start of `import_all`, compute the set of provision keys currently backed by a
review record (and act slugs currently in the manifest), and either (a) delete rows for provision
keys/act slugs no longer present in the source data, or (b) explicitly set their `admission_status` to a
new value such as `invalidated_review_record_removed` / `invalidated_manifest_entry_removed` rather than
leaving the previous status untouched. Add a regression check that imports, removes a review record (or
manifest entry), re-imports against the *same* database file, and asserts the provision is no longer
`admitted`.

**Note on severity:** this does **not** currently affect the correctness of the four admitted provisions
as they stand today — nothing has actually been retracted. It is a blocker for treating the invalidation
mechanism as sound going into Phase 1, where a real, persistent database and an evolving set of review
records are the normal operating mode, not a `--fresh` rebuild every time.

### Finding 2 (moderate — provenance completeness, not source-fidelity) — A review record cites visual-inspection evidence that was not retained

`data/review/rti-2005-section-8.review.json:26` states the reviewer "Rendered and visually inspected PDF
page 10 (printed page 10, not previously rendered as an image in Phase 0 discovery; rendered during this
session with pdftoppm at 150dpi)". `data/review/reviewer.json:8` corroborates this in `tools_used`:
`"pdftoppm (Poppler, page 10 rendered during this session; pages 9 and 11 were already retained as
PNGs)"`. However, `data/discovery/derived/` contains `rti-2005-page-9.png` and `rti-2005-page-11.png` but
**no `rti-2005-page-10.png`** (confirmed by directory listing and `find`). The evidence list in the same
review record (`review.evidence`, lines 27-32) also does not cite a page-10 image — only the page-11 one.

**Impact:** The task brief specifically asks to "Verify that review records describe what was actually
inspected" and to work from "retained local artifacts only." As written, the page-10 visual-inspection
claim cannot be independently verified from what is retained in the repository — only re-derived by
running `pdftoppm`/`pdftotext` afresh, which this review did. That re-derivation confirms the **content**
claim is true (page 10 genuinely contains clauses (a)–(i) as stated — see "Commands run" above), so this is
not a source-fidelity defect in the admitted text. It is a provenance/reproducibility gap: the retained
evidence directory does not actually contain everything the review record and reviewer disclosure say was
produced and inspected during the session.

**Recommended fix:** Either retain the page-10 PNG under `data/discovery/derived/` (regenerable with
`pdftoppm -png -r 150 -f 10 -l 10 data/discovery/rti-2005-pdf.body data/discovery/derived/rti-2005-page`)
and add it to the review record's `evidence` list, or soften the review record's wording to state that the
page-10 render was transient and not retained, so a future reader does not go looking for a file that does
not exist.

### Finding 3 (low — recoverability, not correctness) — A single missing capture file aborts the entire import with an unhandled exception; no partial-failure recovery exists

`load_capture_bytes` (`scripts/offline_importer.py:82-84`) does a bare `.read_text()` /`.read_bytes()` with
no existence check. Isolated-copy testing confirmed that deleting any capture file referenced by a review
record (e.g. `rti-2005-pdf.json`) causes `import_all` to raise an uncaught `FileNotFoundError` for the
*entire* run, not just the affected provision — a missing Environment Act file, for instance, would also
prevent the unrelated RTI provisions from being (re-)admitted in that run.

**Positive finding, confirmed by testing:** this failure mode is **safe**, not corrupting. `import_all`
calls `conn.commit()` exactly once, at the very end (`scripts/offline_importer.py:488`). An isolated-copy
test confirmed that an import which raises partway through leaves a pre-existing database's row counts
completely unchanged — Python's `sqlite3` module does not persist an uncommitted transaction. So a failed
run cannot leave a partially-imported or misleadingly-successful state; it just fails loudly and leaves the
prior good state intact. This satisfies the review brief's "failures do not leave misleading partial
success" requirement.

**Remaining gap:** there is no per-provision fault isolation (one bad/missing fixture blocks the whole
batch) and no distinct exit code or message pointing at which capture was missing versus a generic Python
traceback. For a 4-provision bounded Phase 0 exercise this is acceptable; it should be revisited before
Phase 2/3 batch ingestion, which the project's own `PHASES.md` (Phase 2) already anticipates ("Add bounded
concurrency... Persist per-item outcomes so a failed batch can resume without refetching successful
items").

### Non-findings worth stating explicitly (checked and found correct)

- **RTI-001 splicing prohibition**: independently confirmed the excluded HTML wording
  ("has no relationship to any public activity or interest...") never appears in `rti-2005:8`'s admitted
  `body_text`, and the shorter PDF wording is present, matching both the conflict record and the retained
  PDF bytes I re-extracted myself.
- **RTI-002 page-anchor handling**: the source-stated page hint (`7`) is retained as metadata only; the
  actual bound anchor (PDF page 9) was independently confirmed by re-running `pdftotext` and finding
  section 6's heading text on that exact page of the retained file.
- **Watermark rule scoping**: re-ran the regex directly against both retained PDFs' derived text; all
  matches are exactly the five expected tokens (`In`, `di`, `aC`, `od`, `e`), each isolated on its own
  heavily-indented line — consistent with a diagonal watermark artifact, not legitimate text. The
  regression suite's constructed near-misses (short indent, token-as-substring, token-plus-punctuation) are
  correctly *not* stripped. I did not find a real near-miss anywhere in the two retained documents that the
  rule incorrectly strips or incorrectly preserves.
- **Kerala date resolution**: the conflict record's calibration argument (cross-referencing the bracketed
  assent-date convention against the RTI PDF, where it independently matches known metadata) is logically
  sound and its `residual_uncertainty` disclosure is honest about what it did *not* confirm (the live
  listing UI's exact field mapping). The Act correctly stays `quarantine_fixture` / `ready_for_public_index
  = 0` regardless of the date resolution, confirmed both by the regression check and by my own query
  against a fresh import.
- **OCR exclusion**: RTI Rules, 2012 has zero admitted provisions and is quarantined; confirmed.
- **Reviewer attribution**: each of the four admitted provisions' `review_decisions.reviewer_id` matches
  the reviewer file its own review record actually declares (session-1 reviewer for RTI, session-2 reviewer
  for Environment Act) — confirmed by direct query, not just by the checked-in assertion.
- **Excerpt-to-source mapping**: confirmed the excerpt for `rti-2005:6` is an exact `body_text[start:end]`
  slice with a matching SHA-256 on the full body text.
- **No invented retrieval metrics or overclaiming**: grepped all Phase 0 docs and `IDEA.md`/`PHASES.md` for
  Recall@k/nDCG/BM25/legal-expert-review language. The one Recall@10/nDCG@10 mention (`IDEA.md:39`) is
  explicitly framed as a future target ("Exact launch thresholds belong in the milestone plan once we have
  measured a baseline; they are not established facts today"), not a measured result. Every reviewer
  disclosure file and every mention of the review in `READINESS_MANIFEST.md`/`CONFLICT_POLICY.md`
  explicitly and consistently states this is AI-agent review, not independent legal-expert review. No
  "whole Act approved" language was found anywhere.
- **Cross-document consistency**: `README.md`, `PHASES.md`, `CONFLICT_POLICY.md`, `READINESS_MANIFEST.md`,
  and `CORPUS.md` all agree on the same facts (4 provisions, 2 Acts, 12 manifest documents, 10 candidates +
  2 quarantine fixtures, 19 regression checks, access request pending). I found no drift between them.
- **Command reproducibility**: all four documented commands reproduce exactly as described, from a clean
  copy of the tree, including exact stdout strings ("Verified 16 capture hashes...", the JSON stats line,
  and all 19 "PASS" lines).

## Limitations of this review

- I did not attempt OCR work or evaluate the RTI Rules OCR assessment's six error categories against a
  fresh OCR run — no OCR tooling was invoked, consistent with the "no OCR work started" status the manifest
  already discloses. I only checked that OCR text remains excluded from admission, which it does.
- I did not independently verify the Kerala PDF page renders pixel-by-pixel against the printed assent-date
  bracket; I read the same PNGs the review record cites and consider the textual argument in
  `KERALA-001.json` sound, but a truly independent visual check of those three PNGs was not repeated here
  beyond confirming they exist and are the files the conflict record cites.
- I did not evaluate the eight remaining candidate Acts, since none of them has any admitted text — there
  is nothing to source-fidelity-check yet, consistent with the manifest's own scope statement.
- I did not evaluate India Code's Terms of Use/Copyright Policy for legal enforceability — `ACCESS_AND_REUSE.md`
  already frames this as an open question, and doing so is outside an engineering review's competence and
  outside this review's remit (no external fetches were made).
- This is not a legal-expert certification of any provision's current wording or effect, consistent with
  the project's own repeated disclosures.

## Verdict

**Ready with nonblocking issues**, for the bounded four-provision, two-Act offline technical slice as
narrowly scoped in `READINESS_MANIFEST.md` — with one important caveat about what "ready" covers.

- **Not blocking the current slice**: Finding 1 does not corrupt or misrepresent the state of the four
  provisions *as currently imported from a fresh database*, which is how the manifest is actually
  regenerated today (`offline_importer.py --fresh`, per the documented commands). The source-fidelity work
  itself — the actual text, boundaries, footnotes, anchors, and watermark handling for the four admitted
  provisions — independently checks out against the retained PDF bytes with no defects found.
- **Blocking before this importer is trusted as an ongoing, persistent-database mechanism** (i.e., before
  relying on it across multiple sessions/Phase 1 the way a real ingestion pipeline would, rather than always
  rebuilding fresh): Finding 1 must be fixed. The project's own stated guarantee — that revoking or changing
  a review record invalidates the affected admission — is currently false for the removal case on an
  existing database, which is a realistic and expected event, not an edge case.
- Finding 2 (unretained review evidence) should be fixed before treating the review records as a complete,
  self-contained provenance trail, per the project's own "retained evidence only" standard, though I found
  no actual content discrepancy from it.
- Finding 3 is a documented, low-severity limitation appropriate to defer to Phase 2 as the project's own
  `PHASES.md` already anticipates.

**Separating the three tracks the task asked to keep distinct:**
- **Engineering blockers**: Finding 1 (admission invalidation on an existing/persistent database).
- **Pending access permission**: unchanged and independent — India Code's response to the 20-Act request
  remains outstanding; this review did not and could not affect that.
- **Intentionally excluded future scope**: the other 29 RTI sections, ~35 Environment Act sections, eight
  other candidate Acts, RTI Rules OCR, and alternate-language fixtures are correctly and consistently
  described as out of scope everywhere I checked, not silently implied to be covered.

## Summary

The four admitted provisions (RTI Act sections 6 and 8; Environment (Protection) Act sections 3 and 5A)
independently check out: I recomputed the source PDF hashes, re-ran `pdftotext` myself outside the
importer, and confirmed the admitted text, boundaries, footnotes, and amendment markers match the retained
PDF bytes exactly, with no splicing of the excluded conflicting HTML into section 8. The watermark rule is
correctly scoped and its "65 real matches" claim checks out. Documentation is internally consistent and
free of invented metrics or overclaiming.

The one real defect found — and it is real, reproduced twice independently, and not covered by any of the
19 checked-in regression checks — is that **`import_all` never invalidates or removes rows for provisions
or documents whose backing review record or manifest entry has been removed from an existing (non-fresh)
database**; it only detects invalidation from byte-level/version-level changes to records that still exist.
This does not undermine today's four-provision result, but it is a genuine gap in the "revalidate on
change" guarantee the project documents as already implemented, and should be fixed and covered by a new
regression check before this importer is relied on as anything more than a rebuild-from-scratch tool. A
secondary, lower-severity finding is that one review record (RTI section 8) cites a page-10 visual
inspection whose rendered evidence file was never retained to disk — the underlying content claim held up
under my own re-derivation, but the evidence trail itself is incomplete as retained.

## Remediation note, 2026-09-20 (added after this report; original findings above are unmodified)

This report's Finding 1 (stale-admission invalidation on an existing database) was fixed the same day: see
`scripts/offline_importer.py`'s `invalidate_stale_records` and the "removing a review record..." /
"removing an Act from the manifest..." regression checks it references were added at that point. A separate
follow-up inspection (`docs/phase-0/INSPECTION_FOLLOWUP.md`) then found two further gaps in that same area
— admission was bound to source bytes and a version label but not to the reviewed extracted text itself,
and a restored manifest entry kept a stale removal flag — both since fixed and regression-tested. See
`docs/phase-0/READINESS_MANIFEST.md`'s "Remediation, 2026-09-20" section for the authoritative, current
account of what was fixed, how, and which regression checks now cover it. This note does not alter any
finding above; it only records where the fixes for those findings ended up.
