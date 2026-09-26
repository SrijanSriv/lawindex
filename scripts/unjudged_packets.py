#!/usr/bin/env python3
"""Build per-judge packets for top-10 pairs that have no v1 judgment.

Reads run files, the v1 query and judgment files, and the live corpus.
Writes <out>/packets/<judge>/batch-NN.md and batch-NN.expected.json, the
layout `merge_judgments.py check --judging <out>` reads. Default <out> is
data/benchmark/judging-v2. Never writes to data/benchmark/judging/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawindex.benchmark import JUDGMENTS, QUERIES, corpus_fingerprint, load_queries, read_jsonl  # noqa: E402
from lawindex.search import Snapshot  # noqa: E402
from scripts import judging_packets as judging_packets  # noqa: E402

DEFAULT_OUT = ROOT / "data/benchmark/judging-v2"
RECORD_FIELDS = ("act_title", "section_number", "heading", "body_text", "footnote_text")


def judged_pairs_from_rows(rows: list[dict]) -> set[tuple[str, str]]:
    return {(row["query_id"], row["provision_key"]) for row in rows}


def load_runs(paths: list[Path]) -> list[dict]:
    runs = []
    for path in paths:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"{path}: {error}") from error
        if not isinstance(data, dict):
            raise ValueError(f"{path}: run file must be a JSON object")
        runs.append(data)
    return runs


def require_fingerprint(runs: list[dict], fingerprint: str) -> None:
    for index, run in enumerate(runs):
        manifest = run.get("manifest") if isinstance(run.get("manifest"), dict) else {}
        got = manifest.get("corpus_fingerprint")
        if got != fingerprint:
            raise ValueError(f"run {index} was built against corpus {got!r}, not the live corpus")


def collect_unjudged(runs: list[dict], judged: set[tuple[str, str]]) -> dict[str, dict]:
    """Map query id to {"split", "keys"} for pairs that still need a judgment.

    Keys stay in first-seen order across `runs` (argument order, then the
    order inside each row). The per-judge shuffle starts from that list, so
    a different order would change the packet.
    """
    by_query: dict[str, dict] = {}
    for index, run in enumerate(runs):
        rows = run.get("queries")
        if not isinstance(rows, list):
            raise ValueError(f"run {index}: missing queries list")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
                raise ValueError(f"run {index}: a query row has no id")
            qid = row["id"]
            raw = row.get("unjudged_in_top_10")
            if raw is None or raw == []:
                continue
            if not isinstance(raw, list):
                raise ValueError(f"{qid}: unjudged_in_top_10 must be a list or null")
            split = row.get("split")
            if split not in ("dev", "test"):
                raise ValueError(f"{qid}: split must be dev or test")
            entry = by_query.get(qid)
            if entry is None:
                entry = {"split": split, "keys": [], "seen": set()}
                by_query[qid] = entry
            elif entry["split"] != split:
                raise ValueError(f"{qid}: runs disagree on split")
            for key in raw:
                if not isinstance(key, str) or not key:
                    raise ValueError(f"{qid}: unjudged key must be a provision key")
                if (qid, key) in judged or key in entry["seen"]:
                    continue
                entry["seen"].add(key)
                entry["keys"].append(key)
    return {qid: {"split": entry["split"], "keys": entry["keys"]}
            for qid, entry in by_query.items() if entry["keys"]}


def count_lines(collected: dict[str, dict]) -> list[str]:
    totals = {"dev": [0, 0], "test": [0, 0]}
    for entry in collected.values():
        if entry["split"] not in totals:
            raise ValueError(f"split must be dev or test, got {entry['split']!r}")
        totals[entry["split"]][0] += 1
        totals[entry["split"]][1] += len(entry["keys"])
    lines = []
    for split in ("dev", "test"):
        queries, pairs = totals[split]
        query_word = "query" if queries == 1 else "queries"
        pair_word = "pair" if pairs == 1 else "pairs"
        lines.append(f"{split}: {queries} {query_word}, {pairs} {pair_word}")
    return lines


def _problems(collected: dict[str, dict], queries_by_id: dict, records: dict) -> list[str]:
    problems = []
    for qid, entry in sorted(collected.items()):
        query = queries_by_id.get(qid)
        if query is None:
            problems.append(f"{qid}: not in the query file")
            continue
        if query.get("split") != entry["split"]:
            problems.append(f"{qid}: split {entry['split']!r} disagrees with the query file")
        if not isinstance(query.get("query"), str) or not query["query"].strip():
            problems.append(f"{qid}: query text is missing")
        if not isinstance(query.get("intent"), str) or not query["intent"].strip():
            problems.append(f"{qid}: intent is missing")
        for key in entry["keys"]:
            record = records.get(key)
            if record is None or any(field not in record for field in RECORD_FIELDS):
                problems.append(f"{qid}: {key} is not an admitted provision")
    return problems


def write_unjudged_packets(collected: dict[str, dict], queries: list[dict], records: dict, judge: str,
                           batch_size: int, judging_dir: Path, fingerprint: str) -> list[Path]:
    if judge not in ("A", "B"):
        raise ValueError("judge must be A or B")
    if batch_size < 1:
        raise ValueError("--batch-size must be at least 1")
    queries_by_id = {query["id"]: query for query in queries}
    problems = _problems(collected, queries_by_id, records)
    if problems:
        raise ValueError("cannot build packets:\n" + "\n".join(problems))
    pool = {"pools": {qid: {"candidates": [{"key": key} for key in entry["keys"]]}
                      for qid, entry in collected.items()}}
    return judging_packets.write_packets(judge, pool, queries_by_id, records, batch_size,
                                         judging_dir / "packets", fingerprint)


def execute(runs: list[dict], queries: list[dict], records: dict, judged: set[tuple[str, str]],
            fingerprint: str, judge: str, batch_size: int, judging_dir: Path) -> list[Path]:
    require_fingerprint(runs, fingerprint)
    collected = collect_unjudged(runs, judged)
    written = write_unjudged_packets(collected, queries, records, judge, batch_size, judging_dir, fingerprint)
    for line in count_lines(collected):
        print(line)
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True, type=Path,
                        help="Benchmark run JSON. Repeat for each run.")
    parser.add_argument("--judge", required=True, choices=["A", "B"])
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="Judging directory (default: data/benchmark/judging-v2). "
                             "Pass the same path to merge_judgments.py check --judging.")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runs = load_runs(args.run)
        snapshot = Snapshot()
        fingerprint = corpus_fingerprint(snapshot.records)
        queries = load_queries(QUERIES, act_slugs=set(snapshot.acts))
        judged = judged_pairs_from_rows(read_jsonl(JUDGMENTS))
        execute(runs, queries, snapshot.records, judged, fingerprint, args.judge, args.batch_size, args.out)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
