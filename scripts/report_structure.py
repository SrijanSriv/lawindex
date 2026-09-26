#!/usr/bin/env python3
"""Read-only inspector for the reviewed contextual clause tree (Phase 2).

Reads the structural schema written by scripts/structural_store.py (see
docs/phase-2/STRUCTURAL_MIGRATION.md and docs/phase-2/QUEUE_AND_STRUCTURE.md)
and prints, for each CURRENT root section, its reviewed contextual child
tree: kind, display label, sibling position, offsets into the root text, and
text length. It never prints legal body or footnote text.

This is a reporting tool only. It never runs the importer, never writes to
the database or creates a missing one, never touches source bytes or review
records, and makes no network connection. It opens the database strictly
read-only and performs every read inside one explicit SQLite read
transaction, so a concurrent writer cannot hand it a torn view spanning two
different commits.

See docs/phase-2/STRUCTURE_REPORTING.md for the documented JSON shape and
exactly what this report does and does not verify.
"""
import argparse
import json
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

try:
    from scripts import structural_store as ss
except ModuleNotFoundError:
    import structural_store as ss

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/import/lawindex_offline.sqlite3"

REPORT_SCHEMA_VERSION = 1
NO_STRUCTURE_LABEL = "no reviewed child structure"

# Fixed, hardcoded documentation pointer -- never derived from database
# content, per the bounded task instructions.
LIMITATIONS_DOC = "docs/phase-2/QUEUE_AND_STRUCTURE.md"

LIMITATIONS = [
    "Contextual children are annotations of a reviewed root section, not "
    "independently admitted or independently searchable provisions.",
    "This report checks stored relationships and stored text slices only. "
    "It does not re-verify live source bytes, legal accuracy, reviewer "
    "independence, or corpus reuse permission.",
    "The current search corpus remains the reviewed root sections "
    "themselves; contextual children add no new searchable provisions.",
    "RTI schedule pages are explicitly excluded from structural parsing. "
    "The absence of rows here is not evidence that a schedule was parsed -- "
    "see " + LIMITATIONS_DOC + ".",
]


class ReportError(Exception):
    """A condition that prevents rendering a trustworthy structure report."""


def _fail(message: str) -> "None":
    raise ReportError(message)


def open_readonly(db_path: Path) -> sqlite3.Connection:
    """Open db_path strictly read-only. Never creates a database file.

    Builds the connection URI from Path.resolve().as_uri(), which
    percent-encodes characters such as '#', '?' and spaces that a raw
    f"file:{path}" would pass through unescaped and misinterpret.
    """
    if not db_path.exists():
        _fail(f"database not found: {db_path}")
    if not db_path.is_file():
        _fail(f"database path is not a file: {db_path}")
    uri = db_path.resolve().as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        # Autocommit mode: SELECTs never implicitly open a transaction, so we
        # can wrap the whole report in one explicit BEGIN..ROLLBACK below.
        conn.isolation_level = None
        conn.execute("SELECT 1")
    except sqlite3.Error as exc:
        _fail(f"could not open database read-only: {exc}")
        raise  # unreachable
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def read_transaction(conn: sqlite3.Connection):
    """Run every query inside one explicit read transaction.

    Pins a single consistent database snapshot for the whole report, so a
    concurrent writer (e.g. the importer, mid-commit) cannot cause two
    separate queries here to see different states. Always rolled back, since
    this connection never writes anything.
    """
    conn.execute("BEGIN")
    try:
        yield
    finally:
        conn.execute("ROLLBACK")


def check_schema(conn: sqlite3.Connection) -> int:
    try:
        version = ss.schema_version(conn)
    except ValueError as exc:
        _fail(f"unsupported structural schema: {exc}")
        raise  # unreachable
    except sqlite3.DatabaseError as exc:
        _fail(f"database is corrupt or unreadable: {exc}")
        raise  # unreachable
    if version == 0:
        _fail(
            "database has no structural schema (no 'structural_schema' table); "
            "this looks like a database from before the structural migration "
            "in docs/phase-2/STRUCTURAL_MIGRATION.md. This report cannot run "
            "the migration -- it is read-only."
        )
    return version


def fetch_current_roots(conn: sqlite3.Connection):
    """Current root sections only, joined strictly through current_versions.

    A historical node_versions row that happens to share a document with a
    current root is never treated as one of that root's children: children
    are scoped below by extraction_id, and only the version current_versions
    actually points at is ever used as a root.
    """
    try:
        rows = conn.execute(
            """
            SELECT c.provision_key AS provision_key, c.version_id AS pointer_version_id,
                   v.version_id AS version_id,
                   v.node_id AS node_id, v.extraction_id AS extraction_id,
                   v.parent_version_id AS parent_version_id,
                   v.display_label AS display_label, v.heading AS heading,
                   v.body_text AS body_text,
                   v.pdf_page_from AS pdf_page_from, v.pdf_page_to AS pdf_page_to
            FROM current_versions c LEFT JOIN node_versions v ON v.version_id = c.version_id
            ORDER BY c.provision_key
            """
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        _fail(f"could not read current root sections: {exc}")
        raise  # unreachable
    # A LEFT JOIN, not an INNER JOIN: current_versions.version_id is a
    # dangling reference to a missing node_versions row if v.version_id is
    # NULL here. An INNER JOIN would silently drop that provision_key from
    # the report instead of surfacing the corruption.
    dangling = [r["provision_key"] for r in rows if r["version_id"] is None]
    if dangling:
        _fail(
            "current_versions points at missing node_versions row(s) for: "
            + ", ".join(sorted(dangling))
        )
    return [dict(r) for r in rows]


def fetch_extraction_rows(conn: sqlite3.Connection, extraction_id: str):
    try:
        rows = conn.execute(
            """
            SELECT version_id, parent_version_id, sibling_ordinal, kind,
                   display_label, body_text, source_anchor_json
            FROM node_versions WHERE extraction_id = ?
            """,
            (extraction_id,),
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        _fail(f"could not read extraction {extraction_id!r}: {exc}")
        raise  # unreachable
    return {r["version_id"]: dict(r) for r in rows}


def _child_offsets(root_row: dict, child_row: dict):
    """Validate one child's anchor against the current root and its text.

    Checks the anchor names this exact current root as both its root and
    its mandatory context, that its offsets land inside the root's actual
    text, and that its stored text is the exact code-point slice of the
    root text at those offsets -- never trusting the stored offsets alone.
    """
    try:
        anchor = json.loads(child_row["source_anchor_json"])
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed source anchor for version {child_row['version_id']!r}: {exc}")
    if not isinstance(anchor, dict):
        raise ValueError(f"source anchor for version {child_row['version_id']!r} is not an object")
    if anchor.get("offset_unit") != "unicode_code_points":
        raise ValueError(f"version {child_row['version_id']!r} anchor is not in unicode code points")
    root_id = root_row["version_id"]
    if anchor.get("root_version_id") != root_id or anchor.get("mandatory_context_version_id") != root_id:
        raise ValueError(f"version {child_row['version_id']!r} anchor does not name the current root")
    start, end = anchor.get("start"), anchor.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or isinstance(start, bool) or isinstance(end, bool):
        raise ValueError(f"version {child_row['version_id']!r} has non-integer offsets")
    root_text = root_row["body_text"]
    if not (0 <= start < end <= len(root_text)):
        raise ValueError(f"version {child_row['version_id']!r} offsets are outside the root text")
    if child_row["body_text"] != root_text[start:end]:
        raise ValueError(f"version {child_row['version_id']!r} stored text is not the exact root slice")
    return start, end


def _ancestor_root(version_id, rows_by_id):
    """Walk parent_version_id pointers up from version_id to its ultimate root.

    Returns ('root', root_id) if the chain terminates at a row with a NULL
    parent, ('missing', broken_id) if it references a parent not present in
    rows_by_id, or ('cycle', None) if it loops back on itself. Two different
    node_versions rows can legitimately share one extraction_id -- e.g. a
    heading-only correction reuses the same extraction but mints a new root
    version, leaving the old root version (and, with it, any extraction it
    shares) behind as plain history. Such a row's chain terminates at itself
    (a NULL parent) rather than at the current root, and that is not an
    orphan: it is simply a different, unrelated root that happens to share
    this extraction_id, and this function lets the caller tell the two
    conditions apart instead of conflating them.
    """
    seen = set()
    current = version_id
    while True:
        if current in seen:
            return "cycle", None
        seen.add(current)
        row = rows_by_id.get(current)
        if row is None:
            return "missing", current
        parent = row["parent_version_id"]
        if parent is None:
            return "root", current
        current = parent


def validate_and_build_tree(root_row: dict, rows_by_id: dict):
    """Validate the extraction's shape and return the nested child tree.

    Rejects: a current version that is not itself a root, a missing parent,
    a cycle, a duplicate sibling position under one parent, a child lying
    outside its immediate parent's own range, overlapping siblings, and any
    descendant that is genuinely unreachable (broken chain or cycle) rather
    than simply belonging to a different, unrelated root version that
    happens to share this extraction_id. Offsets/text/anchor identity for
    every descendant are checked with _child_offsets above; containment
    within the immediate parent and sibling ordering are checked here,
    because _child_offsets alone only bounds a child against the root's
    full text, not against its own parent's narrower range.
    """
    root_id = root_row["version_id"]
    if root_id not in rows_by_id:
        raise ValueError(f"current root {root_id!r} is missing from its own extraction")
    if rows_by_id[root_id]["parent_version_id"] is not None:
        raise ValueError(f"current version {root_id!r} is not a root (it has a parent)")

    children_by_parent: dict = {}
    for version_id, row in rows_by_id.items():
        if version_id == root_id:
            continue
        children_by_parent.setdefault(row["parent_version_id"], []).append(row)

    visited = {root_id}

    def walk(parent_id, bound_start, bound_end):
        kids = children_by_parent.get(parent_id, [])
        ordinals = [k["sibling_ordinal"] for k in kids]
        if any(o is None for o in ordinals):
            raise ValueError(f"a child of version {parent_id!r} has no sibling position")
        if len(set(ordinals)) != len(ordinals):
            raise ValueError(f"duplicate sibling position under version {parent_id!r}")
        nested = []
        previous_end = bound_start
        for kid in sorted(kids, key=lambda k: k["sibling_ordinal"]):
            kid_id = kid["version_id"]
            if kid_id in visited:
                raise ValueError(f"cycle detected at version {kid_id!r}")
            visited.add(kid_id)
            start, end = _child_offsets(root_row, kid)
            if not (bound_start <= start < end <= bound_end):
                raise ValueError(
                    f"version {kid_id!r} lies outside its immediate parent's range"
                )
            if start < previous_end:
                raise ValueError(f"version {kid_id!r} overlaps a preceding sibling")
            previous_end = end
            nested.append(
                {
                    "kind": kid["kind"],
                    "display_label": kid["display_label"],
                    "sibling_ordinal": kid["sibling_ordinal"],
                    "root_char_start": start,
                    "root_char_end": end,
                    "text_length": end - start,
                    "children": walk(kid_id, start, end),
                }
            )
        return nested

    tree = walk(root_id, 0, len(root_row["body_text"]))
    for version_id in set(rows_by_id) - visited:
        kind, info = _ancestor_root(version_id, rows_by_id)
        if kind == "root" and info != root_id:
            continue  # a different, unrelated root sharing this extraction_id
        if kind == "missing":
            raise ValueError(f"version {version_id!r} references missing parent {info!r}")
        raise ValueError(f"cycle or orphan descendant at version {version_id!r}")
    return tree


def _count_descendants(tree):
    return len(tree) + sum(_count_descendants(node["children"]) for node in tree)


def build_report(conn: sqlite3.Connection) -> dict:
    schema_version = check_schema(conn)
    roots = []
    for root_row in fetch_current_roots(conn):
        rows_by_id = fetch_extraction_rows(conn, root_row["extraction_id"])
        try:
            tree = validate_and_build_tree(root_row, rows_by_id)
        except ValueError as exc:
            raise ReportError(f"malformed structure for {root_row['provision_key']!r}: {exc}")
        child_count = _count_descendants(tree)
        roots.append(
            {
                "provision_key": root_row["provision_key"],
                "root_version_id": root_row["version_id"],
                "display_label": root_row["display_label"],
                "heading": root_row["heading"],
                "pdf_page_from": root_row["pdf_page_from"],
                "pdf_page_to": root_row["pdf_page_to"],
                "contextual_child_count": child_count,
                "no_reviewed_child_structure": child_count == 0,
                "children": tree,
            }
        )
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "structural_schema_version": schema_version,
        "roots": roots,
        "limitations": LIMITATIONS,
    }


def _render_tree_lines(nodes, indent):
    lines = []
    for node in nodes:
        lines.append(
            " " * indent
            + f"[{node['sibling_ordinal']}] {node['kind']} {node['display_label']} "
            f"offsets={node['root_char_start']}-{node['root_char_end']} "
            f"length={node['text_length']}"
        )
        lines.extend(_render_tree_lines(node["children"], indent + 2))
    return lines


def render_text(report: dict, db_path: Path) -> str:
    lines = []
    lines.append("LawIndex reviewed structure report")
    lines.append(f"database: {db_path}")
    lines.append(f"structural schema version: {report['structural_schema_version']}")
    lines.append(f"current roots: {len(report['roots'])}")
    lines.append("")
    for root in report["roots"]:
        lines.append(f"{root['provision_key']} (version {root['root_version_id']})")
        lines.append(f"  label: {root['display_label']}  heading: {root['heading']}")
        lines.append(f"  PDF pages: {root['pdf_page_from']}-{root['pdf_page_to']}")
        lines.append(f"  contextual children: {root['contextual_child_count']}")
        if root["no_reviewed_child_structure"]:
            lines.append(f"  {NO_STRUCTURE_LABEL}")
        else:
            lines.extend(_render_tree_lines(root["children"], 2))
        lines.append("")
    lines.append("limitations:")
    for note in report["limitations"]:
        lines.append(f"  - {note}")
    return "\n".join(lines) + "\n"


def render_json(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="path to the repository's SQLite database (read-only)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    db_path = Path(args.db)

    try:
        conn = open_readonly(db_path)
        try:
            with read_transaction(conn):
                report = build_report(conn)
        except sqlite3.Error as exc:
            # A safety net around anything check_schema's explicit checks did
            # not anticipate -- surfaced as the same clean diagnostic rather
            # than an unhandled traceback.
            _fail(f"database query failed against this schema: {exc}")
        finally:
            conn.close()
    except ReportError as exc:
        print(f"report_structure: error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        sys.stdout.write(render_json(report))
    else:
        sys.stdout.write(render_text(report, db_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
