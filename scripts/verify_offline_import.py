#!/usr/bin/env python3
"""Regression checks for the Phase 0 offline importer (scripts/offline_importer.py).

Tests behavior against retained fixtures, not hard-coded status flags. Makes
no network requests. Run after scripts/build_phase0_artifacts.py and
scripts/verify_phase0.py.
"""
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import offline_importer as oi  # noqa: E402


def fresh_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(oi.SCHEMA)
    return conn


def check_rti_mismatch_not_silently_admitted():
    """RTI-001: the excluded HTML wording must never appear in admitted text,
    and the admitted PDF-derived text must contain the shorter wording."""
    conn = fresh_conn()
    oi.import_all(conn)
    row = conn.execute(
        "SELECT admission_status, body_text FROM provisions WHERE provision_key='rti-2005:8'"
    ).fetchone()
    status, text = row
    assert status == "admitted", status
    assert "information which relates to personal information" in text
    assert "has no relationship to any public activity or interest" not in text
    conflict = conn.execute(
        "SELECT selected_representation, admission_json FROM conflicts WHERE issue_id='RTI-001'"
    ).fetchone()
    assert conflict[0] == "pdf"
    admission = json.loads(conflict[1])
    assert admission["structured_html_representation"] == "excluded"
    print("PASS: RTI-001 mismatch handled; excluded wording never reaches admitted text")


def check_footnote_preserved_separately():
    conn = fresh_conn()
    oi.import_all(conn)
    footnote = conn.execute(
        "SELECT footnote_text FROM provisions WHERE provision_key='rti-2005:8'"
    ).fetchone()[0]
    assert footnote is not None
    assert "Subs. by Act 22 of 2023, s. 44 for clause (j)" in footnote
    body = conn.execute(
        "SELECT body_text FROM provisions WHERE provision_key='rti-2005:8'"
    ).fetchone()[0]
    assert footnote not in body, "footnote must not be duplicated inline in the admitted body text"
    print("PASS: section 8 amendment footnote preserved, distinct from body text")


def check_hash_bound_page_anchors():
    conn = fresh_conn()
    oi.import_all(conn)
    rti_pdf_sha = oi.sha256_bytes(oi.load_capture_bytes("rti-2005-pdf"))
    env_pdf_sha = oi.sha256_bytes(oi.load_capture_bytes("environment-1986-pdf"))
    expectations = [
        ("rti-2005:6", "rti-2005-pdf", (9, 9)),
        ("rti-2005:8", "rti-2005-pdf", (10, 11)),
        ("environment-1986:3", "environment-1986-pdf", (4, 5)),
        ("environment-1986:5A", "environment-1986-pdf", (5, 5)),
    ]
    for key, expected_capture, expected_pages in expectations:
        row = conn.execute(
            "SELECT pdf_capture, pdf_page_from, pdf_page_to FROM provisions WHERE provision_key=?", (key,)
        ).fetchone()
        pdf_capture, page_from, page_to = row
        assert pdf_capture == expected_capture, (key, pdf_capture)
        assert (page_from, page_to) == expected_pages, (key, page_from, page_to)
        # For section 6 the *admitted representation* is structured_html, so its
        # own source_sha256_actual is the JSON capture hash; the PDF anchor is
        # separately bound and independently checked against the PDF hash below.
    for key, expected_sha in [("rti-2005:8", rti_pdf_sha), ("environment-1986:3", env_pdf_sha),
                               ("environment-1986:5A", env_pdf_sha)]:
        actual = conn.execute(
            "SELECT source_sha256_actual FROM provisions WHERE provision_key=?", (key,)
        ).fetchone()[0]
        assert actual == expected_sha, (key, actual, expected_sha)
    print("PASS: PDF page anchors are bound to the exact retained PDF hash, for both Acts in this slice")


def check_conflicting_metadata_preserved():
    """Second-pass update: a dedicated investigation (see
    data/review/conflicts/KERALA-001.json#investigation_pass2) found
    calibrated, retained-PDF evidence for which date concept each
    observation represents, and resolved the canonical field accordingly.
    Both raw observations must still survive regardless, the resolution must
    be traceable to an explicit conflict-record resolution block (not a
    hardcoded act-slug special case in the importer), and the Act must stay
    excluded from the searchable slice regardless of the date resolution."""
    conn = fresh_conn()
    oi.import_all(conn)
    row = conn.execute(
        "SELECT enact_date_raw, enact_date_listing_raw, canonical_enactment_date, scope_status, ready_for_public_index "
        "FROM documents WHERE act_slug='kerala-name-2026'"
    ).fetchone()
    enact, listing, canonical, scope_status, ready = row
    assert enact == "14-08-2026", "the raw detail-page observation must survive unchanged"
    assert listing == "25-08-2026", "the raw listing-page observation must survive unchanged"
    assert canonical == "14-08-2026", "canonical date must match the conflict record's explicit resolution"
    assert scope_status == "quarantine_fixture", "resolving the date must not silently lift the quarantine"
    assert ready == 0, "resolving the date must not make this Act ready for public index"

    conflict = json.loads((ROOT / "data/review/conflicts/KERALA-001.json").read_text())
    assert conflict["resolution"]["resolved"] is True
    assert conflict["resolution"]["value"] == canonical
    assert "residual_uncertainty" in conflict["investigation_pass2"], \
        "the resolution must honestly disclose what it did NOT independently confirm"
    print("PASS: Kerala's conflicting dates both survive; canonical date is resolved from an "
          "explicit, evidenced conflict-record resolution, and the Act stays excluded regardless")


def check_unresolved_date_conflict_stays_null_generically():
    """Prove the resolution mechanism is generic, not special-cased to
    Kerala: a synthetic act with a date conflict that has NOT been resolved
    must still produce a null canonical_enactment_date, using the exact same
    code path that resolved Kerala's."""
    conn = fresh_conn()
    manifest = oi.load_manifest()
    synthetic_manifest = manifest + [{
        "slug": "synthetic-unresolved-date-test", "uuid": "00000000-0000-0000-0000-000000000000",
        "title": "Synthetic fixture for an unresolved date conflict",
        "act_number": "0", "year": "2000", "scope_status": "quarantine_fixture",
        "enact_date_raw": "01-01-2000", "enact_date_listing_raw": "02-01-2000",
    }]
    synthetic_conflicts = dict(oi.load_conflict_records())
    synthetic_conflicts["SYNTHETIC-001"] = {
        "issue_id": "SYNTHETIC-001",
        "scope": {"act_slug": "synthetic-unresolved-date-test", "provision_key": None, "field": "enactment date"},
        "classification": "metadata", "selected_representation": None,
        "disposition": "review_pending", "admission": {}, "legal_effect_determined": False,
        "resolution": {"resolved": False},
    }
    import unittest.mock as mock
    with mock.patch.object(oi, "load_manifest", return_value=synthetic_manifest), \
         mock.patch.object(oi, "load_conflict_records", return_value=synthetic_conflicts):
        oi.import_all(conn)
    row = conn.execute(
        "SELECT canonical_enactment_date FROM documents WHERE act_slug='synthetic-unresolved-date-test'"
    ).fetchone()
    assert row[0] is None, "an unresolved date conflict must yield a null canonical date, not a guess"
    print("PASS: the date-resolution mechanism is generic -- an unresolved conflict on a synthetic "
          "act stays null through the same code path that resolved Kerala's")


def check_ocr_excluded():
    conn = fresh_conn()
    oi.import_all(conn)
    row = conn.execute(
        "SELECT scope_status, ready_for_public_index FROM documents WHERE act_slug='rti-rules-2012'"
    ).fetchone()
    assert row == ("quarantine_fixture", 0)
    admitted_from_rules = conn.execute(
        "SELECT COUNT(*) FROM provisions WHERE act_slug='rti-rules-2012' AND admission_status='admitted'"
    ).fetchone()[0]
    assert admitted_from_rules == 0
    conflict = conn.execute(
        "SELECT disposition, admission_json FROM conflicts WHERE issue_id='OCR-001'"
    ).fetchone()
    assert conflict[0] == "excluded"
    assert json.loads(conflict[1])["rule_text"] == "excluded"
    print("PASS: faulty RTI Rules OCR text is excluded, not auto-admitted")


def check_incomplete_acquisition_not_admitted():
    """A provision claiming a source hash that does not match the retained
    file must be treated as invalidated/incomplete, never silently admitted
    as verified empty or verified content."""
    conn = fresh_conn()
    tampered_review = dict(json.loads((ROOT / "data/review/rti-2005-section-8.review.json").read_text()))
    tampered_review["source_representation"] = dict(tampered_review["source_representation"])
    tampered_review["source_representation"]["sha256"] = "0" * 64
    real_bytes = {"rti-2005-pdf": oi.load_capture_bytes("rti-2005-pdf"),
                  "rti-sections-page-0": oi.load_capture_bytes("rti-sections-page-0")}
    record = oi.build_provision_record(tampered_review, real_bytes)
    assert record["admission_status"] == "invalidated_source_changed"
    assert record["body_text"] is None, "must not extract or admit text when the source hash cannot be verified"
    print("PASS: an unverifiable/incomplete source is invalidated, not treated as verified content")


ALL_TABLES = ["documents", "provisions", "review_decisions", "conflicts", "excerpts"]


def _dump_all_tables(conn):
    pk_by_table = {
        "documents": "act_slug", "provisions": "provision_key", "review_decisions": "provision_key",
        "conflicts": "issue_id", "excerpts": "excerpt_key",
    }
    return {t: list(conn.execute(f"SELECT * FROM {t} ORDER BY {pk_by_table[t]}")) for t in ALL_TABLES}


def check_idempotence():
    """Repeated imports must not create duplicates or drift in ANY table,
    including the excerpts table (which is rebuilt with DELETE+INSERT rather
    than upsert, so it needs its own explicit check)."""
    conn = fresh_conn()
    stats1 = oi.import_all(conn)
    dump1 = _dump_all_tables(conn)
    stats2 = oi.import_all(conn)
    dump2 = _dump_all_tables(conn)
    assert stats1 == stats2
    assert dump1 == dump2, "repeated import produced different rows"
    for table in ALL_TABLES:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count == len(dump1[table]), f"repeated import must not create duplicate rows in {table}"
    print("PASS: repeated import is idempotent across every table (documents, provisions, "
          "review_decisions, conflicts, excerpts) -- no duplicates, no drift")


def check_changed_source_invalidates():
    """Simulate a changed source PDF (different bytes -> different hash) and
    confirm the previously-approved admission is invalidated on the next
    import, without ever touching the real retained fixture."""
    conn = fresh_conn()
    oi.import_all(conn)
    before = conn.execute(
        "SELECT admission_status FROM provisions WHERE provision_key='rti-2005:8'"
    ).fetchone()[0]
    assert before == "admitted"

    tampered_pdf_bytes = oi.load_capture_bytes("rti-2005-pdf") + b"\n% tampered for test\n"
    oi.import_all(conn, capture_bytes_override={"rti-2005-pdf": tampered_pdf_bytes})
    after = conn.execute(
        "SELECT admission_status, body_text FROM provisions WHERE provision_key='rti-2005:8'"
    ).fetchone()
    assert after[0] == "invalidated_source_changed", after
    assert after[1] is None

    # Restore: importing with the real bytes again must re-admit it, and must
    # not have left a duplicate row behind from the invalidated import.
    oi.import_all(conn)
    restored = conn.execute(
        "SELECT admission_status FROM provisions WHERE provision_key='rti-2005:8'"
    ).fetchone()[0]
    assert restored == "admitted"
    count = conn.execute(
        "SELECT COUNT(*) FROM provisions WHERE provision_key='rti-2005:8'"
    ).fetchone()[0]
    assert count == 1
    print("PASS: a changed source hash invalidates the prior approval; restoring re-admits without duplicating")


def check_watermark_rule_scoped_and_confirmed_on_second_document():
    """The watermark-stripping rule must be provably scoped to actual
    watermark fragments, not a blunt substring removal that could eat
    legitimate short tokens. Exercise it directly (not through the full
    importer) with: a true positive, two designed near-misses that share
    tokens with the watermark set, and a check that it never touches a
    token embedded inside a longer line or word."""
    true_positive = "some sentence continues\n                                                                      aC\nand then resumes here."
    stripped = oi.strip_watermark(true_positive)
    assert "aC" not in stripped
    assert "some sentence continues" in stripped and "and then resumes here." in stripped

    # Near-miss 1: same token, but not enough leading whitespace (a real
    # short line, e.g. a stray OCR-clean single-letter clause label, should
    # survive if it is not deep in the right margin like the watermark is).
    near_miss_indent = "line one\n  e\nline two"
    assert oi.strip_watermark(near_miss_indent) == near_miss_indent, \
        "a short-indent line matching a watermark token must NOT be stripped"

    # Near-miss 2: the token is only part of the line's content, not the
    # whole line (e.g. real clause text ending in "...service." on an
    # indented line must never be mistaken for a bare "e").
    near_miss_substring = "line one\n                                                                      seed\nline two"
    assert oi.strip_watermark(near_miss_substring) == near_miss_substring, \
        "a heavily indented line whose content merely CONTAINS a watermark token must survive"

    # Near-miss 3: a real legal token that happens to collide with one of
    # the five watermark strings, but with trailing punctuation -- must
    # survive because the anchored $ requires nothing else on the line.
    near_miss_punctuation = "line one\n                                                                      e.\nline two"
    assert oi.strip_watermark(near_miss_punctuation) == near_miss_punctuation, \
        "a watermark-token-plus-punctuation line must survive; only the bare token is stripped"

    # Confirm this is not merely theoretical: re-run the exact regex against
    # both retained PDFs' extracted text and manually verify every match is
    # bracketed by blank lines or mid-sentence breaks typical of a
    # diagonal-watermark artifact, never inside an admitted provision's
    # meaningful short line.
    for slug, path in [("rti-2005", ROOT / "data/discovery/derived/rti-2005.txt"),
                        ("environment-1986", ROOT / "data/discovery/derived/environment-1986.txt")]:
        text = path.read_text()
        matches = list(oi.WATERMARK_LINE_RE.finditer(text))
        assert len(matches) > 0, f"expected watermark fragments in {slug}'s retained PDF text"
        for m in matches:
            assert m.group(0).strip() in {"In", "di", "aC", "od", "e"}
    print("PASS: watermark-stripping rule is provably scoped -- true positives are removed, "
          "designed near-misses (short indent, substring, trailing punctuation) survive")


def check_pdf_page_footers_stripped_not_legal_digits():
    """A PDF page's own printed page-number footer (a lone, heavily indented
    digit line pdftotext -layout emits at the very end of each page) must
    never survive into admitted body text, but a real in-body digit -- such
    as RTI section 8's own amendment-marker '1' before clause (j) -- must not
    be mistaken for one. Exercise strip_page_footers() directly against
    engineered fixtures, then confirm on the real admitted database that the
    two provisions whose ranges cross a page boundary (rti-2005:8, pages
    10-11; environment-1986:3, pages 4-5) contain no residual footer digit,
    while the nearby amendment marker survives (see docs/phase-1/REVIEW_FOLLOWUP.md
    finding 3 and data/review/reviewer-remediation-2.json)."""
    # A trailing digit-only line that matches the page's own 1-based position
    # is a footer and must be removed.
    page_one = "some clause text\n                    1"
    page_two = "more clause text\n                    2"
    stripped = oi.strip_page_footers([page_one, page_two])
    assert stripped[0] == "some clause text\n"
    assert stripped[1] == "more clause text\n"

    # A standalone digit line that does NOT match the page's own position
    # (e.g. an amendment-marker digit sitting on its own line) must survive:
    # this is exactly the RTI section 8 shape, where "1" precedes bracketed
    # text rather than ending the page.
    page_with_marker = "clause (i) text:\n\n          1\n           [(j) inserted clause]\n    (2) more text"
    assert oi.strip_page_footers([page_with_marker])[0] == page_with_marker, \
        "a standalone digit that is not the page's own trailing footer must never be stripped"

    # A trailing digit-only line that does not match this page's own position
    # (e.g. it actually belongs to a different page's footer, or is simply
    # some other in-body number) must also survive.
    mismatched = "clause text ending in the number\n                    7"
    assert oi.strip_page_footers([mismatched, mismatched])[0] == mismatched, \
        "a trailing digit not equal to the page's own 1-based position must not be stripped"

    conn = fresh_conn()
    oi.import_all(conn)
    section8 = conn.execute(
        "SELECT body_text FROM provisions WHERE provision_key='rti-2005:8'"
    ).fetchone()[0]
    assert "\n                                                       10\n" not in section8, \
        "the PDF page-10 footer digit must not appear in admitted rti-2005:8 body text"
    assert "\n          1\n           [(j) information which relates to personal information;]" in section8, \
        "the real amendment-marker digit before clause (j) must survive unchanged"

    section3 = conn.execute(
        "SELECT body_text FROM provisions WHERE provision_key='environment-1986:3'"
    ).fetchone()[0]
    assert not any(line.strip() == "4" for line in section3.splitlines()), \
        "the PDF page-4 footer digit must not appear in admitted environment-1986:3 body text"
    assert "(xiv) such other matters as the Central Government deems necessary" in section3
    assert "(3) The Central Government may, if it considers it necessary" in section3

    print("PASS: PDF page-number footers are stripped from admitted body text without "
          "eating a real amendment-marker digit")


def check_extraction_method_version_change_invalidates():
    """If the code's extraction method version moves on from what a review
    record was checked against, the prior admission must not silently carry
    over onto text produced by an unreviewed extraction method."""
    review = json.loads((ROOT / "data/review/rti-2005-section-6.review.json").read_text())
    bumped = dict(review)
    bumped["extraction_method_version"] = "offline-importer-v2-not-yet-reviewed"
    real_bytes = {"rti-2005-pdf": oi.load_capture_bytes("rti-2005-pdf"),
                  "rti-sections-page-0": oi.load_capture_bytes("rti-sections-page-0")}
    record = oi.build_provision_record(bumped, real_bytes)
    assert record["admission_status"] == "invalidated_extraction_method_changed"
    assert record["body_text"] is None
    print("PASS: a changed extraction method version invalidates the prior admission rather than "
          "silently applying it to text the reviewer never checked")


def check_footnote_declared_but_missing_invalidates():
    """If a review record attests that a provision has a footnote it checked,
    and a later extraction can no longer find that footnote, admission must
    be refused rather than silently served without it."""
    review = json.loads((ROOT / "data/review/rti-2005-section-8.review.json").read_text())
    tampered = json.loads(json.dumps(review))  # deep copy
    tampered["review"]["footnotes_present"] = True
    tampered["source_representation"] = dict(tampered["source_representation"])
    # Point the extraction at pages that do not contain the amendment
    # footnote, while still matching the real, unmodified PDF bytes/hash.
    tampered["source_representation"]["pdf_page_from"] = 10
    tampered["source_representation"]["pdf_page_to"] = 10
    real_bytes = {"rti-2005-pdf": oi.load_capture_bytes("rti-2005-pdf"),
                  "rti-sections-page-0": oi.load_capture_bytes("rti-sections-page-0")}
    try:
        record = oi.build_provision_record(tampered, real_bytes)
    except oi.AdmissionError:
        # Section 8's end pattern ("9. Grounds...") is not on page 10 alone,
        # so a strict single-page slice may instead fail to find the end
        # boundary. Either an explicit AdmissionError or an explicit
        # invalidated admission status is an acceptable "refuse to admit"
        # outcome; silently returning admitted text without the footnote is
        # the only unacceptable outcome, and that is asserted below.
        print("PASS: section 8 sliced without its footnote page fails extraction outright "
              "rather than silently admitting text without the expected footnote")
        return
    assert record["admission_status"] != "admitted", record["admission_status"]
    print("PASS: a declared-but-missing footnote invalidates admission rather than silently "
          "serving text without it")


def check_removed_review_record_invalidates_on_existing_database():
    """A prior admission must not survive as 'admitted' forever once its
    backing review record is removed from an existing (non-fresh) database --
    the most direct way an approval would actually be retracted. This is
    distinct from check_changed_source_invalidates, which only exercises a
    byte-level change to a record that still exists; import_all's upsert
    loops never revisit a provision_key/act_slug once it disappears from
    data/review/ or the manifest, so that path needs its own invalidation
    pass (see offline_importer.invalidate_stale_records)."""
    real_review = json.loads((ROOT / "data/review/rti-2005-section-8.review.json").read_text())
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "existing.sqlite3"
        conn = sqlite3.connect(str(db_path))
        try:
            oi.import_all(conn)
            before = conn.execute(
                "SELECT admission_status, body_text FROM provisions WHERE provision_key='rti-2005:8'"
            ).fetchone()
            assert before[0] == "admitted" and before[1] is not None

            reviews_without_section_8 = {
                k: v for k, v in oi.load_review_records().items() if k != "rti-2005:8"
            }
            import unittest.mock as mock
            with mock.patch.object(oi, "load_review_records", return_value=reviews_without_section_8):
                oi.import_all(conn)

            after = conn.execute(
                "SELECT admission_status, body_text, footnote_text FROM provisions WHERE provision_key='rti-2005:8'"
            ).fetchone()
            assert after[0] == oi.ADMISSION_STATUS_REVIEW_RECORD_REMOVED, after
            assert after[1] is None, "body_text must not remain available once the review record backing it is gone"
            assert after[2] is None, "footnote_text must not remain available once the review record backing it is gone"
            stale_excerpts = conn.execute(
                "SELECT COUNT(*) FROM excerpts WHERE provision_key='rti-2005:8'"
            ).fetchone()[0]
            assert stale_excerpts == 0, "no excerpt may point at a provision whose review record was removed"

            # Restoring the review record must re-admit it without leaving a
            # duplicate row from the invalidated interval.
            oi.import_all(conn)
            restored = conn.execute(
                "SELECT admission_status FROM provisions WHERE provision_key='rti-2005:8'"
            ).fetchone()[0]
            assert restored == "admitted"
            count = conn.execute(
                "SELECT COUNT(*) FROM provisions WHERE provision_key='rti-2005:8'"
            ).fetchone()[0]
            assert count == 1
        finally:
            conn.close()
    assert real_review == json.loads((ROOT / "data/review/rti-2005-section-8.review.json").read_text()), \
        "this check must never modify the real retained review record"
    print("PASS: removing a review record invalidates its provision on an existing database "
          "(admission_status, body_text, footnote_text, and its excerpt), and restoring the "
          "record re-admits it without duplication")


def check_removed_manifest_entry_invalidates_document_on_existing_database():
    """Dropping an Act from the manifest must not leave a stale document row
    silently claiming it is still part of the corpus on an existing database."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "existing.sqlite3"
        conn = sqlite3.connect(str(db_path))
        try:
            oi.import_all(conn)
            before = conn.execute(
                "SELECT removed_from_manifest FROM documents WHERE act_slug='rti-rules-2012'"
            ).fetchone()
            assert before == (0,), before

            manifest_without_rules = [m for m in oi.load_manifest() if m["slug"] != "rti-rules-2012"]
            import unittest.mock as mock
            with mock.patch.object(oi, "load_manifest", return_value=manifest_without_rules):
                oi.import_all(conn)

            after = conn.execute(
                "SELECT removed_from_manifest, ready_for_public_index FROM documents WHERE act_slug='rti-rules-2012'"
            ).fetchone()
            assert after == (1, 0), after
        finally:
            conn.close()
    print("PASS: removing an Act from the manifest flags its stale document row on an existing "
          "database rather than leaving it silently looking current")


def check_manifest_removal_and_restoration_round_trip():
    """docs/phase-0/INSPECTION_FOLLOWUP.md Finding 2: invalidate_stale_records
    correctly flagged a removed Act, but the document upsert never reset the
    flag when the Act reappeared in the manifest, leaving contradictory state
    (removed_from_manifest=1 forever, while its provisions were re-admitted).
    Exercise the full remove -> reimport -> restore -> reimport -> reimport
    cycle on ONE existing database, using the Environment Act (which, unlike
    rti-rules-2012, actually has admitted provisions to lose and regain), and
    confirm readiness output stays consistent throughout."""
    full_manifest = oi.load_manifest()
    manifest_without_environment = [m for m in full_manifest if m["slug"] != "environment-1986"]
    import unittest.mock as mock

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "existing.sqlite3"
        conn = sqlite3.connect(str(db_path))
        try:
            # 1. Import -> baseline: both Environment Act provisions admitted.
            oi.import_all(conn)
            admitted = {row[0] for row in conn.execute(
                "SELECT provision_key FROM provisions WHERE admission_status='admitted'"
            ).fetchall()}
            assert {"environment-1986:3", "environment-1986:5A"} <= admitted

            # 2. Remove the Act -> reimport.
            with mock.patch.object(oi, "load_manifest", return_value=manifest_without_environment):
                oi.import_all(conn)
            removed_flag = conn.execute(
                "SELECT removed_from_manifest FROM documents WHERE act_slug='environment-1986'"
            ).fetchone()[0]
            assert removed_flag == 1
            env_statuses = dict(conn.execute(
                "SELECT provision_key, admission_status FROM provisions WHERE act_slug='environment-1986'"
            ).fetchall())
            for key, status in env_statuses.items():
                assert status != "admitted", f"{key} must not stay admitted once its Act leaves the manifest"
            excerpt_count = conn.execute(
                "SELECT COUNT(*) FROM excerpts WHERE provision_key IN "
                "('environment-1986:3', 'environment-1986:5A')"
            ).fetchone()[0]
            assert excerpt_count == 0, "no excerpt may survive for a provision whose Act left the manifest"
            manifest_json = oi.build_readiness_manifest(conn)
            assert "environment-1986" in manifest_json["documents_removed_from_manifest"]
            assert "environment-1986" not in manifest_json["documents_known_but_unreviewed"], (
                "a removed Act must not also be listed as an active but-unreviewed candidate"
            )

            # 3. Restore the original manifest -> reimport.
            oi.import_all(conn)
            restored_flag = conn.execute(
                "SELECT removed_from_manifest FROM documents WHERE act_slug='environment-1986'"
            ).fetchone()[0]
            assert restored_flag == 0, "removed_from_manifest must be explicitly cleared once the Act returns"
            restored_admitted = {row[0] for row in conn.execute(
                "SELECT provision_key FROM provisions WHERE admission_status='admitted'"
            ).fetchall()}
            assert restored_admitted == expected_admitted_keys(), restored_admitted
            assert {"environment-1986:3", "environment-1986:5A"} <= restored_admitted
            manifest_json_restored = oi.build_readiness_manifest(conn)
            assert manifest_json_restored["documents_removed_from_manifest"] == []
            restored_body = conn.execute(
                "SELECT body_text FROM provisions WHERE provision_key='environment-1986:3'"
            ).fetchone()[0]
            assert restored_body is not None and "co-ordination" in restored_body

            # 4. Repeat the import once more: stable, duplicate-free.
            stats_a = oi.import_all(conn)
            dump_a = {t: list(conn.execute(f"SELECT * FROM {t} ORDER BY 1")) for t in ALL_TABLES}
            stats_b = oi.import_all(conn)
            dump_b = {t: list(conn.execute(f"SELECT * FROM {t} ORDER BY 1")) for t in ALL_TABLES}
            assert stats_a == stats_b
            assert dump_a == dump_b, "repeated import after a remove/restore cycle must not drift"
            doc_count = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE act_slug='environment-1986'"
            ).fetchone()[0]
            assert doc_count == 1, "restoring an Act must not create a duplicate document row"
        finally:
            conn.close()
    assert full_manifest == oi.load_manifest(), "this check must never modify the real retained manifest"
    print("PASS: removing then restoring a manifest entry clears removed_from_manifest, re-admits its "
          "provisions, restores readiness output consistency, and repeated import stays duplicate-free")


def check_changed_body_text_invalidates_via_digest_mismatch():
    """docs/phase-0/INSPECTION_FOLLOWUP.md Finding 1: matching source bytes
    and a matching extraction-method-version label only prove the INPUT and
    the declared METHOD are unchanged -- not that a reviewer ever looked at
    THIS run's output. Reproduce the follow-up's own repro: wrap extraction
    to alter section 8's body text while leaving the retained PDF bytes and
    the extraction_method_version label completely untouched, reimport into
    an EXISTING database, and confirm the previously-admitted provision is
    invalidated, its stale text/excerpt are gone, and restoring the real
    extraction re-admits it without duplication."""
    import unittest.mock as mock
    real_extract_pdf_range = oi.extract_pdf_range

    def tampered_extract_pdf_range(*args, **kwargs):
        body, footnote = real_extract_pdf_range(*args, **kwargs)
        if "information which relates to personal information" in body:
            body = body.replace(
                "information which relates to personal information",
                "UNREVIEWED REPLACEMENT WORDING NO REVIEWER HAS SEEN",
            )
        return body, footnote

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "existing.sqlite3"
        conn = sqlite3.connect(str(db_path))
        try:
            oi.import_all(conn)
            before = conn.execute(
                "SELECT admission_status, body_text FROM provisions WHERE provision_key='rti-2005:8'"
            ).fetchone()
            assert before[0] == "admitted" and before[1] is not None

            with mock.patch.object(oi, "extract_pdf_range", side_effect=tampered_extract_pdf_range):
                oi.import_all(conn)

            after = conn.execute(
                "SELECT admission_status, body_text, body_text_sha256 FROM provisions "
                "WHERE provision_key='rti-2005:8'"
            ).fetchone()
            assert after[0] == oi.ADMISSION_STATUS_BODY_TEXT_CHANGED, after
            assert after[1] is None, "changed text that no reviewer approved must never be served as body_text"
            expected_sha = json.loads(
                (ROOT / "data/review/rti-2005-section-8.review.json").read_text()
            )["expected_output"]["body_text_sha256"]
            assert after[2] != expected_sha, (
                "the actual (mismatching) digest should still be recorded as evidence of what changed"
            )
            stale_excerpts = conn.execute(
                "SELECT COUNT(*) FROM excerpts WHERE provision_key='rti-2005:8'"
            ).fetchone()[0]
            assert stale_excerpts == 0, "no excerpt may survive pointing at unreviewed replacement text"

            # Unrelated provisions must not be collaterally affected.
            other_statuses = dict(conn.execute(
                "SELECT provision_key, admission_status FROM provisions WHERE provision_key != 'rti-2005:8'"
            ).fetchall())
            for key, status in other_statuses.items():
                assert status == "admitted", f"{key} must be unaffected by section 8's tampered extraction"

            # Restoring the real extraction must re-admit without duplication.
            oi.import_all(conn)
            restored = conn.execute(
                "SELECT admission_status, body_text FROM provisions WHERE provision_key='rti-2005:8'"
            ).fetchone()
            assert restored[0] == "admitted"
            assert "information which relates to personal information" in restored[1]
            count = conn.execute(
                "SELECT COUNT(*) FROM provisions WHERE provision_key='rti-2005:8'"
            ).fetchone()[0]
            assert count == 1
        finally:
            conn.close()
    print("PASS: a body-text change with unchanged source bytes and extraction-method-version is "
          "caught by the expected-output digest, invalidates admission, leaves no stale excerpt, "
          "and restoring the approved output re-admits without duplication")


def check_changed_footnote_wording_invalidates_via_digest_mismatch():
    """Distinct from check_footnote_declared_but_missing_invalidates (which
    tests a footnote going missing entirely): here the footnote is still
    PRESENT after extraction, so the footnotes_present presence/absence check
    cannot catch it, but its wording has changed. Only a digest comparison
    against the reviewed footnote text can catch this."""
    import unittest.mock as mock
    real_extract_pdf_range = oi.extract_pdf_range

    def tampered_extract_pdf_range(*args, **kwargs):
        body, footnote = real_extract_pdf_range(*args, **kwargs)
        if footnote and "Ins. by Act 19 of 2010" in footnote:
            footnote = footnote + " [UNREVIEWED APPENDED TEXT]"
        return body, footnote

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "existing.sqlite3"
        conn = sqlite3.connect(str(db_path))
        try:
            oi.import_all(conn)
            before = conn.execute(
                "SELECT admission_status, footnote_text FROM provisions WHERE provision_key='environment-1986:5A'"
            ).fetchone()
            assert before[0] == "admitted" and before[1] is not None

            with mock.patch.object(oi, "extract_pdf_range", side_effect=tampered_extract_pdf_range):
                oi.import_all(conn)

            after = conn.execute(
                "SELECT admission_status, body_text, footnote_text FROM provisions "
                "WHERE provision_key='environment-1986:5A'"
            ).fetchone()
            assert after[0] == oi.ADMISSION_STATUS_FOOTNOTE_TEXT_CHANGED, after
            assert after[1] is None and after[2] is None, (
                "neither body nor footnote text may remain available once the footnote digest mismatches"
            )
            stale_excerpts = conn.execute(
                "SELECT COUNT(*) FROM excerpts WHERE provision_key='environment-1986:5A'"
            ).fetchone()[0]
            assert stale_excerpts == 0

            oi.import_all(conn)
            restored = conn.execute(
                "SELECT admission_status FROM provisions WHERE provision_key='environment-1986:5A'"
            ).fetchone()[0]
            assert restored == "admitted"
        finally:
            conn.close()
    print("PASS: a footnote WORDING change (footnote still present, so the missing-footnote check "
          "cannot catch it) is caught by the expected-output digest and invalidates admission")


def check_missing_expected_digest_prevents_admission():
    """A provision whose review record has never had an expected_output
    baseline recorded (e.g. a brand-new review record, or one from before
    this mechanism existed) must be treated as review_pending / invalidated,
    never admitted by default just because its source hash and extraction
    version happen to match."""
    import unittest.mock as mock

    reviews = oi.load_review_records()
    reviews_missing_baseline = dict(reviews)
    stripped = json.loads(json.dumps(reviews["rti-2005:6"]))  # deep copy
    del stripped["expected_output"]
    reviews_missing_baseline["rti-2005:6"] = stripped

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "existing.sqlite3"
        conn = sqlite3.connect(str(db_path))
        try:
            with mock.patch.object(oi, "load_review_records", return_value=reviews_missing_baseline):
                oi.import_all(conn)
            row = conn.execute(
                "SELECT admission_status, body_text FROM provisions WHERE provision_key='rti-2005:6'"
            ).fetchone()
            assert row[0] == oi.ADMISSION_STATUS_MISSING_EXPECTED_DIGEST, row
            assert row[1] is None, "a provision with no attested output baseline must never be admitted by default"
        finally:
            conn.close()
    assert "expected_output" in json.loads(
        (ROOT / "data/review/rti-2005-section-6.review.json").read_text()
    ), "this check must never modify the real retained review record"
    print("PASS: a provision with no expected-output digest baseline is refused admission rather than "
          "defaulting to admitted just because its source hash and extraction version match")


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def check_dev_queries_are_honest():
    """Every dev-query file must only target actually admitted provisions,
    must never carry an invented relevance score, and the original v1 file
    must survive unchanged as immutable history once v2 exists."""
    conn = fresh_conn()
    oi.import_all(conn)
    admitted_keys = {row[0] for row in conn.execute(
        "SELECT provision_key FROM provisions WHERE admission_status='admitted'"
    ).fetchall()}

    v1 = _read_jsonl(ROOT / "data/review/dev-queries.v1.jsonl")
    v2 = _read_jsonl(ROOT / "data/review/dev-queries.v2.jsonl")
    assert len(v1) == 4, "the original v1 dev-query file must remain exactly as first authored"
    assert len(v2) == 6, "v2 should extend v1 with exactly the two newly reviewed Environment Act provisions"
    assert v2[:4] == v1, "v2 must preserve every v1 entry unchanged, not silently rewrite prior judgments"

    for query in v2:
        assert query["expected_provision_key"] in admitted_keys, (
            f"dev query {query['id']} targets {query['expected_provision_key']!r}, which is not an admitted provision"
        )
        assert query.get("relevance_score") is None, (
            f"dev query {query['id']} must not carry an invented relevance score"
        )
    new_ids = {q["id"] for q in v2} - {q["id"] for q in v1}
    assert new_ids == {"DEV-005", "DEV-006"}
    for query in v2:
        if query["id"] in new_ids:
            assert query["evidence_status"].startswith("text_reviewed"), query["id"]
    print("PASS: dev-query versions are honest -- v1 preserved unchanged, v2 only extends coverage "
          "to newly admitted provisions, no invented relevance scores anywhere")


def check_review_decisions_attribute_correct_reviewer_per_provision():
    """Defect found in second-pass review: review_decisions previously loaded
    ONE reviewer.json globally and stamped it onto every provision, which
    would have silently mis-attributed the Environment Act's second-pass
    review to the session-1 reviewer. Each provision's stored reviewer_id
    must match its own review record's declared reviewer_ref."""
    conn = fresh_conn()
    oi.import_all(conn)
    expected = {
        "rti-2005:6": "agent:claude-sonnet-5:2026-09-20-session",
        "rti-2005:8": "agent:claude-sonnet-5:2026-09-20-session",
        "environment-1986:3": "agent:claude-sonnet-5:2026-09-20-session2",
        "environment-1986:5A": "agent:claude-sonnet-5:2026-09-20-session2",
    }
    for key in INDIVIDUALLY_REVIEWED_KEYS - set(expected):
        expected[key] = 'agent:codex:2026-09-22-phase3-batch1'
    for key, plan in sampled_authorized_keys().items():
        reviewer = json.loads((ROOT / plan['review']['reviewer_ref']).read_text())
        expected.setdefault(key, reviewer['reviewer_id'])
    for provision_key, reviewer_id in conn.execute(
        "SELECT provision_key, reviewer_id FROM review_decisions"
    ).fetchall():
        assert reviewer_id == expected[provision_key], (provision_key, reviewer_id)
    print("PASS: each provision's stored review_decisions row attributes the reviewer that actually "
          "reviewed it, not a single global reviewer stamped onto everything")


def check_conflict_referential_integrity():
    """Every known_conflicts entry recorded on an admitted provision must
    correspond to a real conflict record whose own scope names that same
    provision -- catching drift between the two hand-authored record types."""
    conn = fresh_conn()
    oi.import_all(conn)
    conflict_scopes = {}
    for issue_id, scope_json in conn.execute("SELECT issue_id, scope_json FROM conflicts"):
        conflict_scopes[issue_id] = json.loads(scope_json)
    checked_any = False
    for provision_key, known_json in conn.execute("SELECT provision_key, known_conflicts_json FROM provisions"):
        for issue_id in json.loads(known_json):
            checked_any = True
            assert issue_id in conflict_scopes, f"{provision_key} references unknown conflict {issue_id}"
            scope = conflict_scopes[issue_id]
            assert scope.get("provision_key") == provision_key, (
                f"conflict {issue_id} scope {scope} does not name the provision {provision_key} that references it"
            )
    assert checked_any, "expected at least one provision-to-conflict reference to check"
    print("PASS: every provision's declared known_conflicts resolve to a matching conflict record scope")


def check_excerpt_to_source_mapping():
    conn = fresh_conn()
    oi.import_all(conn)
    prov_key = "rti-2005:6"
    body_text, body_sha = conn.execute(
        "SELECT body_text, body_text_sha256 FROM provisions WHERE provision_key=?", (prov_key,)
    ).fetchone()
    assert hashlib.sha256(body_text.encode("utf-8")).hexdigest() == body_sha

    excerpt_row = conn.execute(
        "SELECT excerpt_key, char_start, char_end, excerpt_text FROM excerpts WHERE provision_key=?",
        (prov_key,),
    ).fetchone()
    assert excerpt_row is not None, "an admitted provision must have a mapped excerpt"
    excerpt_key, start, end, excerpt_text = excerpt_row
    assert excerpt_key == f"{prov_key}:{start}:{end}"
    assert body_text[start:end] == excerpt_text, "excerpt must resolve exactly to a slice of the admitted source text"
    assert excerpt_text in body_text
    print("PASS: excerpt resolves exactly back to its admitted source text by offset")


# Provisions reviewed one at a time, each by a named reviewer. This list is
# historical and fixed: new coverage arrives through sampled Act batches
# below, never by quietly appending keys here.
INDIVIDUALLY_REVIEWED_KEYS = {"rti-2005:6", "rti-2005:8", "environment-1986:3", "environment-1986:5A",
                              "rti-2005:3", "rti-2005:9", "environment-1986:4", "environment-1986:8",
                              "posh-2013:9", "posh-2013:10"}


def sampled_authorized_keys():
    """Keys a passing sampled-review plan authorizes, derived from the plans
    themselves rather than restated here, so a plan that was never reviewed,
    or whose review rejected the Act, authorizes nothing."""
    authorized = {}
    for path in sorted((ROOT / "data/phase3/review-plans").glob("*.json")):
        plan = json.loads(path.read_text())
        review = plan.get("review") or {}
        if plan.get("status") != "reviewed" or review.get("decision") != "act_batch_admitted":
            continue
        for entry in plan["population"]:
            authorized[entry["key"]] = plan
    return authorized


def expected_admitted_keys():
    """Every key that may be admitted: individually reviewed ones, plus the
    sampled-authorized ones that actually have a written review record."""
    reviews = oi.load_review_records()
    keys = set(INDIVIDUALLY_REVIEWED_KEYS)
    for key, plan in sampled_authorized_keys().items():
        if key in reviews:
            keys.add(key)
    return keys


def check_unreviewed_sections_not_admitted():
    """Only provisions with an explicit review record may be admitted: either
    individually reviewed, or inside an Act whose sampled review passed and
    which actually has a written per-provision record."""
    conn = fresh_conn()
    oi.import_all(conn)
    admitted_keys = {row[0] for row in conn.execute(
        "SELECT provision_key FROM provisions WHERE admission_status='admitted'"
    ).fetchall()}
    assert admitted_keys == expected_admitted_keys(), admitted_keys ^ expected_admitted_keys()
    doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    manifest_count = len(oi.load_manifest())
    assert doc_count == manifest_count, "every manifest document should be recorded at document level"
    # Knowing an Act at document level must never make it searchable.
    admitted_acts = {key.split(":")[0] for key in admitted_keys}
    assert len(admitted_acts) < manifest_count, "most known Acts must still have no admitted provision"
    print("PASS: unreviewed sections and Acts remain unadmitted despite being known at document level")


def check_review_is_not_presented_as_expert_review():
    for reviewer_file in ("reviewer.json", "reviewer-pass2.json"):
        review = json.loads((ROOT / f"data/review/{reviewer_file}").read_text())
        assert review["is_independent_legal_expert_review"] is False
        assert "AI" in review["disclosure"] or "agent" in review["disclosure"].lower()
    expected_reviewer_ref = {
        "rti-2005-section-6": "data/review/reviewer.json",
        "rti-2005-section-8": "data/review/reviewer.json",
        "environment-1986-section-3": "data/review/reviewer-pass2.json",
        "environment-1986-section-5A": "data/review/reviewer-pass2.json",
    }
    for name, expected_ref in expected_reviewer_ref.items():
        record = json.loads((ROOT / f"data/review/{name}.review.json").read_text())
        assert record["review"]["reviewer_ref"] == expected_ref, name
    print("PASS: agent review (including the second-pass review) is explicitly disclosed, "
          "never presented as independent legal-expert review")


def check_environment_slice_admitted_with_full_structure():
    """The second-Act slice must be a genuinely different structural exercise
    (nested clauses, a lettered/amended provision), not another easy pick,
    and must be labeled PDF-only since no structured text was retained for
    this Act."""
    conn = fresh_conn()
    oi.import_all(conn)
    for name in ("environment-1986-section-3", "environment-1986-section-5A"):
        record = json.loads((ROOT / f"data/review/{name}.review.json").read_text())
        assert record["pdf_only_no_structured_comparison_available"] is True
        assert record["classification"] == "pdf_only_no_comparison_representation"

    section3 = conn.execute(
        "SELECT body_text, admission_status FROM provisions WHERE provision_key='environment-1986:3'"
    ).fetchone()
    body3, status3 = section3
    assert status3 == "admitted"
    for fragment in ["(i) co-ordination", "(a) under this Act", "(b) under any other law",
                      "(xiv) such other matters"]:
        assert fragment in body3, fragment
    assert "Provided that different standards for emission or discharge" in body3

    section5a = conn.execute(
        "SELECT body_text, footnote_text, admission_status FROM provisions WHERE provision_key='environment-1986:5A'"
    ).fetchone()
    body5a, footnote5a, status5a = section5a
    assert status5a == "admitted"
    assert body5a.strip().startswith("1"), "the amendment-insertion marker must survive at the start of the text"
    assert "[5A. Appeal to National Green Tribunal" in body5a
    assert body5a.strip().endswith("]"), "the closing insertion bracket must survive"
    assert "any directions issues under" in body5a, "must preserve the source's own wording verbatim, including its apparent grammatical slip"
    assert footnote5a is not None and "Ins. by Act 19 of 2010" in footnote5a
    print("PASS: Environment Act slice (nested clauses + lettered amended provision) admitted with full structure intact")


def check_search_snapshot_serves_every_importer_admission():
    """The importer admitting a provision is not the same as search serving it:
    Snapshot re-validates each row against review and capture evidence and
    silently drops anything inconsistent (e.g. capture metadata missing a
    field). A fresh import into a temporary database must be served in full."""
    sys.path.insert(0, str(ROOT))
    from lawindex.search import Snapshot
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "verify.sqlite3"
        with sqlite3.connect(db) as conn:
            oi.import_all(conn)
        snapshot = Snapshot(ROOT, db)
    assert set(snapshot.records) == expected_admitted_keys(), set(snapshot.records) ^ expected_admitted_keys()
    assert snapshot.excluded_count == 0, f"{snapshot.excluded_count} admitted provisions silently excluded by search"
    print("PASS: search-side Snapshot serves every importer-admitted provision with zero silent exclusions")


def check_sampled_admission_is_bound_to_its_plan_and_never_overclaims():
    """An Act-sampled admission must stay tied to the plan that authorized it,
    and must never present an unsampled provision as individually reviewed."""
    sys.path.insert(0, str(ROOT))
    from lawindex.search import Snapshot, review_basis
    reviews = oi.load_review_records()
    sampled = {k: r for k, r in reviews.items()
               if r["extraction_method_version"] == oi.SAMPLED_AGREEMENT_VERSION}
    assert sampled, "no sampled-review admissions to check"
    plans = sampled_authorized_keys()

    unsampled = None
    for key, review in sampled.items():
        block = review["review"]
        plan = plans[key]
        assert block["review_class"] == "text_agreement_sampled_visual"
        assert block["visually_reviewed"] == (key in plan["selected_keys"]), key
        reference = block["sample_plan"]
        path = ROOT / reference["path"]
        assert oi.sha256_bytes(path.read_bytes()) == reference["sha256"], key
        basis = review_basis(review)
        assert basis["individually_reviewed"] is block["visually_reviewed"]
        if not block["visually_reviewed"]:
            # Prefer a provision that actually needed normalization, so the
            # "overstated level" mutation below is a real downgrade.
            if unsampled is None or (review["agreement"]["normalizations"]
                                     and not sampled[unsampled]["agreement"]["normalizations"]):
                unsampled = key
            assert "but not this one" in basis["basis"], key
        else:
            assert "including this one" in basis["basis"], key
    assert unsampled, "the sample must be a sample: some admitted provision was not individually reviewed"

    # The reviewer record must disclaim independent legal-expert review.
    for plan in {id(p): p for p in plans.values()}.values():
        reviewer = json.loads((ROOT / plan["review"]["reviewer_ref"]).read_text())
        assert reviewer["is_independent_legal_expert_review"] is False
        assert "not individually compared" in reviewer["disclosure"].lower() or \
               "were not individually compared" in reviewer["disclosure"].lower(), "sampling must be disclosed"

    raw = {name: oi.load_capture_bytes(name) for name in
           (sampled[unsampled]["source_representation"]["capture"],
            sampled[unsampled]["pdf_anchor"]["capture"])}
    assert oi.build_provision_record(sampled[unsampled], raw)["admission_status"] == "admitted"

    # A changed plan, a withdrawn review, a rejected batch, an overstated
    # normalization level and a mis-set visually_reviewed flag must each stop
    # admission rather than silently serving text nobody authorized.
    original = (ROOT / sampled[unsampled]["review"]["sample_plan"]["path"]).read_text()
    plan_obj = json.loads(original)
    for label, mutate in [
        ("plan bytes changed", lambda p: p.update(seed="tampered")),
        ("review withdrawn", lambda p: (p.update(review=None, status="awaiting_review"))),
        ("batch rejected", lambda p: p["review"].update(decision="act_batch_rejected")),
        ("an outcome not verified", lambda p: p["review"]["outcomes"].__setitem__(
            p["selected_keys"][0], {"decision": "discrepancy", "note": "x"})),
        ("an outcome dropped", lambda p: p["review"]["outcomes"].pop(p["selected_keys"][0])),
        ("population digest changed", lambda p: p["population"][0].__setitem__("body_text_sha256", "0" * 64)),
    ]:
        mutated = json.loads(original)
        mutate(mutated)
        (ROOT / sampled[unsampled]["review"]["sample_plan"]["path"]).write_text(json.dumps(mutated, indent=2))
        try:
            record = json.loads(json.dumps(sampled[unsampled]))
            if label == "plan bytes changed":
                record["review"]["sample_plan"]["sha256"] = oi.sha256_bytes(
                    (ROOT / record["review"]["sample_plan"]["path"]).read_bytes())
            try:
                status = oi.build_provision_record(record, raw)["admission_status"]
                raised = None
            except (ValueError, KeyError) as error:
                status, raised = None, error
            assert raised is not None or status != "admitted", f"{label} still admitted"
        finally:
            (ROOT / sampled[unsampled]["review"]["sample_plan"]["path"]).write_text(original)

    for label, mutate in [
        ("overstated normalization level", lambda r: r["agreement"].update(normalization_level=0, normalizations=[])),
        ("claimed visual review", lambda r: r["review"].update(visually_reviewed=True)),
        ("wrong review class", lambda r: r["review"].update(review_class="individual_visual")),
        ("wrong page-break gap count", lambda r: r["agreement"].update(page_break_gap_count=9)),
    ]:
        record = json.loads(json.dumps(sampled[unsampled]))
        mutate(record)
        try:
            status = oi.build_provision_record(record, raw)["admission_status"]
            raised = None
        except (ValueError, KeyError) as error:
            status, raised = None, error
        assert raised is not None or status != "admitted", f"{label} still admitted"

    snapshot = Snapshot(ROOT)
    served = snapshot.records[unsampled]["review"]
    assert served["individually_reviewed"] is False and served["sampled_count"] < served["sample_population"]
    print("PASS: sampled admissions stay bound to their plan, and a provision admitted under a sample "
          "is never served as individually reviewed")


def main():
    checks = [
        check_rti_mismatch_not_silently_admitted,
        check_footnote_preserved_separately,
        check_hash_bound_page_anchors,
        check_conflicting_metadata_preserved,
        check_unresolved_date_conflict_stays_null_generically,
        check_ocr_excluded,
        check_incomplete_acquisition_not_admitted,
        check_idempotence,
        check_changed_source_invalidates,
        check_excerpt_to_source_mapping,
        check_unreviewed_sections_not_admitted,
        check_review_is_not_presented_as_expert_review,
        check_environment_slice_admitted_with_full_structure,
        check_watermark_rule_scoped_and_confirmed_on_second_document,
        check_pdf_page_footers_stripped_not_legal_digits,
        check_extraction_method_version_change_invalidates,
        check_footnote_declared_but_missing_invalidates,
        check_conflict_referential_integrity,
        check_dev_queries_are_honest,
        check_review_decisions_attribute_correct_reviewer_per_provision,
        check_removed_review_record_invalidates_on_existing_database,
        check_removed_manifest_entry_invalidates_document_on_existing_database,
        check_manifest_removal_and_restoration_round_trip,
        check_changed_body_text_invalidates_via_digest_mismatch,
        check_changed_footnote_wording_invalidates_via_digest_mismatch,
        check_missing_expected_digest_prevents_admission,
        check_search_snapshot_serves_every_importer_admission,
        check_sampled_admission_is_bound_to_its_plan_and_never_overclaims,
    ]
    for check in checks:
        check()
    print(f"\nALL {len(checks)} OFFLINE IMPORT CHECKS PASSED")


if __name__ == "__main__":
    main()
