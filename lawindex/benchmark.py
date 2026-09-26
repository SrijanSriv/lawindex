"""Benchmark data contracts: the query set, judgments, splits and the corpus fingerprint.

Schemas are documented in docs/phase-4/BENCHMARK_PLAN.md. Everything here is
pure validation; nothing reads the network or changes the corpus.
"""
import hashlib
import json
from pathlib import Path
import re

from lawindex.retrieval import SearchFilters

ROOT = Path(__file__).resolve().parents[1]
QUERIES = ROOT / "data/benchmark/queries.v1.jsonl"
JUDGMENTS = ROOT / "data/benchmark/judgments.v1.jsonl"

CATEGORIES = ("exact_title", "citation", "topic", "ordinary_language", "terminology_mismatch",
              "acronym", "broad_discovery", "filtered", "out_of_corpus")
LEVELS = ("provision", "document")
SCOPES = ("in_corpus", "partial", "out_of_corpus")
SPLITS = ("dev", "test")
GRADES = (0, 1, 2, 3)
RELEVANT = 2  # binary relevance threshold: grade >= 2
NOTICE_CODES = ("act_not_indexed", "schedules_not_indexed", "instruments_not_indexed",
                "case_law_not_indexed", "state_law_not_indexed", "weak_match")
SPLIT_SALT = "lawindex-bench-v1|"
QUERY_FIELDS = {"id", "info_need", "query", "intent", "category", "level", "scope", "relevant_acts",
                "known_unindexed_targets", "expected_notices", "filters", "split", "origin", "notes"}
REQUIRED_QUERY_FIELDS = {"id", "info_need", "query", "intent", "category", "level", "scope",
                         "filters", "split", "origin"}
JUDGMENT_FIELDS = {"query_id", "provision_key", "grade", "rationale", "source", "resolution",
                   "grades", "reviewer_type", "corpus_fingerprint"}
SOURCES = ("pool", "manual")
RESOLUTIONS = ("agreed", "lower_of_adjacent", "adjudicated")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def split_for(info_need: str, origin: str) -> str:
    """Split is derived, never chosen. Carried-over seeds are dev: the system was built against them."""
    if origin != "authored":
        return "dev"
    return "test" if int(sha256_hex((SPLIT_SALT + info_need).encode()), 16) % 100 < 50 else "dev"


def corpus_fingerprint(records) -> str:
    """Identity of the admitted corpus a run or judgment was made against."""
    rows = [[key, r["act_title"], sha256_hex(r["heading"].encode()), sha256_hex(r["body_text"].encode()),
             sha256_hex((r["footnote_text"] or "").encode())] for key, r in sorted(records.items())]
    return "sha256:" + sha256_hex(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode())


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{number}: invalid JSON ({error.msg})") from error
    return rows


def validate_queries(queries: list[dict], act_slugs=None) -> None:
    """Raise ValueError listing every problem. `act_slugs`, when given, checks relevant_acts and filters."""
    problems = []
    seen, needs = set(), {}
    for q in queries:
        qid = q.get("id", "?")
        def bad(message):
            problems.append(f"{qid}: {message}")
        missing = REQUIRED_QUERY_FIELDS - q.keys()
        if missing:
            bad(f"missing {sorted(missing)}")
            continue
        if q.keys() - QUERY_FIELDS:
            bad(f"unknown fields {sorted(q.keys() - QUERY_FIELDS)}")
        if not re.fullmatch(r"B-\d{3}", qid) or qid in seen:
            bad("id must be unique B-NNN")
        seen.add(qid)
        if not re.fullmatch(r"N-\d{3}", q["info_need"]):
            bad("info_need must be N-NNN")
        for field in ("query", "intent"):
            if not isinstance(q[field], str) or not q[field].strip():
                bad(f"{field} must be non-empty text")
        if q["category"] not in CATEGORIES:
            bad(f"unknown category {q['category']!r}")
        if q["level"] not in LEVELS:
            bad(f"unknown level {q['level']!r}")
        if q["scope"] not in SCOPES:
            bad(f"unknown scope {q['scope']!r}")
        if not (q["origin"] == "authored" or re.fullmatch(r"(seed:P0-0\d\d|dev:DEV-00\d)", q["origin"])):
            bad(f"bad origin {q['origin']!r}")
        if q["split"] != split_for(q["info_need"], q["origin"]):
            bad(f"split {q['split']!r} is not the derived split {split_for(q['info_need'], q['origin'])!r}")
        # Paraphrases share a need and so a split; a need must not mix origins.
        if needs.setdefault(q["info_need"], q["origin"] == "authored") != (q["origin"] == "authored"):
            bad("an info_need mixes authored and carried-over queries")
        if q["level"] == "document":
            if not q.get("relevant_acts") or q["scope"] != "in_corpus":
                bad("document-level queries need relevant_acts and in_corpus scope")
        elif "relevant_acts" in q:
            bad("relevant_acts is only for document-level queries")
        if q["scope"] == "out_of_corpus" and q["level"] != "provision":
            bad("out_of_corpus queries are provision level (nothing to judge)")
        if q["scope"] in ("out_of_corpus", "partial"):
            if q["scope"] == "out_of_corpus" and not q.get("expected_notices"):
                bad("out_of_corpus queries must name expected_notices")
        for code in q.get("expected_notices", []):
            if code not in NOTICE_CODES:
                bad(f"unknown notice code {code!r}")
        if not isinstance(q.get("known_unindexed_targets", []), list):
            bad("known_unindexed_targets must be a list")
        if not isinstance(q["filters"], dict):
            bad("filters must be an object")
        else:
            try:
                SearchFilters(**q["filters"])
            except (TypeError, ValueError) as error:
                bad(f"invalid filters: {error}")
        if act_slugs is not None:
            for slug in q.get("relevant_acts", []):
                if slug not in act_slugs:
                    bad(f"relevant_acts names unknown Act {slug!r}")
            if q["filters"].get("act") and q["filters"]["act"] not in act_slugs:
                bad("filter names an unknown Act")
    if problems:
        raise ValueError("invalid query set:\n" + "\n".join(problems))


def load_queries(path: Path = QUERIES, act_slugs=None) -> list[dict]:
    queries = read_jsonl(path)
    validate_queries(queries, act_slugs)
    return queries


def validate_judgments(judgments: list[dict], queries: list[dict], records=None, fingerprint=None) -> None:
    """Raise ValueError listing every problem. With `records`, every key must be admitted."""
    problems = []
    by_id = {q["id"]: q for q in queries}
    seen = set()
    for number, j in enumerate(judgments, 1):
        def bad(message):
            problems.append(f"judgment {number} ({j.get('query_id')}, {j.get('provision_key')}): {message}")
        if j.keys() != JUDGMENT_FIELDS:
            bad(f"fields must be exactly {sorted(JUDGMENT_FIELDS)}")
            continue
        query = by_id.get(j["query_id"])
        if query is None:
            bad("unknown query")
        elif query["level"] != "provision":
            bad("document-level queries are not judged per provision")
        pair = (j["query_id"], j["provision_key"])
        if pair in seen:
            bad("duplicate pair")
        seen.add(pair)
        if j["grade"] not in GRADES or type(j["grade"]) is not int:
            bad("grade must be 0-3")
        if not isinstance(j["rationale"], str) or not j["rationale"].strip():
            bad("rationale required")
        if j["source"] not in SOURCES or j["resolution"] not in RESOLUTIONS:
            bad("bad source or resolution")
        if j["reviewer_type"] != "ai_model":
            bad("reviewer_type must be ai_model")
        if not isinstance(j["grades"], dict) or not set(j["grades"]) <= {"A", "B"} or any(
                g not in GRADES for g in j["grades"].values()):
            bad("grades must map judge A/B to 0-3")
        if records is not None and j["provision_key"] not in records:
            bad("provision is not admitted in this corpus")
        if fingerprint is not None and j["corpus_fingerprint"] != fingerprint:
            bad("judged against a different corpus")
    if problems:
        raise ValueError("invalid judgments:\n" + "\n".join(problems))


def grades_by_query(judgments: list[dict]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for j in judgments:
        out.setdefault(j["query_id"], {})[j["provision_key"]] = j["grade"]
    return out
