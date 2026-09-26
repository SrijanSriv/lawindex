# Checklist for reviewing India Code's response to the 20-Act access request

Prepared 20 September 2026 (second pass), for use when the user's pending request to India Code (see [ACCESS_AND_REUSE.md](ACCESS_AND_REUSE.md#access-request-status)) receives a reply. **No follow-up message is sent by this checklist or by this session.** This document does not describe, quote, paraphrase, or guess the contents of the user's original email — only the questions a reply should let us answer, drawn from what [ACCESS_AND_REUSE.md](ACCESS_AND_REUSE.md#operational-proposal-subject-to-that-decision) already flagged as open.

Everything below is **unknown until the reply is read**. Filling this in is a future task, not something this session performs speculatively.

## How to use this

When a reply arrives, read it once, then go through every row below and record: the reply's actual wording (quoted, not paraphrased into a stronger claim), and which of `granted` / `denied` / `conditional` / `not addressed` applies. "Not addressed" is a normal, expected outcome for several rows — do not infer permission for anything the reply is silent on.

## Scope of the grant (or refusal)

| # | Question | Why it matters | Status once read |
| --- | --- | --- | --- |
| 1 | Exactly which Acts are covered? Are all 20 requested Acts covered, a subset, or a different list than requested? | The 20-Act request does not itself expand the 10-Act Phase 0 candidate corpus (see [CORPUS.md](CORPUS.md)); a reply might grant fewer, more, or different Acts than either list. | — |
| 2 | Does the grant cover only the Act text, or also associated rules, regulations, notifications, and other linked instruments? | [SOURCE_DISCOVERY.md](SOURCE_DISCOVERY.md) found some Acts have hundreds to thousands of linked subordinate records (e.g. Environment Act: 926 notifications); scope must be explicit, not assumed. | — |
| 3 | Which representations are supplied or permitted — structured HTML/JSON, PDF, both, or a different export format entirely? | The accepted [conflict policy](CONFLICT_POLICY.md) depends on having (or being told we may keep using) both representations to detect and disclose disagreements like RTI-001. | — |
| 4 | Is a specific delivery method specified (bulk export, an API, individually-fetched pages, a data dump on request), or does the grant only confirm that our existing bounded fetching approach is acceptable? | [ACCESS_AND_REUSE.md](ACCESS_AND_REUSE.md) found no documented, supported bulk API contract during discovery; a reply may introduce one, endorse ad hoc fetching, or require something else entirely. | — |

## Automated access and operational limits

| # | Question | Why it matters | Status once read |
| --- | --- | --- | --- |
| 5 | Is automated/scripted access itself permitted, or only manual/individual retrieval? | The Terms of Use observed in Phase 0 said automated access requires express written permission; this is the central gate the whole request exists to clear. | — |
| 6 | Are there request-rate limits, concurrency limits, or time-of-day restrictions specified? | Needed to replace our conservative, self-imposed proposal (one outstanding request, 2+ second spacing) with the source's actual terms, if any. | — |
| 7 | Is there a required user-agent string, API key, contact registration, or other identification to include in requests? | Needed before any Phase 1 importer would be allowed to make live requests (out of scope for this session, which makes none). | — |
| 8 | Is a refresh/re-crawl cadence specified or implied (e.g. "no more than once a day")? | Feeds directly into Phase 8's refresh-cadence design; do not invent a cadence absent explicit guidance. | — |

## Storage, indexing, and display

| # | Question | Why it matters | Status once read |
| --- | --- | --- | --- |
| 9 | Is local storage/retention of fetched content permitted, and for how long? | Determines whether retained fixtures beyond the current small discovery sample may be kept at all. | — |
| 10 | Is building a structured, searchable index from the content permitted? | This is the core of what LawIndex needs; a reply might permit reading/reference use but not indexing. | — |
| 11 | Is public display of excerpts permitted? Full-text display? Are there length or context limits? | Directly determines what a search result page is allowed to show once a search engine exists. | — |
| 12 | Are attribution requirements specified (notices to retain, required linking back to India Code, a required disclaimer)? | The Terms of Use observed in Phase 0 required notices to be retained for personal/reference use; a grant for broader use may impose its own attribution terms. | — |
| 13 | Is commercial vs. non-commercial use distinguished, and which does this grant cover? | LawIndex's intended public search product needs this classified explicitly, not assumed favorably. | — |

## Redistribution and export (only relevant if intended)

| # | Question | Why it matters | Status once read |
| --- | --- | --- | --- |
| 14 | Is redistribution or export of the underlying corpus (as opposed to a live search UI over it) permitted? | The Copyright Policy observed in Phase 0 separately restricted database extraction/redistribution; a grant for search use may not cover this. | — |
| 15 | If redistribution is permitted, are there conditions (format, audience, fee, attribution) attached? | — | — |

## Everything a reply is silent on

For any row above marked "not addressed": do not infer permission, do not infer denial. Record it as an open question, and if the user later says they plan to ask again (as [ACCESS_AND_REUSE.md](ACCESS_AND_REUSE.md) already notes for scope beyond 20 Acts), track it there rather than guessing here.

## What this checklist does not do

- It does not send anything to India Code. No follow-up question from this list is dispatched by this session.
- It does not assume the user's original email asked about every row above — the original email's content is unknown to this session and is not guessed at anywhere in this document.
- It does not change the ten-Act Phase 0 candidate scope, the accepted conflict policy, or any admission decision already made. Even a fully favorable reply only clears the *access/reuse* axis (see the [readiness manifest](READINESS_MANIFEST.md)'s four-axis table) — fidelity review of the remaining candidate Acts is separate, unfinished work.

## Update — 22 September 2026: permission reported granted

The user reports that the ministry permits use of the information for this personal, non-commercial project and that the project may choose any 20 Acts. The original reply has not been inspected; no wording is attributed to the ministry verbatim. This supersedes the historical pending-response status above. See [authorization record](../../data/phase3/access-authorization.json), [proposed inventory](../phase-3/INVENTORY.md), and [Phase 3 architecture](../phase-3/ARCHITECTURE.md). No commercial license, additional Act allowance, or ministry-specific rate limits are inferred. Fidelity review and source-version checks still apply.
