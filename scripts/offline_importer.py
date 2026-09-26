#!/usr/bin/env python3
"""Minimal offline importer for LawIndex Phase 0 technical-readiness checks.

Operates ONLY on retained local fixtures under data/discovery/ and hand-authored
review decisions under data/review/. Makes no network requests, sends no
messages, and does not fetch anything from India Code. Implements the accepted
conflict policy (docs/phase-0/CONFLICT_POLICY.md) for a bounded slice: RTI Act,
2005 sections 6 and 8, plus (as of the second-pass review) Environment
(Protection) Act, 1986 sections 3 and 5A. Every other section of these Acts,
and every other candidate Act, remains unreviewed -- see the review records
under data/review/ for the exact set actually admitted.

This importer is a technical-readiness exercise. It does not grant, imply, or
depend on public-indexing permission from India Code. See
docs/phase-0/ACCESS_AND_REUSE.md.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import re
import sqlite3
import subprocess
from pathlib import Path

try:
    from scripts import structural_store, import_queue
except ModuleNotFoundError:  # Direct execution: python3 scripts/offline_importer.py
    import structural_store
    import import_queue

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/discovery"
REVIEW = ROOT / "data/review"

EXTRACTION_METHOD_VERSION = "offline-importer-v2"
REVIEWED_HTML_VERSION = "phase3-reviewed-html-v1"
SAMPLED_AGREEMENT_VERSION = "phase3-sampled-agreement-v1"
PHASE3_METHODS = {REVIEWED_HTML_VERSION, SAMPLED_AGREEMENT_VERSION}
SUPPORTED_EXTRACTION_METHODS = {EXTRACTION_METHOD_VERSION} | PHASE3_METHODS

# The retained RTI PDF renders a diagonal "IndiaCode" watermark. pdftotext
# -layout emits it as five standalone, heavily right-indented lines per page
# that read (top to bottom) "In", "di", "aC", "od", "e" -- reversed, they
# spell "IndiaCode". This is the only text normalization this importer
# performs; it is scoped to these five exact tokens on their own line with
# substantial leading whitespace, so it cannot silently eat legal text such
# as a lone clause marker.
WATERMARK_LINE_RE = re.compile(r"^[ \t]{10,}(In|di|aC|od|e)[ \t]*$", re.MULTILINE)

# pdftotext -layout renders each retained PDF's printed page number as a lone,
# heavily right-indented digit line at the very end of that page's text --
# confirmed against data/discovery/derived/rti-2005-page-10.png and
# data/discovery/derived/environment-1986-page-0{4,5}.png. A provision whose
# admitted range spans a page boundary (rti-2005:8 across pages 10-11,
# environment-1986:3 across pages 4-5) previously absorbed that footer digit
# into the middle of its body text. The check below only strips a page's
# trailing digit-only line, and only when that digit equals the page's own
# 1-based position in the extracted PDF -- an exact, verifiable identity a
# legitimate in-body number (such as an amendment-marker digit, which is
# never the last line of a page) will not coincidentally share.
PAGE_FOOTER_RE = re.compile(r"[ \t]*(\d+)[ \t]*\n?\Z")

# Each entry: (act_slug, section_number) -> (start_re, end_re, footnote_re_or_None).
# Extraction is deliberately per-(act, section): section numbers are source
# display labels, not globally unique keys, so a bare section-number lookup
# would risk matching the wrong Act's section if this table ever grows to
# cover acts that share a label (e.g. both having a "6").
_PDF_SECTION_PATTERNS = {
    ("rti-2005", "6"): (
        re.compile(r"6\.\s*Request for obtaining information\."),
        re.compile(r"7\.\s*Disposal of request\."),
        None,
    ),
    ("rti-2005", "8"): (
        re.compile(r"8\.\s*Exemption from disclosure of information\."),
        re.compile(r"9\.\s*Grounds for rejection to access in certain cases\."),
        re.compile(r"1\.\s*Subs\.\s*by Act 22 of 2023, s\.\s*44 for clause \(j\) \(w\.e\.f\.\s*13-11-2025\)\."),
    ),
    ("environment-1986", "3"): (
        re.compile(r"3\.\s*Power of Central Government to take measures to protect and improve environment\."),
        re.compile(r"4\.\s*Appointment of officers and their powers and functions\."),
        None,
    ),
    ("environment-1986", "5A"): (
        # The whole section is wrapped in an insertion marker, e.g. "1\n[5A. ...]".
        # Start matching at the marker digit so the admitted text keeps the
        # bracket and superscript that signal it was inserted by amendment.
        re.compile(r"1\s*\[5A\.\s*Appeal to National Green Tribunal\."),
        re.compile(r"6\.\s*Rules to regulate environmental pollution\."),
        re.compile(r"1\.\s*Ins\.\s*by Act 19 of 2010, s\.\s*36 and Schedule III \(w\.e\.f\.\s*18-10-2010\)\."),
    ),
}

ALLOWED_HTML_TAG_RE = re.compile(r"</?(br|hr|span)\b[^>]*/?>", re.IGNORECASE)
ANY_TAG_RE = re.compile(r"<[^>]+>")


class AdmissionError(Exception):
    pass


# Explicit sentinel for "this review record attests no footnote is expected",
# distinct from a missing/absent expected_output.footnote_text_sha256 field
# (which means no baseline was ever recorded at all, and must not qualify a
# provision for admission by default -- see build_provision_record).
NO_FOOTNOTE_EXPECTED = "no-footnote-expected"

ADMISSION_STATUS_MISSING_EXPECTED_DIGEST = "invalidated_missing_expected_digest"
ADMISSION_STATUS_BODY_TEXT_CHANGED = "invalidated_body_text_changed"
ADMISSION_STATUS_FOOTNOTE_TEXT_CHANGED = "invalidated_footnote_text_changed"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_capture_bytes(capture_name: str) -> bytes:
    meta = json.loads((DATA / f"{capture_name}.json").read_text())
    return (ROOT / meta["body_path"]).read_bytes()


def strip_watermark(pdf_text: str) -> str:
    return WATERMARK_LINE_RE.sub("", pdf_text)


_PDFTOTEXT_MEMO: dict[str, tuple[str, ...]] = {}
_PDFTOTEXT_MEMO_LIMIT = 64


def pdftotext_layout(pdf_bytes: bytes) -> list[str]:
    """Run pdftotext against the given bytes; return pages (0-indexed).

    "Fresh" means derived text files on disk are never trusted: the text is
    always produced from the exact bytes passed in. Within one process the
    result is memoized by the SHA-256 of those bytes -- a pure function of
    its input -- because every provision of an Act anchors to the same PDF,
    and re-extracting a 120-page PDF once per provision made a full import
    of 1,500 provisions take tens of minutes. A caller gets its own list.
    """
    key = sha256_bytes(pdf_bytes)
    cached = _PDFTOTEXT_MEMO.get(key)
    if cached is not None:
        return list(cached)
    pages = _pdftotext_layout_uncached(pdf_bytes)
    if len(_PDFTOTEXT_MEMO) >= _PDFTOTEXT_MEMO_LIMIT:
        _PDFTOTEXT_MEMO.clear()
    _PDFTOTEXT_MEMO[key] = tuple(pages)
    return pages


_CLEAN_PAGES_MEMO: dict[str, tuple[str, ...]] = {}


def clean_pdf_pages(pdf_bytes: bytes) -> tuple[str, ...]:
    """pdftotext pages with page-number footers and the watermark removed.

    The same pipeline every Phase 3 path applies, memoized by the SHA-256 of
    the PDF bytes for the life of the process. Returned as a tuple so no
    caller can alter what another caller will receive.
    """
    key = sha256_bytes(pdf_bytes)
    cached = _CLEAN_PAGES_MEMO.get(key)
    if cached is None:
        if len(_CLEAN_PAGES_MEMO) >= _PDFTOTEXT_MEMO_LIMIT:
            _CLEAN_PAGES_MEMO.clear()
        cached = tuple(strip_watermark(p) for p in strip_page_footers(pdftotext_layout(pdf_bytes)))
        _CLEAN_PAGES_MEMO[key] = cached
    return cached


def _pdftotext_layout_uncached(pdf_bytes: bytes) -> list[str]:
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        result = subprocess.run(
            ["pdftotext", "-layout", tmp.name, "-"],
            check=True, capture_output=True, text=True, timeout=60,
        )
    pages = result.stdout.split("\f")
    if pages and pages[-1].strip() == "":
        pages.pop()
    return pages


def strip_page_footers(pages: list[str]) -> list[str]:
    """Drop each page's trailing printed-page-number footer line, in place.

    Only removes a page's last line when it is digits-only AND equal to that
    page's own 1-based position in `pages` -- see PAGE_FOOTER_RE above for why
    that identity check is what makes this safe against eating real legal
    text (a coincidental in-body digit is not, in general, also the running
    page count of the document it appears in).
    """
    cleaned = []
    for index, page in enumerate(pages, start=1):
        match = PAGE_FOOTER_RE.search(page)
        if match and match.group(1) == str(index) and "\n" in page[:match.start()]:
            page = page[:match.start()]
        cleaned.append(page)
    return cleaned


def html_section_to_text(html: str) -> str:
    tags = ANY_TAG_RE.findall(html)
    for tag in tags:
        if not ALLOWED_HTML_TAG_RE.fullmatch(tag):
            raise AdmissionError(f"unexpected HTML tag in section body, refusing silent extraction: {tag!r}")
    text = ALLOWED_HTML_TAG_RE.sub("\n", html)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n+", "\n", text)
    return text.strip()


def extract_pdf_range(pages: list[str], page_from_1idx: int, page_to_1idx: int,
                       start_re: re.Pattern, end_re: re.Pattern,
                       footnote_re: re.Pattern | None = None):
    combined = "\f".join(pages[page_from_1idx - 1: page_to_1idx])
    combined = strip_watermark(combined)
    start_m = start_re.search(combined)
    if not start_m:
        raise AdmissionError("start pattern not found in the declared PDF page range")
    end_m = end_re.search(combined, start_m.end())
    body = combined[start_m.start(): end_m.start() if end_m else None]
    body = body.replace("\f", "\n").strip()
    footnote = None
    if footnote_re:
        fm = footnote_re.search(combined)
        footnote = fm.group(0).strip() if fm else None
    return body, footnote


def load_review_records():
    records = {}
    for path in sorted(REVIEW.glob("*.review.json")):
        record = json.loads(path.read_text())
        if record["provision_key"] in records:
            raise AdmissionError("duplicate provision review: " + record["provision_key"])
        records[record["provision_key"]] = record
    return records


def load_conflict_records():
    records = {}
    for path in sorted((REVIEW / "conflicts").glob("*.json")):
        record = json.loads(path.read_text())
        records[record["issue_id"]] = record
    return records


def load_manifest():
    return json.loads((DATA / "corpus-manifest.json").read_text())["records"]


def build_provision_record(review, capture_bytes_by_name: dict[str, bytes]) -> dict:
    """Pure function: verify hashes and extract text for one reviewed provision.

    capture_bytes_by_name lets tests inject substitute bytes (to simulate a
    changed source) without touching any retained fixture on disk.
    """
    provision_key = review["provision_key"]
    kind = review["selected_representation"]
    src = review["source_representation"]
    capture = src["capture"]
    declared_sha = src["sha256"]
    actual_bytes = capture_bytes_by_name[capture]
    actual_sha = sha256_bytes(actual_bytes)

    out = {
        "provision_key": provision_key,
        "act_slug": review["act_slug"],
        "section_number": review["section_number"],
        "heading": review["heading"],
        "selected_representation": kind,
        "source_capture": capture,
        "source_sha256_declared": declared_sha,
        "source_sha256_actual": actual_sha,
        "extraction_method_version": review["extraction_method_version"],
        "known_conflicts": review.get("known_conflicts", []),
        "classification": review.get("classification"),
        "disposition": review.get("disposition"),
        "acquisition_status": "complete",
        "body_text": None,
        "body_text_sha256": None,
        "footnote_text": None,
        "footnote_text_sha256": None,
        "pdf_capture": None,
        "pdf_page_from": None,
        "pdf_page_to": None,
        "admission_status": "invalidated_source_changed",
    }

    if declared_sha != actual_sha:
        # Source changed since this review was recorded. Do not extract or
        # admit; the prior approval is invalidated until re-reviewed.
        return out

    if review["extraction_method_version"] not in SUPPORTED_EXTRACTION_METHODS:
        # The code that would extract this provision has moved on since the
        # review was recorded against a specific extraction method version.
        # Refuse to silently admit text produced by a method the reviewer
        # never actually looked at.
        out["admission_status"] = "invalidated_extraction_method_changed"
        return out

    if review["extraction_method_version"] in PHASE3_METHODS:
        act = next((a for a in load_manifest() if a['slug'] == review['act_slug']), None)
        if act is None or act.get('scope_status') != 'phase1_candidate':
            out['admission_status'] = 'excluded_quarantine_scope'
            return out
        if review["extraction_method_version"] == SAMPLED_AGREEMENT_VERSION:
            try:
                from scripts.sampled_agreement import extract
            except ModuleNotFoundError:
                from sampled_agreement import extract
        else:
            try:
                from scripts.reviewed_html import extract
            except ModuleNotFoundError:
                from reviewed_html import extract
        body, footnote = extract(review, capture_bytes_by_name, load_manifest())
        anchor = review["pdf_anchor"]
        out["pdf_capture"] = anchor["capture"]
        out["pdf_page_from"] = anchor["pdf_page_from"]
        out["pdf_page_to"] = anchor["pdf_page_to"]
    elif kind == "pdf":
        pages = strip_page_footers(pdftotext_layout(actual_bytes))
        page_from = src["pdf_page_from"]
        page_to = src["pdf_page_to"]
        start_re, end_re, footnote_re = _pdf_patterns(review["act_slug"], review["section_number"])
        body, footnote = extract_pdf_range(pages, page_from, page_to, start_re, end_re, footnote_re)
        out["pdf_capture"] = capture
        out["pdf_page_from"] = page_from
        out["pdf_page_to"] = page_to
    elif kind == "structured_html":
        act_id_result = json.loads(capture_bytes_by_name[capture])
        sections = [x["_embedded"]["indexableObject"]
                    for x in act_id_result["_embedded"]["searchResult"]["_embedded"]["objects"]]
        candidates = [s for s in sections
                      if s["metadata"]["dc.identifier.section_number"][0]["value"] == review["section_number"]]
        if "section_item_uuid" in src:
            candidates = [s for s in candidates if s["uuid"] == src["section_item_uuid"]]
        if len(candidates) != 1:
            raise AdmissionError(
                f"expected exactly one structured section record matching "
                f"{review['act_slug']}:{review['section_number']} in capture {capture!r}, found {len(candidates)}"
            )
        target = candidates[0]
        html = target["metadata"][src["field"]][0]["value"]
        body = html_section_to_text(html)
        footnote = None
        anchor = review.get("pdf_anchor")
        if anchor:
            out["pdf_capture"] = anchor["capture"]
            out["pdf_page_from"] = anchor["pdf_page_from"]
            out["pdf_page_to"] = anchor["pdf_page_to"]
            anchor_bytes = capture_bytes_by_name.get(anchor["capture"])
            if anchor_bytes is not None and sha256_bytes(anchor_bytes) != anchor["sha256"]:
                out["admission_status"] = "invalidated_source_changed"
                return out
    else:
        raise AdmissionError(f"unknown representation kind {kind!r}")

    expects_footnote = review.get("review", {}).get("footnotes_present", False)
    if expects_footnote and not footnote:
        # The review record attests that this provision has a footnote the
        # reviewer actually checked. If extraction no longer finds it, the
        # extraction has silently drifted from what was reviewed -- refuse to
        # admit rather than serve a provision missing text the reviewer saw.
        out["admission_status"] = "invalidated_expected_footnote_missing"
        return out
    if footnote and not expects_footnote:
        out["admission_status"] = "invalidated_unexpected_footnote_found"
        return out

    # Record the actual extracted output's digests unconditionally, even if
    # the checks below end up refusing admission -- this is the evidence a
    # human (or a later session) needs to see WHAT changed, without ever
    # populating body_text/footnote_text with content nobody has reviewed.
    body_sha = sha256_bytes(body.encode("utf-8"))
    footnote_sha = sha256_bytes(footnote.encode("utf-8")) if footnote else None
    out["body_text_sha256"] = body_sha
    out["footnote_text_sha256"] = footnote_sha

    # Bind admission to the reviewed extracted text itself, not merely to the
    # source bytes and a manually maintained extraction-version label. A
    # matching source hash and extraction-version only proves the INPUT and
    # the declared METHOD haven't changed; it does not prove the reviewer
    # actually looked at what this particular run of that method produces --
    # a behavior change inside the same declared version, or an unversioned
    # bug fix/regression in the extraction patterns above, would otherwise
    # sail through unnoticed (see docs/phase-0/INSPECTION_FOLLOWUP.md Finding 1).
    expected = review.get("expected_output")
    if not expected or not expected.get("body_text_sha256") or "footnote_text_sha256" not in expected:
        # No attested baseline for this provision's actual output. A missing
        # baseline must never silently default to "admit" -- that would be
        # exactly the gap this check exists to close.
        out["admission_status"] = ADMISSION_STATUS_MISSING_EXPECTED_DIGEST
        return out

    if body_sha != expected["body_text_sha256"]:
        out["admission_status"] = ADMISSION_STATUS_BODY_TEXT_CHANGED
        return out

    expected_footnote_sha = expected["footnote_text_sha256"]
    if footnote_sha is None:
        if expected_footnote_sha != NO_FOOTNOTE_EXPECTED:
            out["admission_status"] = ADMISSION_STATUS_MISSING_EXPECTED_DIGEST
            return out
    elif expected_footnote_sha == NO_FOOTNOTE_EXPECTED or footnote_sha != expected_footnote_sha:
        out["admission_status"] = ADMISSION_STATUS_FOOTNOTE_TEXT_CHANGED
        return out

    out["body_text"] = body
    if footnote:
        out["footnote_text"] = footnote

    # Never admit anything from an act that is not a phase1_candidate, and
    # never admit an excluded/quarantined representation, regardless of what
    # the hand-authored review record claims.
    manifest_by_slug = {m["slug"]: m for m in load_manifest()}
    act = manifest_by_slug.get(review["act_slug"])
    if act is None or act.get("scope_status") != "phase1_candidate":
        out["admission_status"] = "excluded_quarantine_scope"
        return out

    out["admission_status"] = review.get("admission_status", "review_pending")
    return out


def _pdf_patterns(act_slug: str, section_number: str):
    key = (act_slug, section_number)
    if key not in _PDF_SECTION_PATTERNS:
        raise AdmissionError(f"no extraction pattern registered for {key!r}")
    return _PDF_SECTION_PATTERNS[key]


SCHEMA = """
CREATE TABLE IF NOT EXISTS import_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    provision_key TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    finished_at TEXT,
    status TEXT NOT NULL,
    source_hashes_json TEXT NOT NULL DEFAULT '{}',
    review_sha256 TEXT NOT NULL,
    extraction_method_version TEXT NOT NULL,
    admission_status TEXT,
    error_type TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    act_slug TEXT PRIMARY KEY,
    uuid TEXT,
    title TEXT,
    act_number TEXT,
    year TEXT,
    scope_status TEXT,
    ready_for_public_index INTEGER,
    enact_date_raw TEXT,
    enact_date_listing_raw TEXT,
    canonical_enactment_date TEXT,
    removed_from_manifest INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS provisions (
    provision_key TEXT PRIMARY KEY,
    act_slug TEXT,
    section_number TEXT,
    heading TEXT,
    selected_representation TEXT,
    source_capture TEXT,
    source_sha256_declared TEXT,
    source_sha256_actual TEXT,
    pdf_capture TEXT,
    pdf_page_from INTEGER,
    pdf_page_to INTEGER,
    body_text TEXT,
    body_text_sha256 TEXT,
    footnote_text TEXT,
    footnote_text_sha256 TEXT,
    extraction_method_version TEXT,
    classification TEXT,
    disposition TEXT,
    admission_status TEXT,
    acquisition_status TEXT,
    known_conflicts_json TEXT
);

CREATE TABLE IF NOT EXISTS review_decisions (
    provision_key TEXT PRIMARY KEY,
    reviewer_id TEXT,
    reviewer_type TEXT,
    is_independent_legal_expert_review INTEGER,
    review_scope TEXT,
    evidence_json TEXT,
    review_time_note TEXT
);

CREATE TABLE IF NOT EXISTS conflicts (
    issue_id TEXT PRIMARY KEY,
    scope_json TEXT,
    classification TEXT,
    selected_representation TEXT,
    disposition TEXT,
    admission_json TEXT,
    legal_effect_determined INTEGER
);

CREATE TABLE IF NOT EXISTS excerpts (
    excerpt_key TEXT PRIMARY KEY,
    provision_key TEXT,
    char_start INTEGER,
    char_end INTEGER,
    excerpt_text TEXT
);
"""


def _migrate_schema(conn):
    """Add columns introduced after a database file may already exist on disk.

    CREATE TABLE IF NOT EXISTS (in SCHEMA) does not alter a table that already
    exists with an older column set, so a database built before this column
    was added would otherwise silently lack it.
    """
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
    if "removed_from_manifest" not in existing_cols:
        conn.execute("ALTER TABLE documents ADD COLUMN removed_from_manifest INTEGER DEFAULT 0")


ADMISSION_STATUS_REVIEW_RECORD_REMOVED = "invalidated_review_record_removed"


def invalidate_stale_records(conn, current_act_slugs: set[str], current_provision_keys: set[str]):
    """Invalidate rows left over from a prior import whose backing source
    record (a review file or a manifest entry) has since been removed.

    Byte-level and version-level changes to a record that still exists are
    already caught inside build_provision_record (source hash mismatch,
    extraction-method-version mismatch, footnote-consistency mismatch). But
    if the review record or manifest entry disappears entirely -- the most
    direct way an approval would actually be retracted, or an Act dropped
    from scope -- import_all's upsert loops never touch that row again,
    because they only iterate over records that currently exist. Without
    this pass, a previously admitted provision (or a previously known
    document) would keep reporting its old, no-longer-backed status forever
    on an existing (non-fresh) database. See docs/phase-0/INDEPENDENT_REVIEW.md
    Finding 1.
    """
    existing_act_slugs = {row[0] for row in conn.execute("SELECT act_slug FROM documents")}
    for slug in existing_act_slugs - current_act_slugs:
        conn.execute(
            "UPDATE documents SET removed_from_manifest = 1, ready_for_public_index = 0 "
            "WHERE act_slug = ?",
            (slug,),
        )

    existing_provision_keys = {row[0] for row in conn.execute("SELECT provision_key FROM provisions")}
    for key in existing_provision_keys - current_provision_keys:
        conn.execute(
            "UPDATE provisions SET admission_status = ?, body_text = NULL, body_text_sha256 = NULL, "
            "footnote_text = NULL, footnote_text_sha256 = NULL WHERE provision_key = ?",
            (ADMISSION_STATUS_REVIEW_RECORD_REMOVED, key),
        )
        conn.execute("DELETE FROM excerpts WHERE provision_key = ?", (key,))


def upsert(conn, table, pk_col, row: dict):
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != pk_col)
    sql = (f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) "
           f"ON CONFLICT({pk_col}) DO UPDATE SET {updates}")
    conn.execute(sql, [row[c] for c in cols])


def invalidate_import_text(conn, key, status):
    """Revoke searchable output without erasing historical attempt evidence."""
    conn.execute("UPDATE provisions SET admission_status = ?, body_text = NULL, "
                 "body_text_sha256 = NULL, footnote_text = NULL, footnote_text_sha256 = NULL "
                 "WHERE provision_key = ?", (status, key))
    conn.execute("DELETE FROM excerpts WHERE provision_key = ?", (key,))
    conn.execute("DELETE FROM current_versions WHERE provision_key = ?", (key,))


@contextmanager
def import_lock(db_path):
    """One cooperating importer per database; never wait indefinitely."""
    if not db_path:  # Private in-memory connection, used by fixture checks.
        yield
        return
    with open(str(Path(db_path).resolve()) + ".import.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AdmissionError("another importer owns this database") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def import_all(conn, capture_bytes_override: dict[str, bytes] | None = None, *, resume=False):
    db_path = next(row[2] for row in conn.execute("PRAGMA database_list") if row[1] == "main")
    with import_lock(db_path):
        return _import_all_locked(conn, capture_bytes_override, resume=resume)


def _import_all_locked(conn, capture_bytes_override=None, *, resume=False):
    """Run (or re-run) the offline import. Idempotent: safe to call repeatedly.

    capture_bytes_override lets a caller substitute bytes for named captures,
    to exercise changed-source invalidation without touching real fixtures.
    """
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _migrate_schema(conn)
    conn.commit()
    structural_store.migrate(conn)
    conn.executescript(import_queue.SCHEMA)
    if [r[0] for r in conn.execute("SELECT version FROM import_queue_schema")] != [1]:
        raise ValueError("unsupported import queue schema")
    manifest = load_manifest()
    reviews = load_review_records()
    conflicts = load_conflict_records()
    reviewer_cache: dict[str, dict] = {}
    # Decide reuse before inventory writes can mask a changed stored output.
    try:
        fingerprint = import_queue.input_fingerprint(ROOT, manifest, reviews, conflicts, capture_bytes_override)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        fingerprint = None  # Full per-item processing retains failure isolation.
    skipped = {key for key in reviews if resume and import_queue.reusable(conn, ROOT, key, fingerprint)}

    invalidate_stale_records(
        conn,
        current_act_slugs={m["slug"] for m in manifest},
        current_provision_keys=set(reviews.keys()),
    )

    def reviewer_for(review: dict) -> dict:
        # Each review record names its own reviewer file. Loading it per
        # record (instead of one hard-coded reviewer.json for everything)
        # is what makes a second-pass reviewer's identity actually land in
        # review_decisions for the provisions it reviewed, rather than every
        # provision being silently attributed to whichever reviewer file
        # happened to be loaded first.
        ref = review["review"]["reviewer_ref"]
        if ref not in reviewer_cache:
            reviewer_cache[ref] = json.loads((ROOT / ref).read_text())
        return reviewer_cache[ref]

    # Enactment-date conflicts are resolved (or left unresolved) entirely
    # through conflict records, never by an act-slug special case here: a
    # conflict record's own "resolution" block is the single place that can
    # turn a disputed date into a canonical one, and it must show its work
    # (see KERALA-001.json). No known conflict on a field means the single
    # retained observation is used as-is; an unresolved known conflict means
    # the canonical value stays null, never guessed or averaged.
    date_conflicts_by_act = {}
    for conflict in conflicts.values():
        scope = conflict.get("scope", {})
        if scope.get("field") == "enactment date" and scope.get("act_slug"):
            date_conflicts_by_act[scope["act_slug"]] = conflict

    for m in manifest:
        conflict = date_conflicts_by_act.get(m["slug"])
        if conflict is None:
            canonical_date = m.get("enact_date_raw")
        else:
            resolution = conflict.get("resolution") or {}
            canonical_date = resolution.get("value") if resolution.get("resolved") else None
        upsert(conn, "documents", "act_slug", {
            "act_slug": m["slug"],
            "uuid": m["uuid"],
            "title": m["title"],
            "act_number": m.get("act_number"),
            "year": m.get("year"),
            "scope_status": m["scope_status"],
            "ready_for_public_index": 0,
            "enact_date_raw": m.get("enact_date_raw"),
            "enact_date_listing_raw": m.get("enact_date_listing_raw"),
            "canonical_enactment_date": canonical_date,
            # A document currently present in the manifest is, by definition,
            # not removed -- explicitly reset the flag rather than leaving a
            # prior invalidate_stale_records() pass's value in place. Without
            # this, an Act that was temporarily dropped and then restored
            # would keep reporting removed_from_manifest=1 forever (see
            # docs/phase-0/INSPECTION_FOLLOWUP.md Finding 2).
            "removed_from_manifest": 0,
        })

    for issue_id, conflict in conflicts.items():
        upsert(conn, "conflicts", "issue_id", {
            "issue_id": issue_id,
            "scope_json": json.dumps(conflict["scope"]),
            "classification": conflict["classification"],
            "selected_representation": conflict.get("selected_representation"),
            "disposition": conflict["disposition"],
            "admission_json": json.dumps(conflict["admission"]),
            "legal_effect_determined": int(conflict["legal_effect_determined"]),
        })


    # Commit inventory and revoke all old text before doing fallible work. A
    # crash cannot leave unprocessed rows claiming this run verified them.
    conn.execute("UPDATE import_attempts SET status = 'interrupted', "
                 "finished_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE status = 'running'")
    for (key,) in conn.execute("SELECT provision_key FROM import_jobs").fetchall():
        if key not in reviews:
            conn.execute("UPDATE import_jobs SET status='removed', output_fingerprint=NULL WHERE provision_key=?", (key,))
    for (key,) in conn.execute("SELECT provision_key FROM current_versions").fetchall():
        if key not in reviews:
            conn.execute("DELETE FROM current_versions WHERE provision_key=?", (key,))
    for key in reviews:
        if key not in skipped:
            invalidate_import_text(conn, key, "pending_revalidation")
            conn.execute("INSERT INTO import_jobs(provision_key,input_fingerprint,status) VALUES (?,?,'pending') "
                         "ON CONFLICT(provision_key) DO UPDATE SET input_fingerprint=excluded.input_fingerprint, "
                         "status='pending',output_fingerprint=NULL", (key,fingerprint))
    conn.commit()

    admitted_count = len(skipped)
    failed_count = 0
    for provision_key, review in reviews.items():
        if provision_key in skipped:
            continue
        review_digest = sha256_bytes(json.dumps(review, sort_keys=True).encode())
        cursor = conn.execute(
            "INSERT INTO import_attempts (provision_key, status, review_sha256, extraction_method_version) "
            "VALUES (?, 'running', ?, ?)",
            (provision_key, review_digest, review["extraction_method_version"]))
        attempt_id = cursor.lastrowid
        conn.execute("UPDATE import_jobs SET status='running',last_attempt_id=? WHERE provision_key=?", (attempt_id,provision_key))
        conn.commit()
        try:
            names = {review["source_representation"]["capture"]}
            if review.get("pdf_anchor"):
                names.add(review["pdf_anchor"]["capture"])
            real_bytes = {}
            for name in sorted(names):
                real_bytes[name] = (capture_bytes_override[name]
                    if capture_bytes_override and name in capture_bytes_override
                    else load_capture_bytes(name))
                # Preserve hashes already observed even if a later input fails.
                conn.execute("UPDATE import_attempts SET source_hashes_json = ? WHERE attempt_id = ?",
                             (json.dumps({n: sha256_bytes(b) for n, b in real_bytes.items()}, sort_keys=True), attempt_id))
                conn.commit()
            record = build_provision_record(review, real_bytes)
            upsert(conn, "provisions", "provision_key", {
                "provision_key": record["provision_key"],
                "act_slug": record["act_slug"],
                "section_number": record["section_number"],
                "heading": record["heading"],
                "selected_representation": record["selected_representation"],
                "source_capture": record["source_capture"],
                "source_sha256_declared": record["source_sha256_declared"],
                "source_sha256_actual": record["source_sha256_actual"],
                "pdf_capture": record["pdf_capture"],
                "pdf_page_from": record["pdf_page_from"],
                "pdf_page_to": record["pdf_page_to"],
                "body_text": record["body_text"],
                "body_text_sha256": record["body_text_sha256"],
                "footnote_text": record["footnote_text"],
                "footnote_text_sha256": record["footnote_text_sha256"],
                "extraction_method_version": record["extraction_method_version"],
                "classification": record["classification"],
                "disposition": record["disposition"],
                "admission_status": record["admission_status"],
                "acquisition_status": record["acquisition_status"],
                "known_conflicts_json": json.dumps(record["known_conflicts"]),
            })

            reviewer = reviewer_for(review)
            upsert(conn, "review_decisions", "provision_key", {
                "provision_key": provision_key,
                "reviewer_id": reviewer["reviewer_id"],
                "reviewer_type": reviewer["reviewer_type"],
                "is_independent_legal_expert_review": int(reviewer["is_independent_legal_expert_review"]),
                "review_scope": review["review"]["scope"],
                "evidence_json": json.dumps(review["review"]["evidence"]),
                "review_time_note": reviewer["actual_review_time_note"],
            })

            if record["admission_status"] == "admitted":
                patterns = _PDF_SECTION_PATTERNS.get((review["act_slug"], review["section_number"]), ())
                config = {
                    "provision_key": provision_key,
                    "pdf_patterns": [(p.pattern, p.flags) if p else None for p in patterns],
                    "watermark_pattern": WATERMARK_LINE_RE.pattern,
                    "footer_pattern": PAGE_FOOTER_RE.pattern,
                    "html_allowed_tags": ALLOWED_HTML_TAG_RE.pattern,
                    "method_version": review["extraction_method_version"],
                }
                if review["extraction_method_version"] in PHASE3_METHODS:
                    config["html_allowed_tags"] = "br hr span i b sup sub p div strong em u center"
                    config["pdf_agreement"] = "whole body; whitespace only; unique occurrence; exact reviewed pages"
                if review["extraction_method_version"] == SAMPLED_AGREEMENT_VERSION:
                    config["pdf_agreement"] = ("whole body; unique occurrence; exact reviewed pages; enumerated "
                                               "normalizations " + ", ".join(review["agreement"]["normalizations"]))
                    config["review_class"] = review["review"]["review_class"]
                    config["sample_plan_digest"] = review["review"]["sample_plan"]["plan_digest"]
                profile_path = REVIEW / "structure" / (provision_key.replace(":", "-section-") + ".json")
                if profile_path.exists():
                    config["structure_profile"] = json.loads(profile_path.read_text())
                structural_store.promote(conn, ROOT, record, review, reviewer, real_bytes, config)

            conn.execute("DELETE FROM excerpts WHERE provision_key = ?", (provision_key,))
            if record["admission_status"] == "admitted" and record["body_text"]:
                text = record["body_text"]
                end = min(160, len(text))
                excerpt_text = text[:end]
                conn.execute(
                    "INSERT INTO excerpts (excerpt_key, provision_key, char_start, char_end, excerpt_text) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (f"{provision_key}:0:{end}", provision_key, 0, end, excerpt_text),
                )
                admitted_count += 1

            conn.execute("UPDATE import_attempts SET status = ?, admission_status = ?, "
                         "finished_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE attempt_id = ?",
                         ("succeeded" if record["admission_status"] == "admitted" else "quarantined",
                          record["admission_status"], attempt_id))
            import_queue.finish(conn, ROOT, provision_key,
                "succeeded" if record["admission_status"] == "admitted" else "quarantined", attempt_id, fingerprint)
            conn.commit()
        except (OSError, ValueError, KeyError, AdmissionError, subprocess.SubprocessError) as exc:
            conn.rollback()
            invalidate_import_text(conn, provision_key, "invalidated_import_failed")
            conn.execute("UPDATE import_attempts SET status = 'failed', error_type = ?, "
                         "admission_status = 'invalidated_import_failed', "
                         "finished_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE attempt_id = ?",
                         (type(exc).__name__, attempt_id))
            import_queue.finish(conn, ROOT, provision_key, "failed", attempt_id, fingerprint)
            conn.commit()
            failed_count += 1

    conn.commit()
    return {"documents": len(manifest), "provisions_admitted": admitted_count, "conflicts": len(conflicts), "provisions_failed": failed_count, "provisions_skipped": len(skipped)}


def build_readiness_manifest(conn) -> dict:
    cur = conn.execute("SELECT provision_key, act_slug, admission_status, disposition, known_conflicts_json FROM provisions")
    provisions = [dict(zip(["provision_key", "act_slug", "admission_status", "disposition", "known_conflicts"], row))
                  for row in cur.fetchall()]
    cur = conn.execute("SELECT act_slug, scope_status, ready_for_public_index, removed_from_manifest FROM documents")
    documents = [dict(zip(["act_slug", "scope_status", "ready_for_public_index", "removed_from_manifest"], row))
                 for row in cur.fetchall()]
    active_documents = [d for d in documents if not d["removed_from_manifest"]]
    removed_documents = [d["act_slug"] for d in documents if d["removed_from_manifest"]]
    reviewed_act_slugs = {p["act_slug"] for p in provisions}
    admitted_provisions = [p for p in provisions if p["admission_status"] == "admitted"]
    scope_acts = ", ".join(sorted({p["act_slug"] for p in admitted_provisions})) or "none"
    manifest = {
        "schema_version": 1,
        "generated_by": "scripts/offline_importer.py",
        "scope": (
            f"Bounded slice: only the specific provisions listed under "
            f"reviewed_and_admitted_provisions below, across these Acts: {scope_acts}. "
            f"Not a claim about any other section of those Acts or about any other Act."
        ),
        "reviewed_and_admitted_provisions": admitted_provisions,
        "reviewed_but_not_admitted_provisions": [p for p in provisions if p["admission_status"] != "admitted"],
        # Only documents currently present in the manifest count as active
        # candidate scope. A document dropped from the manifest is not a
        # current candidate and must not be listed alongside ones that are --
        # it is surfaced explicitly below instead, never silently omitted.
        "documents_known_but_unreviewed": [
            d["act_slug"] for d in active_documents if d["act_slug"] not in reviewed_act_slugs
        ],
        "documents_removed_from_manifest": removed_documents,
        "public_indexing_permission_status": "User reports ministry permission for up to 20 chosen Acts, personal non-commercial use; see data/phase3/access-authorization.json. Original grant not independently inspected.",
        "technical_readiness_is_independent_of_permission": True,
        "ready_for_public_index": False,
    }
    return manifest


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data/import/lawindex_offline.sqlite3"))
    parser.add_argument("--manifest-out", default=str(ROOT / "data/import/readiness_manifest.json"))
    parser.add_argument("--fresh", action="store_true", help="delete the database file before importing")
    parser.add_argument("--resume", action="store_true", help="skip successful items only after input and stored-output verification")
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with import_lock(db_path):
        if args.fresh and db_path.exists():
            db_path.unlink()

        conn = sqlite3.connect(str(db_path))
        try:
            stats = _import_all_locked(conn, resume=args.resume)
            manifest = build_readiness_manifest(conn)
            Path(args.manifest_out).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
            print(json.dumps(stats))
            print(f"Wrote {args.manifest_out}")
            if stats["provisions_failed"]:
                raise SystemExit(1)
        finally:
            conn.close()


if __name__ == "__main__":
    main()
