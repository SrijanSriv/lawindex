#!/usr/bin/env python3
"""Run the retrieval benchmark over the live Snapshot and write a run record.

    python3 scripts/run_benchmark.py [--queries PATH] [--judgments PATH] [--run-id ID] [--out PATH]
                                     [--rankings-only] [--compare RUN_JSON] [--split dev|test]

    python3 scripts/run_benchmark.py --baseline RUN --candidate RUN [--adoption]

Reads the frozen query set (and, unless --rankings-only, the judgments) and
runs every query through the unmodified search system. No network, no
importer run, no ranking change. Schemas: docs/phase-4/BENCHMARK_PLAN.md.

`--baseline` and `--candidate` do not re-run search. They compare two stored
run files with a paired bootstrap on per-query nDCG@10 differences.
`--adoption` is valid only together with both of those. It prints each
condition from docs/phase-4/TARGETS.md and still exits 0 when a condition fails.
"""
import argparse
import json
from pathlib import Path
import platform
import sqlite3
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lawindex import benchmark  # noqa: E402
from lawindex.adoption import adoption_report, format_adoption_report  # noqa: E402
from lawindex.evaluation import aggregate, evaluate_query, paired_ndcg_comparison  # noqa: E402
from lawindex.retrieval import SearchFilters  # noqa: E402
from lawindex.search import Snapshot  # noqa: E402

LIMIT = 20
CODE_FILES_NOTE = "sha256 of every lawindex/*.py plus this script, sorted by path"
# Metric keys compared for --compare, beyond ranking/notices (search_ms and
# wall_ms are timing, not correctness, and are excluded per the plan).
IGNORED_ROW_KEYS = {"search_ms", "wall_ms"}


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")


def code_sha256() -> dict:
    files = sorted({*ROOT.glob("lawindex/*.py"), ROOT / "scripts/run_benchmark.py"},
                   key=lambda p: str(p.relative_to(ROOT)))
    return {str(p.relative_to(ROOT)): benchmark.sha256_hex(p.read_bytes()) for p in files}


def run(args) -> dict:
    snapshot = Snapshot()
    queries_path = args.queries or benchmark.QUERIES
    all_queries = benchmark.load_queries(queries_path, act_slugs=set(snapshot.acts))

    judgments_sha256 = None
    grades_by_query: dict = {}
    if not args.rankings_only:
        judgments_path = args.judgments or benchmark.JUDGMENTS
        judgments = benchmark.read_jsonl(judgments_path)
        fingerprint = benchmark.corpus_fingerprint(snapshot.records)
        try:
            benchmark.validate_judgments(judgments, all_queries, records=snapshot.records,
                                         fingerprint=fingerprint)
        except ValueError as error:
            sys.exit(f"judgments invalid (the corpus may have changed since judging): {error}")
        judgments_sha256 = benchmark.sha256_hex(Path(judgments_path).read_bytes())
        grades_by_query = benchmark.grades_by_query(judgments)

    queries = [q for q in all_queries if q["split"] == args.split] if args.split else all_queries

    backend = None
    if args.mode != "lexical":
        from lawindex.embedding import VectorBackend
        backend = VectorBackend.load(ROOT, args.vector_index)

    rows, method = [], None
    for query in queries:
        filters = SearchFilters(**query["filters"])
        started = time.perf_counter()
        response = snapshot.search(query["query"], limit=LIMIT, filters=filters, mode=args.mode,
                                   vector_backend=backend)
        wall_ms = round((time.perf_counter() - started) * 1000, 6)
        row = evaluate_query(query, response, grades_by_query.get(query["id"], {}), snapshot.records)
        row["wall_ms"] = wall_ms
        rows.append(row)
        method = method or response["trace"]["method"]

    manifest = {
        "run_id": args.run_id or default_run_id(),
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark_plan": "docs/phase-4/BENCHMARK_PLAN.md",
        "queries_sha256": benchmark.sha256_hex(Path(queries_path).read_bytes()),
        "judgments_sha256": judgments_sha256,
        "corpus_fingerprint": benchmark.corpus_fingerprint(snapshot.records),
        "provision_count": len(snapshot.records),
        "code_sha256": code_sha256(),
        "method": method,
        "mode": args.mode,
        "vector_model": backend.model if backend else None,
        "limit": LIMIT,
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "split": args.split or "all",
        "rankings_only": bool(args.rankings_only),
    }
    return {"manifest": manifest, "queries": rows, "aggregate": aggregate(rows)}


def fmt(entry) -> str:
    if not entry or entry.get("mean") is None:
        return "n/a"
    return f"{entry['mean']:.4f}"


def print_summary(result: dict) -> None:
    agg = result["aggregate"]
    lines_order = [name for name in ("overall", "split:dev", "split:test") if name in agg]
    for name in lines_order:
        g = agg[name]
        line = (f"{name:12s} n={g['n']:4d}  nDCG@10={fmt(g['ndcg_at_10'])}  MRR={fmt(g['mrr'])}  "
                f"Recall@10={fmt(g['recall_at_10'])}  Success@3={fmt(g['success_at_3'])}  "
                f"MRR_doc={fmt(g['mrr_doc'])}  notice_recall={fmt(g['notice_recall'])}  "
                f"false_notice={fmt(g['false_notice_rate'])}")
        if "p50_ms" in g:
            line += f"  p50={g['p50_ms']}ms  p95={g['p95_ms']}ms"
        print(line)
    excluded = agg.get("excluded", {})
    total_excluded = sum(len(ids) for ids in excluded.values())
    if total_excluded:
        print(f"excluded: " + ", ".join(f"{reason}={len(ids)}" for reason, ids in excluded.items()))
    # The test split is never inspected per query while tuning; only dev rows are listed here.
    dev_rows = [r for r in result["queries"] if r["split"] == "dev" and r.get("ndcg_at_10") is not None]
    worst = sorted(dev_rows, key=lambda r: r["ndcg_at_10"])[:10]
    if worst:
        print("worst 10 (dev split) by nDCG@10:")
        for r in worst:
            print(f"  {r['id']:8s} nDCG@10={r['ndcg_at_10']:.4f}  {r['category']:20s} {r['ranking'][:1]}")


def print_paired_comparison(report: dict, list_unpaired: bool = True) -> None:
    """Per-split mean of (candidate − baseline) nDCG@10, with the 95% interval.

    Adoption reports pass ``list_unpaired=False`` so query ids are not printed.
    """
    print(f"paired nDCG@10 (candidate - baseline), {report['resamples']} resamples, "
          f"seed {report['seed']}, 95% interval")
    if not report["splits"]:
        print("no paired scored queries")
    for name in sorted(report["splits"]):
        group = report["splits"][name]
        ci = group["ci95"]
        ci_text = "n/a" if not ci else f"[{ci[0]:.6f}, {ci[1]:.6f}]"
        mean = group["mean_difference"]
        mean_text = "n/a" if mean is None else f"{mean:.6f}"
        print(f"split:{name:8s} n={group['n']:4d}  mean difference={mean_text}  95% CI {ci_text}")
    if report["unscored"]:
        print(f"unscored: {len(report['unscored'])} queries with no nDCG@10 in either run")
    if report["unpaired"]:
        if list_unpaired:
            for item in report["unpaired"]:
                print(f"unpaired: {item['id']} ({item['reason']})")
        else:
            print(f"unpaired: {len(report['unpaired'])} queries")


def load_run(path: Path) -> dict:
    data = json.loads(Path(path).read_text())
    queries = data.get("queries") if isinstance(data, dict) else None
    if not isinstance(queries, list):
        raise ValueError(f"{path} has no queries list")
    return data


def compare_runs(old: dict, new: dict) -> list:
    """Differences that make a run non-reproducing (timings and code digest excluded)."""
    diffs = []
    om, nm = old["manifest"], new["manifest"]
    for key in ("corpus_fingerprint", "queries_sha256", "judgments_sha256"):
        if om.get(key) != nm.get(key):
            diffs.append(f"manifest.{key}: {om.get(key)!r} != {nm.get(key)!r}")
    old_rows = {r["id"]: r for r in old["queries"]}
    new_rows = {r["id"]: r for r in new["queries"]}
    for qid in sorted(set(old_rows) | set(new_rows)):
        o, n = old_rows.get(qid), new_rows.get(qid)
        if o is None:
            diffs.append(f"{qid}: present only in the new run")
            continue
        if n is None:
            diffs.append(f"{qid}: present only in the stored run")
            continue
        for key in sorted((set(o) | set(n)) - IGNORED_ROW_KEYS):
            if o.get(key) != n.get(key):
                diffs.append(f"{qid}.{key}: {o.get(key)!r} != {n.get(key)!r}")
    return diffs


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--judgments", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--rankings-only", action="store_true")
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--split", choices=("dev", "test"))
    parser.add_argument("--mode", choices=("lexical", "vector", "hybrid"), default="lexical",
                        help="vector and hybrid need .venv/bin/python and a built vector index")
    parser.add_argument("--vector-index", type=Path,
                        help="vector index file (default: data/index/vectors-bge-small-en-v1.5.json)")
    parser.add_argument("--baseline", type=Path,
                        help="stored run; with --candidate, paired nDCG@10 comparison (no search)")
    parser.add_argument("--candidate", type=Path,
                        help="stored run; with --baseline, paired nDCG@10 comparison (no search)")
    parser.add_argument("--adoption", action="store_true",
                        help="with --baseline and --candidate, print the TARGETS.md adoption report")
    args = parser.parse_args()

    if args.adoption and not (args.baseline and args.candidate):
        sys.exit("--adoption is valid only together with --baseline and --candidate")
    if args.baseline or args.candidate:
        if not (args.baseline and args.candidate):
            sys.exit("paired comparison needs both --baseline and --candidate")
        if any((args.compare, args.rankings_only, args.split, args.queries, args.judgments,
                args.run_id, args.out)):
            sys.exit("paired comparison only reads the two run files; do not combine it with a new run")
        try:
            baseline = load_run(args.baseline)
            candidate = load_run(args.candidate)
            print_paired_comparison(
                paired_ndcg_comparison(baseline["queries"], candidate["queries"]),
                list_unpaired=not args.adoption)
            if args.adoption:
                print(format_adoption_report(adoption_report(baseline, candidate)))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            sys.exit(str(error))
        return

    try:
        result = run(args)
    except ValueError as error:
        sys.exit(str(error))

    out_path = args.out or (ROOT / f"data/benchmark/runs/{result['manifest']['run_id']}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, sort_keys=False) + "\n")

    print_summary(result)

    if args.compare:
        stored = json.loads(Path(args.compare).read_text())
        if stored["manifest"].get("code_sha256") != result["manifest"]["code_sha256"]:
            print("(code differs from the compared run -- informational only)")
        diffs = compare_runs(stored, result)
        if not diffs:
            print("REPRODUCED")
            sys.exit(0)
        for line in diffs[:20]:
            print(line)
        if len(diffs) > 20:
            print(f"... and {len(diffs) - 20} more differences")
        sys.exit(1)


if __name__ == "__main__":
    main()
