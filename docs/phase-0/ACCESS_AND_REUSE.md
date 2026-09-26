# India Code — access and reuse observations

Observed 20 September 2026. This records the portal's stated conditions; it is not a conclusion about their legal enforceability or copyright in legislation.

## Published conditions

The rendered [Terms of Use](https://indiacode.gov.in/info/term-of-use), dated 22 June 2026, say automated access requires express written permission. They permit personal, non-commercial reference use with notices retained and restrict commercial reproduction. The disclaimer limits completeness/accuracy assurances and gives the English Act version precedence in a discrepancy.

The rendered [Copyright Policy](https://indiacode.gov.in/info/copyright-policy), also dated 22 June 2026, asserts rights over portal content, metadata, databases, and software. It restricts systematic database extraction, reproduction, derivative use, and mirroring without permission. It separately says API use requires written authorization and API data storage/redistribution requires permission. It describes limited research/reference uses and a written-request route to the Legislative Department.

These findings came from rendered browser text. The retained `terms.body` and `copyright.body` files are **application shells**, not complete copies of those policies. No permission had been requested during the original inspection; the user subsequently reported sending a request, as recorded below. No terms-acceptance form was submitted by the agent.

## Access request status

**Request sent by the user; reply/permission pending as of this update on 20 September 2026.** The user reports emailing the India Code team requesting corpus access for **20 Acts**, and plans to contact them again if more Acts are needed. The exact sending date, email text, list of Acts, requested usage rights, and any response were not supplied. This records the user's report, not an independently inspected email.

The 20-Act request is an access scope, not an approved allowance or a change from our ten-Act initial candidate corpus. Do not infer permission for all Acts, associated instruments, automated updates, storage, public display, or redistribution. When a response arrives, record its exact scope and conditions. Expansion beyond the requested 20 Acts should follow the user's stated plan to request additional scope.

## Access diagnostics

- New-domain `/robots.txt`: retained HTTP 502 response. This is **not** a permissive robots file.
- Old-domain `/robots.txt`: retained HTTP 404 response. It says nothing about new-domain permissions.
- HEAD on the new homepage returned 405 while GET succeeded. Do not use HEAD failure alone to declare the source unavailable.
- Some early clients/tool requests returned 502 or empty rendered content while a browser and subsequent GET worked. Do not infer broad availability guarantees from this single session.
- The frontend configuration includes a UI rate limiter. It is not a published crawler allowance or API contract.

## Decision before bulk ingestion or public reuse

The intended LawIndex service goes beyond private reference reading. Resolve the source's access/storage/public-display conditions before expanding the discovery sample into a crawler or publishing a corpus. That may mean operator permission, an appropriate export arrangement, or a reviewed alternative source/access basis. Technical reachability does not settle this question.

The limited retained artifacts are local discovery evidence, not a licensed corpus release. Keep them out of a public data distribution until the decision is documented. No source-provided branding or notices have been removed from the original files.

When reviewing the reply to the user's 20-Act request, check whether it covers: the public legal search purpose; the specific Acts; desired metadata, sections, PDFs, and change feeds; local storage/indexing; display of attributed excerpts and source links; commercial/non-commercial use; update frequency; request limits; and redistribution/export if needed. Confirm a supported API/export, retention, and attribution conditions where available. These are questions to resolve from the reply or a later clarification, not claims about what the user already wrote. No additional message has been sent by the agent.

## Operational proposal, subject to that decision

Use one outstanding request, at least two seconds between requests, explicit URL manifests, caching, finite retries with backoff, and a stop on access denials or throttling. This is our proposed conservative budget, **not** a limit authorized by the source. The Phase 0 capture helper is a bounded diagnostic tool, not a production crawler.

## Update — 22 September 2026: permission reported granted

The user reports that the ministry permits use of the information for this personal, non-commercial project and that the project may choose any 20 Acts. The original reply has not been inspected; no wording is attributed to the ministry verbatim. This supersedes the historical pending-response status above. See [authorization record](../../data/phase3/access-authorization.json), [proposed inventory](../phase-3/INVENTORY.md), and [Phase 3 architecture](../phase-3/ARCHITECTURE.md). No commercial license, additional Act allowance, or ministry-specific rate limits are inferred. Fidelity review and source-version checks still apply.
