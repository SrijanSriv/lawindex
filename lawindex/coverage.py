"""Inventory accounting only. Searchable counts come exclusively from live Snapshot records."""
import json
from pathlib import Path
import re
from scripts.acquire_phase3 import validate_inventory, canonical, sha, validate_url, verify_acquisition
from scripts.phase3_candidates import VERSION


def read(path): return json.loads(path.read_text())


def build_coverage(root, snapshot):
    root=Path(root)
    inventory=read(root/'data/phase3/inventory.v1.json')
    records=validate_inventory(inventory)
    inventory_hash=sha(canonical(inventory).encode())
    dest=root/'data/phase3/acquisition'
    checked={}
    rows=[]
    for proposed in records:
        slug=proposed['slug']
        row=dict(slug=slug,title=proposed['title'],acquisition_status='not_requested',
                 source_section_count=None,pdf_count=None,candidate_status='not_processed',
                 agreement_review_pending_count=None,typographic_agreement_review_pending_count=None,
                 quarantined_count=None,quarantine_reasons=None,
                 searchable_provision_count=sum(p['act_slug']==slug for p in snapshot.records.values()),
                 full_act_coverage_verified=False,diagnostic=None)
        try:
            path=dest/'acts'/(slug+'.json')
            if path.exists():
                act=read(path)
                if act['slug']!=slug or act['inventory_sha256']!=inventory_hash:
                    raise ValueError('acquisition belongs to another inventory or Act')
                row['acquisition_status']=act['status']
                if act['status']=='acquisition_failed':row['diagnostic']=act['error']
                elif act['status']=='captured_review_pending':
                    verify_acquisition(act,dest)
                    row.update(source_section_count=act['section_count'],pdf_count=len(act['pdfs']))
                    candidate_path=root/'data/phase3/candidates'/(slug+'.json')
                    if candidate_path.exists():
                        candidate=read(candidate_path)
                        if candidate.get('status')=='parse_failed':
                            row.update(candidate_status='parse_failed',diagnostic=candidate['reason'])
                        else:
                            if candidate['source_acquisition_sha256']!=sha(json.dumps(act,sort_keys=True).encode()):
                                raise ValueError('candidate report is stale')
                            items=candidate['candidates']
                            if (len(items)!=act['section_count'] or len({c['key'] for c in items})!=len(items)
                                or any(c['parser_version']!=VERSION or c.get('search_admitted') is not False or
                                       c['status'] not in {'agreement_review_pending','typographic_agreement_review_pending','quarantined'} for c in items)):
                                raise ValueError('candidate inventory is inconsistent')
                            reasons={}
                            for c in items:
                                if c['status']=='quarantined':reasons[c['reason']]=reasons.get(c['reason'],0)+1
                            row.update(candidate_status='parsed_review_pending',
                                agreement_review_pending_count=sum(c['status']=='agreement_review_pending' for c in items),
                                typographic_agreement_review_pending_count=sum(c['status']=='typographic_agreement_review_pending' for c in items),
                                quarantined_count=sum(c['status']=='quarantined' for c in items),
                                quarantine_reasons=dict(sorted(reasons.items())))
                else:raise ValueError('unknown acquisition state')
        except (OSError,ValueError,KeyError,TypeError) as error:
            row.update(acquisition_status='invalid_evidence',candidate_status='unavailable',
                       source_section_count=None,pdf_count=None,agreement_review_pending_count=None,
                       typographic_agreement_review_pending_count=None,quarantined_count=None,
                       quarantine_reasons=None,diagnostic=str(error))
        rows.append(row)
    return dict(schema_version=1,inventory_id=inventory['inventory_id'],inventory_sha256=inventory_hash,
        selected_act_count=len(rows),captured_act_count=sum(r['acquisition_status']=='captured_review_pending' for r in rows),
        searchable_act_count=sum(r['searchable_provision_count']>0 for r in rows),
        searchable_provision_count=sum(r['searchable_provision_count'] for r in rows),rows=rows,
        limitations=[
            'Captured is not reviewed, admitted, or complete searchable coverage.',
            'Candidate counts are extraction bookkeeping, not fidelity approval. Exact agreement folds whitespace only; typographic agreement additionally applies the enumerated normalizations recorded on each candidate (dash/quote glyphs, reference marks, hyphenation, spacing, case, editorial brackets, footnote blocks at page breaks). Both still need boundary/layout review.',
            'Quarantine reasons are recorded per Act; a quarantined candidate whose body aligned but whose footnote differs is a representation difference for review, not a wording error in the law.',
            'Source section counts are observed portal records, not a count of every legal provision or schedule.',
            'No full Act has passed coverage reconciliation. Unknown counts are null, not zero.',
            'PDF counts include separately retained language versions; only selected English candidates are parsed.',
            'Searchable counts are derived from live admission checks, independently of acquisition/candidate status.',
        ])
