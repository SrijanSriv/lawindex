#!/usr/bin/env python3
"""Turn a passing sampled-review plan into per-provision review records.

One record per aligned candidate, each carrying its own expected-output
digests, the plan it was authorized by, and whether this particular
provision was visually reviewed. Existing review records are never
overwritten: an individually reviewed provision keeps its stronger record.

Every record is verified through the canonical importer's own
build_provision_record before anything is written, so a record that would
not admit is never created. This writes no database; run the importer after.
"""
import argparse
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from scripts.acquire_phase3 import DEST, atomic_json, verify_acquisition  # noqa: E402
from scripts import offline_importer as oi  # noqa: E402
from scripts.sample_review_plan import load_plan, plan_digest, plan_path  # noqa: E402
from scripts.sampled_agreement import CHECKED_SCOPE, REVIEW_CLASS, VERSION  # noqa: E402

DISCOVERY = ROOT / 'data/discovery'
REVIEW = ROOT / 'data/review'


def receipts():
    return [json.loads(Path(f).read_text()) for f in glob.glob(str(DEST / 'receipts/*.json'))]


def materialize(name, receipt, content_type, root=ROOT, act_slug=None):
    """Copy retained Phase 3 bytes into data/discovery as a named capture.

    Not a new acquisition: the bytes, URL, status and fetch time all come
    from the retained receipt, and an existing capture must match exactly.
    """
    blob = DEST / 'blobs' / (receipt['sha256'] + '.body')
    raw = blob.read_bytes()
    if oi.sha256_bytes(raw) != receipt['sha256']:
        raise ValueError('retained blob does not match its receipt')
    body_path = root / 'data/discovery' / (name + '.body')
    meta_path = root / 'data/discovery' / (name + '.json')
    if body_path.exists():
        if oi.sha256_bytes(body_path.read_bytes()) != receipt['sha256']:
            raise ValueError(f'existing capture {name} holds different bytes')
        return name
    full = next((r for r in receipts() if r['url'] == receipt['url']
                 and r['sha256'] == receipt['sha256'] and r['status'] == 200), None)
    if full is None:
        raise ValueError('no retained receipt with a fetch time for ' + receipt['url'])
    body_path.write_bytes(raw)
    atomic_json(meta_path, dict(
        requested_url=receipt['url'], effective_url=receipt['url'], http_status=receipt['status'],
        curl_exit_code=receipt['curl_exit'], content_type=content_type,
        fetched_at_utc=full['fetched_at'], sha256=receipt['sha256'], bytes=len(raw),
        body_path=str(body_path.relative_to(root)),
        note=('Exact copy of retained Phase 3 HTTP bytes; not a new acquisition. Receipt in '
              'data/phase3/acquisition/acts/' + act_slug + '.json')))
    return name


def build_records(slug, root=ROOT):
    plan = load_plan(slug, root)
    if plan.get('status') != 'reviewed' or not plan.get('review'):
        raise ValueError('plan has no recorded review')
    if plan['review']['decision'] != 'act_batch_admitted':
        raise ValueError('sample review rejected this Act batch: ' + plan['review']['decision_note'])
    act = json.loads((DEST / 'acts' / (slug + '.json')).read_text())
    verify_acquisition(act)
    manifest = {a['slug']: a for a in oi.load_manifest()}
    if slug not in manifest:
        raise ValueError(f'{slug} is not in data/discovery/corpus-manifest.json; the ingestion-manifest '
                         'migration must add it before its provisions can be admitted')
    entry = manifest[slug]
    # A section listing is paginated at size=100, so a large Act has several
    # captures. Each is materialized under its own page name, and every
    # provision is bound to the capture that actually holds its section item.
    listings = [r for r in act['captures']
                if 'identifier_collection=SECTION' in r['url'] and 'f.act_id=' + entry['act_id'] in r['url']]
    if not listings:
        raise ValueError('no retained section-listing capture for this Act')
    pages = {}
    for receipt in listings:
        page = re.search(r'[?&]page=(\d+)', receipt['url'])
        if page is None:
            raise ValueError('section-listing capture has no page number: ' + receipt['url'])
        if int(page.group(1)) in pages:
            raise ValueError('duplicate section-listing page capture')
        pages[int(page.group(1))] = receipt
    capture_by_uuid, listing_by_name = {}, {}
    for page, receipt in sorted(pages.items()):
        name = materialize(f'phase3-{slug}-sections-page-{page}', receipt, 'application/hal+json', root, slug)
        listing_by_name[name] = receipt
        listing = json.loads((root / 'data/discovery' / (name + '.body')).read_bytes())
        for row in listing['_embedded']['searchResult']['_embedded']['objects']:
            uuid = row['_embedded']['indexableObject']['uuid']
            if uuid in capture_by_uuid:
                raise ValueError('section item appears in more than one listing page')
            capture_by_uuid[uuid] = name
    pdf_receipt = next(r for r in act['captures'] if r['sha256'] == plan['pdf_sha256'])
    pdf_capture = materialize(f'phase3-{slug}-pdf', pdf_receipt, 'application/pdf', root, slug)

    digest = plan_digest(plan)
    reference = dict(path=str(plan_path(slug, root).relative_to(root)),
                     sha256=oi.sha256_bytes(plan_path(slug, root).read_bytes()),
                     plan_digest=digest, population_count=plan['population_count'],
                     selected_count=len(plan['selected_keys']))
    selected = set(plan['selected_keys'])
    records = {}
    for p in plan['population']:
        visually = p['key'] in selected
        sections_capture = capture_by_uuid.get(p['source_item_uuid'])
        if sections_capture is None:
            raise ValueError('section item is absent from every retained listing page: ' + p['key'])
        records[p['key']] = dict(
            provision_key=p['key'], act_slug=slug, act_uuid=act['item']['uuid'],
            section_number=p['section_number'], heading=p['heading'],
            selected_representation='structured_html',
            selected_representation_reason=(
                'Whole body agrees with the retained PDF at normalization level '
                f"{p['stratum']}; admitted under this Act's sampled visual review"
                + (' and individually compared in that sample.' if visually else ', not individually compared.')),
            source_representation=dict(kind='structured_html', capture=sections_capture,
                                       sha256=listing_by_name[sections_capture]['sha256'],
                                       field='dc.identifier.section_page_note',
                                       section_item_uuid=p['source_item_uuid'], act_id=entry['act_id']),
            pdf_anchor=dict(capture=pdf_capture, sha256=plan['pdf_sha256'],
                            pdf_page_from=p['pdf_page_from'], pdf_page_to=p['pdf_page_to']),
            agreement=dict(normalization_level=len([n for n in p['normalizations'] if n != 'footnote-block-skip']),
                           normalizations=p['normalizations'],
                           page_break_gap_count=p['page_break_gap_count'],
                           footnote_normalization_level=p.get('footnote_normalization_level'),
                           method='enumerated typographic normalization applied to both representations'),
            review=dict(reviewer_ref=plan['review']['reviewer_ref'], review_class=REVIEW_CLASS,
                        checked_scope=CHECKED_SCOPE, visually_reviewed=visually,
                        footnotes_present=p['has_footnote'], sample_plan=reference,
                        scope=plan['review']['scope_note'],
                        evidence=(plan['renders'].get(p['key'], []) if visually else [])
                                 + [f'data/discovery/{sections_capture}.body', f'data/discovery/{pdf_capture}.body',
                                    reference['path']]),
            known_conflicts=[],
            classification='formatting_only_verified_equivalent' if not p['normalizations'] else 'typographic_equivalence_verified',
            disposition='verified_equivalent',
            admission_status='admitted',
            extraction_method_version=VERSION,
            expected_output=dict(body_text_sha256=p['body_text_sha256'],
                                 footnote_text_sha256=p['footnote_text_sha256'] or oi.NO_FOOTNOTE_EXPECTED,
                                 established_by=plan['review']['reviewer_ref'],
                                 established_note=('Established by automated whole-body agreement recorded in the '
                                                   'sample plan; individually compared only if visually_reviewed.')))
    return plan, records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--act', required=True)
    parser.add_argument('--write', action='store_true', help='write records (default: verify only)')
    args = parser.parse_args()
    plan, records = build_records(args.act)
    raw = {}
    written = skipped = 0
    for key, record in sorted(records.items()):
        path = REVIEW / (key.replace(':', '-section-') + '.review.json')
        for name in (record['source_representation']['capture'], record['pdf_anchor']['capture']):
            raw.setdefault(name, oi.load_capture_bytes(name))
        built = oi.build_provision_record(record, raw)
        if built['admission_status'] != 'admitted':
            raise SystemExit(f'{key}: would not admit ({built["admission_status"]}); refusing to write any record')
        if path.exists():
            skipped += 1
            continue
        if args.write:
            path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
        written += 1
    verb = 'wrote' if args.write else 'verified (dry run)'
    print(f'{args.act}: {verb} {written} review records, {skipped} left untouched '
          f'({len(plan["selected_keys"])} of {plan["population_count"]} visually reviewed)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
