# Phase 0 — metadata availability and normalization

Observed 20 September 2026. Evidence: [11 rendered Act observations](../../data/discovery/observations/acts.json), [raw RTI item](../../data/discovery/rti-item.body), [10 raw section records](../../data/discovery/rti-sections-page-0.body), five PDF captures, and the rendered RTI Rules item. Availability here applies only to this sample.

Source metadata values are arrays carrying `value`, `language`, `authority`, `confidence`, and `place`. Retain the arrays in raw storage. A source `confidence` value is not our extraction-confidence score.

## Document metadata

| Target concept | Observed source / extraction | Example or availability | Reliability and missing-value handling |
| --- | --- | --- | --- |
| Source record ID | JSON `uuid` / Act URL | RTI `37520cf3-...` | Source identity, not proof of immutable legal version |
| Source handle | JSON `handle` | RTI `123456789/496169` | Retain separately; old/new handle equivalence unverified |
| Act ID | `dc.identifier.act_id`; section-link filter | Present in all 11 inspected navigation links | Use for observed parent joins, not by parsing components of the string |
| Citation ID | `dc.identifier.givenid` | RTI `2005-22` | Keep raw; do not assume universal format |
| Short title | `dc.title`; Title row | Present in 11/11 | Preserve punctuation; optional separate search-normalized form |
| Long title | `dc.title.long_title`; Long Title row | Displayed in 10/11; absent on Kerala sample | Null when not present; never generate one from a summary |
| Act number | `dc.identifier.act_number` | RTI `22`; present in 11/11 | Store string to preserve source formatting |
| Act year | `dc.date.act_year` | RTI `2005`; present in 11/11 | Normalize a valid year separately from raw text |
| Enactment date | `dc.date.enact_date`; Enact Date row | RTI JSON `2005-06-15`; UI `15-06-2005` | Explicit date-format parsing; preserve competing observations and leave canonical value null until reconciled; see conflict policy |
| Issue/publication date | `dc.date.issued`; Published date on rule | RTI `2005-06-15`; rule displayed `31-07-2012` | Do not equate with assent, commencement, or Gazette publication without evidence |
| Enforcement | `dc.date.enforcement_date` | Displayed in 8/11; RTI is a sentence | Preserve raw string; parsed date only when unambiguous; absence does not mean not in force |
| Displayed modification date | `dc.date.last_modified` | Displayed in 7/11; RTI `2025-11-18` | Distinct from fetch time and top-level repository `lastModified` |
| Repository update time | JSON `lastModified` | RTI `2026-09-12T18:02:24.194212Z` | Useful for change detection, not legal effect or textual consolidation date |
| Repository accession time | `dc.date.accessioned` | RTI `2026-07-10T20:10:39Z` | Migration/import provenance, not enactment |
| Ministry | `dc.identifier.ministry_name` and `_id` | Displayed in 11/11 | Preserve observed label and identifier; historical administrative accuracy unverified |
| Department | `dc.identifier.department_name` and `_id` | Displayed in 5/11 | Null when absent; do not copy ministry into department |
| Instrument kind | `dc.identifier.collection` | `ACT`, `SECTION`; rule UI `RULE` | Use for Act/rule/section classification |
| Source subject category | `dc.type`; Type row | Social, Economic, Developmental, Historical; 10/11 | **Not** instrument kind or legal status; keep as `source_category` |
| Jurisdiction | `dc.identifier.state_name`; Jurisdiction row | All sampled Acts display `CENTRAL` | Source classification; do not infer from place names in titles |
| Notification | Notification No. row | Displayed in 5/11; can contain a full citation sentence | Preserve raw text; exact JSON key not verified in this sample |
| Source repeal flag | `dc.identifier.repealed` | RTI string `false` | Parse only literal known values; preserve as source assertion, not independently established validity |
| Preamble | `dc.identifier.preamble_description` | RTI HTML including recitals | Preserve separately from title, history, and section text; sanitize for display |
| Legislative history | `dc.legislation.history` | RTI narrative HTML | Contextual source material, not statutory passage or a complete amendment ledger |
| Summary | `dc.description.abstract` | RTI prose summary | Exclude from exact-legislation index; do not confuse with enacted text |
| PDF source | `/pdf-viewer/{item UUID}/{bitstream UUID}` | Displayed for all 11 Acts | Retain viewer URL, file identity, and separately verified download URL |
| Public source URL | Observed `/act/{UUID}` / `/items/{UUID}` | Verified browser navigation | Do not blindly use `dc.identifier.uri`, which points to a test host in RTI |
| Language | Metadata value `language`; file content/labels | All sampled JSON language attributes null; inspected PDF text English | Store observed/inferred language with its basis; UI language is not document language |

## Structure and related instruments

| Target concept | Observed source / extraction | Example | Decision |
| --- | --- | --- | --- |
| Provision source ID | Section item UUID plus `dc.identifier.section_id` | Section 6 UUID `822280bc-...` | Retain both; namespace old numeric identifiers by source/parent |
| Provision heading | Section `dc.title` | Request for obtaining information | Distinct field from full body |
| Provision label | `dc.identifier.section_number` | `6`; Environment UI has `5A` | String, not integer |
| Ordering | `dc.identifier.order_number` | Separate from section label | Numeric sort only when valid; missing/duplicate order is a validation issue |
| Parent Act | `dc.identifier.act_id`, `_act_name`, `_act_number` | All 10 RTI sections join the same Act ID | Verify parent existence and match before indexing |
| Provision body | `dc.identifier.section_page_note` | HTML clauses, provisos, and breaks | Preserve raw HTML; derive safe text without changing wording |
| Footnotes | `dc.identifier.section_footnote` | RTI section 1 amendment footnote | Keep with source provision and link markers; do not drop as boilerplate |
| Subsections/clauses | Embedded body text | RTI section 6 `(1)`, `(2)`, `(3)`, `(a)`, `(b)` | Parse cautiously in Phase 1/2; not demonstrated as separate API entities |
| Chapter membership | PDF headings | RTI Chapters I–VI visible in PDF | No chapter field found in sampled JSON; derive with evidence or leave unknown |
| Schedules | Schedules navigation; PDF | RTI First/Second Schedules | First-slice schedules require extraction; API schedule schema not yet verified |
| PDF page hints | `dc.identifier.page_number`, `_page_from`, `_page_to` | Section 6 says `7`, linked PDF uses `9`; range fields can be `0` | Preserve hints; do not create authoritative anchors from them |
| Next-section hint | `dc.identifier.next_section` | RTI `2.Definitions.` | Raw navigation hint, not canonical ID |
| Linked instrument | Act UI counts and `/items/{UUID}` links | RTI two rules; Environment many instrument types | Metadata first; recurse only through explicit selected scope |
| Linked source ID | `dc.identifier.linked_id` | RTI section 1 has a rule-like source ID | Relationship meaning not yet fully verified; do not infer applicability |
| Amendment relationships | Act UI button, PDF notes | RTI PDF lists amending Acts | Preserve notes; do not assume an exhaustive machine-readable version graph |

## Raw versus normalized values

For every normalized field keep its source field name, raw value, representation ID/hash, and transformation version. Use `null` for unknown values. Distinguish a verified empty collection from a failed request or an uninspected collection.

The [accepted conflict policy](CONFLICT_POLICY.md) governs selection, review, and admission. A source metadata confidence value, OCR score, reviewed fidelity, and legal authority are distinct concepts.

The current fixture demonstrates why legal identity, repository metadata, source claims, and selected display text must remain separate. A more structured representation can still be older than its linked PDF.
