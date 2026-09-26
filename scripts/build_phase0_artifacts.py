#!/usr/bin/env python3
"""Rebuild Phase 0 derived reports from retained evidence. Makes no network requests."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
import sys
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/discovery'
DOCS = ROOT / 'docs/phase-0'
BASE = 'https://indiacode.gov.in'
sys.path.insert(0, str(ROOT))
from scripts.ingestion_manifest import phase3_records  # noqa: E402


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def main():
    captures = []
    for path in sorted(DATA.glob('*.json')):
        record = json.loads(path.read_text())
        if 'body_path' not in record:
            continue
        raw = (ROOT / record['body_path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record['sha256'], path
        assert len(raw) == record['bytes'], path
        captures.append({'capture':path.stem, **record})
    write_json(DATA / 'capture-index.json', captures)

    pdfs = []
    for capture in captures:
        if 'application/pdf' not in (capture['content_type'] or ''):
            continue
        src = ROOT / capture['body_path']
        assert src.read_bytes().startswith(b'%PDF-'), src
        assert capture['http_status'] == 200 and capture['curl_exit_code'] == 0, src
        slug = capture['capture'].removesuffix('-pdf')
        out = DATA / 'derived' / (slug + '.txt')
        subprocess.run(['pdftotext', '-layout', str(src), str(out)], check=True)
        info = subprocess.run(['pdfinfo', str(src)], check=True, capture_output=True, text=True).stdout
        (DATA / 'derived' / (slug + '-pdfinfo.txt')).write_text(info)
        count = int(re.search(r'^Pages:\s+(\d+)', info, re.M)[1])
        content = out.read_text()
        pages = content.split('\f')
        if pages[-1].strip() == '':
            pages.pop()
        assert len(pages) == count, slug
        pdfs.append({'slug':slug, 'pages':count, 'extracted_characters':len(content),
                     'characters_by_page':[len(p.strip()) for p in pages],
                     'source_sha256':capture['sha256'],
                     'text_path':str(out.relative_to(ROOT)),
                     'text_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
                     'classification':'scan_with_existing_ocr' if slug == 'rti-rules-2012' else 'text_pdf',
                     'classification_basis':'PDF metadata, extracted text; RTI and RTI Rules also visually inspected.',
                     'review':'Extraction diagnostics only, not a whole-document legal-fidelity certification.'})
    write_json(DATA / 'pdf-report.json', pdfs)

    observations = json.loads((DATA / 'observations/acts.json').read_text())['records']
    assert len(observations) == 11
    assert len({x['uuid'] for x in observations}) == 11
    manifest = []
    for item in observations:
        slug = item['slug']
        record = dict(item)
        record.update({
            'enact_date_raw_format':'DD-MM-YYYY',
            'source_url':f"{BASE}/act/{item['uuid']}",
            'metadata_url':f"{BASE}/act/{item['uuid']}/details",
            'sections_url':f"{BASE}/act/{item['uuid']}/sections?" + urlencode({
                'f.identifier_collection':'SECTION,equals', 'f.act_id':item['act_id']+',equals',
                'spc.sf':'dc.identifier.order_number','spc.sd':'ASC'}),
            'pdf_viewer_url':f"{BASE}/pdf-viewer/{item['uuid']}/{item['bitstream_uuid']}",
            'jurisdiction_observed':'CENTRAL', 'collection_observed':'ACT',
            'target_language':'en', 'language_basis':'English rendered metadata; PDF text inspected only where retained.',
            'scope_status':'quarantine_fixture' if slug == 'kerala-name-2026' else 'phase1_candidate',
            'ingestion_status':'not_imported', 'full_text_review_status':'pending',
            'ready_for_public_index':False,
            'extraction_plan':'Obtain authorized source snapshot; preserve structured section HTML and PDF as distinct representations; verify agreement and page mapping before indexing. On disagreement, hold provision for reviewed PDF extraction.',
            'known_issues':[],
        })
        if slug == 'rti-2005':
            record['known_issues'] = ['RTI-001: section 8(1)(j) structured/PDF conflict', 'RTI-002: source page numbers differ from linked PDF']
        if slug == 'kerala-name-2026':
            record['known_issues'] = ['KERALA-001: collection/date metadata conflict; excluded from first searchable corpus']
        pdf = next((p for p in pdfs if p['slug'] == slug), None)
        record['retained_pdf'] = {'capture':slug+'-pdf','sha256':pdf['source_sha256'],'pages':pdf['pages']} if pdf else None
        manifest.append(record)
    manifest.append({
        'slug':'rti-rules-2012','title':'RTI Rules, 2012','uuid':'4ae1e247-787e-4e6d-a6de-a5f0f5943431',
        'source_url':BASE+'/items/4ae1e247-787e-4e6d-a6de-a5f0f5943431',
        'pdf_viewer_url':BASE+'/pdf-viewer/4ae1e247-787e-4e6d-a6de-a5f0f5943431/538b3925-cbee-41f4-bd95-c7ca0c9f0003',
        'bitstream_uuid':'538b3925-cbee-41f4-bd95-c7ca0c9f0003',
        'filename':'RTIRules_2012_English_0.pdf','parent_slug':'rti-2005',
        'collection_observed':'RULE','jurisdiction_observed':'CENTRAL','published_date_raw':'31-07-2012',
        'parent_act_year_raw':'2005','parent_act_number_raw':'22','last_modified_display':'08-05-2018',
        'scope_status':'quarantine_fixture','ready_for_public_index':False,'ingestion_status':'not_imported',
        'known_issues':['OCR-001: scanned PDF with existing but defective OCR; parent Act year is not rule publication year'],
        'retained_pdf':{'capture':'rti-rules-2012-pdf','sha256':next(p['source_sha256'] for p in pdfs if p['slug']=='rti-rules-2012'),'pages':4},
        'extraction_plan':'Retain linked-instrument metadata; defer searchable rule text until OCR and structure are reviewed.'
    })
    # Ingestion-manifest migration: the Phase 3 Acts are appended from their
    # hash-bound item captures, so this stays the single writer of the
    # corpus manifest and the file is always complete after one run.
    phase0_count = len(manifest)
    manifest += phase3_records({m['slug'] for m in manifest})
    write_json(DATA / 'corpus-manifest.json', {
        'schema_version':2, 'observed_on':'2026-09-20',
        'scope':'20 candidate central Acts in English; 2 additional quarantine fixtures',
        'record_sources':{
            'phase0_rendered_page_observations':'Manually transcribed from rendered Act Details pages on 2026-09-20; enact_date_raw is DD-MM-YYYY.',
            'derived_from_phase3_item_capture':'Derived on 2026-09-22 from retained, hash-bound Phase 3 item captures; enact_date_raw is YYYY-MM-DD and last_modified_display is null because the item API does not supply it.'},
        'date_format_warning':'enact_date_raw keeps each source\'s own string; read enact_date_raw_format before parsing.',
        'source_access_status':'User reports ministry permission for up to 20 chosen Acts, personal non-commercial use; see data/phase3/access-authorization.json. Original grant not independently inspected.',
        'records':manifest})

    item = json.loads((DATA / 'rti-item.body').read_text())
    result = json.loads((DATA / 'rti-sections-page-0.body').read_text())['_embedded']['searchResult']
    sections = [x['_embedded']['indexableObject'] for x in result['_embedded']['objects']]
    assert result['page'] == {'number':0,'size':10,'totalPages':4,'totalElements':31}
    assert len(sections) == 10
    assert all(x['metadata']['dc.identifier.act_id'][0]['value'] == item['metadata']['dc.identifier.act_id'][0]['value'] for x in sections)
    # Preserve a small, exact structured-section fixture for a future parser regression.
    section6 = next(x for x in sections if x['metadata']['dc.identifier.section_number'][0]['value']=='6')
    write_json(DATA / 'derived/rti-section-6.json', section6)
    section8 = next(x for x in sections if x['metadata']['dc.identifier.section_number'][0]['value']=='8')
    html8 = section8['metadata']['dc.identifier.section_page_note'][0]['value']
    pdftext = (DATA / 'derived/rti-2005.txt').read_text()
    assert 'has no relationship to any public activity or interest' in html8
    assert 'has no relationship to any public activity or interest' not in pdftext
    assert 'information which relates to personal information;' in pdftext
    assert section6['metadata']['dc.identifier.page_number'][0]['value']=='7'
    assert '6. Request for obtaining information' in pdftext.split('\f')[8]
    findings = {
        'rti_item_uuid':item['uuid'],'rti_handle':item['handle'],
        'rti_transport_last_modified':item['lastModified'],
        'rti_display_last_modified':item['metadata']['dc.date.last_modified'][0]['value'],
        'section_page':result['page'],
        'metadata_key_union':sorted(set(item['metadata']).union(*(set(x['metadata']) for x in sections))),
        'observed_structured_language_values':sorted({str(v.get('language')) for x in [item]+sections for values in x['metadata'].values() for v in values}),
        'confirmed_findings':['RTI-001','RTI-002'],
        'all_missing_values_remain_unknown':True,
    }
    write_json(DATA / 'structured-report.json', findings)
    candidates = sum(m['scope_status'] == 'phase1_candidate' for m in manifest)
    fixtures = sum(m['scope_status'] == 'quarantine_fixture' for m in manifest)
    print(f'Verified {len(captures)} capture hashes; analyzed {len(pdfs)} PDFs; built {len(manifest)} manifest entries '
          f'({candidates} candidates, {fixtures} quarantine fixtures; {phase0_count} from Phase 0 observations, '
          f'{len(manifest) - phase0_count} derived from Phase 3 item captures).')
    print('Verified 10 section records, parent relationships, pagination, and the two retained RTI discrepancy fixtures. No network requests made.')


if __name__ == '__main__':
    main()
