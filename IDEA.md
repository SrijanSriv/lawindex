# LawIndex

LawIndex is an open search engine for public law, starting with Indian central legislation from [India Code](https://indiacode.gov.in/).

Phase 0 confirmed that the original `www.indiacode.nic.in` homepage now points to this new domain. See the [source-discovery report](docs/phase-0/SOURCE_DISCOVERY.md) for current access, fidelity, and coverage findings.

We want to make legislation easy to search, explore, and retrieve from. A person should be able to describe what they are looking for in ordinary language, find relevant legal documents and provisions, read the exact passages, and follow them back to the original government source.

The retrieval system is the core of LawIndex. An optional AI answer layer may eventually help explain retrieved material, but search must remain useful on its own.

## The problem we are solving

Finding legislation requires more than finding a document with similar words. Users may not know the name of an Act, the relevant section, or the terminology used in legislation. A useful result needs to connect their query to the right provision and preserve enough context to understand it.

For a query such as:

> What does Indian law say about environmental clearance for mining?

LawIndex should surface relevant legislation and specific passages, with their titles, section references, context, and source links. This is an example search question, not a claim that the initial corpus contains every source needed to answer it.

We are trying to reduce the distance between a question and the public legal text that helps resolve it.

## Our north star

**A user can reliably find the relevant legal provision, understand its context, and verify it against the original public source.**

The ideal path is:

```text
Question or search terms
    → relevant documents and exact passages
    → section and surrounding context
    → full document
    → original government source
```

Success means the relevant provision appears near the top, the quoted passage faithfully represents the source, and the user can see what corpus and version they are searching. A polished interface or a fluent generated answer cannot compensate for missing or incorrect source material.

Our primary quality measure will be retrieval success on a representative, reviewed set of questions: how often we return a judged-relevant provision within the first few results. We will track passage Recall@10 and nDCG@10 alongside source fidelity, coverage, freshness, and latency. Exact launch thresholds belong in the milestone plan once we have measured a baseline; they are not established facts today.

## The first product

The initial product is a simple search experience for Indian central legislation ingested from India Code.

Users should be able to:

- Search using a topic, plain-language question, Act title, or section reference.
- See relevant documents and exact sections or passages prominently in results.
- Recognize the document title, provision label, document type, and available dates.
- Open a provision, inspect surrounding context, and navigate to the full document.
- Follow a link to the source page and original document or PDF where available.
- Understand the indexed corpus's coverage, limitations, and last successful source checks.

The interface should feel like a focused search engine or documentation search. It can be visually simple while retrieval and document quality mature.

The intended public addresses are `lawindex.live` and `india.lawindex.live`. Their exact landing-page and routing arrangement can be decided at launch. India is the only initial jurisdiction.

## Initial scope

Start with a small, verified slice of India Code central legislation, then expand to a declared central-legislation inventory. Preserve associated sections, chapters, schedules, rules, regulations, and amendment information when actually available and reliably extractable.

Discover the source before promising its coverage. Do not assume every Act has every metadata field, all associated instruments are present, or a source page provides a complete historical account of the law.

Useful metadata includes:

- Document title, Act number, year, and document type.
- Ministry or department, where available.
- Chapters, sections, subsections, clauses, and schedules.
- Relationships to rules, regulations, and other associated instruments.
- Amendment, commencement, repeal, and other date or status information explicitly provided by the source.
- Language, source page URL, and original document or PDF URL.
- Internal provenance: fetch time, content hash, parser version, and source snapshot.

Missing or uncertain information should remain explicitly unknown. Retrieval date, enactment date, and legal effective date are different concepts. We must not imply that a retrieved document is the currently operative law simply because it was recently fetched.

## Product and engineering principles

### 1. Faithful, reproducible ingestion

Keep original source artifacts and a record of how we transformed them. Reprocessing the same source with the same pipeline should produce consistent structured output. Failed or uncertain extractions must be visible.

### 2. Structure is part of the product

Legal passages belong to documents, chapters, sections, and schedules. Preserve that hierarchy wherever the source supports it. A search chunk is a retrieval representation of a provision, not a replacement for the provision itself.

### 3. Retrieval quality is measurable

Begin with lexical search and establish a baseline. Compare embeddings, hybrid retrieval, reranking, metadata filters, query expansion, and passage strategies against the same evaluation data. Keep improvements that demonstrate value.

### 4. Every result is traceable

Show exact source passages and stable internal links to their context. Preserve government-source links and the provenance needed to investigate an extraction or indexing error.

### 5. The pipeline is inspectable

For a query, we should be able to inspect lexical candidates, semantic candidates, merged candidates, reranker scores, final rankings, and stage timings. “Why this matched” must describe actual retrieval evidence; semantic similarity is not an exact text match or proof of legal applicability.

### 6. Keep the first system small

Use PostgreSQL as the initial structured store and start with PostgreSQL full-text search or a deliberately selected lexical alternative. PostgreSQL full-text ranking and BM25 are distinct methods and should be named and evaluated accurately. Avoid adding infrastructure until a measured need justifies it.

### 7. Search works without generation

If we eventually add natural-language answers, each substantive claim must be supported by retrieved source passages and linked citations. Insufficient evidence should produce an explicit limitation. The answer layer must be independently disableable.

## System shape

```text
India Code
    → crawler / importer
    → retained source artifacts
    → extraction and normalization
    → structured documents and provisions in PostgreSQL
    → versioned passage generation
    → lexical index / optional vector index
    → candidate merging / optional reranking
    → exact passages and source-linked search results
```

Keep ingestion, canonical document storage, passage generation, and retrieval separable. We should be able to change an embedding model or passage strategy without recrawling the source, and rebuild an index without losing document identity or source provenance.

LawIndex is both a public search product and a retrieval engineering laboratory. The experimentation should make the product better while keeping the user experience clear and direct.

## Priorities and boundaries

Our priorities, in order, are:

1. Correct and reproducible ingestion.
2. Good document structure.
3. Search quality.
4. Source traceability.
5. Retrieval evaluation.
6. Fast search.
7. Clean UI.

These priorities do not imply that evaluation or traceability waits until later: both begin with the first working slice.

The initial release does not aim to provide comprehensive Indian legal research, court judgments, every state law, historical law as of any date, personalized legal advice, or an autonomous legal chatbot. Rules and regulations are included only to the extent supported by the chosen source and declared ingestion scope.

“Open” describes the intended public accessibility and inspectability of the project. We still need to choose a code license and verify source-specific reuse conditions before publishing a code release or redistributing a corpus. Public availability alone does not settle redistribution permissions.

## Where this could go

Once the India search engine is useful and maintained, we can consider state legislation, additional official sources, government orders, judgments, developer APIs, and other jurisdictions. Addresses such as `up.lawindex.live`, `uk.lawindex.live`, `us.lawindex.live`, `api.lawindex.live`, and `docs.lawindex.live` are future possibilities, not current implementation requirements.

Expansion should follow evidence of user need, source quality, and our ability to evaluate and maintain each corpus.

**The first concrete win:** a working search engine over a declared slice of India Code where a user can reliably retrieve relevant documents and exact provisions, then verify them at the source.

See [PHASES.md](PHASES.md) for the proposed milestones and completion gates.
