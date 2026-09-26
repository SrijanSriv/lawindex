# Bounded implementation: private schedule review viewer

Build a small offline viewer for the immutable candidate produced by `scripts/schedule_layout.py`. This is presentation tooling for source review, not a parser, acceptance decision, public website, or change to the legal search app.

Read `docs/phase-2/SCHEDULE_LAYOUT.md` and the emitted model. If an independent review report already exists, read it and surface its actual verdict; do not assume approval. Work may proceed before that report arrives, but label the result implementation candidate / independent review pending.

Allowed code/docs changes: create `scripts/render_schedule_review.py`, `tests/test_schedule_viewer.py`, and `docs/phase-2/SCHEDULE_VIEWER.md`; add a link/commands to README. Generated private HTML/images/PDF copy may go only under `data/import/schedule-viewer/`. Do not modify the parser, profile, queue, structural store, tests owned by others, independent review report/JSON, raw source/reviews, database, server, or web app. No network or external services. No Sites deployment or publishing: this is a local development review artifact.

Deliver a standard-library CLI that takes `--artifact PATH`, optional `--review PATH`, and `--output-dir PATH`. It validates the model schema and digests by calling the existing parser/helper functions against the fixed retained source path, then writes a self-contained local HTML report. Do not trust an arbitrary filesystem/source URL stored in the model. Refuse an artifact that differs from a fresh model of the current source/profile. Do not execute the importer or write SQLite.

Display each page's words at the model's original PDF-point coordinates in SVG (with a viewBox matching the page dimensions), alongside source-page images rendered from the exact hash-verified PDF. Optional links to a private byte-identical PDF copy should go to the correct pages. Explain that SVG word positions do not recreate every font/graphic and the PDF/image is the visual reference. Do not form paragraphs by concatenating the alternatives or generate a synthesized oath.

Show the two First Schedule alternatives and their shared context clearly. Show all Second Schedule entries, the separate omission, and note references; selecting a reference may highlight its source marker, affected words/entries, and matching footnote. Preserve brackets and omission marks. No default selection that changes wording. Both accepted and pending review states must remain explicitly non-search-admitted, with no claim of public reuse permission or legally current wording.

Escape every extracted word/label used in HTML/SVG and safely serialize any embedded JSON (including '<' and closing-script sequences); never interpret extracted text as markup or commands. Use no remote scripts, fonts, or assets. Keyboard-accessible buttons/links, readable labels, and a text legend are sufficient; no framework or visual redesign of the main app.

Tests: deterministic output, UTF-8 and escaping hostile/synthetic labels, unknown artifact/schema or wrong source hash rejected, missing/stale review never displayed as accepted, all 27 serial positions/11 notes/13 links represented, correct page links, no DB/source mutation, and no code path calling the importer. Use temporary output directories. Manually inspect the actual generated viewer against the original two pages in a browser and record what you checked; do not claim a full accessibility audit.

Run the full unit suite and the existing importer/search checks. Never run `--fresh`. Finish with changed files, reproduction commands, verification results, screenshots/inspection notes if useful, and limitations. Report any blocking model defect with a reproduction; do not silently fix it or widen your scope. Do not mark Phase 2 complete.

## Accepted review and advisory checks

The independent review now exists at `docs/phase-2/INDEPENDENT_SCHEDULE_REVIEW.md`, with the record at `data/review/structure/rti-schedule-independent-review.json`. Read both and validate the binding through the existing helper; the current accepted artifact is `a111a35d9a490fe6a2f789c41e21648c4a4e565333db0d7d153fdbe671544288`. Do not hardcode acceptance or this digest as a substitute for validation.

Explicitly verify O1: the source image/PDF remains available for underlining, italics, small caps, footnote rules, superscript styling, and larger type that positioned words alone do not reproduce. Verify O5: note 6 highlights its full recorded affected span, including the superscript 7 inside the shared bracket. Display the actual reviewer disclosure (AI agent, not an independent legal expert); the helper's accepted status alone does not validate credentials (O3). Missing disclosure fields must not produce an invented reviewer description. Treat baseline/profile changes as requiring new review (O2), never as a viewer-side fix.
