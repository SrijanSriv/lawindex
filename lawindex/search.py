"""Read-only admission boundary and disposable FTS5 index for the bounded slice.

The importer owns the on-disk database. Each request reads one database snapshot,
validates it against current evidence, and builds a tiny private search index.
There is no second persistent index to become stale.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import quote, urlparse

from scripts.offline_importer import SUPPORTED_EXTRACTION_METHODS, NO_FOOTNOTE_EXPECTED
from scripts import structural_store
from .retrieval import COMPETITIVE_SHARE, LexicalRetriever, RetrievalRequest, RetrievalResult, SearchFilters, section_order
from . import modes, vectors

ROOT = Path(__file__).resolve().parents[1]
METHOD = "sqlite-fts5-bm25-v1"
SCORE_NOTES = {
    "lexical": "Lower FTS5 BM25 scores rank first; not legal confidence.",
    "vector": "Higher cosine similarity ranks first; similarity of meaning, not legal confidence.",
    "hybrid": "Higher reciprocal-rank-fusion scores rank first; they combine ranks only, not legal confidence.",
}
ALIASES = {"rti-2005": ["RTI"], "environment-1986": ["Environment", "EPA"], "posh-2013": ["POSH", "POSH Act", "Sexual Harassment of Women at Workplace Act"]}
STOPWORDS = set("a an the and or of to in on for with under is are do does i my me what which how can need want act section sections s".split())
TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
SECTION = re.compile(r"\b(?:sections?|s)\.?\s*(\d+[a-z]?)\b", re.I)
# Quoted text is a literal phrase constraint, never parsed for references.
PHRASE = re.compile(r'["\u201c\u201d]([^"\u201c\u201d]+)["\u201c\u201d]')
YEAR = r"(?:18|19|20)\d{2}"
# Citation forms identify an Act; they constrain and are never lexical terms.
ACT_NUMBER = re.compile(r"\b(?:act\s+)?(?:no\.?\s*)?(\d{1,3})\s+of\s+(" + YEAR + r")\b", re.I)
# A capitalised name written immediately before "Act, YEAR" is a cited title
# ("National Green Tribunal Act, 2010"). Connector words may sit inside it;
# at least one capitalised word other than "The" must be present.
TITLE_CONNECTORS = {"of", "and", "the", "to", "for", "in", "on", "at", "with", "&"}
TITLE_RUN = re.compile(r"((?:(?:[A-Z][\w'\u2019-]*|\([A-Z][^)]*\)|of|and|the|to|for|in|on|at|with|&),?\s+)*"
                       r"(?:[A-Z][\w'\u2019-]*|\([A-Z][^)]*\)))\s*$")
ACT_YEAR = re.compile(r"\bact\b,?\s*(?:of\s+)?(" + YEAR + r")\b|\b(" + YEAR + r")\s+act\b", re.I)
# Markers the reviewed text itself uses; excerpt context is a position hint
# read from them, not a separately admitted structural claim.
# A marker opens a sub-section only at a line start or right after the
# heading's closing ".—"; "sub-section (1)" cross-references never count.
SUBSECTION = re.compile(r"(?:^|\n|\.\s*\u2014)\s*\((\d+[A-Z]?)\)")
PROVISO = re.compile(r"(?:^|\n)\s*Provided\s+(?:further\s+|also\s+)?that\b")
MAX_PHRASES = 5
CONTEXT_NOTE = ("Excerpt context is read from the numbering and proviso markers inside the reviewed text of that "
                "provision. It locates the excerpt; it is not a separate structural admission.")
NOTICE = "Local research prototype. Only the listed provisions are reviewed; no Act is fully indexed. Current legal effect has not been established. The user reports ministry permission to use up to 20 chosen Acts for this personal, non-commercial project."


def review_basis(review: dict) -> dict:
    """How this particular provision was reviewed, from its own record.

    A provision admitted under an Act-level sample must never be presented as
    individually compared: the sample is stated as a sample, and whether this
    provision was in it is stated explicitly.
    """
    block = review.get("review", {})
    plan = block.get("sample_plan")
    if block.get("review_class") != "text_agreement_sampled_visual" or not plan:
        return {"type": "AI-agent fidelity review", "independent_legal_expert": False,
                "review_class": "individual_visual", "individually_reviewed": True,
                "basis": "This provision's whole text was individually compared against the source PDF."}
    individually = bool(block.get("visually_reviewed"))
    selected, population = plan.get("selected_count"), plan.get("population_count")
    if not isinstance(selected, int) or not isinstance(population, int) or not 0 < selected <= population:
        raise ValueError("invalid sample plan reference")
    basis = (f"This provision's whole text was matched against the source PDF automatically. "
             f"{selected} of {population} provisions of this Act were also compared by eye"
             + (", including this one." if individually else ", but not this one."))
    return {"type": "AI-agent fidelity review", "independent_legal_expert": False,
            "review_class": "text_agreement_sampled_visual", "individually_reviewed": individually,
            "sampled_count": selected, "sample_population": population, "basis": basis}


# What the index holds, and what it never holds. A query can reach outside
# the index in several ways besides naming an unselected Act, and each gets
# its own notice. Notices inform; they never hide results.
STATES = ("andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "goa", "gujarat",
          "haryana", "himachal pradesh", "jharkhand", "karnataka", "kerala", "madhya pradesh",
          "maharashtra", "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "punjab",
          "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura", "uttar pradesh", "uttarakhand",
          "west bengal", "delhi", "jammu and kashmir", "ladakh", "puducherry", "chandigarh")
STATE_RE = re.compile(r"\b(" + "|".join(re.escape(name) for name in STATES) + r")\b", re.I)
SCHEDULE_RE = re.compile(r"\bschedules?\b", re.I)
INSTRUMENT_RE = re.compile(r"\b(?:[A-Z][\w()&-]*\s+)+(?:Rules|Regulations)\b|\b(?:rules|regulations),?\s+(?:18|19|20)\d\d\b")
CASE_LAW_RE = re.compile(r"\b(?:judge?ments?|case\s+laws?|precedents?|rulings?)\b", re.I)
WEAK_MATCH_SHARE = 0.5
# Words people use to phrase a question, which legal text rarely contains;
# they say nothing about whether the index holds the answer.
QUESTION_WORDS = {"why", "explain", "whether", "when", "where", "who", "whom", "tell", "know",
                  "please", "about", "am", "if", "should", "must", "will", "would", "could"}
SUFFIXES = ("ations", "ation", "ments", "ment", "ings", "ing", "ions", "ion", "ies", "ied",
            "ers", "er", "ed", "es", "s")


def _stem(word: str) -> str:
    """A light suffix strip applied to both query and text, so "requests"
    meets "request" without "quantum" meeting "quantity"."""
    word = word.lower()
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _known_act_notices(query, known_titles, indexed_mentions, unmatched_title=None):
    """Notices for listed Acts the query names, unless that same mention is an indexed Act.

    A name the existing cited-title notice already covers is not repeated. Matching
    is whole-word and case-insensitive, so one short name is not found inside a longer one.
    """
    if not known_titles:
        return []
    covered = [match.span() for pattern in indexed_mentions for match in pattern.finditer(query)]
    cited = None
    if unmatched_title:
        cited_match = re.search(r"(?<!\w)" + r"\s+".join(re.escape(part) for part in unmatched_title.split()) + r"(?!\w)", query)
        cited = cited_match.span() if cited_match else None

    def already_named(start, end):
        if any(left <= start and end <= right for left, right in covered):
            return True
        return cited is not None and start < cited[1] and cited[0] < end

    notices = []
    for entry in known_titles:
        spans = [match.span() for pattern in entry["patterns"] for match in pattern.finditer(query)]
        if any(not already_named(start, end) for start, end in spans):
            notices.append({"code": "act_not_indexed",
                            "message": f"\u201c{entry['title']}\u201d is not one of the indexed Acts."})
    return notices


def coverage_notices(query, parsed, topic_terms, unmatched_title, results, records,
                     known_titles=(), indexed_mentions=()):
    """Notices telling the reader where a query reaches outside the index."""
    # Quoted or not, a query about a schedule or a rule is about something the
    # index does not hold; quotes change citation parsing, not scope.
    text = query
    notices = []
    if unmatched_title:
        notices.append({"code": "act_not_indexed",
                        "message": f"\u201c{unmatched_title} Act\u201d is not one of the indexed Acts, so no results are shown for it."})
    notices.extend(_known_act_notices(query, known_titles, indexed_mentions, unmatched_title))
    if SCHEDULE_RE.search(text):
        notices.append({"code": "schedules_not_indexed",
                        "message": "Schedules are not searchable yet. Results come from sections only; open a source PDF to read a schedule."})
    if INSTRUMENT_RE.search(text):
        notices.append({"code": "instruments_not_indexed",
                        "message": "Rules, regulations and notifications made under these Acts are not included. Results show the Acts themselves."})
    if CASE_LAW_RE.search(text):
        notices.append({"code": "case_law_not_indexed",
                        "message": "Court judgments are not included. Results show statutory text only."})
    state = STATE_RE.search(text)
    if state:
        notices.append({"code": "state_law_not_indexed",
                        "message": f"Only central Acts are indexed; {state.group(1).title()} state laws are not included."})
    # A lexical index returns anything sharing a word with the query. When even
    # the best result holds fewer than half the query's words, say so.
    words = [t for t in topic_terms if not t.isdigit() and t not in QUESTION_WORDS]
    if len(words) >= 3 and results:
        best = 0.0
        for result in results:
            record = records[result["key"]]
            # An Act's own short names count as present: "RTI" names the Act
            # even though its body never says "RTI".
            text = " ".join((record["act_title"], record["heading"], record["body_text"],
                             *ALIASES.get(record["act_slug"], [])))
            present = {_stem(token) for token in TOKEN.findall(text)}
            best = max(best, sum(_stem(word) in present for word in words) / len(words))
        if best < WEAK_MATCH_SHARE:
            notices.append({"code": "weak_match",
                            "message": "No result contains most of your search words. The answer may not be in the indexed text."})
    return notices


class Unavailable(Exception):
    """Required import or evidence is missing/malformed; do not serve old text."""


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text())


def source_url(value):
    parsed = urlparse(value or "")
    if parsed.scheme != "https" or parsed.hostname != "indiacode.gov.in":
        raise ValueError("unverified source host")
    return value


def query_terms(query: str):
    if len(query) > 500:
        raise ValueError("Query must contain at most 500 characters.")
    return list(dict.fromkeys(t.lower() for t in TOKEN.findall(query) if t.lower() not in STOPWORDS))[:40]


def parse_query(query: str) -> dict:
    """Split a query into literal phrases, citation constraints and topic terms.

    Constraints (section, Act number, Act year) are parsed only from text
    outside quotes and are removed before topic terms are taken, so "Act, 2005"
    identifies an Act rather than ranking provisions whose text mentions 2005.
    """
    if len(query) > 500:
        raise ValueError("Query must contain at most 500 characters.")
    phrases: list[tuple[str, ...]] = []

    def take_phrase(match):
        tokens = tuple(t.lower() for t in TOKEN.findall(match.group(1)))
        if tokens and len(phrases) < MAX_PHRASES:
            phrases.append(tokens)
        return " "
    unquoted = remainder = PHRASE.sub(take_phrase, query)
    act_number = year = None
    citation = ACT_NUMBER.search(remainder)
    if citation:
        act_number, year = citation.group(1).lstrip("0") or "0", citation.group(2)
        remainder = ACT_NUMBER.sub(" ", remainder, count=1)
    cited_title = None
    if not citation:
        dated = ACT_YEAR.search(remainder)
        if dated:
            year = dated.group(1) or dated.group(2)
            if dated.group(1):
                cited_title = cited_title_before(remainder[:dated.start()])
            remainder = ACT_YEAR.sub(" ", remainder, count=1)
    section_match = SECTION.search(remainder)
    section = section_match.group(1).lower() if section_match else None
    return {"phrases": phrases, "act_number": act_number, "year": year, "section": section,
            "cited_title": cited_title,
            "unquoted": unquoted, "remainder": remainder, "terms": query_terms(remainder)}


def cited_title_before(text: str):
    """The capitalised name written immediately before "Act", if any."""
    run = TITLE_RUN.search(text)
    if not run:
        return None
    words = run.group(1).split()
    # A cited title starts at its first capitalised word ("the POSH" -> "POSH").
    while words and words[0].lower() in TITLE_CONNECTORS and not words[0][0].isupper():
        words.pop(0)
    named = [w for w in (x.strip("(),") for x in words)
             if w and w[0].isupper() and w.lower() not in TITLE_CONNECTORS]
    return " ".join(words) if named else None


def title_year(title: str):
    """The year printed in the Act's own title, which can differ from the
    source's recorded Act year (the Competition Act, 2002 is Act 12 of 2003)."""
    match = re.search(r"(?<!\d)(" + YEAR + r")(?!\d)", title or "")
    return match.group(1) if match else None


def title_patterns(title: str):
    """Forms under which an Act title may be cited: with or without the leading
    'The' and the trailing year, whitespace-tolerant, whole words only."""
    base = re.sub(r"\.\s*$", "", title.strip())
    forms = {base, re.sub(r",?\s*" + YEAR + r"$", "", base)}
    forms |= {re.sub(r"^the\s+", "", f, flags=re.I) for f in list(forms)}
    return [re.compile(r"(?<!\w)" + r"\s+".join(re.escape(w) for w in f.split()) + r"(?!\w)", re.I)
            for f in forms if f]


KNOWN_ACT_TITLES = "data/reference/central_act_titles.v1.json"


def short_name_pattern(name: str):
    parts = name.split()
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(part) for part in parts) + r"(?!\w)", re.I)


def validate_known_titles(entries, indexed_titles):
    """Reject duplicate titles, short names under 3 characters, and any title
    that would also match one of the indexed Acts."""
    if not isinstance(entries, list):
        raise ValueError("known Act titles must be a list")
    indexed = []
    for title in indexed_titles:
        if not isinstance(title, str) or not title.strip():
            raise ValueError("indexed Act title must be a non-empty string")
        indexed.append((title, title_patterns(title)))
    accepted = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("known Act title entry must be an object")
        title, short_names, year = entry.get("title"), entry.get("short_names"), entry.get("year")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("known Act title must be a non-empty string")
        if not isinstance(short_names, list):
            raise ValueError("known Act short names must be a list")
        for name in short_names:
            if not isinstance(name, str) or len(name.strip()) < 3:
                raise ValueError(f"short name too short: {name!r}")
        if isinstance(year, bool) or not isinstance(year, int):
            raise ValueError("known Act year must be an integer")
        patterns = title_patterns(title)
        known_count = len(accepted)
        for index, (other, other_patterns) in enumerate(accepted + indexed):
            if any(pattern.search(other) for pattern in patterns) or any(pattern.search(title) for pattern in other_patterns):
                kind = "duplicate known Act title" if index < known_count else "known Act title collides with an indexed Act"
                raise ValueError(f"{kind}: {title}")
        accepted.append((title, patterns))
    return entries


def load_known_titles(path, indexed_titles):
    data = read_json(Path(path))
    if not isinstance(data, dict):
        raise ValueError("known Act titles file must be an object")
    provenance = data.get("provenance")
    if not isinstance(provenance, str) or not provenance.strip():
        raise ValueError("known Act titles need a provenance statement")
    entries = validate_known_titles(data.get("titles"), indexed_titles)
    loaded = []
    for entry in entries:
        patterns = list(title_patterns(entry["title"]))
        patterns.extend(short_name_pattern(name.strip()) for name in entry["short_names"])
        loaded.append({"title": entry["title"].strip(), "year": entry["year"], "patterns": patterns})
    return loaded


def _candidate_pairs(pairs):
    return {key: value for key, value in pairs if key in ("candidates", "key")}


def candidate_section_keys(path: Path):
    """Casefolded provision key to source section label, or None if unusable.

    The candidate file is read for keys only. Its text is discarded, and a
    missing or malformed file adds no notice rather than failing search.
    """
    try:
        data = json.loads(Path(path).read_text(), object_pairs_hook=_candidate_pairs)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    items = data.get("candidates")
    if not isinstance(items, list):
        return None
    found = {}
    for item in items:
        if not isinstance(item, dict):
            return None
        key = item.get("key")
        if not isinstance(key, str) or key.count(":") != 1:
            return None
        slug, label = key.split(":", 1)
        if not slug or not label:
            return None
        found[key.casefold()] = label
    return found


def one_indexed_act(acts, selected_acts, act_filter):
    """The single indexed Act a query names by title, alias or the act filter."""
    chosen = []
    for slug in selected_acts:
        if slug in acts and slug not in chosen:
            chosen.append(slug)
    if isinstance(act_filter, str) and act_filter.strip():
        wanted = act_filter.casefold()
        for slug in acts:
            if slug.casefold() == wanted and slug not in chosen:
                chosen.append(slug)
    return chosen[0] if len(chosen) == 1 else None


def held_back_section_notice(act_slug, act_title, section, source_keys, records):
    """Notice when the named section is in the source file but not searchable."""
    if not act_slug or not section:
        return None
    labels = source_keys.get(act_slug) if source_keys else None
    if not labels:
        return None
    key = f"{act_slug}:{section}".casefold()
    label = labels.get(key)
    if label is None or any(name.casefold() == key for name in records):
        return None
    return {"code": "section_not_indexed",
            "message": (f"Section {label} of {act_title} exists in the source but is not searchable yet. "
                        "Open the source PDF to read it.")}


def merge_spans(spans):
    merged = []
    for left, right in sorted(spans):
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    return merged


def excerpt_context(text: str, position: int | None) -> dict | None:
    """Sub-section and proviso the position falls in, per the text's own markers."""
    if position is None:
        return None
    subsection, scope_start = None, 0
    for marker in SUBSECTION.finditer(text):
        if marker.start(1) > position:
            break
        subsection, scope_start = marker.group(1), marker.end()
    proviso = any(scope_start <= m.start() <= position for m in PROVISO.finditer(text))
    return {"subsection": subsection, "proviso": proviso}


def excerpt(text: str, terms: list[str], phrases: tuple[tuple[str, ...], ...] = ()) -> dict:
    """Exact Unicode-code-point slice; segments avoid JS offset ambiguities."""
    phrase_spans = []
    for tokens in phrases:
        pattern = re.compile(r"(?<!\w)" + r"\W+".join(re.escape(t) for t in tokens) + r"(?!\w)", re.I)
        phrase_spans += [(m.start(), m.end()) for m in pattern.finditer(text)]
    term_spans = [(m.start(), m.end()) for m in TOKEN.finditer(text) if m.group().lower() in terms]
    # Anchor on the first literal phrase when one is found; else the first term.
    anchor = min(phrase_spans)[0] if phrase_spans else (min(term_spans)[0] if term_spans else None)
    start = max(0, anchor - 70) if anchor is not None else 0
    end = min(len(text), start + 320)
    spans = [(l, r) for l, r in merge_spans(phrase_spans + term_spans) if start <= l and r <= end]
    segments, cursor = [], start
    for left, right in spans:
        if left > cursor:
            segments.append({"text": text[cursor:left], "match": False})
        segments.append({"text": text[left:right], "match": True})
        cursor = right
    if cursor < end:
        segments.append({"text": text[cursor:end], "match": False})
    return {"text": text[start:end], "start": start, "end": end,
            "offset_unit": "unicode_code_points", "segments": segments,
            "omitted_before": start > 0, "omitted_after": end < len(text),
            "context": excerpt_context(text, anchor)}


class Snapshot:
    def __init__(self, root: Path = ROOT, db: Path | None = None):
        self.root = Path(root)
        self.db = db or self.root / "data/import/lawindex_offline.sqlite3"
        self.records: dict[str, dict] = {}
        self.pdfs: dict[str, bytes] = {}
        self.acts: dict[str, dict] = {}
        self.known_titles: list[dict] = []
        self.indexed_mentions: list = []
        self.source_keys: dict[str, dict[str, str]] = {}
        # Values shared by many provisions are read once per snapshot (that is,
        # once per request), never across requests, so a changed or withdrawn
        # reviewer file is still caught on the very next request.
        self._reviewers: dict[str, tuple[dict, str]] = {}
        self.excluded_count = 0
        self._captures = {}
        started = time.perf_counter()
        try:
            self._load()
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            raise Unavailable("Import or review evidence unavailable. Run the documented offline checks and import.") from error
        self.validation_ms = round((time.perf_counter() - started) * 1000, 3)

    def _capture(self, name):
        if not re.fullmatch(r"[a-z0-9-]+", name):
            raise ValueError("invalid capture name")
        if name not in self._captures:
            meta = read_json(self.root / f"data/discovery/{name}.json")
            # Never trust a metadata-supplied arbitrary filesystem path.
            raw = (self.root / f"data/discovery/{name}.body").read_bytes()
            self._captures[name] = (raw, digest(raw), meta)
        return self._captures[name]

    def _load(self):
        manifest = {m["slug"]: m for m in read_json(self.root / "data/discovery/corpus-manifest.json")["records"]}
        reviews = {}
        for path in sorted((self.root / "data/review").glob("*.review.json")):
            review = read_json(path)
            key = review["provision_key"]
            if key in reviews:
                raise ValueError("duplicate review identity")
            reviews[key] = review
        conn = sqlite3.connect(self.db.resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN")
            if structural_store.schema_version(conn) != structural_store.VERSION:
                raise ValueError("structural migration required")
            rows = conn.execute("""SELECT p.*, d.removed_from_manifest, d.scope_status
                FROM provisions p JOIN documents d USING(act_slug)
                WHERE p.admission_status='admitted'""").fetchall()
            for row in rows:
                p = dict(row)
                review, act = reviews.get(p["provision_key"]), manifest.get(p["act_slug"])
                try:
                    if not review or not act or not self._eligible(p, review, act):
                        self.excluded_count += 1
                        continue
                    reviewer, reviewer_canonical = self._reviewer(review["review"]["reviewer_ref"])
                    p["body_text"], p["footnote_text"] = structural_store.current_text(
                        conn, p, review, reviewer, reviewer_canonical=reviewer_canonical)
                    self._add(p, review, act)
                except (OSError, ValueError, KeyError, TypeError):
                    # A missing, withdrawn or inconsistent version has no legacy fallback.
                    self.excluded_count += 1
        finally:
            conn.close()
        indexed_titles = [act["title"] for act in self.acts.values()]
        self.known_titles = load_known_titles(self.root / KNOWN_ACT_TITLES, indexed_titles)
        mentions = [pattern for act in self.acts.values() for pattern in act["titles"]]
        mentions.extend(short_name_pattern(alias) for aliases in ALIASES.values() for alias in aliases)
        self.indexed_mentions = mentions
        self._load_source_keys()

    def _load_source_keys(self):
        loaded = {}
        directory = self.root / "data/phase3/candidates"
        for slug in self.acts:
            keys = candidate_section_keys(directory / f"{slug}.json")
            if keys:
                loaded[slug] = keys
        self.source_keys = loaded

    def _reviewer(self, ref):
        if ref not in self._reviewers:
            reviewer = read_json(self.root / ref)
            self._reviewers[ref] = (reviewer, structural_store.canonical(reviewer))
        return self._reviewers[ref]

    def _eligible(self, p, review, act):
        if (p["removed_from_manifest"] or p["scope_status"] != "phase1_candidate"
                or act["scope_status"] != "phase1_candidate" or review.get("admission_status") != "admitted"):
            return False
        for field in ("act_slug", "section_number", "heading", "selected_representation", "extraction_method_version"):
            if p[field] != review[field]:
                return False
        if review["extraction_method_version"] not in SUPPORTED_EXTRACTION_METHODS:
            return False
        expected = review.get("expected_output", {})
        if not p["body_text"] or digest(p["body_text"].encode()) != expected.get("body_text_sha256"):
            return False
        if p["body_text_sha256"] != expected["body_text_sha256"]:
            return False
        footnote_hash = digest(p["footnote_text"].encode()) if p["footnote_text"] else NO_FOOTNOTE_EXPECTED
        if footnote_hash != expected.get("footnote_text_sha256"):
            return False
        if p["footnote_text_sha256"] != (footnote_hash if p["footnote_text"] else None):
            return False
        src = review["source_representation"]
        if p["source_capture"] != src["capture"]:
            return False
        if self._capture(src["capture"])[1] != src["sha256"]:
            return False
        if p["source_sha256_actual"] != src["sha256"] or p["source_sha256_declared"] != src["sha256"]:
            return False
        anchor = review.get("pdf_anchor", src)
        if self._capture(anchor["capture"])[1] != anchor["sha256"]:
            return False
        if (p["pdf_capture"], p["pdf_page_from"], p["pdf_page_to"]) != (
                anchor["capture"], anchor["pdf_page_from"], anchor["pdf_page_to"]):
            return False
        if not 1 <= anchor["pdf_page_from"] <= anchor["pdf_page_to"]:
            return False
        if json.loads(p["known_conflicts_json"]) != review.get("known_conflicts", []):
            return False
        return True

    def _add(self, p, review, act):
        conflicts = []
        for issue in review.get("known_conflicts", []):
            if not re.fullmatch(r"[A-Z]+-\d+", issue):
                raise ValueError("invalid conflict identity")
            conflict = read_json(self.root / f"data/review/conflicts/{issue}.json")
            if conflict["scope"]["provision_key"] != p["provision_key"]:
                raise ValueError("conflict belongs to another provision")
            for observation in conflict.get("observations", []):
                if "capture" in observation and "sha256" in observation:
                    if self._capture(observation["capture"])[1] != observation["sha256"]:
                        raise ValueError("conflict evidence changed")
            conflicts.append({"id": issue, "classification": conflict["classification"],
                              "disposition": conflict["disposition"],
                              "explanation": conflict["selected_value_rationale"]})
        anchor = review.get("pdf_anchor", review["source_representation"])
        pdf, pdf_hash, meta = self._capture(anchor["capture"])
        if not pdf.startswith(b"%PDF-"):
            raise ValueError("not a PDF")
        key = p["provision_key"]
        link = "/api/sources/" + quote(key, safe="") + ".pdf"
        metadata = {"year": act.get("year"), "ministry": act.get("ministry"),
                    "document_type": act.get("collection_observed")}
        metadata = {k: v.strip() if isinstance(v, str) and v.strip() else None for k, v in metadata.items()}
        if metadata["year"] is not None and not re.fullmatch(r"[0-9]{4}", metadata["year"]):
            metadata["year"] = None
        act_number = act.get("act_number")
        if not (isinstance(act_number, str) and re.fullmatch(r"[0-9]{1,3}", act_number)):
            act_number = None
        section_count = act.get("section_count_observed")
        known = self.acts.get(p["act_slug"])
        if known is None or known["title"] != act["title"]:
            self.acts[p["act_slug"]] = {
                "title": act["title"], "titles": title_patterns(act["title"]),
                "source_section_count": section_count if isinstance(section_count, int) and section_count >= 0 else None}
        record = {"metadata": metadata, "key": key, "act_slug": p["act_slug"], "act_title": act["title"],
                  "act_number": act_number, "title_year": title_year(act["title"]),
                  "section_number": p["section_number"], "heading": p["heading"],
                  "body_text": p["body_text"], "footnote_text": p["footnote_text"],
                  "representation": p["selected_representation"], "conflicts": conflicts,
                  "source": {"act_url": source_url(act["source_url"]),
                             "viewer_url": source_url(act["pdf_viewer_url"]),
                             "local_pdf_url": link + f"#page={anchor['pdf_page_from']}",
                             "pdf_download_url": link,
                             "pdf_page_from": anchor["pdf_page_from"], "pdf_page_to": anchor["pdf_page_to"],
                             "pdf_sha256": pdf_hash, "text_source_sha256": p["source_sha256_actual"],
                             "fetched_at": meta["fetched_at_utc"],
                             "source_stated_modified_date": act.get("last_modified_display"),
                             "body_text_sha256": p["body_text_sha256"]},
                  "review": review_basis(review),
                  "coverage_note": "Only listed provisions are available; full Act text is not indexed."}
        self.records[key] = record
        self.pdfs[key] = pdf

    def corpus(self):
        acts = {}
        for p in self.records.values():
            act = acts.setdefault(p["act_slug"], {"slug": p["act_slug"], "title": p["act_title"], "metadata": p["metadata"], "provisions": []})
            act["provisions"].append({"key": p["key"], "section_number": p["section_number"], "heading": p["heading"]})
        for act in acts.values():
            act["provisions"].sort(key=lambda p: section_order(p["section_number"]))
        return {"notice": NOTICE, "provision_count": len(self.records), "acts": list(acts.values()),
                "excluded_since_import_count": self.excluded_count, "public_use_permission": "personal_noncommercial_20_acts_user_reported",
                "filter_options": {name: sorted({p["metadata"][name] for p in self.records.values()
                                                if p["metadata"][name] is not None})
                                   for name in ("year", "ministry", "document_type")}}

    def scope(self) -> dict:
        """What a search covers, stated beside every result list."""
        acts = len({p["act_slug"] for p in self.records.values()})
        return {"provision_count": len(self.records), "act_count": acts,
                "statement": (f"Searching {len(self.records):,} sections of {acts} central Acts. Not included: "
                              "schedules, rules and regulations, state laws, court judgments, and sections "
                              "held back because their two official versions disagree.")}

    def navigation(self, key: str) -> dict:
        """Previous/next admitted provision of the same Act, in section order.

        Movement is between admitted provisions only. Sections between them,
        and everything else in the source PDF, are neither indexed nor reviewed.
        """
        p = self.records[key]
        siblings = sorted((r for r in self.records.values() if r["act_slug"] == p["act_slug"]),
                          key=lambda r: section_order(r["section_number"]))
        brief = [{"key": r["key"], "section_number": r["section_number"], "heading": r["heading"]} for r in siblings]
        index = [r["key"] for r in siblings].index(key)
        return {"act_slug": p["act_slug"], "act_title": p["act_title"], "admitted": brief,
                "previous": brief[index - 1] if index > 0 else None,
                "next": brief[index + 1] if index + 1 < len(brief) else None,
                "source_section_count": self.acts[p["act_slug"]]["source_section_count"],
                "note": ("Previous and next move only between admitted provisions of this Act. Sections between "
                         "them, and the rest of the source PDF, are not indexed or reviewed.")}

    def _retriever(self, mode, query, vector_backend):
        if mode == "lexical":
            return LexicalRetriever(ALIASES)
        if vector_backend is None:
            raise Unavailable(f"The {mode} mode needs a vector index, and none is loaded.")
        try:
            vectors.check(vector_backend.index, self.records, vector_backend.model)
        except vectors.IndexMismatch as error:
            raise Unavailable(f"The vector index does not match the admitted corpus: {error}") from error
        query_vector = vector_backend.query_vector(query)
        cls = modes.VectorRetriever if mode == "vector" else modes.HybridRetriever
        return cls(vector_backend.index, query_vector, ALIASES)

    def _notices(self, query, parsed, topic_terms, unmatched_title, results, selected_acts, section, filters):
        notices = coverage_notices(query, parsed, topic_terms, unmatched_title, results, self.records,
                                    self.known_titles, self.indexed_mentions)
        act_slug = one_indexed_act(self.acts, selected_acts, filters.act)
        if act_slug:
            held_back = held_back_section_notice(
                act_slug, self.acts[act_slug]["title"], section, self.source_keys, self.records)
            if held_back:
                notices.append(held_back)
        return notices

    def search(self, query: str, limit: int = 10, *, filters: SearchFilters | None = None,
               mode: str | None = None, vector_backend=None):
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Limit must be between 1 and 20.")
        mode = modes.parse_mode(mode)
        started = time.perf_counter()
        parsed = parse_query(query)
        terms, section, phrases = parsed["terms"], parsed["section"], tuple(parsed["phrases"])
        # A section reference is a structural lookup against provision metadata,
        # not a lexical claim about the body text: an admitted provision is not
        # required to repeat its own section number inside its reviewed text
        # (e.g. rti-2005:6's body starts "(1) A person, who desires..." with no
        # literal "6" anywhere). Only genuine topic words -- what is left of
        # `terms` once the section-number token itself is removed -- are used
        # to build the lexical match; the section number itself never has to
        # appear in indexed text to resolve.
        topic_terms = [t for t in terms if t != section] if section else list(terms)
        # Titles are matched before citation stripping, so "…Act, 2005" still names the Act.
        unquoted = parsed["unquoted"]
        selected_acts = [slug for slug, act in self.acts.items()
                         if any(pattern.search(unquoted) for pattern in act["titles"]) or any(
                             re.search(r"\b" + re.escape(alias.lower()) + r"\b", unquoted.lower()) for alias in ALIASES.get(slug, []))]
        phrase_expressions = ['"' + " ".join(tokens) + '"' for tokens in phrases]
        match_expression = " OR ".join(['"' + t + '"' for t in topic_terms] + phrase_expressions)
        filters = filters or SearchFilters()
        # A cited title that names no admitted Act is not a request for some
        # other Act of the same year: "National Green Tribunal Act, 2010" must
        # not fall back to the FCRA, 2010.
        unmatched_title = parsed["cited_title"] if parsed["cited_title"] and not selected_acts else None
        per_act_cap = None
        retriever = self._retriever(mode, query, vector_backend)
        if unmatched_title:
            retrieval = RetrievalResult((), 0, retriever.method)
        else:
            names_an_act = bool(selected_acts or filters.act or parsed["act_number"])
            per_act_cap = None if names_an_act else max(2, -(-limit * 3 // 10))
            retrieval = retriever.retrieve(self.records, RetrievalRequest(
                match_expression, section, tuple(selected_acts), filters, limit,
                phrases=tuple(phrase_expressions), act_number=parsed["act_number"], year=parsed["year"],
                per_act_cap=per_act_cap))
        candidates = [(c.key, c.score) for c in retrieval.candidates]
        highlight = list(dict.fromkeys(terms + [t for tokens in phrases for t in tokens]))
        results = []
        for key, score in candidates[:limit]:
            p = self.records[key]
            result = {k: v for k, v in p.items() if k not in ("body_text", "footnote_text")}
            result.update({"score": score, "excerpt": excerpt(p["body_text"], highlight, phrases), "has_footnote": bool(p["footnote_text"])})
            results.append(result)
        return {"query": query, "results": results, "total": retrieval.total, "corpus": self.corpus(),
                "excerpt_context_note": CONTEXT_NOTE,
                "scope": self.scope(),
                # Acts whose close matches the per-Act cap kept off this page.
                "more_in_acts": [{"act_slug": slug, "act_title": self.acts[slug]["title"], "close_matches_not_shown": count}
                                 for slug, count in retrieval.held_back] if retrieval.diversified else [],
                "notices": self._notices(query, parsed, topic_terms, unmatched_title, results,
                                         selected_acts, section, filters),
                "trace": {"method": retrieval.method, "mode": mode, "filters": filters.as_dict(),
                          **({"side_ranks": {r["key"]: retriever.side_ranks.get(r["key"], {}) for r in results}}
                             if mode == "hybrid" else {}),
                          "candidate_count": retrieval.total, "candidate_limit": limit, "terms": terms, "match_expression": match_expression,
                          "phrases": [" ".join(tokens) for tokens in phrases],
                          "citation": {"act_number": parsed["act_number"], "year": parsed["year"],
                                       "cited_title": parsed["cited_title"],
                                       "cited_title_unmatched": bool(unmatched_title)},
                          "act_filters": selected_acts, "section_filter": section,
                          "candidates": [{"key": k, "score": s} for k, s in candidates],
                          "final_order": [r["key"] for r in results],
                          "diversity": {"per_act_cap": per_act_cap, "applied": retrieval.diversified,
                                        "competitive_share": COMPETITIVE_SHARE,
                                        "note": "When a query names no Act, no single Act takes more than per_act_cap places on the page; total still counts every match."},
                          "score_note": SCORE_NOTES[mode],
                          "validation_ms": self.validation_ms,
                          "search_ms": round((time.perf_counter() - started) * 1000, 3)}}
