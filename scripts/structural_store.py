"""Versioned structural storage. No fetching, extraction, or implicit approval.

The importer owns transactions and promotion. Historical rows are immutable;
current_versions is the revocable pointer. Legacy provisions/excerpts are a
compatibility projection, not an alternate source for serving legal text.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid

VERSION = 1
PASSAGE_STRATEGY = 'whole-section-v1'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(value).hexdigest()


def identity(kind, value):
    return kind + ':' + sha(canonical(value).encode())


# Statements are executed individually inside an explicit transaction. Do not
# use executescript here: it can commit a caller's transaction before the DDL.
DDL = [
    'CREATE TABLE structural_schema (version INTEGER PRIMARY KEY CHECK(version = 1))',
    '''CREATE TABLE source_blobs (
        sha256 TEXT PRIMARY KEY CHECK(length(sha256)=64), byte_count INTEGER NOT NULL CHECK(byte_count>0))''',
    '''CREATE TABLE source_snapshots (
        snapshot_id TEXT PRIMARY KEY, act_slug TEXT NOT NULL REFERENCES documents(act_slug),
        blob_sha256 TEXT NOT NULL REFERENCES source_blobs(sha256), capture_name TEXT NOT NULL,
        representation TEXT NOT NULL, source_url TEXT, fetched_at TEXT,
        body_path TEXT NOT NULL, metadata_json TEXT NOT NULL)''',
    '''CREATE TABLE extractions (
        extraction_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES source_snapshots(snapshot_id),
        parser_version TEXT NOT NULL, config_json TEXT NOT NULL, config_sha256 TEXT NOT NULL,
        body_sha256 TEXT NOT NULL, footnote_sha256 TEXT,
        outcome TEXT NOT NULL CHECK(outcome='verified_output'))''',
    '''CREATE TABLE structural_nodes (
        node_id TEXT PRIMARY KEY, act_slug TEXT NOT NULL REFERENCES documents(act_slug))''',
    '''CREATE TABLE provision_aliases (
        provision_key TEXT PRIMARY KEY, node_id TEXT NOT NULL REFERENCES structural_nodes(node_id))''',
    '''CREATE TABLE node_versions (
        version_id TEXT PRIMARY KEY, node_id TEXT NOT NULL REFERENCES structural_nodes(node_id),
        extraction_id TEXT NOT NULL REFERENCES extractions(extraction_id),
        parent_version_id TEXT REFERENCES node_versions(version_id),
        sibling_ordinal INTEGER CHECK(sibling_ordinal>=0),
        kind TEXT NOT NULL CHECK(kind IN ('chapter','section','subsection','clause','schedule','table','unknown')),
        display_label TEXT NOT NULL, heading TEXT NOT NULL, body_text TEXT NOT NULL CHECK(length(body_text)>0),
        body_sha256 TEXT NOT NULL, source_anchor_json TEXT NOT NULL,
        pdf_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(snapshot_id),
        pdf_page_from INTEGER NOT NULL CHECK(pdf_page_from>=1),
        pdf_page_to INTEGER NOT NULL CHECK(pdf_page_to>=pdf_page_from),
        CHECK(parent_version_id IS NULL OR (parent_version_id!=version_id AND sibling_ordinal IS NOT NULL)),
        UNIQUE(parent_version_id, sibling_ordinal))''',
    '''CREATE TABLE version_footnotes (
        version_id TEXT PRIMARY KEY REFERENCES node_versions(version_id),
        text TEXT NOT NULL CHECK(length(text)>0), text_sha256 TEXT NOT NULL,
        source_anchor_json TEXT NOT NULL)''',
    '''CREATE TABLE version_admissions (
        admission_id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES node_versions(version_id),
        review_sha256 TEXT NOT NULL, reviewer_sha256 TEXT NOT NULL,
        review_json TEXT NOT NULL, reviewer_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status='admitted'))''',
    '''CREATE TABLE passages (
        passage_id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES node_versions(version_id),
        field TEXT NOT NULL CHECK(field IN ('body','footnote')), strategy_version TEXT NOT NULL,
        char_start INTEGER NOT NULL CHECK(char_start>=0), char_end INTEGER NOT NULL CHECK(char_end>char_start),
        text TEXT NOT NULL, UNIQUE(version_id, field, strategy_version, char_start, char_end))''',
    '''CREATE TABLE current_versions (
        provision_key TEXT PRIMARY KEY REFERENCES provision_aliases(provision_key),
        version_id TEXT NOT NULL REFERENCES node_versions(version_id),
        admission_id TEXT NOT NULL REFERENCES version_admissions(admission_id))''',
    '''CREATE TABLE instrument_relationships (
        relationship_id TEXT PRIMARY KEY, from_act_slug TEXT NOT NULL REFERENCES documents(act_slug),
        to_act_slug TEXT NOT NULL REFERENCES documents(act_slug), relation_type TEXT NOT NULL,
        evidence_snapshot_id TEXT NOT NULL REFERENCES source_snapshots(snapshot_id),
        evidence_anchor_json TEXT NOT NULL CHECK(length(evidence_anchor_json)>2),
        CHECK(from_act_slug!=to_act_slug))''',
    '''CREATE TRIGGER version_scope BEFORE INSERT ON node_versions BEGIN
        SELECT CASE WHEN NOT EXISTS (
          SELECT 1 FROM structural_nodes n JOIN extractions e ON e.extraction_id=NEW.extraction_id
          JOIN source_snapshots s ON s.snapshot_id=e.snapshot_id
          JOIN source_snapshots p ON p.snapshot_id=NEW.pdf_snapshot_id
          WHERE n.node_id=NEW.node_id AND n.act_slug=s.act_slug AND p.act_slug=n.act_slug
          AND p.representation='pdf') THEN RAISE(ABORT,'version document/source mismatch') END;
        SELECT CASE WHEN NEW.parent_version_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM node_versions p WHERE p.version_id=NEW.parent_version_id
          AND p.extraction_id=NEW.extraction_id)
          THEN RAISE(ABORT,'parent must preexist in same extraction') END;
        SELECT CASE WHEN EXISTS (
          WITH RECURSIVE ancestors(version_id,node_id,parent_version_id) AS (
            SELECT version_id,node_id,parent_version_id FROM node_versions WHERE version_id=NEW.parent_version_id
            UNION ALL SELECT p.version_id,p.node_id,p.parent_version_id FROM node_versions p
              JOIN ancestors a ON p.version_id=a.parent_version_id)
          SELECT 1 FROM ancestors WHERE node_id=NEW.node_id)
          THEN RAISE(ABORT,'node cannot be its own ancestor') END;
    END''',
    '''CREATE TRIGGER passage_slice BEFORE INSERT ON passages BEGIN
        SELECT CASE WHEN NEW.char_end > COALESCE((SELECT length(CASE NEW.field
          WHEN 'body' THEN v.body_text ELSE f.text END) FROM node_versions v
          LEFT JOIN version_footnotes f USING(version_id) WHERE v.version_id=NEW.version_id),0)
          OR NEW.text IS NOT (SELECT substr(CASE NEW.field WHEN 'body' THEN v.body_text ELSE f.text END,
          NEW.char_start+1,NEW.char_end-NEW.char_start) FROM node_versions v
          LEFT JOIN version_footnotes f USING(version_id) WHERE v.version_id=NEW.version_id)
          THEN RAISE(ABORT,'passage is not exact source slice') END;
    END''',
    '''CREATE TRIGGER relationship_scope BEFORE INSERT ON instrument_relationships BEGIN
        SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM source_snapshots
          WHERE snapshot_id=NEW.evidence_snapshot_id AND act_slug=NEW.from_act_slug)
          THEN RAISE(ABORT,'relationship evidence must belong to originating instrument') END;
    END''',
]
# Prevent rewriting history (including alias reassignment). Parent versions must
# already exist and cannot change, so a cycle cannot be constructed incrementally.
IMMUTABLE = ('source_blobs', 'source_snapshots', 'extractions', 'structural_nodes',
             'provision_aliases', 'node_versions', 'version_footnotes',
             'version_admissions', 'passages', 'instrument_relationships')
for table in IMMUTABLE:
    for action in ('UPDATE', 'DELETE'):
        DDL.append(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
                   f"BEGIN SELECT RAISE(ABORT,'immutable structural history'); END")
for action in ('INSERT', 'UPDATE'):
    DDL.append(f'''CREATE TRIGGER current_scope_{action.lower()} BEFORE {action} ON current_versions BEGIN
        SELECT CASE WHEN NOT EXISTS (
          SELECT 1 FROM provision_aliases a JOIN node_versions v ON v.node_id=a.node_id
          JOIN version_admissions r ON r.version_id=v.version_id
          WHERE a.provision_key=NEW.provision_key AND v.version_id=NEW.version_id
          AND r.admission_id=NEW.admission_id AND r.status='admitted')
          THEN RAISE(ABORT,'current version/admission/alias mismatch') END;
    END''')


def schema_version(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='structural_schema'").fetchone():
        return 0
    rows = conn.execute('SELECT version FROM structural_schema').fetchall()
    if len(rows) != 1 or rows[0][0] != VERSION:
        raise ValueError('unsupported structural schema version')
    return VERSION


def migrate(conn):
    """Add schema atomically, with a unique on-disk backup before first upgrade.

    Existing rows are deliberately not trusted/backfilled by DDL. The ordinary
    importer revalidates retained evidence and promotes each provision afterward.
    Caller must hold the importer lock. Returns backup path, or None.
    """
    if conn.in_transaction:
        raise ValueError('migration requires an idle connection')
    conn.execute('PRAGMA foreign_keys=ON')
    if schema_version(conn) == VERSION:
        return None
    backup_path = None
    db_path = next(r[2] for r in conn.execute('PRAGMA database_list') if r[1] == 'main')
    if db_path and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='provisions'").fetchone():
        with tempfile.NamedTemporaryFile(prefix=Path(db_path).name + '.pre-structure-v1-', suffix='.sqlite3',
                                         dir=Path(db_path).parent, delete=False) as f:
            backup_path = Path(f.name)
        backup = sqlite3.connect(backup_path)
        try:
            conn.backup(backup)
        finally:
            backup.close()
    try:
        conn.execute('BEGIN IMMEDIATE')
        for statement in DDL:
            conn.execute(statement)
        conn.execute('INSERT INTO structural_schema VALUES (?)', (VERSION,))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return backup_path


def keep(conn, table, row):
    """Insert immutable, content-addressed data or prove identical reuse."""
    cols = list(row)
    existing = conn.execute(f"SELECT {','.join(cols)} FROM {table} WHERE {cols[0]}=?", (row[cols[0]],)).fetchone()
    if existing is not None:
        if tuple(existing) != tuple(row.values()):
            raise ValueError('immutable identity collision in ' + table)
        return row[cols[0]]
    conn.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", tuple(row.values()))
    return row[cols[0]]


def retain_blob(root, raw):
    """Atomically retain bytes by hash; never replace an existing artifact.

    A rolled-back item may leave an unreferenced blob, which is safe. Database
    history never points at a half-written blob or relies on a mutable capture
    filename to retain a past source. Blobs stay private under data/import.
    """
    folder = root / 'data/import/source-blobs'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (sha(raw) + '.body')
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError('retained content-addressed blob is corrupt')
        return
    with tempfile.NamedTemporaryFile(dir=folder, delete=False) as f:
        temporary = Path(f.name)
        try:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.read_bytes() != raw:
                    raise ValueError('retained content-addressed blob is corrupt')
        finally:
            temporary.unlink(missing_ok=True)


def snapshot(conn, root, act_slug, capture, representation, raw):
    meta = json.loads((root / f'data/discovery/{capture}.json').read_text())
    byte_hash = sha(raw)
    if meta['sha256'] != byte_hash:
        raise ValueError('snapshot metadata does not attest these bytes')
    retain_blob(root, raw)
    keep(conn, 'source_blobs', {'sha256': byte_hash, 'byte_count': len(raw)})
    row = dict(act_slug=act_slug, blob_sha256=byte_hash, capture_name=capture,
               representation=representation, source_url=meta.get('effective_url'),
               fetched_at=meta.get('fetched_at_utc'), body_path=meta['body_path'], metadata_json=canonical(meta))
    return keep(conn, 'source_snapshots', {'snapshot_id': identity('snapshot', row), **row})


def promote(conn, root, record, review, reviewer, raw_by_capture, config):
    """Called only after original fidelity checks, inside the item's transaction."""
    if record['admission_status'] != 'admitted' or not record['body_text']:
        raise ValueError('cannot promote an unadmitted provision')
    if review.get('admission_status') != 'admitted':
        raise ValueError('review does not admit this version')
    for field in ('provision_key', 'act_slug', 'section_number', 'heading',
                  'selected_representation', 'extraction_method_version'):
        if record[field] != review[field]:
            raise ValueError('record differs from review')
    body_hash = sha(record['body_text'].encode())
    footnote_hash = sha(record['footnote_text'].encode()) if record['footnote_text'] else None
    expected = review.get('expected_output', {})
    if (body_hash != record['body_text_sha256'] or body_hash != expected.get('body_text_sha256')
        or footnote_hash != record['footnote_text_sha256']
        or (footnote_hash or 'no-footnote-expected') != expected.get('footnote_text_sha256')):
        raise ValueError('output is not the reviewed text')
    for binding in (review['source_representation'], review.get('pdf_anchor', review['source_representation'])):
        if sha(raw_by_capture[binding['capture']]) != binding['sha256']:
            raise ValueError('source does not match review')
    key, act = record['provision_key'], record['act_slug']
    src = review['source_representation']
    anchor = review.get('pdf_anchor', src)
    source_id = snapshot(conn, root, act, src['capture'], review['selected_representation'], raw_by_capture[src['capture']])
    pdf_id = snapshot(conn, root, act, anchor['capture'], 'pdf', raw_by_capture[anchor['capture']])
    extraction = dict(snapshot_id=source_id, parser_version=record['extraction_method_version'],
                      config_json=canonical(config), config_sha256=sha(canonical(config).encode()),
                      body_sha256=record['body_text_sha256'], footnote_sha256=record['footnote_text_sha256'],
                      outcome='verified_output')
    extraction_id = keep(conn, 'extractions', {'extraction_id': identity('extraction', extraction), **extraction})
    alias = conn.execute('SELECT node_id FROM provision_aliases WHERE provision_key=?', (key,)).fetchone()
    if alias:
        node_id = alias[0]
        if conn.execute('SELECT act_slug FROM structural_nodes WHERE node_id=?', (node_id,)).fetchone()[0] != act:
            raise ValueError('cannot reassign provision to a different document')
    else:
        # Bootstrap from an explicitly reviewed public key once; later labels do
        # not recompute identity. Renumbering requires an explicit future mapping.
        node_id = str(uuid.uuid4())
        keep(conn, 'structural_nodes', dict(node_id=node_id, act_slug=act))
        keep(conn, 'provision_aliases', dict(provision_key=key, node_id=node_id))
    version = dict(node_id=node_id, extraction_id=extraction_id, parent_version_id=None,
                   sibling_ordinal=None, kind='section', display_label=record['section_number'],
                   heading=record['heading'], body_text=record['body_text'], body_sha256=record['body_text_sha256'],
                   source_anchor_json=canonical(src), pdf_snapshot_id=pdf_id,
                   pdf_page_from=record['pdf_page_from'], pdf_page_to=record['pdf_page_to'])
    version_id = keep(conn, 'node_versions', {'version_id': identity('version', version), **version})
    profile = config.get('structure_profile')
    if profile is not None:
        try:
            from scripts.clause_structure import parse
        except ModuleNotFoundError:
            from clause_structure import parse
        if profile.get('provision_key') != key:
            raise ValueError('boundary review belongs to a different provision')
        children = parse(record['body_text'], profile, src['sha256'])
        parents = {None: version_id}
        for child in children:
            existing_child = conn.execute('SELECT node_id FROM node_versions WHERE parent_version_id=? '
                                          'AND sibling_ordinal=?', (parents[child['parent']],child['ordinal'])).fetchone()
            child_node_id = (existing_child[0] if existing_child else
                             str(uuid.uuid5(uuid.UUID(node_id), version_id + ':' + child['path'])))
            keep(conn, 'structural_nodes', dict(node_id=child_node_id, act_slug=act))
            child_version = dict(node_id=child_node_id,extraction_id=extraction_id,
                parent_version_id=parents[child['parent']],sibling_ordinal=child['ordinal'],
                kind=child['kind'],display_label='(' + child['path'].split('/')[-1] + ')',heading='',
                body_text=child['text'],body_sha256=sha(child['text'].encode()),
                source_anchor_json=canonical(dict(root_version_id=version_id,
                    start=child['start'],end=child['end'],offset_unit='unicode_code_points',
                    mandatory_context_version_id=version_id,profile_sha256=sha(canonical(profile).encode()))),
                pdf_snapshot_id=pdf_id,pdf_page_from=record['pdf_page_from'],pdf_page_to=record['pdf_page_to'])
            child_version_id = keep(conn, 'node_versions', {'version_id': identity('version',child_version), **child_version})
            parents[child['path']] = child_version_id
    if record['footnote_text']:
        keep(conn, 'version_footnotes', dict(version_id=version_id, text=record['footnote_text'],
             text_sha256=record['footnote_text_sha256'], source_anchor_json=canonical(anchor)))
    review_json, reviewer_json = canonical(review), canonical(reviewer)
    admission = dict(version_id=version_id, review_sha256=sha(review_json.encode()),
                     reviewer_sha256=sha(reviewer_json.encode()), review_json=review_json,
                     reviewer_json=reviewer_json, status='admitted')
    admission_id = keep(conn, 'version_admissions', {'admission_id': identity('admission', admission), **admission})
    for field, text in [('body', record['body_text']), ('footnote', record['footnote_text'])]:
        if text:
            passage = dict(version_id=version_id, field=field, strategy_version=PASSAGE_STRATEGY,
                           char_start=0, char_end=len(text), text=text)
            keep(conn, 'passages', {'passage_id': identity('passage', passage), **passage})
    conn.execute('INSERT INTO current_versions VALUES (?,?,?) ON CONFLICT(provision_key) DO UPDATE '
                 'SET version_id=excluded.version_id, admission_id=excluded.admission_id',
                 (key, version_id, admission_id))


def current_text(conn, projection, review, reviewer, reviewer_canonical=None):
    """Read structural text and prove agreement with live review and projection.

    The caller ALSO performs existing source-byte, conflict, anchor and scope
    verification. Missing/stale structures never fall back to legacy text.
    """
    row = conn.execute('''SELECT v.*, n.act_slug, e.parser_version, e.body_sha256 AS output_hash,
        e.footnote_sha256 AS output_footnote_hash, s.capture_name, s.blob_sha256, s.representation,
        s.act_slug AS source_act, p.capture_name AS pdf_capture, p.blob_sha256 AS pdf_hash,
        p.act_slug AS pdf_act, p.representation AS pdf_kind,
        f.text AS footnote_text, f.text_sha256 AS footnote_hash,
        a.node_id AS alias_node, r.review_json, r.reviewer_json, r.status AS review_status,
        r.version_id AS admitted_version
        FROM current_versions c JOIN node_versions v USING(version_id)
        JOIN structural_nodes n ON n.node_id=v.node_id
        JOIN provision_aliases a ON a.provision_key=c.provision_key
        JOIN extractions e ON e.extraction_id=v.extraction_id
        JOIN source_snapshots s ON s.snapshot_id=e.snapshot_id
        JOIN source_snapshots p ON p.snapshot_id=v.pdf_snapshot_id
        JOIN version_admissions r ON r.admission_id=c.admission_id
        LEFT JOIN version_footnotes f ON f.version_id=v.version_id
        WHERE c.provision_key=?''', (projection['provision_key'],)).fetchone()
    if row is None:
        raise ValueError('no current structural version')
    v = dict(row)
    matches = {
        'act_slug': 'act_slug', 'display_label': 'section_number', 'heading': 'heading',
        'body_text': 'body_text', 'body_sha256': 'body_text_sha256',
        'footnote_text': 'footnote_text', 'footnote_hash': 'footnote_text_sha256',
        'parser_version': 'extraction_method_version', 'capture_name': 'source_capture',
        'blob_sha256': 'source_sha256_actual', 'representation': 'selected_representation',
        'pdf_capture': 'pdf_capture', 'pdf_page_from': 'pdf_page_from', 'pdf_page_to': 'pdf_page_to'}
    if any(v[a] != projection[b] for a, b in matches.items()):
        raise ValueError('structural/projection disagreement')
    # The caller may pass the reviewer's canonical form when it has already
    # computed it for this snapshot; it is the same function of the same dict.
    if reviewer_canonical is None:
        reviewer_canonical = canonical(reviewer)
    if (v['review_json'] != canonical(review) or v['reviewer_json'] != reviewer_canonical
        or v['review_status'] != 'admitted' or v['admitted_version'] != v['version_id']
        or v['alias_node'] != v['node_id'] or v['source_act'] != v['act_slug']
        or v['pdf_act'] != v['act_slug'] or v['pdf_kind'] != 'pdf'
        or v['source_anchor_json'] != canonical(review['source_representation'])
        or v['pdf_hash'] != review.get('pdf_anchor', review['source_representation'])['sha256']
        or v['output_hash'] != v['body_sha256'] or v['output_footnote_hash'] != v['footnote_hash']):
        raise ValueError('structural review/source binding mismatch')
    for field, text in [('body', v['body_text']), ('footnote', v['footnote_text'])]:
        if text:
            rows = conn.execute('SELECT char_start,char_end,text FROM passages WHERE version_id=? '
                                'AND field=? AND strategy_version=?', (v['version_id'], field, PASSAGE_STRATEGY)).fetchall()
            if [tuple(p) for p in rows] != [(0, len(text), text)]:
                raise ValueError('missing or inconsistent whole-provision passage')
    return v['body_text'], v['footnote_text']
