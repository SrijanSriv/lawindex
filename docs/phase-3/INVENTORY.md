# Selected 20-Act inventory

Prepared and selected 22 September 2026. Permission to choose up to 20 Acts is recorded from the user in [the authorization record](../../data/phase3/access-authorization.json). The selection is now frozen for this acquisition batch. All 20 Acts have subsequently been captured; see [acquisition status](ACQUISITION_AND_CANDIDATES.md). Selection/capture does not establish completeness, commencement, or current legal effect. The original ministry reply was not inspected.

The first ten reuse our existing candidates, including difficult parser fixtures. The next ten broaden practical query coverage. Kerala and RTI Rules remain historical quarantine fixtures outside this proposed 20-Act acquisition inventory. No new corpus text was downloaded in this planning increment; official search references are discovery leads, not verified ingestion endpoints. Resolve each central instrument identity on the current portal before fetching.

| # | Act / source reference | Why include it |
| --- | --- | --- |
| 1 | [The Right to Information Act, 2005](https://indiacode.gov.in/act/37520cf3-5c3f-4c0b-aa4a-5985e6f522bf) | Ordinary-language queries, chapters, schedules, amendment footnotes, staged commencement; representation-conflict fixture. |
| 2 | [The Digital Personal Data Protection Act, 2023.](https://indiacode.gov.in/act/c058fa9f-eaf0-4ca3-98f1-3443b087bca9) | Newer Act, missing department and commencement metadata, terminology around data processing. |
| 3 | [The Copyright Act, 1957](https://indiacode.gov.in/act/6b893162-631a-453b-a7b9-89685716889b) | Older amended Act, larger section inventory, notification text, missing displayed modification date. |
| 4 | [The Mental Healthcare Act, 2017](https://indiacode.gov.in/act/63a1a7f4-fc92-49c3-808b-6f0bc3ede89c) | Rights and health terminology, distinct enactment and enforcement dates. |
| 5 | [The Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013](https://indiacode.gov.in/act/6497706b-d8a5-4486-a968-9975498de966) | Long title, common acronym versus statutory wording, missing department. |
| 6 | [The Foreign Contribution (Regulation) Act, 2010](https://indiacode.gov.in/act/e62ef217-2250-4380-935c-d9ad915454b1) | Different subordinate-instrument types and common acronym queries. |
| 7 | [The Occupational Safety, Health and Working Conditions Code, 2020](https://indiacode.gov.in/act/68f0e43a-9120-4028-8e08-0f63f5a0e061) | A Code stored in the ACT collection; commencement differs from enactment year. |
| 8 | [The Repealing and Amending Act, 2023](https://indiacode.gov.in/act/fd1a7f72-25b4-48af-82d0-6c3c6509b098) | Amending/repealing instrument; Historical is a source category, not a legal-status conclusion. |
| 9 | [The Merchant Shipping Act, 2025](https://indiacode.gov.in/act/5a5bb080-385a-4542-8b8e-ac42e773708e) | Long 125-page PDF, contents pages and amendment notes; stress case for passage boundaries. |
| 10 | [The Environment (Protection) Act, 1986](https://indiacode.gov.in/act/10eea11f-bfda-41d0-b8dc-58176e704613) | Environmental topic queries, section 5A, and a large subordinate-instrument fanout that must be bounded. |
| 11 | [The Consumer Protection Act, 2019](https://www.indiacode.nic.in/bitstream/123456789/15256/1/eng201935.pdf) | Consumer complaints and remedies; ordinary-language queries. |
| 12 | [The Information Technology Act, 2000](https://www.indiacode.nic.in/bitstream/123456789/13116/1/it_act_2000_updated.pdf) | Digital transactions and technology terminology; amendment-sensitive text. |
| 13 | [The Rights of Persons with Disabilities Act, 2016](https://www.indiacode.nic.in/handle/123456789/2155?locale=en) | Accessibility, rights and administrative duties. |
| 14 | [The National Food Security Act, 2013](https://www.indiacode.nic.in/indiacode/handle/123456789/2113?col=123456789%2F1362&view_type=search) | Entitlements and administrative responsibilities. |
| 15 | [The Right of Children to Free and Compulsory Education Act, 2009](https://www.indiacode.nic.in/indiacode/handle/123456789/2086?view_type=browse) | School access, qualifications and exceptions. |
| 16 | [The Legal Services Authorities Act, 1987](https://www.indiacode.nic.in/bitstream/123456789/9316/1/slsa198739.pdf) | Access to legal services; eligibility queries. |
| 17 | [The Indian Contract Act, 1872](https://www.indiacode.nic.in/handle/123456789/12845) | Definitions, illustrations and dense cross-references. |
| 18 | [The Arbitration and Conciliation Act, 1996](https://upload.indiacode.nic.in/showfile?actid=AC_CEN_3_46_00004_199626_1517807323919&filename=a1996-26.pdf&type=actfile) | Procedural retrieval and longer structured documents. |
| 19 | [The Real Estate (Regulation and Development) Act, 2016](https://housing.maharashtra.gov.in/en/document/the-real-estate-regulation-and-development-act-2016/) | Housing and buyer queries; source discovery must resolve the central Act. |
| 20 | [The Competition Act, 2002](https://www.indiacode.nic.in/indiacode/bitstream/123456789/2010/7/A2003-12.pdf) | Definitions and institutional powers; title year is not necessarily enactment year. |

## Batches

1. Establish the generic section inventory and review workflow on RTI and Environment using retained evidence. Reconcile every source-listed section and schedule; the current four sections are only a starting point.
2. Add shorter rights-focused Acts: Legal Services, Education, Food Security, POSH, DPDP and Mental Healthcare. Actual batch order may change after source inspection; no assumption of easy extraction.
3. Process remaining Acts in bounded batches after the first expansion audit passes. Keep difficult amendments, illustrations and schedules quarantined until reviewed.

## Coverage accounting contract

Use this inventory as the Act denominator only after selection is frozen. Maintain separate representation records and a source-listed provision inventory per Act. Counts of retained PDFs, parsed candidates, reviewed provisions and live-searchable provisions are different measures. Never use a successful fetch or one reviewed section as proof of a complete Act.

Each representation records capture/source hash, parser version, outcome (`not_requested`, `fetch_failed`, `captured`, `parse_failed`, `review_pending`, `quarantined`, or `reviewed`), reason, and evidence. Live indexing is derived separately through the existing admission boundary, not set by an operator flag. Unknown provision totals stay null. Historical/removed inventory members remain auditable. Every failure and exclusion must be visible; unknown must not become zero.

The existing Phase 0 manifest stays immutable in meaning and is not replaced by this proposal. A later main-agent migration will connect approved acquisition records to the canonical importer; the proposal itself is never admission input.
