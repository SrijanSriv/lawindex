"""Retrievers rank only records already admitted by Snapshot; they never admit text."""
from contextlib import closing
from dataclasses import dataclass
import re
import sqlite3
from typing import Mapping, Protocol


def section_order(label: str):
    """Natural order for section labels: 3 < 5A < 9 < 10; non-numeric labels last."""
    match = re.match(r'(\d+)(.*)', label)
    return (0, int(match.group(1)), match.group(2).upper()) if match else (1, 0, label.upper())


@dataclass(frozen=True)
class SearchFilters:
    act: str | None = None
    year: str | None = None
    ministry: str | None = None
    document_type: str | None = None

    def __post_init__(self):
        for name, value in self.as_dict().items():
            if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 200):
                raise ValueError(f'{name} must be a non-empty string of at most 200 characters.')
        if self.year is not None and not re.fullmatch(r'[0-9]{4}', self.year):
            raise ValueError('year must contain exactly four ASCII digits.')

    def as_dict(self):
        return {name: getattr(self, name) for name in ('act', 'year', 'ministry', 'document_type')}

    def matches(self, record):
        metadata = record['metadata']
        values = {'act': record['act_slug'], **metadata}
        return all(value is None or (isinstance(values.get(name), str) and
                   values[name].casefold() == value.casefold()) for name, value in self.as_dict().items())


@dataclass(frozen=True)
class RetrievalRequest:
    match_expression: str
    section: str | None
    act_slugs: tuple[str, ...]
    filters: SearchFilters
    limit: int
    # Quoted phrases are constraints: every phrase must occur (FTS5 phrase
    # match, so stemming still applies). They also feed match_expression for
    # ranking, but ranking never relaxes them.
    phrases: tuple[str, ...] = ()
    # Citation constraints parsed from the query ("Act 22 of 2005", "Act, 2005").
    # A cited year matches the source's recorded year OR the year in the Act's
    # own title: the Competition Act, 2002 is Act 12 of 2003, and citing it by
    # either year must find it. The explicit `year` filter stays strict on the
    # recorded metadata, which is what the filter contract documents.
    act_number: str | None = None
    year: str | None = None
    # When a query names no Act, no single Act may take more than this many
    # places on the returned page. Every match still counts toward `total`.
    per_act_cap: int | None = None


@dataclass(frozen=True)
class Candidate:
    key: str
    score: float


@dataclass(frozen=True)
class RetrievalResult:
    candidates: tuple[Candidate, ...]
    total: int
    method: str
    diversified: bool = False
    # Close matches the per-Act cap kept off the page, per Act.
    held_back: tuple[tuple[str, int], ...] = ()


COMPETITIVE_SHARE = 0.6


def cap_per_act(candidates, records, cap, limit):
    """The page of `limit` candidates with at most `cap` from any one Act
    among *competitive* candidates -- those scoring at least COMPETITIVE_SHARE
    of the best score. A generic query spreads across Acts; a focused one
    ("seafarer wages") keeps its Act's strong results instead of promoting
    weak matches from elsewhere. If capping leaves the page short, held-back
    competitive candidates fill it first, then weaker ones in rank order.
    Returns (page in rank order, {act: competitive candidates kept off the page}).
    """
    best = abs(candidates[0].score) if candidates else 0.0
    ranked = list(enumerate(candidates))
    strong = [item for item in ranked if best and abs(item[1].score) >= COMPETITIVE_SHARE * best]
    weak = [item for item in ranked if item not in strong]
    counts, page, held = {}, [], []
    for rank, candidate in strong:
        act = records[candidate.key]['act_slug']
        if counts.get(act, 0) < cap:
            counts[act] = counts.get(act, 0) + 1
            page.append((rank, candidate))
        else:
            held.append((rank, candidate))
        if len(page) == limit:
            break
    for item in held + weak:
        if len(page) == limit:
            break
        page.append(item)
    shown = {candidate.key for _, candidate in page}
    # Competitive candidates the cap kept off the page, per Act.
    left_out = {}
    for _, candidate in held:
        if candidate.key not in shown:
            act = records[candidate.key]['act_slug']
            left_out[act] = left_out.get(act, 0) + 1
    ordered = [candidate for _, candidate in sorted(page, key=lambda item: item[0])]
    return ordered, left_out


class Retriever(Protocol):
    def retrieve(self, records: Mapping[str, dict], request: RetrievalRequest) -> RetrievalResult: ...


def check_limit(limit):
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('Limit must be between 1 and 20.')


def eligible_keys(records, request) -> set:
    """Keys every retrieval mode may return: filters, section and citation constraints."""
    return {key for key, p in records.items() if request.filters.matches(p)
            and (request.section is None or p['section_number'].casefold() == request.section)
            and (not request.act_slugs or p['act_slug'] in request.act_slugs)
            and (request.act_number is None or p.get('act_number') == request.act_number)
            and (request.year is None or request.year in
                 {p['metadata'].get('year'), p.get('title_year')})}


def browse_order(records, eligible):
    """Browsing order is by Act, then natural section order; canonical key breaks ties."""
    return [Candidate(key, 0.0) for key in sorted(
        eligible, key=lambda k: (records[k]['act_slug'], section_order(records[k]['section_number']), k))]


def is_browse(request) -> bool:
    return request.section is not None or request.act_number is not None or request.year is not None \
        or any(v is not None for v in request.filters.as_dict().values())


def page_result(candidates, records, request, method, total=None) -> RetrievalResult:
    """Cut ranked candidates to the page, applying the per-Act cap to ranked queries."""
    total = len(candidates) if total is None else total
    if request.per_act_cap and request.match_expression:
        page, left_out = cap_per_act(candidates, records, request.per_act_cap, request.limit)
        # Applied means the cap changed the page, not merely that it ran.
        changed = [c.key for c in page] != [c.key for c in candidates[:request.limit]]
        return RetrievalResult(tuple(page), total, method, changed,
                               tuple(sorted(left_out.items(), key=lambda item: (-item[1], item[0]))))
    return RetrievalResult(tuple(candidates[:request.limit]), total, method)


class LexicalRetriever:
    method = 'sqlite-fts5-bm25-v1'

    def __init__(self, aliases):
        self.aliases = aliases

    def _index(self, records):
        # Index the whole admitted snapshot so filter selection doesn't redefine
        # BM25's corpus statistics.
        index = sqlite3.connect(':memory:')
        index.execute("CREATE VIRTUAL TABLE search USING fts5(key UNINDEXED, title, heading, body, footnote, tokenize='porter unicode61')")
        for p in records.values():
            index.execute('INSERT INTO search VALUES(?,?,?,?,?)',
                (p['key'], p['act_title'] + ' ' + ' '.join(self.aliases.get(p['act_slug'], [])),
                 p['heading'], p['body_text'], p['footnote_text'] or ''))
        return index

    def phrase_eligible(self, records, phrases) -> set:
        """Keys containing every quoted phrase (FTS5 phrase match, stemmed)."""
        with closing(self._index(records)) as index:
            return {key for (key,) in index.execute(
                'SELECT key FROM search WHERE search MATCH ?', (' AND '.join(phrases),))}

    def retrieve(self, records, request):
        check_limit(request.limit)
        eligible = eligible_keys(records, request)
        candidates = []
        # Apply every constraint before the top-k cut.
        if request.match_expression:
            with closing(self._index(records)) as index:
                if request.phrases:
                    # Phrase constraints narrow eligibility; they never widen it.
                    eligible &= {key for (key,) in index.execute(
                        'SELECT key FROM search WHERE search MATCH ?', (' AND '.join(request.phrases),))}
                candidates = [Candidate(key, score) for key, score in index.execute(
                    'SELECT key, bm25(search,0,4,3,1,0.5) FROM search WHERE search MATCH ? ORDER BY 2,1',
                    (request.match_expression,)) if key in eligible]
        elif is_browse(request):
            candidates = browse_order(records, eligible)
        return page_result(candidates, records, request, self.method)
