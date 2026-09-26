# RTI schedule layout contract

Implementation complete for retained PDF pages 23–24; the separate AI reviewer has accepted the current layout (see [review](INDEPENDENT_SCHEDULE_REVIEW.md)). Private viewer verification and the bounded Phase 2 gate audit are complete; see [gate audit](PHASE2_GATE_AUDIT.md). This is a positive source-position model, not a search admission or a reconstruction of legally current wording.

## Decision

Do not force the schedules into the section-body representation. Use exact PDF words and bounding boxes, plus explicit relationships between those words. Keep the original PDF as the visual reference. Do not concatenate both oath alternatives into one sentence, infer a renumbered list from amendment superscripts, or detach shared brackets from the entries they enclose.

`scripts/schedule_layout.py` implements this bounded parser. `data/review/structure/rti-schedule-layout-profile.json` binds the source PDF, extracted word/layout hash, word-to-region partition, relationships, and expected output payload. The profile records that the implementation agent established these baselines during its own visual review; it is not an independent acceptance record.

The old `rti-schedule-quarantine.json` and `schedule_outcome()` remain valid negative fixtures for the PLAIN-TEXT splitter. They do not prohibit a separate, position-preserving representation. No existing search review is changed.

## Source and output

- Source: `data/discovery/rti-2005-pdf.body`, pages 23 and 24, bound to the retained SHA-256.
- Extraction: Poppler `pdftotext -bbox-layout`, page-bounded, with a 60-second timeout. The exact words, order, dimensions, and coordinates are hashed. Tool output drift requires investigation/review; it is never silently rebased.
- Model: all 142 words on page 23 and 279 on page 24. Each word has an ID, exact extracted text, and a box in PDF points measured from the top-left corner.
- Primary groups partition every word exactly once, including headings, cross-references, captions, watermarks, and page numbers. Nonlegal decoration is labeled rather than dropped from the source model.
- Relationships reference existing word/group IDs; they do not manufacture replacement legal text.
- Artifacts are written atomically under `data/import/schedules/<artifact_sha256>.json`. Repeated builds are identical; an existing different/corrupt file is refused. These private artifacts do not modify the SQLite database.

The artifact includes `source_capture`, the fixed repository source path, PDF SHA-256, and actual page numbers. A consumer must verify the known source file's bytes before presenting links and must not follow arbitrary artifact-supplied filesystem paths.

## First Schedule

The model records separate `oath` and `affirmation` regions, with an `exclusive_alternatives` relationship and shared prefix/continuation. The common “that I will…” words begin on the same printed line as the oath option and belong to the continuation, not exclusively to that option. The model retains their actual positions.

A viewer must show both choices with their printed relationship. It must not insert a default choice, flatten the alternative into the common sentence, or claim an edited oath is an authentic source quotation. Graphic rules, fonts, and the handwritten-name blank are not reconstructed as a form; the original PDF remains the visual reference.

## Second Schedule

The model preserves all 27 printed serial positions, including serial 7's omission notation, and a distinct unnumbered omitted block after serial 21. It does not collapse the numbering or interpret current applicability.

Thirteen superscript occurrences link to eleven separately stored footnote regions:

- Note 5 has three occurrences, for printed entries 16, 17, and 18.
- Note 6's bracketed group covers entries 19–21 and the following omitted block; note 7 separately annotates that omission.
- Note 9's group covers entries 23–25.
- Note 3 annotates the bracketed word within entry 8, not the complete entry as newly substituted text.
- The other references retain their printed entry scope; source spelling and punctuation are not corrected.

Every occurrence must resolve exactly once to the matching numbered footnote. Scope groups and affected words remain explicit references to the original positioned words. These are printed-annotation relationships, not determinations of historical legal effect.

## Validation and acceptance

```sh
python3 scripts/schedule_layout.py
python3 -m unittest tests.test_schedule_layout -v
```

The CLI prints the immutable artifact path and digest. Without a separate review its status is `needs_independent_review`. Validation rejects changed source bytes, coordinates/text/order, missing/duplicate words, invalid alternative regions, bad amendment links, unsupported versions, and output differing from the implementation baseline. The profile's baseline is a regression reference, not proof that the implementation agent's interpretation is right.

The independent agent must author `data/review/structure/rti-schedule-independent-review.json` in this exact shape:

```json
{
  "schema_version": 1,
  "artifact_sha256": "actual CLI artifact digest",
  "profile_sha256": "actual artifact profile_sha256",
  "source_sha256": "actual artifact source_sha256",
  "parser_version": "rti-schedule-layout-v1",
  "pages": [23, 24],
  "reviewer": {
    "id": "actual reviewer identity or honestly disclosed agent identity",
    "independent_of_implementation": true,
    "type": "ai_agent",
    "independent_legal_expert": false
  },
  "decision": "accept_layout",
  "findings": []
}
```

Use `changes_requested` and actual findings if anything is wrong. The reviewer should add evidence/procedure details to its companion Markdown report. Independence here means a separate review agent from the implementer, not an independent legal expert. The implementation agent must not fill in acceptance on the reviewer's behalf.

```sh
python3 scripts/schedule_layout.py --review data/review/structure/rti-schedule-independent-review.json
```

Only a matching separate acceptance yields `layout_reviewed_not_search_admitted`. Changed artifacts/profile/source/parser invalidate the review binding. Findings or mismatched binding yield a nonzero CLI exit. No outcome of this tool ever sets `search_admitted` to true or grants public reuse permission.

The independently accepted artifact digest is `a111a35d9a490fe6a2f789c41e21648c4a4e565333db0d7d153fdbe671544288`. Rebuild and use the emitted digest rather than assuming this remains current after changes. Earlier implementation drafts may remain in the private artifact directory; do not review a draft merely because it is the first file in a directory listing.

## Why this can satisfy the bounded Phase 2 gate

The gate concerns faithful parsing, traceability, and controlled failures; it does not require every parsed representation to become a search result. This representation supplies a positive schedule model that can be checked against the retained PDF. Closure still requires separate source review and verified local presentation; it cannot be claimed from passing self-authored tests alone. General schedule/table parsing, searchable schedule passages, and a larger corpus remain future scope.
