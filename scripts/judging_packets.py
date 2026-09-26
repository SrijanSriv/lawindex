#!/usr/bin/env python3
"""Build per-judge markdown judging packets from a candidate pool, per
docs/phase-4/BENCHMARK_PLAN.md ("Judging" / "Protocol").

Read-only over the pool file and the live corpus; never runs the importer.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawindex.benchmark import QUERIES, corpus_fingerprint, load_queries  # noqa: E402
from lawindex.search import Snapshot  # noqa: E402

DEFAULT_POOL = ROOT / "data/benchmark/pools/pool.v1.json"
DEFAULT_OUT = ROOT / "data/benchmark/judging/packets"
GUIDE_PATH = "docs/phase-4/JUDGING_GUIDE.md"
TRUNCATE_AT = 6000


def shuffled_keys(keys: list[str], judge: str, query_id: str) -> list[str]:
    """Per-judge, per-query shuffle so the two judges see candidates in different orders."""
    order = list(keys)
    random.Random(f"{judge}|{query_id}").shuffle(order)
    return order


def render_candidate(key: str, record: dict) -> str:
    body = record["body_text"]
    if len(body) > TRUNCATE_AT:
        body = body[:TRUNCATE_AT] + f"\n\n[Truncated. Read the rest with: python3 scripts/show_provision.py {key}]"
    footnote = record["footnote_text"] or "(none)"
    return (f"### {key}\n\n"
            f"**Act:** {record['act_title']}\n"
            f"**Section:** {record['section_number']}\n"
            f"**Heading:** {record['heading']}\n\n"
            f"{body}\n\n"
            f"**Footnote:** {footnote}\n")


def render_query_block(query: dict, ordered_keys: list[str], records: dict) -> str:
    lines = [f"## {query['id']}", "", f"**Query:** {query['query']}", f"**Intent:** {query['intent']}"]
    if query.get("filters"):
        lines.append(f"**Filters:** {json.dumps(query['filters'], sort_keys=True)}")
    parts = ["\n".join(lines)]
    parts += [render_candidate(key, records[key]) for key in ordered_keys]
    return "\n\n".join(parts)


def render_packet(judge: str, batch: int, query_blocks: list[str]) -> str:
    header = (f"# Judging packet: judge {judge}, batch {batch:02d}\n\n"
              f"Read {GUIDE_PATH} before judging. Grade each candidate 0-3 against the query's "
              f"stated intent and give a one-sentence rationale for every judgment. Candidates are "
              f"shown with no rank, score or method.\n")
    return "\n\n".join([header] + query_blocks) + "\n"


def build_batches(query_ids, batch_size: int) -> list[list[str]]:
    ordered = sorted(query_ids)
    return [ordered[i:i + batch_size] for i in range(0, len(ordered), batch_size)]


def write_packets(judge: str, pool: dict, queries_by_id: dict, records: dict, batch_size: int,
                   out_dir: Path, fingerprint: str) -> list[Path]:
    batches = build_batches(pool["pools"].keys(), batch_size)
    judge_dir = out_dir / judge
    judge_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for number, query_ids in enumerate(batches, 1):
        query_blocks, expected_queries = [], {}
        for query_id in query_ids:
            query = queries_by_id[query_id]
            keys = [c["key"] for c in pool["pools"][query_id]["candidates"]]
            order = shuffled_keys(keys, judge, query_id)
            expected_queries[query_id] = order
            query_blocks.append(render_query_block(query, order, records))
        md_path = judge_dir / f"batch-{number:02d}.md"
        expected_path = judge_dir / f"batch-{number:02d}.expected.json"
        md_path.write_text(render_packet(judge, number, query_blocks))
        expected_path.write_text(json.dumps(
            {"judge": judge, "batch": number, "corpus_fingerprint": fingerprint, "queries": expected_queries},
            indent=2, ensure_ascii=False) + "\n")
        written.append(md_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", required=True, choices=["A", "B"])
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--queries", type=Path, default=QUERIES)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    pool = json.loads(args.pool.read_text())
    snapshot = Snapshot()
    fingerprint = corpus_fingerprint(snapshot.records)
    if fingerprint != pool["manifest"]["corpus_fingerprint"]:
        print("error: pool was built against a different corpus; re-run pool_candidates.py", file=sys.stderr)
        return 1
    queries_by_id = {q["id"]: q for q in load_queries(args.queries, act_slugs=set(snapshot.acts))}
    missing = set(pool["pools"]) - set(queries_by_id)
    if missing:
        print(f"error: pool references queries not in the query file: {sorted(missing)}", file=sys.stderr)
        return 1
    written = write_packets(args.judge, pool, queries_by_id, snapshot.records, args.batch_size, args.out,
                             fingerprint)
    print(f"Wrote {len(written)} batch(es) for judge {args.judge} to {args.out / args.judge}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
