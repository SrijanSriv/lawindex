#!/usr/bin/env python3
"""Ingestion-manifest migration: corpus-manifest records for the Phase 3 Acts.

The Phase 0 manifest records were transcribed by hand from rendered Act
Details pages. The Phase 3 Acts instead have hash-bound HTTP item captures,
so their records are derived from those captures rather than re-transcribed:
every field below is read out of the retained bytes, and a field the API
never supplied is recorded as null instead of being invented.

Two consequences are recorded explicitly rather than smoothed over:

  * `enact_date_raw` keeps each source's own string. The Act Details pages
    print DD-MM-YYYY; the item API returns YYYY-MM-DD. Every record now
    carries `enact_date_raw_format` so no consumer can assume one of them.
  * `last_modified_display` is a rendered-page field with no API equivalent,
    so it is null for these Acts, and `source_stated_modified_date` in search
    shows "Not stated" rather than a guess.

This module writes nothing; build_phase0_artifacts.py composes the manifest.
"""
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from scripts.acquire_phase3 import DEST, sha, verify_acquisition  # noqa: E402

BASE = 'https://indiacode.gov.in'
PHASE3_DATE_FORMAT = 'YYYY-MM-DD'
PHASE0_DATE_FORMAT = 'DD-MM-YYYY'


def one(metadata, name, optional=False):
    values = metadata.get(name, [])
    if not values:
        if optional:
            return None
        raise ValueError('missing item field: ' + name)
    if len(values) != 1 or not isinstance(values[0]['value'], str):
        raise ValueError('ambiguous item field: ' + name)
    return values[0]['value'].strip() or None


def english_pdf(act):
    """Same explicit rule the candidate extractor uses: exactly one English PDF."""
    english = [pdf for pdf in act.get('pdfs', []) if not pdf['name'].lower().startswith('h')]
    if len(english) != 1:
        raise ValueError('English PDF identity requires explicit review: ' + act['slug'])
    return english[0]


def pdf_pages(sha256):
    blob = DEST / 'blobs' / (sha256 + '.body')
    raw = blob.read_bytes()
    if sha(raw) != sha256:
        raise ValueError('retained PDF blob does not match its recorded hash')
    info = subprocess.run(['pdfinfo', str(blob)], check=True, capture_output=True, text=True).stdout
    return int(re.search(r'^Pages:\s+(\d+)', info, re.M)[1])


def record_for(slug, inventory_by_slug, root=ROOT):
    act = json.loads((DEST / 'acts' / (slug + '.json')).read_text())
    if act['status'] != 'captured_review_pending':
        raise ValueError(f'{slug}: acquisition is {act["status"]}, not a manifest candidate')
    verify_acquisition(act)
    item = act['item']
    metadata = item['metadata']
    act_id = one(metadata, 'dc.identifier.act_id')
    pdf = english_pdf(act)
    proposed = inventory_by_slug.get(slug, {})
    return {
        'slug': slug,
        'uuid': item['uuid'],
        'title': one(metadata, 'dc.title'),
        'act_number': one(metadata, 'dc.identifier.act_number', optional=True),
        'year': one(metadata, 'dc.date.act_year', optional=True),
        'enact_date_raw': one(metadata, 'dc.date.enact_date', optional=True),
        'enact_date_raw_format': PHASE3_DATE_FORMAT,
        'enforcement_date_raw': one(metadata, 'dc.date.enforcement_date', optional=True),
        # The rendered Act Details "last modified" line has no item-API
        # equivalent; null means not observed, never "unchanged".
        'last_modified_display': None,
        'ministry': one(metadata, 'dc.identifier.ministry_name', optional=True),
        'department': one(metadata, 'dc.identifier.department_name', optional=True),
        'type': one(metadata, 'dc.type', optional=True),
        'long_title_present': bool(one(metadata, 'dc.identifier.preamble_description', optional=True)),
        'notification_present': None,
        'act_id': act_id,
        'bitstream_uuid': pdf['uuid'],
        'filename': pdf['name'],
        'section_count_observed': act['section_count'],
        'linked_counts': None,
        'rationale': proposed.get('selection_reason'),
        'source_url': f"{BASE}/act/{item['uuid']}",
        'metadata_url': f"{BASE}/act/{item['uuid']}/details",
        'sections_url': f"{BASE}/act/{item['uuid']}/sections?" + urlencode({
            'f.identifier_collection': 'SECTION,equals', 'f.act_id': act_id + ',equals',
            'spc.sf': 'dc.identifier.order_number', 'spc.sd': 'ASC'}),
        'pdf_viewer_url': f"{BASE}/pdf-viewer/{item['uuid']}/{pdf['uuid']}",
        'jurisdiction_observed': one(metadata, 'dc.identifier.state_name', optional=True) or 'CENTRAL',
        'collection_observed': one(metadata, 'dc.identifier.collection', optional=True) or 'ACT',
        'target_language': 'en',
        'language_basis': 'English item metadata and the single English PDF of the retained capture; PDF text compared per provision at candidate extraction.',
        'scope_status': 'phase1_candidate',
        'ingestion_status': 'not_imported',
        'full_text_review_status': 'pending',
        'ready_for_public_index': False,
        'extraction_plan': 'Structured section HTML and the retained PDF are distinct representations; whole-body agreement produces review candidates only, and admission requires a recorded review (individual or Act-sampled).',
        'known_issues': [],
        'retained_pdf': {'capture': f'phase3-{slug}-pdf', 'sha256': pdf['sha256'],
                         'pages': pdf_pages(pdf['sha256']),
                         'capture_materialized_on_admission': True},
        'record_basis': 'derived_from_phase3_item_capture',
        'record_evidence': f'data/phase3/acquisition/acts/{slug}.json',
    }


def phase3_records(existing_slugs, root=ROOT):
    """Manifest records for captured Phase 3 Acts not already in the manifest."""
    inventory = json.loads((root / 'data/phase3/inventory.v1.json').read_text())
    by_slug = {r['slug']: r for r in inventory['records']}
    records = []
    for path in sorted((DEST / 'acts').glob('*.json')):
        slug = path.stem
        if slug in existing_slugs or slug not in by_slug:
            continue
        records.append(record_for(slug, by_slug, root))
    return records


if __name__ == '__main__':
    manifest = json.loads((ROOT / 'data/discovery/corpus-manifest.json').read_text())['records']
    for record in phase3_records({m['slug'] for m in manifest}):
        print(record['slug'], '|', record['title'], '|', record['act_number'], 'of', record['year'],
              '|', record['section_count_observed'], 'sections |', record['ministry'])
