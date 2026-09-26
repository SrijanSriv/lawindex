# LawIndex — Market and Ecosystem Research

Research date: **20 September 2026**. This is a decision document for [LawIndex](IDEA.md), covering existing products, potential data suppliers, reusable infrastructure, and evaluation resources. It is a focused landscape review, not an exhaustive vendor directory or a market-size estimate.

Evidence comes from official product documentation, provider announcements, research project documentation, and our own [Phase 0 observations](docs/phase-0/SOURCE_DISCOVERY.md). Advertised capabilities are not independently measured performance. Paid products and authenticated APIs were not tested in this review. Prices, access conditions, and product availability should be checked again before use.

## 1. What this means for LawIndex

**Yes, much of the proposed user experience already exists.** Legal search, provision navigation, citation links, natural-language search, and AI-assisted research are established product features. Merely adding embeddings or a chatbot is not a convincing distinction.

The opportunity worth pursuing is a small, inspectable system that answers a measurable engineering question:

> How well can we retrieve exact provisions from a declared corpus of Indian legislation, while preserving source fidelity, legal structure, and evidence about versions?

Recommended positioning:

> LawIndex is an open-source experiment in information retrieval for Indian law, with a useful public search interface. It compares lexical, semantic, hybrid, and reranked retrieval on a versioned corpus and publishes its methodology, evaluation, and limitations.

This is a proposed positioning, not a claim that a licensed open corpus, benchmark, or public service already exists. Our current [north star](IDEA.md) remains useful: help someone find a relevant provision, understand its context, and verify it at the source.

Three distinctions matter throughout this document:

- **Accessible is not necessarily redistributable.** Website access, API access, local indexing, and publishing a downloadable corpus are different permissions.
- **A feature is not a quality measurement.** “Semantic search” tells us little about relevance, missed provisions, or text accuracy.
- **A useful research project need not replace a professional legal database.** A reproducible negative result can be valuable even when an incumbent search engine performs better.

## 2. Existing systems and what to learn

### India Code — the official source is also a search competitor

The government announced the revamped portal on **13 August 2026**. Its announced features include AI-assisted, semantic, and speech search; navigation through amendments and legislative history; links between Acts and subordinate legislation; e-Gazette integration; and improved document viewing. The announcement describes multilingual access across 22 scheduled languages as something the portal seeks to enable; it does not establish complete, verified translations of every instrument. [Official PIB announcement](https://www.pib.gov.in/PressReleaseIframePage.aspx?LID=1&PRID=2299217&RegID=3&lang=2&reg=48).

**What we should learn:** Treat Acts, provisions, subordinate instruments, and publication history as connected entities. Keep source navigation central to the experience. Evaluate the new portal, rather than describing an older version as the current competitor.

**How it can help:** It remains our initial source-discovery target and an external comparator for the same legislation. A supported export or authorized API could remove substantial crawling and maintenance work.

**What remains unresolved:** Our Phase 0 review found restrictive published automation and reuse conditions, and an actual mismatch between structured provision text and a linked PDF. The observed `/server/api` endpoints are implementation details, not proof of a supported public data service. The retained terms/copyright HTTP files are application shells; the policy observations came from rendered browser text. [Access and reuse findings](docs/phase-0/ACCESS_AND_REUSE.md), [source-discovery evidence](docs/phase-0/SOURCE_DISCOVERY.md).

**Decision:** Retain India Code as a source candidate and benchmark target. Resolve the ingestion basis and representation disagreements before expanding into bulk ingestion or claiming that our text is current law.

### Indian Kanoon — the closest broad public-search reference

Indian Kanoon documents free search across laws and judgments, phrase and Boolean search, title/citation matching, filters, citation links, and navigation through legislation at multiple structural levels. Provision-level search is therefore not new territory. [Free features](https://indiankanoon.org/free_features/).

Its API homepage advertises **more than 3 crore orders**, approximately 30 million. That is a provider-reported scale figure, not an independently audited count of unique laws or evidence of complete legislation coverage. [API overview](https://api.indiankanoon.org/).

Indian Kanoon also markets **Prism**, including conversational research and document-oriented AI tools. We should not characterize the overall product as simply an old lexical engine, or label its ranking algorithm BM25 without evidence. [Prism](https://indiankanoon.org/prism/).

**What we should learn:** Support exact legal references alongside ordinary-language queries; let users move between a short result, its full provision, and its parent instrument; make related sources discoverable.

**How it can help:** Its documented API is the strongest immediately identifiable shortcut for obtaining external search results, document representations, and candidate passages. It could support a prototype and a comparison run, subject to the intended use and access conditions.

**What remains unresolved:** Coverage of our particular ten-Act slice, provision identity, representation freshness, original-file availability, and permission for independently stored or redistributed datasets need validation. Search-result availability is not a complete corpus inventory.

**Decision:** Run a bounded API feasibility pilot before assuming we need to implement every source adapter ourselves. Keep its role explicit: an upstream search service, a candidate supplier, or a permitted corpus supplier are different architectures. Section 4 develops this option.

### Manupatra — learn the professional research workflow

Manupatra's published feature documentation describes fielded and citation search, Act searches by title/text/number, navigation by chapter, section, schedule and other units, filters, and links connecting legislation and judgments. It includes combinations such as an order and rule lookup within the Code of Civil Procedure. [Official feature documentation](https://www.manupatra.com/ipAccess.aspx).

**What we should learn:** Legal references are structured queries. A search such as an Act name plus a section label should not depend entirely on semantic similarity. Readers need dependable navigation and context after the initial match.

**How it can help:** Use the documented workflows as a design checklist and, if appropriate access is available, a source of user-experience comparisons.

**Boundary:** This review did not verify a general-purpose data API or redistribution arrangement. Its professional content and editorial features should not be treated as a source we can freely ingest. Reproducing the breadth of this product is outside our first release.

### SCC Online — natural-language search is already part of the market

SCC Online announced **SmartSearch** on 4 February 2026 as natural-language search over its research materials, available to Web Edition subscribers without an additional charge at that announcement date. Its July 2026 **AI Pro** announcement also promotes AI-supported legal research. These are product announcements, not independent accuracy studies. [SmartSearch announcement](https://www.scconline.com/blog/post/2026/02/04/scc-online-smartsearch-natural-language-search/), [AI Pro introduction](https://www.scconline.com/blog/post/2026/07/30/scc-online-ai-pro-smartest-way-to-legal-solutions/).

**What we should learn:** Ordinary-language input alone is not differentiation. The quality and provenance of the material returned, the usefulness of citations, and the reader's ability to verify a result matter more.

**How it can help:** It provides a professional reference experience for citation presentation and research navigation. Comparisons require access to the specific product mode being tested.

**Boundary:** No suitable public data API or reuse license was verified here. A comparison against a system with judgments and editorial commentary must account for its different corpus; otherwise we would confuse coverage with ranking quality.

### CaseMine — query formats can extend beyond a search box

CaseMine markets **Parallel Search** for natural-language research, **AMICUS** for conversational assistance, and **CaseIQ** for using documents to find related authorities. [India-facing product page](https://www.casemine.com/?locale=en_IN), [CaseIQ](https://www.casemine.com/caseiq).

**What we should learn:** A document or fact pattern can be a useful query. Later, LawIndex could test whether a short scenario retrieves the right provision better than a few keywords.

**How it can help:** Its workflows suggest evaluation query types and future interaction patterns.

**Boundary:** Document-to-precedent retrieval is different from our initial legislation task. No bulk-data or API arrangement suitable for LawIndex was verified. Defer uploads, drafting, and conversational features until basic provision retrieval is evaluated.

### LegitQuest — structure inside a document is valuable

LegitQuest's FAQ describes a free public library alongside subscription research features. Its **iDRAF** feature separates judgment components such as issues, arguments, reasoning, and decisions. [Official FAQ](https://www.legitquest.com/faq).

**What we should learn:** A result is more useful when its structural role is clear. For legislation, our corresponding units are definitions, substantive provisions, exceptions, provisos, and schedules—not judgment rhetorical roles copied indiscriminately.

**How it can help:** It is a reference for navigation to meaningful document segments. We can investigate structure-aware retrieval as a measured experiment.

**Boundary:** The documented feature does not establish the accuracy of automated segmentation. We did not verify a data-access route for ingestion.

### PRS Legislative Research — context and discovery, rather than a replacement corpus

PRS provides routes to parliamentary and state Bills and Acts, legislative briefs, committee reports, and policy reviews. Its Bills Track distinguishes legislative status. [Bills Track and resource navigation](https://prsindia.org/billtrack).

**What we should learn:** A Bill, an enacted Act, an amendment, and explanatory analysis are different objects. Status labels and related-document links should remain explicit.

**How it can help:** Use it to discover instruments and understand terminology when drafting query categories or investigating coverage gaps. Independently verify target provisions in the selected source representation.

**Boundary:** Do not silently index a brief as statutory text, treat a Bill as operative legislation, or assume site-wide redistribution rights from a notice on an individual publication. Avoid copying its explanations into benchmark questions wholesale.

## 3. Infrastructure and research we can build on

These resources are useful even when their jurisdiction or task differs from LawIndex.

| Resource | Verified offering | Practical use for LawIndex | Limitation |
| --- | --- | --- | --- |
| [Laws.Africa Content API](https://laws.africa/api/detail/) | Structured legislative XML/HTML, tables of contents, amendment/publication metadata, and historical points in time where available | Study a legislation-specific data contract before inventing our own | Different corpus; API access and underlying content terms need separate review |
| [Indigo](https://laws.africa/open-law-technology/) | Legislation management using Akoma Ntoso, amendment workflows, provision commencement tracking, and version comparison | Learn the distinction between an instrument, an expression/version, and a provision; evaluate reusable components | A full editorial platform may exceed our needs; inspect component licenses and maintenance before adoption |
| [CourtListener / Free Law Project](https://wiki.free.law/c/courtlistener/help/api) | REST APIs, bulk files, replication, and event services, with access through memberships or commercial arrangements | Learn how an open legal-information service separates interactive search, bulk delivery, and updates | US-oriented data does not solve Indian legislation ingestion; open access is not unlimited free API use |
| [OpenNyAI](https://opennyai.readthedocs.io/en/latest/) | A legal NLP framework focused on Indian judgments | Evaluate entity extraction or rhetorical-role tooling if judgments enter scope | Judgment-trained processing is not automatically suitable for Acts; verify model and dataset licenses independently |
| [IL-TUR: prior-case retrieval](https://exploration-lab.github.io/IL-TUR/docs/tasks/prior-case-retrieval-pcr/) | Indian case-to-case retrieval data, relevance labels, evaluation, and baselines | Reuse evaluation ideas; exercise an experimental retrieval harness | Case-document queries and citation-derived relevance differ from citizen questions about provisions |
| [IL-TUR: statute identification](https://exploration-lab.github.io/IL-TUR/docs/tasks/legal-statute-identification-lsi/) | Case facts mapped to a fixed set of IPC-based labels, with train/development/test splits | Study facts-to-law evaluation and leakage prevention | It is a bounded classification task, not a current, comprehensive central-legislation search benchmark |
| [LegalBench-RAG](https://arxiv.org/abs/2408.10343) | Expert-annotated retrieval evaluation focused on relevant source text | Learn how to evaluate the specificity of retrieved evidence | Its corpus and questions do not establish performance on Indian legislation |

**Adoption principle:** Borrow schemas, evaluation methods, and narrowly useful components first. Do not adopt an entire stack merely because it is legal-domain software. A dataset being downloadable does not settle its suitability, provenance, permitted redistribution, or freshness.

No reviewed resource has yet been established as a ready-made, rights-cleared replacement for our selected India Code corpus and intended provision-level benchmark.

## 4. Indian Kanoon API: the most concrete development shortcut

### Documented interface

The API documents the following endpoint families and JSON/XML responses. Its documentation supports token authentication as well as signed requests. An authenticated integration was not executed during this research. [API documentation](https://api.indiankanoon.org/documentation/).

| Endpoint | Purpose in a possible pilot |
| --- | --- |
| `/search/?formInput=<query>&pagenum=<page>` | Obtain ranked candidates; pagination starts at zero |
| `/doc/<docid>/` | Inspect the provider's document representation |
| `/docfragment/<docid>/?formInput=<query>` | Obtain query-related fragments |
| `/docmeta/<docid>/` | Inspect available metadata |
| `/origdoc/<docid>/` | Request an original court copy where supported; do not assume every Act has an original PDF here |

Store provider identifiers separately from LawIndex identities. An Act, a section, a source representation, and a provider document ID should not collapse into one interchangeable key.

### Published cost and an illustrative pilot

Published prepaid rates are ₹0.50 per search, ₹0.50 per original document, ₹0.20 per document, ₹0.05 per fragment, and ₹0.02 per metadata request. The pricing page offers ₹500 in signup test credit and describes ₹10,000 monthly credit for non-commercial use **subject to administrator verification**. Neither credit has been obtained for this project. [Pricing](https://api.indiankanoon.org/pricing/).

An illustrative request budget, not a quote or an executed run:

| Requests | Calculation | Base cost |
| --- | --- | ---: |
| 200 searches, one page each | 200 × ₹0.50 | ₹100 |
| 2,000 distinct documents | 2,000 × ₹0.20 | ₹400 |
| Metadata for those documents | 2,000 × ₹0.02 | ₹40 |
| 2,000 query/document fragments | 2,000 × ₹0.05 | ₹100 |
| **Total** | Before credits or other applicable charges | **₹640** |

Requesting 2,000 original copies would add ₹1,000, if available. Pagination, retries, and repeated uncached calls change this estimate. One search page per question does not guarantee comprehensive candidates. The actual ten-Act pilot should be substantially smaller and should deduplicate document fetches where permitted.

### What the published terms establish—and what to clarify

The API terms permit displaying its search, documents, and fragments in another product. They require conspicuous **“powered by IKanoon”** attribution, including integrated RAG or fine-tuning uses, with placement rules. They also describe prepaid access and provide data without accuracy warranties. [API terms](https://api.indiankanoon.org/terms/).

Our reading of that page does **not establish a blanket license** for releasing a downloadable corpus or operating an unrestricted independent bulk index. This is an unresolved scope question, not a claim that those uses are prohibited. Before choosing it as our corpus supplier, clarify permitted retention, embeddings/index creation, excerpt display, redistribution, and publication of benchmark artifacts. API attribution must coexist with original-source provenance.

### Which shortcut solves which problem?

| Approach | Work it saves | What we can honestly claim |
| --- | --- | --- |
| API-backed search interface | Initial crawling, indexing, and ranking | A LawIndex interface powered by Indian Kanoon |
| Retrieve API candidates, then rerank | Large-scale candidate generation | An experiment in reranking that provider's candidate pool |
| Build our own index from an appropriately licensed export or retained corpus | Source acquisition, depending on agreement | Independent retrieval over that explicitly declared corpus |
| Use API results only as an external comparator | Manual collection of comparison rankings | A dated comparison with that API search mode |

Reranking cannot recover a relevant provision absent from the supplied candidate pool. An API-backed prototype is useful, but it does not demonstrate that LawIndex independently outperforms Indian Kanoon at corpus retrieval.

### Proposed feasibility pilot

1. Map the existing ten candidate Acts to provider records using title, year, number, and jurisdiction; record ambiguity instead of forcing a match.
2. Inspect a small selection of complete provisions, nested clauses, and a schedule. Check whether identifiers and text boundaries support our canonical structure.
3. Investigate the RTI representation discrepancy using the retained official evidence; agreement with another source is a clue, not proof of current legal effect.
4. Run a subset of our 24 seed questions and preserve query, filters, timestamp, provider IDs, ranks, and permitted response artifacts.
5. Measure useful coverage, provision mapping success, observed costs, and missing metadata. Resolve retention and publication conditions before committing to a corpus strategy.

**Exit decision:** use the API as a comparator, an attributed prototype backend, a permitted data supplier, or none of these. Do not assume the answer in advance.

## 5. Where LawIndex could make a worthwhile contribution

These are hypotheses to test, not unsupported claims that incumbents lack the capabilities.

| Proposed contribution | Concrete implementation | Evidence needed |
| --- | --- | --- |
| Reproducible retrieval research | Versioned corpus manifest, query set, judgments, configurations, and run files | Another person can reproduce a result using artifacts they are entitled to access |
| Faithful provision retrieval | Exact provision text, parent context, source link, representation label | Reviewed text and citation checks pass across difficult fixtures |
| Visible uncertainty about versions | Separate retrieval date, enactment date, stated amendment information, and unresolved discrepancies | The UI never silently converts a recent fetch into a claim of current legal effect |
| Inspectable ranking | Show lexical/vector candidate sets, fusion, reranker scores, and timings in a research view | A result's path through the pipeline can be reconstructed |
| Honest coverage | Publish indexed, excluded, failed, and unknown counts against a declared inventory | Users can determine whether a query falls outside the supported corpus |
| Useful legal structure | Preserve clauses, provisos, definitions, schedules, and document relationships | Structure-aware retrieval improves reviewed queries without breaking source fidelity |

The strongest locally observed reason to prioritize fidelity is the **RTI Act section 8(1)(j) disagreement between structured text and the linked PDF**. Phase 0 did not determine the currently operative wording. We also observed a section-to-PDF page hint mismatch. These are specific fixtures for our ingestion and citation tests, not evidence that all official data is unreliable. [Phase 0 report](docs/phase-0/SOURCE_DISCOVERY.md).

Candidate experiments should follow the existing roadmap: establish a named lexical baseline, then test vectors, hybrid fusion, reranking, query expansion, and passage boundaries against it. PostgreSQL's built-in full-text ranking should not be called BM25. An improvement should survive evaluation across query categories, latency, and cost—not just selected demo questions.

## 6. A fair benchmark against existing systems

An “India Code vs Indian Kanoon vs LawIndex” table is a useful destination, but there are **no measured comparison scores yet**. Neither vendor marketing nor a handful of successful queries supplies Recall@10, MRR, or nDCG.

### Track A: controlled retrieval experiments

Use the same permitted corpus snapshot and provision identities for each LawIndex method. Compare the actual initial lexical implementation, a BM25 implementation if added, vector retrieval, hybrid retrieval, and reranking. Hold extraction, corpus scope, query set, relevance judgments, and result-unit rules constant unless that variable is the experiment.

This isolates ranking changes. Report configurations, model versions, candidate counts, index build details, run date, and query latency/cost. Keep development and held-out test queries separate; do not tune on the test results.

### Track B: external product comparisons

Run the same user intent through available India Code and Indian Kanoon modes, and optionally paid products where access permits. Record the exact submitted query, syntax changes, filters, sort order, account tier, mode, date, and top results. Test natural-language and expert-syntax workflows separately if both matter.

Report two views where feasible:

- **Common-scope comparison:** questions with relevant provisions verified in every compared system, with representation/version differences disclosed. If a service cannot restrict its corpus to the agreed slice, disclose that rather than calling the experiment fully controlled.
- **Real-world usefulness:** what each product returns under its normal coverage. Report coverage failures separately from ranking failures.

Do not compare an Act-level hit directly with a clause-level hit as though they offer identical precision. Report document discovery and provision retrieval separately, and define duplicate-result handling before scoring.

### Build judgments independently of any one engine

Grow our 24 unjudged seeds toward the roadmap's **100–200 reviewed questions**, covering exact references, plain-language needs, paraphrases, exceptions, definitions, related instruments, and out-of-scope requests. Derive questions from user needs and independently inspected provisions; do not create the entire benchmark by paraphrasing one engine's best results.

Pool candidates from multiple systems and manual source inspection. Have reviewers judge their relevance without seeing the originating system where practical, recording disagreements and adjudication. API fragments are candidate evidence, not ground-truth judgments. Preserve the applicable document/version boundary in each judgment.

| Measurement | Interpretation and limitation |
| --- | --- |
| Success@k | Whether at least one judged-relevant provision appears in the first k results |
| MRR@k | How early the first relevant result appears; insufficient for questions needing several provisions |
| nDCG@k | Ranking quality with predefined graded relevance labels |
| Recall@k | Fraction of known relevant provisions retrieved; call it pooled/judged recall when judgments are incomplete |
| Citation and text fidelity | Whether result text, provision labels, and source anchors match the reviewed representation |
| Coverage, latency, cost | Operational usefulness alongside relevance; report independently |

Include per-query results and uncertainty estimates, not only aggregate averages. For out-of-scope questions, measure whether the interface communicates the limitation; do not force meaningless recall denominators for questions with no relevant item in the declared corpus.

A useful benchmark can be published without republishing restricted full text: release permitted queries, identifiers, judgments, code, configurations, and acquisition instructions as appropriate. State any access requirements and resulting reproducibility limits explicitly.

## 7. Decisions and next actions

| Priority | Action | Deliverable / decision |
| --- | --- | --- |
| Now: Phase 0 | Resolve source acquisition and intended reuse for the first corpus; compare India Code access with the Indian Kanoon option | A documented source choice covering storage, indexing, display, refresh, and any redistribution |
| Now: Phase 0 | Perform the bounded provider/provision mapping pilot when access is available | Evidence of coverage, text fidelity, IDs, cost, and operational constraints |
| Now: Phase 0 | Retain source disagreements as explicit fixtures; complete review of the candidate slice | An accepted corpus plus quarantined items, not silent reconciliation |
| Phase 1 | Build query → provision → context → source over that accepted slice | A useful lexical search path and reproducible seed-query runs |
| Phases 2–3 | Borrow legislation-modeling ideas selectively; preserve provenance and stable internal identity | Dependable imports and declared coverage |
| Phase 4 | Establish independent relevance judgments and the two evaluation tracks | A benchmark protocol, held-out questions, and honest baseline report |
| Phases 5–6 | Test hybrid search, reranking, expansion, and structure changes | Measured improvements or documented negative results |
| Later | Revisit judgment tools, uploaded-document queries, multilingual retrieval, and AI answers | Separate evidence-led scope decisions |

The most useful shortcuts are **a suitable data-access arrangement, existing evaluation methodology, and mature legislation-modeling patterns**. The work we still need to own is choosing a reliable corpus, preserving its meaning and provenance, and measuring retrieval honestly.

This research supports the sequence in [PHASES.md](PHASES.md); it does not mark unresolved Phase 0 gates complete or establish that a new commercial legal-research business is viable. Customer demand, willingness to pay, and comparative product quality remain untested.
