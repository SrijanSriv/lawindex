#!/usr/bin/env python3
"""Measure the weak_match notice on the frozen benchmark.

One line per dev query, then a threshold sweep. The test split is the same
sweep as counts only, so those queries stay held out. `--json` writes the
same data, again with the test split as counts only.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lawindex import benchmark  # noqa: E402
from lawindex.retrieval import SearchFilters  # noqa: E402
from lawindex.search import (  # noqa: E402
    ALIASES, QUESTION_WORDS, TOKEN, WEAK_MATCH_SHARE, Snapshot, _stem, parse_query,
)

LIMIT = 20
NOTICE_MIN_WORDS = 3
THRESHOLDS = (0.2, 0.3, 0.4, 0.5, 0.6)
MIN_WORD_COUNTS = (3, 4, 5)


def topic_terms(query: str) -> list[str]:
    """The terms Snapshot.search passes into coverage_notices."""
    parsed = parse_query(query)
    terms, section = parsed["terms"], parsed["section"]
    return [t for t in terms if t != section] if section else list(terms)


def content_words(query: str) -> list[str]:
    """Content words the notice scores: topic terms, minus digits and question words."""
    return [t for t in topic_terms(query) if not t.isdigit() and t not in QUESTION_WORDS]


def best_share(words, results, records):
    """Best fraction of content words present in a result. None if either side is empty.

    Presence is the notice's definition: a stemmed query word occurs among the
    stems of the Act title, heading, body and that Act's aliases.
    """
    if not words or not results:
        return None
    best = 0.0
    for result in results:
        record = records[result["key"]]
        text = " ".join((record["act_title"], record["heading"], record["body_text"],
                         *ALIASES.get(record["act_slug"], [])))
        present = {_stem(token) for token in TOKEN.findall(text)}
        best = max(best, sum(_stem(word) in present for word in words) / len(words))
    return best


def notice_would_fire(word_count: int, results, share) -> bool:
    """The notice's gate and its strict half-share comparison, kept together."""
    if word_count < NOTICE_MIN_WORDS or not results or share is None:
        return False
    return share < WEAK_MATCH_SHARE


def measure_query(query: dict, response: dict, records) -> dict:
    words = content_words(query["query"])
    results = response["results"]
    share = best_share(words, results, records)
    fired = any(notice["code"] == "weak_match" for notice in response["notices"])
    return {"id": query["id"], "split": query["split"], "scope": query["scope"],
            "category": query["category"], "content_words": len(words),
            "best_share": share, "weak_match": fired,
            "agrees": fired == notice_would_fire(len(words), results, share)}


def flagged(row: dict, threshold: float, min_words: int) -> bool:
    share = row["best_share"]
    return row["content_words"] >= min_words and share is not None and share < threshold


def sweep(rows: list[dict]) -> list[dict]:
    cells = []
    for threshold in THRESHOLDS:
        for min_words in MIN_WORD_COUNTS:
            chosen = [row for row in rows if flagged(row, threshold, min_words)]
            cells.append({
                "threshold": threshold,
                "min_words": min_words,
                "in_corpus": sum(row["scope"] == "in_corpus" for row in chosen),
                "out_or_partial": sum(row["scope"] in ("out_of_corpus", "partial") for row in chosen),
            })
    return cells


def format_share(share) -> str:
    return "n/a" if share is None else f"{share:.4f}"


def format_query_line(row: dict) -> str:
    fired = "yes" if row["weak_match"] else "no"
    return (f"{row['id']}  {row['scope']}  {row['category']}  "
            f"words={row['content_words']}  share={format_share(row['best_share'])}  "
            f"weak_match={fired}")


def format_sweep_line(cell: dict) -> str:
    return (f"threshold={cell['threshold']:.1f}  min_words={cell['min_words']}  "
            f"in_corpus={cell['in_corpus']}  out_or_partial={cell['out_or_partial']}")


def render(dev_rows: list[dict], dev_sweep: list[dict], test_sweep: list[dict]) -> str:
    lines = ["consistency: held for every query",
             "in_corpus counts are false notices; out_or_partial is out_of_corpus plus partial",
             "dev"]
    lines.extend(format_query_line(row) for row in dev_rows)
    lines.append("dev sweep")
    lines.extend(format_sweep_line(cell) for cell in dev_sweep)
    lines.append("test sweep")
    lines.extend(format_sweep_line(cell) for cell in test_sweep)
    return "\n".join(lines) + "\n"


def public_row(row: dict) -> dict:
    return {"id": row["id"], "scope": row["scope"], "category": row["category"],
            "content_words": row["content_words"], "best_share": row["best_share"],
            "weak_match": row["weak_match"]}


def payload(dev_rows: list[dict], dev_sweep: list[dict], test_sweep: list[dict]) -> dict:
    return {"consistent": True,
            "dev": {"queries": [public_row(row) for row in dev_rows], "sweep": dev_sweep},
            "test": {"sweep": test_sweep}}


def failure_report(rows: list[dict]) -> str:
    dev = [row for row in rows if row["split"] == "dev" and not row["agrees"]]
    test_n = sum(1 for row in rows if row["split"] == "test" and not row["agrees"])
    lines = [f"consistency failed: {len(dev)} dev, {test_n} test"]
    lines.extend(format_query_line(row) for row in dev)
    return "\n".join(lines) + "\n"


def analyze(snapshot, queries: list[dict]) -> list[dict]:
    rows = []
    for query in queries:
        filters = SearchFilters(**query["filters"])
        response = snapshot.search(query["query"], limit=LIMIT, filters=filters)
        rows.append(measure_query(query, response, snapshot.records))
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if WEAK_MATCH_SHARE != 0.5:
        sys.stderr.write(f"WEAK_MATCH_SHARE is {WEAK_MATCH_SHARE}, not 0.5; stopping\n")
        return 1
    snapshot = Snapshot()
    queries = benchmark.load_queries(benchmark.QUERIES, act_slugs=set(snapshot.acts))
    rows = analyze(snapshot, queries)
    if any(not row["agrees"] for row in rows):
        sys.stdout.write(failure_report(rows))
        return 1
    dev = [row for row in rows if row["split"] == "dev"]
    test = [row for row in rows if row["split"] == "test"]
    dev_sweep, test_sweep = sweep(dev), sweep(test)
    sys.stdout.write(render(dev, dev_sweep, test_sweep))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload(dev, dev_sweep, test_sweep), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
