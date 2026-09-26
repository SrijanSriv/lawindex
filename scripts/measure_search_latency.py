#!/usr/bin/env python3
"""Measure per-request Snapshot validation and search cost on the live corpus.

Each API request rebuilds the snapshot (evidence re-validation) and a private
FTS5 index. This reports where that time goes so the persistent-index decision
in docs/phase-3 is made from measurement, not assumption. Read-only.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lawindex.search import ROOT, Snapshot  # noqa: E402

QUERIES = ['information', 'RTI section 6', '"give any reason"', 'Act 22 of 2005', 'complaint "three months"',
           'National Green Tribunal', 'exemption from disclosure third party', 'section 9', 'POSH inquiry conciliation',
           'hazardous substances procedural safeguards']


def percentile(values, share):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(share * (len(ordered) - 1)))]


def summary(values):
    return {'n': len(values), 'median_ms': round(statistics.median(values), 3),
            'p95_ms': round(percentile(values, 0.95), 3), 'max_ms': round(max(values), 3)}


def measure_http(root, rounds):
    """Wall-clock time of whole search requests, each of which re-validates
    the corpus, exactly as a browser sees it."""
    import threading
    from urllib.parse import quote
    from urllib.request import urlopen
    from lawindex.server import make_server
    server = make_server(root, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f'http://127.0.0.1:{server.server_port}/api/search?q='
        with urlopen(base + 'warmup') as response:
            response.read()
        times = []
        for _ in range(rounds):
            for query in QUERIES:
                started = time.perf_counter()
                with urlopen(base + quote(query)) as response:
                    response.read()
                times.append((time.perf_counter() - started) * 1000)
    finally:
        server.shutdown()
        server.server_close()
    return {'requests': len(times), 'end_to_end': summary(times),
            'note': 'Whole loopback /api/search requests after one warm-up; each request re-validates the corpus.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds', type=int, default=20)
    parser.add_argument('--root', default=str(ROOT))
    parser.add_argument('--http', action='store_true',
                        help='time whole /api/search requests through the loopback server instead')
    args = parser.parse_args()
    root = Path(args.root)
    if args.http:
        print(json.dumps(measure_http(root, args.rounds), indent=2))
        return
    validation, search, per_query = [], [], {q: [] for q in QUERIES}
    for _ in range(args.rounds):
        started = time.perf_counter()
        snapshot = Snapshot(root)
        validation.append((time.perf_counter() - started) * 1000)
        for query in QUERIES:
            ms = snapshot.search(query)['trace']['search_ms']
            search.append(ms)
            per_query[query].append(ms)
    report = {'provision_count': len(snapshot.records), 'rounds': args.rounds,
              'snapshot_validation': summary(validation), 'search_after_validation': summary(search),
              'per_query_median_ms': {q: round(statistics.median(v), 3) for q, v in per_query.items()},
              'note': 'Wall-clock on this machine; validation dominates and is paid once per HTTP request.'}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
