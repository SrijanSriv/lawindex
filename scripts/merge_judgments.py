#!/usr/bin/env python3
"""Validate judge output and merge two independent judgments into the graded
judgments file, per docs/phase-4/BENCHMARK_PLAN.md ("Judging" / "Merge").

Read-only over the judging directory and the live corpus, except for the
files this script itself writes under --judging and --out.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawindex.benchmark import (GRADES, JUDGMENTS, QUERIES, RELEVANT, SOURCES, load_queries,  # noqa: E402
                                 read_jsonl, validate_judgments)
from lawindex.search import Snapshot  # noqa: E402

JUDGES = ("A", "B")
BATCH_FILE_RE = re.compile(r"batch-(\d+)\.expected\.json")
DEFAULT_JUDGING = ROOT / "data/benchmark/judging"


def batch_path(judging: Path, judge: str, batch: int, kind: str) -> Path:
    if kind == "expected":
        return judging / "packets" / judge / f"batch-{batch:02d}.expected.json"
    if kind == "raw":
        return judging / "raw" / judge / f"batch-{batch:02d}.jsonl"
    raise ValueError(kind)


def check_batch(judging: Path, judge: str, batch: int, records: dict) -> tuple[list[str], dict]:
    """Validate one judge output file against its packet.

    Returns (problems, counts) where counts is {"judgments": pool judgments,
    "manual": manual judgments, "unindexed": unindexed_target lines}. An
    empty `problems` list means the batch is OK.
    """
    problems: list[str] = []
    counts = {"judgments": 0, "manual": 0, "unindexed": 0}
    expected_path = batch_path(judging, judge, batch, "expected")
    raw_path = batch_path(judging, judge, batch, "raw")
    if not expected_path.exists():
        return [f"missing packet {expected_path}"], counts
    if not raw_path.exists():
        return [f"missing judge output {raw_path}"], counts

    expected_queries: dict = json.loads(expected_path.read_text())["queries"]
    expected_pairs = {(qid, key) for qid, keys in expected_queries.items() for key in keys}
    seen_pool_pairs: set = set()
    manual_seen: dict = {}
    manual_totals: dict = {}

    for number, line in enumerate(read_jsonl(raw_path), 1):
        def bad(message: str, _number=number):
            problems.append(f"{raw_path}:{_number}: {message}")

        kind = line.get("kind")
        if kind == "judgment":
            query_id, key = line.get("query_id"), line.get("provision_key")
            grade, rationale, source = line.get("grade"), line.get("rationale"), line.get("source")
            if grade not in GRADES or type(grade) is not int:
                bad(f"grade must be 0-3 ({query_id}, {key})")
            if not isinstance(rationale, str) or not rationale.strip():
                bad(f"rationale required ({query_id}, {key})")
            if source not in SOURCES:
                bad(f"bad source {source!r} ({query_id}, {key})")
            elif source == "pool":
                pair = (query_id, key)
                if pair not in expected_pairs:
                    bad(f"unexpected pool judgment ({query_id}, {key})")
                elif pair in seen_pool_pairs:
                    bad(f"duplicate pool judgment ({query_id}, {key})")
                else:
                    seen_pool_pairs.add(pair)
                    counts["judgments"] += 1
            else:  # manual
                counts["manual"] += 1
                if query_id not in expected_queries:
                    bad(f"manual judgment for a query not in this batch ({query_id}, {key})")
                else:
                    if key in expected_queries[query_id]:
                        bad(f"manual key already in the pool ({query_id}, {key})")
                    seen = manual_seen.setdefault(query_id, set())
                    if key in seen:
                        bad(f"repeated manual key ({query_id}, {key})")
                    seen.add(key)
                    manual_totals[query_id] = manual_totals.get(query_id, 0) + 1
                    if key not in records:
                        bad(f"manual key is not an admitted provision ({query_id}, {key})")
        elif kind == "unindexed_target":
            counts["unindexed"] += 1
            target, rationale = line.get("target"), line.get("rationale")
            if not isinstance(target, str) or not target.strip():
                bad("unindexed_target target must be non-empty")
            if not isinstance(rationale, str) or not rationale.strip():
                bad("rationale required")
            if line.get("query_id") not in expected_queries:
                bad(f"unindexed_target for a query not in this batch ({line.get('query_id')})")
        else:
            bad(f"unknown kind {kind!r}")

    for pair in sorted(expected_pairs - seen_pool_pairs):
        problems.append(f"{raw_path}: missing pool judgment for {pair}")
    for query_id, total in manual_totals.items():
        if total > 5:
            problems.append(f"{raw_path}: {query_id}: more than five manual judgments ({total})")
    return problems, counts


def discover_batches(judging: Path, judge: str) -> list[int]:
    packet_dir = judging / "packets" / judge
    if not packet_dir.exists():
        return []
    numbers = []
    for path in packet_dir.glob("batch-*.expected.json"):
        match = BATCH_FILE_RE.match(path.name)
        if match:
            numbers.append(int(match.group(1)))
    return sorted(numbers)


def compute_agreement(pool_grades: dict, query_category: dict) -> dict:
    """pool_grades: {(query_id, key): {"A": (grade, rationale), "B": (grade, rationale)}}."""

    def stats(pairs: list[tuple[int, int]]) -> dict:
        n = len(pairs)
        if n == 0:
            return {"pairs": 0, "exact_agreement": None, "within_one_agreement": None, "kappa": None}
        exact = sum(1 for a, b in pairs if a == b) / n
        within_one = sum(1 for a, b in pairs if abs(a - b) <= 1) / n
        labels_a = [1 if a >= RELEVANT else 0 for a, _b in pairs]
        labels_b = [1 if b >= RELEVANT else 0 for _a, b in pairs]
        observed = sum(1 for x, y in zip(labels_a, labels_b) if x == y) / n
        p_yes_a, p_yes_b = sum(labels_a) / n, sum(labels_b) / n
        expected = p_yes_a * p_yes_b + (1 - p_yes_a) * (1 - p_yes_b)
        if abs(1 - expected) < 1e-12:
            kappa = 1.0 if observed == 1.0 else 0.0
        else:
            kappa = (observed - expected) / (1 - expected)
        return {"pairs": n, "exact_agreement": exact, "within_one_agreement": within_one, "kappa": kappa}

    pairs = [(v["A"][0], v["B"][0]) for v in pool_grades.values()]
    by_category: dict[str, list] = {}
    for (query_id, _key), grades in pool_grades.items():
        by_category.setdefault(query_category.get(query_id, "unknown"), []).append(
            (grades["A"][0], grades["B"][0]))
    return {"overall": stats(pairs), "by_category": {cat: stats(by_category[cat]) for cat in sorted(by_category)}}


class MergeIncomplete(Exception):
    """Raised when data/benchmark/judgments.v1.jsonl cannot be written yet."""

    def __init__(self, remaining: int):
        self.remaining = remaining
        super().__init__(f"{remaining} pairs remain")


def merge_judgments(judging: Path, out_path: Path, queries: list[dict], records: dict) -> list[dict]:
    """Merge both judges' output. Writes agreement.json, to_adjudicate.jsonl and
    unindexed_targets.json under `judging` unconditionally, then writes `out_path`
    (validated with validate_judgments) only if adjudication.jsonl exists and
    covers every pair in to_adjudicate.jsonl exactly.

    Raises ValueError if a batch fails check or the two judges' batches disagree.
    Raises MergeIncomplete (with .remaining) when adjudication is not yet complete.
    """
    batches = {judge: discover_batches(judging, judge) for judge in JUDGES}
    if not batches["A"] or batches["A"] != batches["B"]:
        raise ValueError(f"judge batches differ: A={batches['A']} B={batches['B']}")

    failures = []
    for judge in JUDGES:
        for batch in batches[judge]:
            problems, _counts = check_batch(judging, judge, batch, records)
            failures += [f"{judge} batch {batch}: {p}" for p in problems]
    if failures:
        raise ValueError("batches failed check:\n" + "\n".join(failures))

    pool_grades: dict = {}
    manual_entries: dict = {}
    unindexed: dict = {}
    fingerprints = set()
    for judge in JUDGES:
        for batch in batches[judge]:
            expected = json.loads(batch_path(judging, judge, batch, "expected").read_text())
            fingerprints.add(expected["corpus_fingerprint"])
            for line in read_jsonl(batch_path(judging, judge, batch, "raw")):
                if line["kind"] == "judgment":
                    pair = (line["query_id"], line["provision_key"])
                    bucket = pool_grades if line["source"] == "pool" else manual_entries
                    bucket.setdefault(pair, {})[judge] = (line["grade"], line["rationale"])
                else:
                    per_query = unindexed.setdefault(line["query_id"], {})
                    entry = per_query.setdefault(line["target"], {"judges": [], "rationales": {}})
                    if judge not in entry["judges"]:
                        entry["judges"].append(judge)
                    entry["rationales"][judge] = line["rationale"]
    if len(fingerprints) != 1:
        raise ValueError(f"packets were built against different corpora: {sorted(fingerprints)}")
    fingerprint = fingerprints.pop()

    resolved: dict = {}
    to_adjudicate = []
    for pair, by_judge in pool_grades.items():
        grade_a, rationale_a = by_judge["A"]
        grade_b, rationale_b = by_judge["B"]
        if grade_a == grade_b:
            resolved[pair] = ("agreed", grade_a, rationale_a)
        elif (grade_a >= RELEVANT) == (grade_b >= RELEVANT) and abs(grade_a - grade_b) == 1:
            resolved[pair] = ("lower_of_adjacent", min(grade_a, grade_b), rationale_a)
        else:
            to_adjudicate.append({"query_id": pair[0], "provision_key": pair[1], "source": "pool",
                                   "grade_a": grade_a, "rationale_a": rationale_a,
                                   "grade_b": grade_b, "rationale_b": rationale_b})
    for pair, by_judge in manual_entries.items():
        grade_a, rationale_a = by_judge.get("A", (None, None))
        grade_b, rationale_b = by_judge.get("B", (None, None))
        to_adjudicate.append({"query_id": pair[0], "provision_key": pair[1], "source": "manual",
                               "grade_a": grade_a, "rationale_a": rationale_a,
                               "grade_b": grade_b, "rationale_b": rationale_b})
    to_adjudicate.sort(key=lambda row: (row["query_id"], row["provision_key"]))

    query_category = {q["id"]: q["category"] for q in queries}
    agreement = compute_agreement(pool_grades, query_category)
    unindexed_out = {
        query_id: [{"target": target, "judges": sorted(entry["judges"]), "rationales": entry["rationales"]}
                    for target, entry in sorted(targets.items())]
        for query_id, targets in sorted(unindexed.items())
    }

    judging.mkdir(parents=True, exist_ok=True)
    (judging / "agreement.json").write_text(json.dumps(agreement, indent=2) + "\n")
    (judging / "to_adjudicate.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in to_adjudicate))
    (judging / "unindexed_targets.json").write_text(
        json.dumps(unindexed_out, indent=2, ensure_ascii=False) + "\n")

    to_adjudicate_pairs = {(row["query_id"], row["provision_key"]) for row in to_adjudicate}
    adjudication_path = judging / "adjudication.jsonl"
    adjudicated = {}
    if adjudication_path.exists():
        for line in read_jsonl(adjudication_path):
            adjudicated[(line["query_id"], line["provision_key"])] = line
    if not adjudication_path.exists() or set(adjudicated) != to_adjudicate_pairs:
        raise MergeIncomplete(len(to_adjudicate_pairs - set(adjudicated)))

    judgments = []
    for pair, (resolution, grade, rationale) in resolved.items():
        grades = {"A": pool_grades[pair]["A"][0], "B": pool_grades[pair]["B"][0]}
        judgments.append({"query_id": pair[0], "provision_key": pair[1], "grade": grade, "rationale": rationale,
                           "source": "pool", "resolution": resolution, "grades": grades,
                           "reviewer_type": "ai_model", "corpus_fingerprint": fingerprint})
    for row in to_adjudicate:
        pair = (row["query_id"], row["provision_key"])
        adjudication = adjudicated[pair]
        grades = {}
        if row["grade_a"] is not None:
            grades["A"] = row["grade_a"]
        if row["grade_b"] is not None:
            grades["B"] = row["grade_b"]
        judgments.append({"query_id": pair[0], "provision_key": pair[1], "grade": adjudication["grade"],
                           "rationale": adjudication["rationale"], "source": row["source"],
                           "resolution": "adjudicated", "grades": grades,
                           "reviewer_type": "ai_model", "corpus_fingerprint": fingerprint})
    judgments.sort(key=lambda j: (j["query_id"], j["provision_key"]))
    validate_judgments(judgments, queries, records=records, fingerprint=fingerprint)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in judgments))
    return judgments


def cmd_check(args) -> int:
    problems, counts = check_batch(args.judging, args.judge, args.batch, Snapshot().records)
    if problems:
        for problem in problems:
            print(problem)
        return 1
    print(f"OK {counts['judgments']} judgments, {counts['manual']} manual, {counts['unindexed']} unindexed")
    return 0


def cmd_merge(args) -> int:
    snapshot = Snapshot()
    queries = load_queries(args.queries, act_slugs=set(snapshot.acts))
    try:
        judgments = merge_judgments(args.judging, args.out, queries, snapshot.records)
    except MergeIncomplete as incomplete:
        print(f"{incomplete.remaining} pairs remain")
        return 0
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Wrote {len(judgments)} judgments to {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check_parser = sub.add_parser("check", help="Validate one judge output file.")
    check_parser.add_argument("--judge", required=True, choices=JUDGES)
    check_parser.add_argument("--batch", required=True, type=int)
    check_parser.add_argument("--judging", type=Path, default=DEFAULT_JUDGING)
    check_parser.set_defaults(func=cmd_check)

    merge_parser = sub.add_parser("merge", help="Merge both judges' completed output.")
    merge_parser.add_argument("--judging", type=Path, default=DEFAULT_JUDGING)
    merge_parser.add_argument("--out", type=Path, default=JUDGMENTS)
    merge_parser.add_argument("--queries", type=Path, default=QUERIES)
    merge_parser.set_defaults(func=cmd_merge)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
