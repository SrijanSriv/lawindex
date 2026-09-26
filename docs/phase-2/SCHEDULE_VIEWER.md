# Private local viewer for the RTI schedule layout candidate

`scripts/render_schedule_review.py` is presentation tooling for source
review, not a parser, an acceptance decision, a public website, or a change
to the legal search app. It reads an artifact already produced by
`scripts/schedule_layout.py` (see [the layout contract](SCHEDULE_LAYOUT.md))
and writes a local, offline HTML report so a human or another agent can look
at the retained PDF pages and the model side by side.

## What it does and does not do

- It revalidates the supplied `--artifact` against a **fresh** model built
  from the fixed retained source path and the current layout profile, using
  `scripts/schedule_layout.py`'s own `parse`/`artifact_digest` functions. If
  the supplied artifact does not match that fresh model exactly, it refuses
  to render anything.
- It never reads `source_path`/`source_capture` out of the artifact to
  decide what file to open; the retained source is always the fixed
  repository path `data/discovery/rti-2005-pdf.body`.
- If `--review` is supplied, the review's status is decided solely by
  `schedule_layout.assess_review`, the same function `schedule_layout.py`
  itself uses. This script never fills in acceptance on the reviewer's
  behalf; a missing, stale, or invalid review is always shown as pending
  (or as its specific failure), never as accepted.
- It does not call the importer, does not write to SQLite, and does not
  touch the raw source, review files, or database.
- Output is deterministic: for a given artifact/review pair it always
  produces the same HTML (no timestamps, no random ordering).

## Usage

```sh
python3 scripts/schedule_layout.py
python3 scripts/render_schedule_review.py \
  --artifact data/import/schedules/<digest>.json \
  --output-dir data/import/schedule-viewer
```

Add `--review data/review/structure/rti-schedule-independent-review.json`
to use the now-existing separate review and verify whether it actually
binds and accepts. The command prints a JSON line with the viewer path,
artifact digest, and `review_status`; open the printed `index.html` in a
browser directly from disk (`file://...`).

`--output-dir` defaults to `data/import/schedule-viewer/`, which is a
private, ignored directory for local review artifacts (HTML, page images,
and a byte-identical PDF copy) and is never served, published, or read by
the search app.

## What the viewer shows

- A status banner naming the artifact digest and the actual review status
  (`needs_independent_review`, `layout_reviewed_not_search_admitted`,
  `changes_requested`, or one of the `invalid_review_*` bind failures) —
  never a claim of acceptance beyond what `assess_review` actually returned.
- The First Schedule's two alternatives (oath / affirmation) shown as
  separate panels sharing the same printed prefix/continuation, with no
  default selection and no synthesized merged sentence.
- The Second Schedule's all 27 printed serial positions in order, the
  separate unnumbered omitted block after serial 21, and all 11 footnotes
  with keyboard-accessible "Highlight" buttons. Selecting one highlights its
  source marker, affected words, and the matching footnote text together,
  scoped exactly to the artifact's own `amendment_reference` relations.
- For each page: an inline SVG of the model's own words at their original
  PDF-point positions (`viewBox` matched to the page's PDF point
  dimensions), the actual rendered page image (from the hash-verified PDF,
  via `pdftoppm`), and a link to a private byte-identical PDF copy at the
  right page.
- A closing legend stating explicitly that the SVG layer does not
  reconstruct fonts, rules, or graphics (words can visually overlap,
  especially the diagonal watermark, which the model stores only as
  axis-aligned per-word boxes); the page image and PDF are the actual
  visual reference. The banner and legend also state, on every page and in
  every review state, that nothing here is a search admission, a grant of
  public reuse permission, or a claim that the shown text is legally
  current.

## Security notes

- Every extracted word/label is HTML/SVG-escaped before being written into
  the page. Structural metadata embedded for the note-highlighting feature
  is serialized as JSON with `<`, `>`, and `&` escaped so it cannot break out
  of its `<script type="application/json">` element even via a literal
  `</script>` sequence in extracted text.
- No remote scripts, fonts, or stylesheets are loaded; everything needed to
  view the report is in the generated directory.

## Manual verification performed

The generated `index.html` for the current candidate digest
(`a111a35d9a490fe6a2f789c41e21648c4a4e565333db0d7d153fdbe671544288`, subject
to change on rebuild) was opened in a real browser tab and checked against
the two source pages:

- The status banner correctly read "Implementation candidate — independent
  review pending" with no artifact/review supplied, and correctly switched to
  "Independently reviewed layout — not search-admitted" only when fed a
  review record that actually bound to that exact artifact/profile/source
  digest with `independent_of_implementation: true` and no findings.
- Both First Schedule alternatives rendered with the shared prefix/
  continuation, matching the retained PDF's own wording, with neither
  pre-selected.
- All 27 Second Schedule entries, the separate omitted block, and all 11
  footnotes were present; clicking a footnote's "Highlight" button toggled
  `aria-pressed` and added `.note-active` to exactly the words/groups its
  `amendment_reference` relation names (spot-checked note-5, which correctly
  highlighted entries 16/17/18 plus its own marker occurrences, and note-6,
  which correctly covered entries 19-21 plus the separate omitted block).
- The rendered page images matched the retained PDF pages 23-24 exactly
  (including the diagonal "IndiaCode" watermark, which the SVG word layer
  necessarily shows as separate stacked letter boxes rather than a diagonal
  line, per its own axis-aligned bounding boxes — explained in the legend).
- Page links pointed at `schedule.pdf#page=23` and `#page=24` respectively.

This was a manual visual/interaction check against the two known pages, not
a full accessibility audit (no screen-reader pass, no automated a11y
scanner run).

## Known limitation to flag, not fix here

None found that block this viewer; any defect in the underlying layout
model itself is `scripts/schedule_layout.py`'s scope, not this viewer's, and
is not silently patched here.

## Main-agent final inspection and remediation — 21 September 2026

The original manual checks above missed scope expansion for partial footnotes and the omitted block's actual position in the HTML. Both are now corrected: highlight only the explicit marker/affected words/footnote, and place the omission between serials 21 and 22. Whole-region shading is allowed only when every word in that region is affected. The misleading “competent authorities” heading and duplicate list numbering are removed; shared oath context appears separately from the two alternatives. Reviewer disclosures are shown as supplied, with missing fields explicitly reported as missing; they are not credential verification. A fixed light palette avoids pale status backgrounds inheriting light text from dark mode.

Main-agent browser verification with the actual accepted review used a temporary loopback server for the generated directory, avoiding the earlier local-file preview limitation. Both page images loaded. Note 3 highlighted only `3`, `[Frontier]`, and its footnote; the whole entry box remained unhighlighted. Note 6 activated by keyboard included superscript 7 and all omitted stars and toggled off cleanly. PDF page links and byte-identical PDF copy were checked. All 132 unit tests (22 viewer tests), 26 importer checks, Phase 0 verification, and six development queries pass. No full accessibility audit is claimed. The source/model/profile/review and real DB remained unchanged. See [final gate audit](PHASE2_GATE_AUDIT.md).
