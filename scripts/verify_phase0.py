#!/usr/bin/env python3
"""Verify Phase 0 evidence and cross-file references without fetching sources."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/discovery'


def main():
    # Later phases materialize their own captures into data/discovery. This
    # script verifies the Phase 0 evidence, so it checks every capture's
    # bytes but asserts counts only over the original Phase 0 set.
    captures = json.loads((DATA / 'capture-index.json').read_text())
    assert len({x['capture'] for x in captures}) == len(captures)
    for record in captures:
        raw = (ROOT / record['body_path']).read_bytes()
        assert len(raw) == record['bytes'], record['capture']
        assert hashlib.sha256(raw).hexdigest() == record['sha256'], record['capture']
    by_capture = {x['capture']:x for x in captures}
    phase0_captures = [x for x in captures if not x['capture'].startswith('phase3-')]
    assert len(phase0_captures) == 16, len(phase0_captures)

    manifest = json.loads((DATA / 'corpus-manifest.json').read_text())['records']
    by_slug = {x['slug']:x for x in manifest}
    assert len(by_slug) == len(manifest) == 22
    phase0_records = [x for x in manifest if x.get('record_basis') != 'derived_from_phase3_item_capture']
    phase3_records = [x for x in manifest if x.get('record_basis') == 'derived_from_phase3_item_capture']
    assert len(phase0_records) == 12 and len(phase3_records) == 10
    assert sum(x['scope_status']=='phase1_candidate' for x in phase0_records)==10
    assert sum(x['scope_status']=='quarantine_fixture' for x in manifest)==2
    assert all(x['scope_status']=='phase1_candidate' for x in phase3_records)
    assert all(x['ready_for_public_index'] is False for x in manifest)
    for record in manifest:
        assert record['source_url'].startswith('https://indiacode.gov.in/')
        # Mixed date provenance must stay labelled, never silently merged.
        if record.get('enact_date_raw'):
            fmt = record['enact_date_raw_format']
            pattern = r'\d{2}-\d{2}-\d{4}' if fmt == 'DD-MM-YYYY' else r'\d{4}-\d{2}-\d{2}'
            assert re.fullmatch(pattern, record['enact_date_raw']), (record['slug'], record['enact_date_raw'])
        if record.get('retained_pdf'):
            pdf = record['retained_pdf']
            if pdf.get('capture_materialized_on_admission') and pdf['capture'] not in by_capture:
                continue  # Phase 3 capture not yet copied in; the blob is hash-checked at admission.
            assert pdf['sha256'] == by_capture[pdf['capture']]['sha256']
    queries = [json.loads(line) for line in (DATA/'seed-queries.jsonl').read_text().splitlines()]
    assert len(queries)==24 and len({x['id'] for x in queries})==24
    assert all(x['judgment_status']=='unjudged' for x in queries)
    assert all(x['split']=='development_smoke' for x in queries)
    for query in queries:
        for target in query['candidate_targets']:
            assert target['document_slug'] in by_slug, query['id']
    report = json.loads((DATA / 'pdf-report.json').read_text())
    phase0_report = [x for x in report if not x['slug'].startswith('phase3-')]
    assert len(phase0_report)==5 and sum(x['pages'] for x in phase0_report)==173
    for pdf in report:
        assert hashlib.sha256((ROOT/pdf['text_path']).read_bytes()).hexdigest()==pdf['text_sha256']
        assert len(pdf['characters_by_page'])==pdf['pages']
    # These captures intentionally demonstrate failure/shell states. They are not documents.
    assert by_capture['current-robots']['http_status']==502
    assert by_capture['legacy-robots']['http_status']==404
    assert len({by_capture[x]['sha256'] for x in ['current-home','terms','copyright','central-collection-page']})==1
    print(f'PASS: 16 original Phase 0 hashes (of {len(captures)} captures), 5 Phase 0 PDF/text reports, '
          f'22 manifest records (12 Phase 0 observations + 10 derived from Phase 3 item captures), '
          '24 unjudged queries, and failure/shell fixtures.')


if __name__ == '__main__':
    main()
