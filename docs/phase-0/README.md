# Phase 0 — start here

**Phase 0 answered: “Can we turn the source material into trustworthy input for a search engine?”**

We investigated India Code, saved a small sample, found problems in its representations, decided how to handle them, and built an offline importer that prepares reviewed provisions for later search.

**Current status, 20 September 2026: the bounded offline technical work is complete. We can proceed to local Phase 1 development.** India Code's response to the request for access to 20 Acts remains pending. Expanded acquisition and public use still depend on the applicable permission.

## What we actually have

There are three different scopes. Keeping them separate makes the other documents easier to understand:

| Scope | What it means |
| --- | --- |
| **20 Acts requested** | The amount of access requested from India Code. A request is not permission, and these are not 20 imported Acts. |
| **10 candidate Acts** | Our proposed initial collection. We inspected their available metadata, but have not reviewed all their text. |
| **4 reviewed provisions across 2 Acts** | The small slice actually prepared and accepted for local technical use. |

The four provisions are:

- **RTI Act, section 6:** requests for information.
- **RTI Act, section 8:** exemptions from disclosure.
- **Environment (Protection) Act, section 3:** Central Government powers to protect and improve the environment.
- **Environment (Protection) Act, section 5A:** appeals to the National Green Tribunal.

These descriptions identify the provisions; they are not advice about their current applicability. Reviewing four provisions does not mean either entire Act has been approved.

## What we learned from the source

India Code moved to a new domain and uses a website that loads its content dynamically. Simply downloading a webpage can return the website's empty application shell instead of legal text.

More importantly, different representations can disagree:

| Problem we found | Decision and current treatment |
| --- | --- |
| RTI section 8's website text differs from its linked PDF | Preserve both. Use the reviewed PDF-derived whole section for our slice and disclose the disagreement. Do not mix the two wordings. |
| RTI section 6's website page hint says 7, but its provision starts on PDF file page 9 | Preserve the original hint, but use the verified page-9 link for that exact PDF. |
| Kerala Act listing and detail pages show different dates | Retained-PDF investigation supports selecting 14 August 2026 for the enactment-date field. Both observations remain recorded; the reason the listing displayed the other date is not fully established. The Act stays outside our searchable slice. |
| RTI Rules contain a scanned PDF with faulty machine-read text | Keep the file and metadata, but exclude its rule text until a future extraction/review effort. |

Our governing rule is: **keep the evidence, make the selection explicit, and exclude text we cannot verify.** A reviewed PDF is our reference snapshot; its format does not prove that it represents currently operative law.

## What we built

The offline importer reads the saved files and prepares a small local SQLite database. It makes no source requests.

```text
Saved source files
    → extract the selected provisions
    → check source and reviewed-text fingerprints
    → apply review and conflict decisions
    → store admitted provisions and source links
```

Each provision is tied to its source file, extraction method, review record, and verified PDF location. The importer checks both the original file and the extracted wording against recorded fingerprints. If either changes unexpectedly, the affected text loses its admission instead of silently replacing the reviewed version.

We also prepared six development questions with expected provision targets. They will help test search once it exists. **No search engine or retrieval-performance result exists yet.**

## What the reviews caught

The agents did more than write documentation. Implementation reviews exposed defects and led to fixes:

- Withdrawing a review could previously leave its provision admitted in an existing database.
- Changed extraction output could previously pass if the extraction-version label stayed the same.
- Removing and restoring an Act could leave contradictory database state.
- A PDF page image mentioned in a review was not retained. It has now been regenerated, with its actual later provenance disclosed.

The current suite has **26 passing regression checks**, including these failure cases, repeated imports, source anchors, footnotes, exclusions, and excerpt mapping. All four documented reproduction commands were rerun successfully in an isolated copy. (A 26th check, added 2026-09-21, guards against a PDF page-number footer digit leaking into admitted body text at a page boundary — see [UI_VERIFICATION.md](../phase-1/UI_VERIFICATION.md#remediation-2026-09-21) for what that fixed.)

The text reviews were performed by AI agents. The independent engineering review was a separate agent review, not a qualified human legal review.

## What remains—and whether it blocks moving on

| Item | Status |
| --- | --- |
| Local search development using the four provisions | **Ready to begin in Phase 1.** |
| India Code permission | Pending separately; needed for the affected expanded acquisition and public-use work. |
| More provisions and Acts | Later corpus expansion; not required to finish this bounded Phase 0 slice. |
| OCR, other languages, historical legal-effect reconstruction | Outside the initial slice. |
| Independent legal-expert review | Not performed; retain that qualification. |

Some earlier documents say the “overall ingestion-readiness gate remains open.” That includes access permission and broader corpus readiness. It does not undo completion of the bounded offline technical work. Historical review reports also retain findings that were subsequently fixed: read their appended remediation notes for current status.

## How to read the rest of this directory

Start with the first three; use the others when you need their specific details.

| Document | Read it to understand… |
| --- | --- |
| [READINESS_MANIFEST.md](READINESS_MANIFEST.md) | Exactly what is ready today, what was fixed, and what remains excluded. |
| [SOURCE_DISCOVERY.md](SOURCE_DISCOVERY.md) | What we observed on India Code and the evidence behind the source problems. |
| [CONFLICT_POLICY.md](CONFLICT_POLICY.md) | The rules for choosing text, preserving disagreements, and allowing content into the index. |
| [CORPUS.md](CORPUS.md) | Why the ten Acts were selected and where the initial scope stops. |
| [METADATA_MATRIX.md](METADATA_MATRIX.md) | What each source field means and how we handle missing or conflicting values. |
| [ACCESS_AND_REUSE.md](ACCESS_AND_REUSE.md) | The source's observed access conditions and the pending request. |
| [ACCESS_RESPONSE_CHECKLIST.md](ACCESS_RESPONSE_CHECKLIST.md) | How to assess India Code's reply when it arrives. |
| [RTI_RULES_OCR_ASSESSMENT.md](RTI_RULES_OCR_ASSESSMENT.md) | Why the scanned rules were excluded and what future OCR work would require. |
| [INDEPENDENT_REVIEW.md](INDEPENDENT_REVIEW.md) | The separate agent's engineering review, its original findings, and later remediation. |
| [INSPECTION_FOLLOWUP.md](INSPECTION_FOLLOWUP.md) | The additional inspection that found the extracted-text and restoration bugs, followed by their fixes. |

### A few terms used in those documents

- **Corpus:** the collection of documents or provisions we choose to work with.
- **Fixture:** a saved example used for development and testing.
- **Hash/digest:** a fingerprint that lets us detect changes in a file or text. It detects change; it does not establish truth.
- **Provenance:** the record of where text came from and how we processed and reviewed it.
- **Admitted:** accepted for the declared local technical slice. It does not mean permission for public use or certification of legal effect.
- **Quarantined:** retained as evidence but excluded from normal retrieval.

## Reproduce the work

From the project root, with Python 3 and Poppler installed:

```sh
python3 scripts/build_phase0_artifacts.py
python3 scripts/verify_phase0.py
python3 scripts/offline_importer.py --fresh
python3 scripts/verify_offline_import.py
```

`--fresh` rebuilds the generated local database. Original source captures are preserved. The output is four admitted provisions, not an index of complete Acts.

The next product milestone is described in [Phase 1](../../PHASES.md#phase-1--build-the-first-working-search-engine): **query → relevant provision → exact text and context → original source.**
