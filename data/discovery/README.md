# Phase 0 evidence

These are local research fixtures captured on 20 September 2026. They are not the production corpus, not a legal-status certification, and not a licensed public dataset. Read [the source report](../../docs/phase-0/SOURCE_DISCOVERY.md) and [access findings](../../docs/phase-0/ACCESS_AND_REUSE.md) before expanding or redistributing them.

## File types

- `*.body`: original response bytes. The extension deliberately does not assert successful extraction. Inspect the companion JSON's content type and HTTP status; PDF captures begin with `%PDF-`.
- Companion `*.json`: requested/effective URL, UTC fetch time, HTTP status, type, transport outcome, byte count, and SHA-256. These describe acquisition, not content accuracy.
- `capture-index.json`: generated catalog of all 16 raw captures.
- `observations/acts.json`: manually transcribed browser metadata observations for 11 Acts; not raw response bytes. Null section counts mean unverified, not zero. Source URLs are reconstructed explicitly in the generated manifest from observed IDs/routes.
- `corpus-manifest.json`: 10 proposed Act candidates and two additional quarantine fixtures; every record remains unimported and not ready for public indexing.
- `seed-queries.jsonl`: 24 development queries with candidate hints; all formal relevance judgments remain unjudged.
- `pdf-report.json`: extraction diagnostics for five files, including per-page text lengths and derived-text hashes.
- `structured-report.json`: observed JSON fields, identity, pagination, and confirmed RTI discrepancy checks.
- `derived/`: reproducible PDF text, PDF metadata reports, one structured section record, and three visual-inspection PNGs. Extracted text may contain watermark fragments, OCR errors, and repeated contents entries. It is not ready-made searchable legal text.

## Known response classes

| Capture | Meaning |
| --- | --- |
| `legacy-home` | Migration notice |
| `current-home`, `terms`, `copyright`, `central-collection-page` | Same frontend application shell; no rendered content |
| `current-robots` | HTTP 502 error body; no usable robots guidance |
| `legacy-robots` | HTTP 404 error body |
| `current-main-js`, `current-config` | Delivered application code/config inspected to understand client rendering and backend routing |
| `rti-item` | One raw Act metadata response |
| `rti-sections-page-0` | One page of 10 RTI section records; source reports 31 total |
| Five `*-pdf` captures | Original reference PDFs with their source notices intact |

Rendered policy text was inspected through the browser; the policy response shells do not contain it. Findings in the access note are paraphrased observations, not an archived full policy snapshot.

## Offline reproduction

From the repository root:

```sh
python3 scripts/build_phase0_artifacts.py
python3 scripts/verify_phase0.py
```

Requires Python 3, `pdfinfo`, and `pdftotext`. Existing originals are never regenerated or fetched by these commands. Generated text hashes can vary across Poppler versions; the original source hashes are the fixed provenance anchors.

The three PNGs were generated with `pdftoppm -png -singlefile`: RTI pages 9 and 11, and RTI Rules page 1. They support targeted visual review; no claim is made that every retained page was visually checked.
