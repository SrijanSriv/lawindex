#!/usr/bin/env python3
"""Print admitted provisions for manual pool exploration and judging support.

Read-only: never runs the importer, never writes to the database, never makes
a network connection.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawindex.retrieval import section_order  # noqa: E402
from lawindex.search import Snapshot  # noqa: E402

SNIPPET_RADIUS = 80
SNIPPET_LENGTH = 160


def snippet(text: str, match: re.Match) -> str:
    start = max(0, match.start() - SNIPPET_RADIUS)
    end = min(len(text), start + SNIPPET_LENGTH)
    return text[start:end]


def show_keys(records: dict, keys: list[str], out=sys.stdout) -> int:
    unknown = [key for key in keys if key not in records]
    if unknown:
        print(f"error: unknown provision key(s): {', '.join(unknown)}", file=sys.stderr)
        return 1
    for key in keys:
        r = records[key]
        print(f"=== {key} ===", file=out)
        print(f"Act: {r['act_title']}", file=out)
        print(f"Section: {r['section_number']}", file=out)
        print(f"Heading: {r['heading']}", file=out)
        print("Body:", file=out)
        print(r["body_text"], file=out)
        print("Footnote:", file=out)
        print(r["footnote_text"] or "(none)", file=out)
        print(file=out)
    return 0


def show_act(records: dict, acts: dict, slug: str, out=sys.stdout) -> int:
    if slug not in acts:
        print(f"error: unknown Act {slug!r}", file=sys.stderr)
        return 1
    sections = sorted((r for r in records.values() if r["act_slug"] == slug),
                       key=lambda r: section_order(r["section_number"]))
    print(f"{acts[slug]['title']} ({slug}): {len(sections)} admitted sections", file=out)
    for r in sections:
        print(f"{r['section_number']}\t{r['heading']}", file=out)
    return 0


def show_grep(records: dict, pattern: str, slug: str | None, out=sys.stdout) -> int:
    try:
        regex = re.compile(pattern, re.I)
    except re.error as error:
        print(f"error: invalid pattern: {error}", file=sys.stderr)
        return 1
    matches = []
    for r in records.values():
        if slug and r["act_slug"] != slug:
            continue
        match, haystack = regex.search(r["heading"]), r["heading"]
        if not match:
            match, haystack = regex.search(r["body_text"]), r["body_text"]
        if match:
            matches.append((r, snippet(haystack, match)))
    matches.sort(key=lambda item: (item[0]["act_slug"], section_order(item[0]["section_number"])))
    if not matches:
        print("No admitted provisions match.", file=out)
        return 0
    for r, text in matches:
        print(f"{r['key']}\t{r['heading']}\t{text!r}", file=out)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keys", nargs="*", help="Provision keys to print in full.")
    parser.add_argument("--act", help="List admitted sections of this Act, or scope --grep to it.")
    parser.add_argument("--grep", help="Case-insensitive regex over admitted headings and bodies.")
    args = parser.parse_args()

    snapshot = Snapshot()
    if args.grep:
        return show_grep(snapshot.records, args.grep, args.act)
    if args.keys:
        return show_keys(snapshot.records, args.keys)
    if args.act:
        return show_act(snapshot.records, snapshot.acts, args.act)
    parser.error("give provision KEY(s), --act SLUG, or --grep PATTERN")
    return 2  # pragma: no cover - parser.error exits before this


if __name__ == "__main__":
    raise SystemExit(main())
