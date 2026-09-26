#!/usr/bin/env python3
"""Run development smoke queries; optional JSON output, no source fetching."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lawindex.search import Snapshot  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    snapshot = Snapshot()
    runs = []
    for line in (ROOT / "data/review/dev-queries.v2.jsonl").read_text().splitlines():
        query = json.loads(line)
        result = snapshot.search(query["query"])
        keys = [r["key"] for r in result["results"]]
        expected = query["expected_provision_key"]
        runs.append({"id": query["id"], "query": query["query"], "expected": expected,
                     "actual_order": keys, "expected_rank": keys.index(expected) + 1 if expected in keys else None,
                     "trace": result["trace"]})
    report = {"scope": "Development smoke queries over four provisions, not a held-out benchmark.",
              "provision_count": len(snapshot.records), "runs": runs}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
