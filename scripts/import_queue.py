"""Conservative offline checkpoints, never a substitute for review admission.

All retained inputs invalidate together; outputs are bound per provision so a
completed item survives an interruption while another item is being imported.
"""
import json
import locale
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

try:
    from scripts import structural_store as ss
except ModuleNotFoundError:
    import structural_store as ss

SCHEMA = '''
CREATE TABLE IF NOT EXISTS import_queue_schema (version INTEGER PRIMARY KEY CHECK(version=1));
INSERT OR IGNORE INTO import_queue_schema VALUES(1);
CREATE TABLE IF NOT EXISTS import_jobs (
    provision_key TEXT PRIMARY KEY,
    input_fingerprint TEXT,
    output_fingerprint TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','quarantined','failed','removed')),
    last_attempt_id INTEGER REFERENCES import_attempts(attempt_id)
);
'''


def input_fingerprint(root, manifest, reviews, conflicts, overrides=None):
    """Hash bytes afresh, never mtime/size. Unavailable dependencies disable reuse.

    Intentionally global/coarse for this small corpus. Includes excluded conflict
    observations and reviewer files, not merely the chosen representation.
    """
    files = {}
    folders = [(root / 'data/discovery', {'.json', '.body'}),
               (root / 'data/review', {'.json', '.jsonl'}),
               (Path(__file__).resolve().parent, {'.py'}),
               (Path(__file__).resolve().parent.parent / 'lawindex', {'.py'})]
    for index, (folder, extensions) in enumerate(folders):
        for path in sorted(folder.rglob('*')):
            if path.is_file() and path.suffix in extensions and '__pycache__' not in path.parts:
                files[f'{index}/{path.relative_to(folder)}'] = ss.sha(path.read_bytes())
    # Follow explicit dependencies as well as conventional directories. A
    # reviewer or capture body moved elsewhere must not escape invalidation.
    dependencies = {}
    names = set()
    for review in reviews.values():
        ref = review['review']['reviewer_ref']
        dependencies['reviewer:' + ref] = ss.sha((root / ref).read_bytes())
        names.add(review['source_representation']['capture'])
        if review.get('pdf_anchor'):
            names.add(review['pdf_anchor']['capture'])
    for conflict in conflicts.values():
        names.update(o['capture'] for o in conflict.get('observations', []) if 'capture' in o)
    for name in sorted(names):
        meta = json.loads((root / f'data/discovery/{name}.json').read_text())
        dependencies['capture:' + name] = ss.sha((root / meta['body_path']).read_bytes())
    executable = shutil.which('pdftotext')
    if not executable:
        raise OSError('pdftotext unavailable; checkpoint disabled')
    version = subprocess.run([executable, '-v'], capture_output=True, timeout=5, check=True)
    payload = dict(files=files, dependencies=dependencies, manifest=manifest, reviews=reviews, conflicts=conflicts,
                   overrides={n:ss.sha(b) for n,b in (overrides or {}).items()},
                   pdf_tool_hash=ss.sha(Path(executable).read_bytes()),
                   pdf_tool_version=ss.sha(version.stdout + version.stderr), python=sys.version,
                   sqlite=sqlite3.sqlite_version, encoding=locale.getencoding(),
                   locale={k:os.environ.get(k) for k in ('LANG','LC_ALL','LC_CTYPE')})
    return ss.identity('inputs-v1', payload)


def output_fingerprint(conn, root, key):
    """Bind current graph, compatibility projection, and retained blob bytes."""
    current = conn.execute('SELECT version_id,admission_id FROM current_versions WHERE provision_key=?', (key,)).fetchone()
    if not current:
        return None
    version, admission = current
    queries = [
        ('provision', 'SELECT * FROM provisions WHERE provision_key=?', (key,)),
        ('review', 'SELECT * FROM review_decisions WHERE provision_key=?', (key,)),
        ('excerpt', 'SELECT * FROM excerpts WHERE provision_key=? ORDER BY excerpt_key', (key,)),
        ('document', 'SELECT d.* FROM documents d JOIN provisions p USING(act_slug) WHERE p.provision_key=?', (key,)),
        ('current', 'SELECT * FROM current_versions WHERE provision_key=?', (key,)),
        ('alias', 'SELECT * FROM provision_aliases WHERE provision_key=?', (key,)),
        ('node', 'SELECT n.* FROM structural_nodes n JOIN node_versions v USING(node_id) WHERE v.version_id=?', (version,)),
        ('version', 'SELECT * FROM node_versions WHERE version_id=?', (version,)),
        ('footnotes', 'SELECT * FROM version_footnotes WHERE version_id=?', (version,)),
        ('admission', 'SELECT * FROM version_admissions WHERE admission_id=?', (admission,)),
        ('passages', 'SELECT * FROM passages WHERE version_id=? ORDER BY passage_id', (version,)),
        ('extraction', 'SELECT e.* FROM extractions e JOIN node_versions v USING(extraction_id) WHERE v.version_id=?', (version,)),
        ('hierarchy', '''SELECT child.* FROM node_versions child JOIN node_versions root
            ON child.extraction_id=root.extraction_id WHERE root.version_id=? ORDER BY child.version_id''', (version,)),
        ('hierarchy_nodes', '''SELECT DISTINCT n.* FROM structural_nodes n JOIN node_versions child USING(node_id)
            JOIN node_versions root ON child.extraction_id=root.extraction_id
            WHERE root.version_id=? ORDER BY n.node_id''', (version,)),
        ('snapshots', '''SELECT s.* FROM source_snapshots s WHERE snapshot_id IN (
            SELECT pdf_snapshot_id FROM node_versions WHERE version_id=? UNION
            SELECT e.snapshot_id FROM extractions e JOIN node_versions v USING(extraction_id) WHERE v.version_id=?)
            ORDER BY snapshot_id''', (version,version)),
    ]
    payload = {label:[list(r) for r in conn.execute(sql,args)] for label,sql,args in queries}
    if not payload['provision'] or conn.execute('SELECT admission_status FROM provisions WHERE provision_key=?',(key,)).fetchone()[0] != 'admitted':
        return None
    blobs = conn.execute('''SELECT DISTINCT b.sha256,b.byte_count FROM source_blobs b
        JOIN source_snapshots s ON s.blob_sha256=b.sha256 WHERE s.snapshot_id IN (
          SELECT pdf_snapshot_id FROM node_versions WHERE version_id=? UNION
          SELECT e.snapshot_id FROM extractions e JOIN node_versions v USING(extraction_id) WHERE v.version_id=?)
        ORDER BY b.sha256''',(version,version)).fetchall()
    payload['blobs'] = []
    for byte_hash, size in blobs:
        raw = (root / 'data/import/source-blobs' / (byte_hash + '.body')).read_bytes()
        if ss.sha(raw) != byte_hash or len(raw) != size:
            return None
        payload['blobs'].append([byte_hash,size])
    return ss.identity('outputs-v1',payload)


def reusable(conn, root, key, fingerprint):
    if fingerprint is None:
        return False
    row = conn.execute('''SELECT j.output_fingerprint FROM import_jobs j JOIN import_attempts a
        ON a.attempt_id=j.last_attempt_id AND a.provision_key=j.provision_key
        WHERE j.provision_key=? AND j.status='succeeded' AND a.status='succeeded'
        AND a.admission_status='admitted' AND j.input_fingerprint=?''', (key,fingerprint)).fetchone()
    if not row or not row[0]:
        return False
    try:
        return row[0] == output_fingerprint(conn,root,key)
    except (OSError, ValueError, KeyError):
        return False


def finish(conn, root, key, status, attempt_id, fingerprint):
    output = output_fingerprint(conn,root,key) if status == 'succeeded' else None
    conn.execute('''UPDATE import_jobs SET status=?,last_attempt_id=?,input_fingerprint=?,output_fingerprint=?
        WHERE provision_key=?''',(status,attempt_id,fingerprint,output,key))
