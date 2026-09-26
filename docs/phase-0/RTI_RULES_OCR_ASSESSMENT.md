# RTI Rules, 2012 — OCR assessment and deferred disposition

Investigated 20 September 2026 (second pass), by the same kind of AI coding agent that built the offline importer, comparing the retained scanned page image against the retained PDF's existing embedded OCR text layer. This is not an independent legal-expert review, and it does not attempt to fix or re-OCR anything — see `data/review/reviewer-pass2.json`.

Evidence: [`data/discovery/rti-rules-2012-pdf.body`](../../data/discovery/rti-rules-2012-pdf.body), [`data/discovery/derived/rti-rules-2012.txt`](../../data/discovery/derived/rti-rules-2012.txt) (the file's own embedded OCR text, extracted via `pdftotext`), [`data/discovery/derived/rti-rules-2012-page-1.png`](../../data/discovery/derived/rti-rules-2012-page-1.png) (retained render of page 1).

## Disposition

**Deferred and excluded.** No rule text from this instrument is admitted, reviewed, or searchable. Only the parent-instrument metadata (title, parent Act, source/PDF links) is retained, per [`data/review/conflicts/OCR-001.json`](../../data/review/conflicts/OCR-001.json). This assessment does not change that disposition; it documents *why*, concretely, so a future decision to invest in OCR has a real baseline instead of a vague "the scan looked bad."

## Observed error types (from page 1, cross-checked against the rendered image)

| # | Category | Example (source vs. extracted) | Why it matters for legal text |
| --- | --- | --- | --- |
| 1 | Digit/letter confusion | `1. Short title` → `I. Short title`; `11. Procedure` (elsewhere) → `I I.` in one place and `11.` in another; a page header's `PART II` → `PART 11` on a different page | Rule numbers and Roman-numeral part labels are load-bearing identifiers; conflating `1`/`I`/`11`/`II` can misidentify which rule or which Gazette part a passage belongs to. |
| 2 | Clause-marker corruption | `(f) all other words...` → `(Call other words...`; a later, unrelated `(f) no fee for inspection...` → `(Ono fee for inspection...` | The **same letter** (f) was misread two different ways in the same document. This is not cosmetic: an importer that trusted OCR clause labels could silently misfile or mislabel a sub-clause. |
| 3 | Missing clause marker | Rule 11's item (i) ("receive oral or written evidence...") has no `(i)` label in the extracted text, though sibling items (ii)-(vi) are present | A dropped label breaks the enumerated structure outright; naive clause-splitting on this text would merge item (i) into the preceding sentence. |
| 4 | Letter-pair / word-merge errors | `Information Act` → `InforrnationAct` (merged, "rm"→"rn"); `senior in rank` → `is:senior in rank` (space→colon); `Section 19 of` → `Section 19'of` (space→apostrophe); `publication` → `pUblication` (stray inserted capital) | These corrupt exact wording, which the accepted conflict policy requires to be preserved verbatim for anything admitted. |
| 5 | Complete failure on handwritten/stamped content | A handwritten reference stamp, visually "2848 GI/12-2", extracted as `'g q8 6-112--2` | Not a partial misread — total garbage. No confidence signal exists that would have flagged this differently from clean body text. |
| 6 | Complete failure on non-Latin script | A bilingual Gazette footer line extracted as `%RR                : 3ffiltIR17` (meaningless ASCII) | Any Hindi/Devanagari content in this instrument is not degraded, it is lost. This is a hard blocker for any bilingual admission, not just an English-quality issue. |

None of these are hypothetical. All six were found on one page and its immediately surrounding text; a full-document pass would very likely surface more.

## Why this cannot be fixed by a confidence threshold

Per the accepted [conflict policy §6](CONFLICT_POLICY.md#6-ocr-excerpts-and-user-visible-treatment), no OCR confidence cutoff is adopted, and this fixture provides no reason to change that: Poppler's `pdftotext` extraction of an *existing* embedded OCR layer carries no confidence scores at all (unlike, say, a fresh EasyOCR pass with per-box confidence). The errors catalogued above are exactly the "extractable but not accurate" case the policy already anticipated — there is no numeric signal in the retained file that would let an importer auto-route only the bad spans to review; the entire document would need visual, page-by-page human or reviewed re-transcription regardless of any threshold choice.

## What admitting this instrument would require (acceptance criteria for future work)

This is **not a plan to start OCR work now** — no new OCR stack is installed and no further pages are processed in this session. If a future task takes this on, admission of any RTI Rules, 2012 provision should require, at minimum:

1. **A chosen OCR engine and version**, run against the retained scanned PDF (not a re-fetch), with its confidence scores retained at their actual per-token/per-line granularity — not collapsed into a single document-level score.
2. **Page-by-page visual review** of every admitted rule against its rendered page image, the same way RTI sections 6/8 and Environment Act sections 3/5A were reviewed in this corpus — clause labels specifically checked against the image, given error type #2 above.
3. **An explicit, tested rule for handwritten/stamped annotations** (error type #5): either exclude such regions from extraction entirely with a documented boundary, or flag them as unreviewable and never present them as body text.
4. **A decision on non-Latin content** (error type #6) before any bilingual admission — likely requiring a different OCR configuration (language pack) entirely, not a fix to the English pipeline.
5. **The same hash-binding and invalidation machinery already built for RTI/Environment**: any admitted rule text must be bound to the exact retained file hash and the exact OCR engine/version, and either changing must invalidate the admission, exactly as `scripts/offline_importer.py` already does for the PDF/HTML representations in this corpus.
6. **Reviewer disclosure**: whoever performs that future review must disclose reviewer identity and type with the same honesty as `data/review/reviewer.json` / `reviewer-pass2.json` — an AI agent's visual check is not independent legal-expert review here either.

## What this assessment does not claim

- It does not claim RTI Rules, 2012 is unimportant or that its fee schedule and appeal procedure are not useful search targets eventually.
- It does not claim these six error types are exhaustive; only page 1 and directly observed surrounding text were catalogued.
- It does not start, schedule, or scope an actual OCR project — that remains explicitly future, optional work.
