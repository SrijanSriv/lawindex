#!/usr/bin/env python3
"""Build or update the vector index for the admitted corpus.

    .venv/bin/python scripts/build_vectors.py [--out PATH] [--allow-download]

Embeds every admitted section (whole-section-v1) with the local model in
lawindex/embedding.py. Unchanged sections are reused from an existing index.
Progress is saved after each batch, so an interrupted build resumes. The
index is derived data: it never admits text.
"""
import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lawindex import vectors  # noqa: E402
from lawindex.embedding import Embedder, default_index_path  # noqa: E402
from lawindex.search import Snapshot  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=default_index_path(ROOT))
    parser.add_argument("--allow-download", action="store_true",
                        help="fetch the model weights if they are not cached (the one recorded exception)")
    args = parser.parse_args()

    records = Snapshot().records
    embedder = Embedder(allow_download=args.allow_download)
    previous = None
    if args.out.exists():
        try:
            previous = vectors.load(args.out)
        except (vectors.IndexMismatch, ValueError, KeyError) as error:
            print(f"ignoring unreadable index: {error}")
    started = time.perf_counter()

    def save_progress(partial):
        vectors.save(partial, args.out)
        print(f"  saved {len(partial.vectors)} / {len(records)}", flush=True)

    index = vectors.build(records, embedder.passages, embedder.model_id, previous=previous,
                          batch_size=64, on_batch=save_progress)
    vectors.save(index, args.out)
    vectors.check(index, records, embedder.model_id)
    print(f"index: {args.out} model={index.model} dim={index.dim} records={len(index.vectors)} "
          f"build_s={time.perf_counter() - started:.1f} size_bytes={args.out.stat().st_size}")


if __name__ == "__main__":
    main()
