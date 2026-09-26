# Independent review: RTI schedule model and Phase 2 fidelity

You are a separate review agent, not the implementation agent. Audit the source fidelity and acceptance boundary of the new RTI schedule layout model. Do not assume the implementation summary, profile, or passing tests establish correctness.

Read `docs/phase-2/SCHEDULE_LAYOUT.md`, `docs/phase-2/PHASE2_GATE_AUDIT.md`, `scripts/schedule_layout.py`, and `tests/test_schedule_layout.py`. Rebuild the candidate with `python3 scripts/schedule_layout.py` and record its emitted path/digest. The source is the retained `data/discovery/rti-2005-pdf.body`, pages 23 and 24. Verify its hash yourself. Render those pages yourself with Poppler and inspect them visually; existing PNGs may be secondary evidence but are not a substitute for looking at the source. No network, messages, new acquisition, or public source publication.

Compare the artifact to the PDF, not merely to the profile that generated it. Check all words/positions/regions; the First Schedule's oath versus affirmation alternatives and shared continuation; all 27 Second Schedule serial positions; the separately omitted block; all 13 superscript occurrences and all 11 footnotes; note 3's word-level scope; note 5's three references; note 6's shared bracket; note 7's omission; note 9's shared entries 23–25. Check preserved spelling, punctuation, brackets, asterisks, footer/watermark labeling, and source/page anchors. Identify any meaning or layout lost by the model, including graphical information that requires the original PDF.

Review rejection behavior: source/output changes, missing/duplicated words, incorrect footnote/scope links, and stale review digests must fail. Confirm neither model generation nor independent acceptance adds schedules to SQLite/search or grants reuse permission. You may use temporary mutated fixtures for adversarial tests; do not edit real evidence or the implementation to make tests pass.

Allowed persistent outputs ONLY:
1. `docs/phase-2/INDEPENDENT_SCHEDULE_REVIEW.md`: verdict, precise findings with source-page/word/group identifiers, methods, hashes, commands/results, and limitations.
2. `data/review/structure/rti-schedule-independent-review.json`: the exact digest-bound shape specified in SCHEDULE_LAYOUT.md, filled with real values. Set decision to `accept_layout` only if all checks actually pass with no unresolved findings; otherwise use `changes_requested` and enumerate findings.
3. Your own private evidence renders under `data/import/independent-schedule-review/`.

Do not modify the parser, profile/baselines, database/schema, source bytes, prior review decisions, search API/UI, inspector, or phase status. Do not independently grant search admission. Disclose yourself as an AI review agent, not a legal expert; record actual timing only if measured, otherwise say not separately instrumented.

Run the focused schedule tests and standard full checks (`python3 -m unittest discover -s tests -v`, `python3 scripts/verify_offline_import.py`, `python3 scripts/verify_phase0.py`, `python3 scripts/evaluate_search.py`). No `--fresh`, no real database rebuild. Evaluate the final review record with `python3 scripts/schedule_layout.py --review data/review/structure/rti-schedule-independent-review.json` and report the actual status. Leave the final Phase 2 closure decision to the main agent.
