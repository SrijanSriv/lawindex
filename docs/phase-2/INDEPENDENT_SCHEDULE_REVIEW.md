# Independent review: RTI schedule layout model — 21 September 2026

**Verdict: `accept_layout`.** The candidate artifact `a111a35d9a490fe6a2f789c41e21648c4a4e565333db0d7d153fdbe671544288` is a faithful positioned-word model of retained PDF pages 23–24. Every check listed in the review prompt was performed against the source PDF and passed. No findings require changes to the model. Advisory observations (non-blocking limitations of the model and validator) are listed separately below; they do not alter the decision.

**Reviewer disclosure.** This review was performed by an AI review agent (`agent:claude-opus-5:2026-09-21-independent-schedule-review`), a separate session from the Codex implementation agent that authored the parser, profile, and baselines. I am not a legal expert; this is a source-fidelity and acceptance-boundary review, not a determination of legal effect, current applicability, or public reuse rights. Wall-clock review duration was not separately instrumented.

**What this review does not do.** It does not admit either schedule into SQLite or search, does not grant reuse permission, does not close Phase 2, and does not modify the parser, profile, source bytes, database, prior review decisions, search API/UI, inspector, or phase status. The final Phase 2 closure decision is left to the main agent.

## Persistent outputs of this review

| Path | Purpose |
| --- | --- |
| `docs/phase-2/INDEPENDENT_SCHEDULE_REVIEW.md` | this report |
| `data/review/structure/rti-schedule-independent-review.json` | digest-bound review record (SHA-256 `a846ca04f9fe9a54e7ae46d086f986ae263ab1ddf4505160792822c352786a54`) |
| `data/import/independent-schedule-review/rti-page-23.png`, `rti-page-24.png` | my own 200 DPI Poppler renders of the source pages |
| `data/import/independent-schedule-review/zoom-*.png` | 400 DPI crops of the oath block, entries 6–12, and entries 18–27 |
| `data/import/independent-schedule-review/overlay-page-2{3,4}*.png` | artifact group boxes and marker→footnote links drawn over my renders |
| `data/import/independent-schedule-review/adversarial_mutations.py` | the mutation script whose results are tabulated below (runs against in-memory copies only) |

## Hashes and binding verified by me

| Item | Value | How verified |
| --- | --- | --- |
| Source `data/discovery/rti-2005-pdf.body` | `c1ef189ec4f34d4f346886d6c2fc4a6e8aec2da0eedcfeff9c10401ec9cfb2f5` | `shasum -a 256`; matches `rti-2005-pdf.json` capture record and the artifact's `source_sha256` |
| Candidate artifact digest | `a111a35d9a490fe6a2f789c41e21648c4a4e565333db0d7d153fdbe671544288` | emitted by `python3 scripts/schedule_layout.py`; recomputed from the file with `artifact_digest()`; equals the digest named in `SCHEDULE_LAYOUT.md` |
| Artifact file bytes | `44c64fccd276930e6ed4155a066bc373bdc5cea09018312ce85f6b567b6c6963` | `shasum -a 256` of `data/import/schedules/a111a35d….json` |
| Profile canonical digest | `5ddf98803c577ec72d7cc3a9face1370612b5cacb59cdc2bd026b5ccddb580ac` | recomputed from `rti-schedule-layout-profile.json`; equals artifact `profile_sha256` |
| Profile file bytes | `12f2225a2a7e5a9c0b555bc5320531afec34f62176a8179a7979bb8d71f2ce5a` | unchanged before/after all commands in this review |
| Database file bytes | `24b305672a9d3e6858a5fe03a5cedf91d4c19e9e0e83d957e0ddd938e6a5c341` | unchanged before/after all commands in this review |
| Poppler | `pdftotext version 25.10.0` | the extracted-layout hash `04a36151…` is what this Poppler build produces; see limitations |

The stale draft `data/import/schedules/6115b9d7….json` was not reviewed as the candidate. I diffed it: identical words, groups, and relations; it differs only in `profile_sha256`, `source_path`, and `source_capture` (the draft predates those anchors). It is superseded, not conflicting.

## Method

1. Read `SCHEDULE_LAYOUT.md`, `PHASE2_GATE_AUDIT.md`, `scripts/schedule_layout.py`, `tests/test_schedule_layout.py`.
2. Verified the source hash, rebuilt the candidate, recomputed its digest.
3. Rendered pages 23 and 24 myself with `pdftoppm -r 200` and inspected them; rendered 400 DPI crops of the regions where a single glyph matters (superscripts, asterisk counts, brackets, underline).
4. Dumped every word (id, text, bbox) and every group/relation from the artifact and compared them, word by word, to the rendered pages.
5. Drew every group's bounding box and every marker→footnote link over my own render to confirm coordinates land on the printed glyphs.
6. Confirmed the character multiset of all 421 artifact words equals the character multiset of plain `pdftotext` output for the same pages (2,319 characters each, zero difference either way): the `-bbox-layout` extraction neither dropped nor invented text.
7. Ran 29 adversarial mutations of the source/extraction/profile and 15 review-record variations, on in-memory copies only.
8. Checked that nothing in `lawindex/`, `web/`, or the database references the schedule artifacts.
9. Ran the focused tests and the four standard checks; authored the review record; evaluated it with `--review`.

## Fidelity checks against the PDF

### Page 23 — First Schedule (142 words, 9 groups, 1 relation)

| Check | Result |
| --- | --- |
| Title `THE FIRST SCHEDULE` (w0–w2), cross-reference `[See sections 13 (3) and 16(3)]` (w3–w8) | Match, including the source's inconsistent spacing `13 (3)` vs `16(3)` |
| Caption (w9–w47), small-caps | Match. Poppler splits small-cap words at the capital (`F`/`ORM`, `C`/`HIEF`, `/T`/`HE`, …); the artifact keeps these exact tokens and positions rather than repairing them |
| Shared prefix (w48–w61) `“I, ....................., having been appointed … Commissioner` | Match; 21-dot blank and opening curly quote preserved |
| `oath` = w62–w67 `swear in the name of God` at y 173.9 | Match; this is the underlined alternative on the printed line |
| `affirmation` = w78–w79 `solemnly affirm` at y 186.6, x 90.0 | Match; printed on its own indented line directly below the oath words, as a stacked alternative |
| `continuation` = w68–w77 (`that I will bear true faith and allegiance to the`, same printed line as the oath) + w85–w140 | Match. The common words begin on the oath's line and are correctly assigned to the continuation, not to the oath. Group is non-contiguous only because watermark words w80–w84 sit between in extraction order |
| `exclusive_alternatives` relation: choices `[oath, affirmation]`, prefix `prefix`, suffix `continuation` | Present and correct |
| Watermark w80–w84 `In di aC od e` (rotated, x 276–395, y 318–421) | Labeled `nonlegal_watermark`, not dropped |
| Footer `23` (w141) | Labeled `page_number` |
| Closing `laws.”.` (w140) | Curly close-quote plus full stop preserved |

### Page 24 — Second Schedule (279 words, 44 groups, 13 relations)

**All 27 serial positions.** `entry-1` … `entry-27` each exist, are contiguous word ranges (except `entry-15`, which skips the interleaved watermark word w100), and read exactly as printed. Spot-verified spelling and punctuation kept as printed, not corrected: `Sashtra Seema Bal` (entry-15), `Border Road Development Board` (entry-21), `Indo-Tibetan`, `Income-tax (Investigation).]`, `Financial Intelligence Unit, India.]`. Entries 20, 21, 24, 25 are printed with a slightly larger left indent (x 110.8/111.0 vs 108.0) and entries 22–27 in a larger face (box height 13.3 vs 12.2); both are retained through coordinates.

**Serial 7.** `entry-7` = w58 `7.`, w59 `2` (superscript, height 7.7), w60 `***.` — three asterisks then a full stop, confirmed at 400 DPI. Note 2 (`Serial Number 7 omitted …`) links here.

**Separately omitted block.** `omitted-block` (role `omission`) = w140 `7` (superscript) + w141–w144 `*` ×4 + w145 `*]` — five asterisks with the closing bracket attached to the last, confirmed at 400 DPI. It is a distinct group after `entry-21`, not merged into any entry.

**Brackets.** Opening `[` is attached to the serial token (`[2.`, `[15.`, `[16.`, `[17.`, `[18.`, `[19.`, `[22.`, `[23.`, `[26.`, `[27.`) and closing `]` to the last token of the bracketed span (`Secretariat.]`, `Bal.]`, `(Investigation).]`, `Organisation.]`, `India.]`, `*]`, `Secretariat.]`, `Grid.]`, `Command.]`, `Team.]`). Entry 19 opens a bracket with no close on its line; entry 23 likewise; the closes are `*]` (w145) and `Grid.]` (w165) respectively — matching the print.

**13 superscript occurrences → 11 footnotes.** Every relation's marker word is a bare digit token with superscript height (7.7 pt for entries 2–21, 8.9 pt for entries 22–27), and its `note_id` equals `note-<digit>`:

| Marker | Text | Note | Scope groups | Affected words |
| --- | --- | --- | --- | --- |
| w21 | 1 | note-1 | entry-2 | w22–w39 (18) |
| w59 | 2 | note-2 | entry-7 | w60 `***.` |
| w63 | 3 | note-3 | entry-8 | **w64 `[Frontier]` only** |
| w99 | 4 | note-4 | entry-15 | w101–w104 |
| w105 | 5 | note-5 | entry-16 | w106–w111 |
| w112 | 5 | note-5 | entry-17 | w113–w117 |
| w118 | 5 | note-5 | entry-18 | w119–w123 |
| w124 | 6 | note-6 | entry-19, entry-20, entry-21, omitted-block | w125–w145 (21) |
| w140 | 7 | note-7 | omitted-block | w141–w145 |
| w146 | 8 | note-8 | entry-22 | w147–w151 |
| w152 | 9 | note-9 | entry-23, entry-24, entry-25 | w153–w165 (13) |
| w166 | 10 | note-10 | entry-26 | w167–w170 |
| w171 | 11 | note-11 | entry-27 | w172–w177 |

- **Note 3 word-level scope:** in print the bracket encloses only `Frontier` inside `8. Special ³[Frontier] Force of the Cabinet Secretariat.`; the model's affected set is exactly w64. Correct.
- **Note 5's three references:** entries 16, 17, 18 each carry their own superscript `5` and their own bracket; three separate relations. Correct.
- **Note 6's shared bracket:** `⁶[19.` opens, and the bracket closes at `*]` after the omitted block, so 20, 21, and the asterisk row are inside it. The model's scope is the four groups and affected span w125–w145. Correct.
- **Note 7's omission:** `⁷*   *   *   *   *]` is annotated separately by note 7 with scope `omitted-block`. Correct.
- **Note 9's shared entries 23–25:** `⁹[23.` opens, closes at `Grid.]`; scope entries 23–25. Correct.

**11 footnotes.** `note-1` … `note-11` read exactly as printed, including the source's own inconsistent comma usage (`319(E), dated` vs `235(E) dated`; `347, dated`), `G.S.R.` spacing, and `Omitted by G.S.R. 235(E) dated 27-3-2008.` without `notification No.`. All 11 are referenced by at least one relation; none is unreferenced or duplicated.

**Decoration.** Watermark words w79, w80, w90, w95, w100 (`od e aC di In` in extraction order; same bounding boxes as page 23) labeled `nonlegal_watermark`; footer `24` (w278) labeled `page_number`. Caption and title labeled.

**Positions.** The overlay renders show every group box tightly enclosing its printed text and every marker box sitting on its superscript glyph.

## Rejection behaviour (adversarial, in-memory copies only)

All 29 mutations were rejected with `ValueError`. The message column shows which check caught each:

| Mutation | Caught by |
| --- | --- |
| Source bytes appended / one byte flipped | `source changed` (before any extraction) |
| Extracted word text corrected (`Sashtra`→`Sashastra`) | `word text/order/coordinates changed` |
| Extracted word order swapped; a watermark word dropped; page number changed | `word text/order/coordinates changed` |
| One word dropped from note-11; one word duplicated into entry-3 | `regions must partition every source word exactly once` |
| First continuation word moved into `oath` (flattening the alternative) | `alternative wording changed` |
| `affirmation` merged into `continuation` | `missing oath region` |
| Watermark relabeled `entry`; entry-7 merged into entry-6 | `must preserve all 27 printed serial positions` |
| note-5 occurrence relinked to note-4 | `marker does not match footnote number` |
| A note-5 occurrence deleted; note-1 relation duplicated | `every superscript occurrence must resolve once` |
| note-6 scope drops omitted-block; note-7 scope moved to entry-21; note-3 affected extended into entry-9 | `amendment reference outside declared scope` |
| note-11 group removed and words folded into note-10 | `all 11 footnotes are required` |
| Page-23 relation removed / choices reordered | `oath alternatives must be explicit` / `invalid oath context` |
| Profile `source_sha256` or `extracted_layout_sha256` rebased; `schema_version` 2 | source/extraction/profile checks |
| omitted-block merged into entry-21 (with relations adjusted); note-6 scope trimmed **and** affected trimmed; note-9 scope drops entry-25 with affected trimmed; note-3 affected widened to the whole entry; `interpretation` label edited | **`layout output differs from implementation baseline`** only — see observation O2 |

Review-record variations (`assess_review`): valid record → `layout_reviewed_not_search_admitted`; stale artifact digest (the old draft's), stale profile digest, stale source digest, `parser_version` v2, `pages=[23]`, or a non-dict record → `invalid_review_binding`; `accept_layout` with non-empty findings, or decision `approve` → `invalid_review_decision`; `changes_requested` (with or without findings) → `changes_requested`; `independent_of_implementation` false, the string `"true"`, or missing `id` → `invalid_review_provenance`. Adding `search_admitted: true` to the review record has no effect; the artifact's `search_admitted` stays `false`. The CLI exits 1 for every status other than `needs_independent_review` and `layout_reviewed_not_search_admitted`. The test `test_cli_is_idempotent_without_touching_database_or_source` additionally confirms a tampered existing artifact file is refused rather than overwritten.

## Search / database boundary

- `grep` over `lawindex/`, `web/`, and `scripts/` (excluding the layout module and the separate viewer script): no code reads `data/import/schedules/` or the review record.
- The SQLite file's SHA-256 was identical before and after `schedule_layout.py`, `--review`, the full test suite, and all verification scripts. `review_decisions` still holds 4 rows, `version_admissions` 5 rows; `passages` contains no schedule text (`Sashtra`, `solemnly affirm`, `SECOND SCHEDULE` return 0 rows).
- Neither `parse()` nor `assess_review()` opens the database; the artifact hard-codes `search_admitted: false` and the review status string itself says `not_search_admitted`.

## Commands and results

| Command | Result |
| --- | --- |
| `python3 scripts/schedule_layout.py` | artifact `data/import/schedules/a111a35d….json`, `review_status: needs_independent_review`, `search_admitted: false`, exit 0 |
| `python3 -m unittest tests.test_schedule_layout -v` | 10 tests OK |
| `python3 -m unittest discover -s tests -v` | **110 tests OK**, exit 0; one non-failing SQLite `ResourceWarning` (pre-existing, noted in the gate audit) |
| `python3 scripts/verify_offline_import.py` | **ALL 26 OFFLINE IMPORT CHECKS PASSED**, exit 0 |
| `python3 scripts/verify_phase0.py` | PASS: 16 original hashes, 5 PDF/text reports, 12 manifest records, 24 unjudged queries, failure/shell fixtures; exit 0 |
| `python3 scripts/evaluate_search.py` | 6 development queries (DEV-001…DEV-006), each `expected_rank: 1`; exit 0; smoke set only |
| `python3 scripts/schedule_layout.py --review data/review/structure/rti-schedule-independent-review.json` | **`review_status: layout_reviewed_not_search_admitted`, `search_admitted: false`, exit 0** |

No `--fresh`, no database rebuild, no network, no new acquisition, no messages sent.

## Advisory observations (non-blocking; not findings against the candidate)

These do not contradict anything the artifact claims — its own `limitations` already state that graphic rules and fonts are not reconstructed — but the main agent and any viewer author should know them.

- **O1. Graphical information that only the original PDF carries.** (a) The underline beneath `swear in the name of God`, which is the print's visual signal that it is the alternative to `solemnly affirm`; (b) italics on `See` and on the `3` in `13 (3)`/`16(3)`; (c) small-caps rendering of both captions (the model has the split tokens, not the styling); (d) the horizontal footnote separator rule above note 1; (e) superscript status itself, which is present only implicitly through the marker words' smaller box height and the `amendment_reference` relation, not as an explicit word attribute; (f) the larger type used for entries 22–27; (g) the watermark's rotation. None of this is legal text, and the artifact correctly directs readers to the PDF as the visual reference.
- **O2. The implementation baseline hash is load-bearing for some scope semantics.** `validate_relations` requires `affected_word_ids ⊆ scope` and the marker ∈ scope, but not that affected equals scope-minus-marker. The five mutations in the last table row (e.g. widening note 3 to the whole of entry 8, or dropping entry 25 from note 9 while trimming the affected list) pass every semantic check and are caught only by `expected_artifact_payload_sha256`. Today that baseline is correct — I verified it against the PDF — but if a future implementation agent rebases the baseline, the semantic validator alone would not catch those particular misreadings. Re-review after any baseline change, as `SCHEDULE_LAYOUT.md` already requires.
- **O3. `assess_review` does not enforce `reviewer.type` or `reviewer.independent_legal_expert`.** The record shape in `SCHEDULE_LAYOUT.md` requires them, and my record supplies them, but a record omitting them still evaluates to `layout_reviewed_not_search_admitted`. Consider the JSON shape, not the tool, as the enforcement of the disclosure.
- **O4. Marker detection is fixture-specific.** Markers are identified as any all-digit token inside an `entry`/`omission` group. That is exact for these pages (every serial is `N.` with a dot, so no serial is a bare digit) but would misfire on a schedule entry containing a bare number. This is consistent with the parser's stated scope of pages 23–24 only.
- **O5. Note 6's affected span includes w140, the superscript `7`.** This is faithful to the print (the `7` sits inside the `⁶[ … ]` bracket) and is the consistent result of "scope minus own marker", but a viewer highlighting note 6's affected words will also highlight note 7's marker.
- **O6. Poppler binding.** `extracted_layout_sha256` is the output of `pdftotext 25.10.0 -bbox-layout`. A different Poppler build may tokenize small caps or the rotated watermark differently and would fail closed with `word text/order/coordinates changed`, which is the intended behaviour, but it means the model is reproducible only with a compatible Poppler.
- **O7. Cosmetic:** the candidate artifact file has mode `0600` (temp-file default) while the earlier draft is `0644`; no functional consequence.

## Limitations of this review

- Performed by an AI agent, not a legal expert; I compared the model to the retained PDF and did not assess whether the printed amendments reflect the law as it stands.
- Visual comparison was done on my own 200 DPI and 400 DPI Poppler renders of the retained bytes; I did not consult India Code online or any other copy (network use was out of scope).
- I did not review `scripts/render_schedule_review.py` (the separate viewer handoff) beyond confirming it does not write the database; the PDF, not the viewer, was my source of truth.
- The review record is bound to artifact `a111a35d…`, profile `5ddf9880…`, source `c1ef189e…`, and parser `rti-schedule-layout-v1`. Any change to any of those invalidates it and requires re-review.
