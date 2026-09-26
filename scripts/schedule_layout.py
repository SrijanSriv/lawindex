"""Source-position-preserving models of the two retained RTI schedules.

This is a bounded layout parser, not a plain-text or search admission path.
Profiles and artifacts are hash-bound. Every extracted word is retained exactly
once in a primary region; secondary relationships reference those same words.
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

try:
    from scripts import structural_store as ss
except ModuleNotFoundError:
    import structural_store as ss

ROOT = Path(__file__).resolve().parents[1]
PARSER_VERSION = 'rti-schedule-layout-v1'
NS = {'h': 'http://www.w3.org/1999/xhtml'}
DEFAULT_PROFILE = ROOT / 'data/review/structure/rti-schedule-layout-profile.json'


def extract_pages(raw):
    with tempfile.NamedTemporaryFile(suffix='.pdf') as f:
        f.write(raw); f.flush()
        result = subprocess.run(['pdftotext','-f','23','-l','24','-bbox-layout',f.name,'-'],
                                check=True,capture_output=True,timeout=60)
    tree = ET.fromstring(result.stdout)
    pages = []
    for number,p in enumerate(tree.findall('.//h:page',NS),23):
        width,height = float(p.attrib['width']),float(p.attrib['height'])
        words=[]
        for i,w in enumerate(p.findall('.//h:word',NS)):
            box=[float(w.attrib[k]) for k in ('xMin','yMin','xMax','yMax')]
            if not all(math.isfinite(n) for n in box+[width,height]) or not (0<=box[0]<box[2]<=width and 0<=box[1]<box[3]<=height):
                raise ValueError('invalid source word coordinates')
            words.append(dict(id=f'p{number}-w{i}',text=w.text or '',bbox=box))
        if not words: raise ValueError('empty schedule page')
        pages.append(dict(page=number,width=width,height=height,words=words))
    if [p['page'] for p in pages] != [23,24]:
        raise ValueError('both declared schedule pages are required')
    return pages


def groups_for(page, spec):
    words={w['id']:w for w in page['words']}
    groups=[];assigned=[];ids=set()
    for group in spec['groups']:
        gid=group['id'];refs=group['word_ids']
        if gid in ids or not refs or any(r not in words for r in refs):
            raise ValueError('invalid, duplicate, or empty layout region')
        ids.add(gid);assigned.extend(refs)
        boxes=[words[r]['bbox'] for r in refs]
        groups.append(dict(id=gid,role=group['role'],word_ids=refs,
            bbox=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]))
    if len(assigned)!=len(set(assigned)) or set(assigned)!=set(words):
        raise ValueError('regions must partition every source word exactly once')
    return groups


def validate_relations(page, groups, relations):
    words={w['id']:w for w in page['words']}; by_group={g['id']:g for g in groups}
    if page['page']==23:
        if len(relations)!=1 or relations[0]['kind']!='exclusive_alternatives':
            raise ValueError('oath alternatives must be explicit')
        r=relations[0]
        if r['choices']!=['oath','affirmation'] or r['shared_prefix']!='prefix' or r['shared_suffix']!='continuation':
            raise ValueError('invalid oath context')
        for group in r['choices']+[r['shared_prefix'],r['shared_suffix']]:
            if group not in by_group: raise ValueError('missing oath region')
        for group,expected in [('oath',['swear','in','the','name','of','God']),('affirmation',['solemnly','affirm'])]:
            if [words[w]['text'] for w in by_group[group]['word_ids']]!=expected:
                raise ValueError('alternative wording changed')
    else:
        expected_entries={f'entry-{i}' for i in range(1,28)}
        if {g['id'] for g in groups if g['role']=='entry'} != expected_entries:
            raise ValueError('schedule must preserve all 27 printed serial positions')
        if {g['id'] for g in groups if g['role']=='footnote'}!={f'note-{i}' for i in range(1,12)}:
            raise ValueError('all 11 footnotes are required')
        markers=[]
        for r in relations:
            if r['kind']!='amendment_reference' or r['marker_word_id'] not in words:
                raise ValueError('invalid amendment marker')
            marker=r['marker_word_id']; number=words[marker]['text']
            if r['note_id']!='note-'+number or r['note_id'] not in by_group:
                raise ValueError('marker does not match footnote number')
            if not r['scope_groups'] or any(g not in by_group or by_group[g]['role'] not in ('entry','omission') for g in r['scope_groups']):
                raise ValueError('invalid amendment scope')
            scope={w for g in r['scope_groups'] for w in by_group[g]['word_ids']}
            if marker not in scope or not r['affected_word_ids'] or not set(r['affected_word_ids'])<=scope:
                raise ValueError('amendment reference outside declared scope')
            markers.append(marker)
        expected_markers={w for g in groups if g['role'] in ('entry','omission') for w in g['word_ids'] if words[w]['text'].isdigit()}
        if len(markers)!=len(set(markers)) or set(markers)!=expected_markers:
            raise ValueError('every superscript occurrence must resolve once')
        if {r['note_id'] for r in relations}!={f'note-{i}' for i in range(1,12)}:
            raise ValueError('unreferenced footnote')


def parse(raw, profile):
    if not isinstance(profile,dict) or profile.get('schema_version')!=1 or profile.get('parser_version')!=PARSER_VERSION:
        raise ValueError('unsupported schedule layout profile')
    if ss.sha(raw)!=profile.get('source_sha256'):
        raise ValueError('source changed; fresh layout review required')
    pages=extract_pages(raw)
    if ss.sha(ss.canonical(pages).encode())!=profile.get('extracted_layout_sha256'):
        raise ValueError('word text/order/coordinates changed; fresh layout review required')
    specs=profile['pages']
    if [p['page'] for p in specs]!=[23,24]: raise ValueError('invalid page inventory')
    output=[]
    for page,spec in zip(pages,specs):
        groups=groups_for(page,spec)
        validate_relations(page,groups,spec['relations'])
        output.append({**page,'groups':groups,'relations':spec['relations']})
    artifact = dict(schema_version=1,parser_version=PARSER_VERSION,source_sha256=ss.sha(raw),
        profile_sha256=ss.sha(ss.canonical(profile).encode()),
        source_capture='rti-2005-pdf',source_path='data/discovery/rti-2005-pdf.body',
        coordinate_system='PDF points, top-left origin; word boxes, not reconstructed prose',
        pages=output,search_admitted=False,
        limitations=['Only this retained snapshot and pages 23-24 are supported.',
                    'Read with the original PDF; graphic rules and fonts are not reconstructed.',
                    'Relationships describe the printed layout, not current legal effect.',
                    'Implementation baselines do not constitute independent review.'])
    if payload_digest(artifact)!=profile.get('expected_artifact_payload_sha256'):
        raise ValueError('layout output differs from implementation baseline')
    return artifact


def artifact_digest(artifact):
    return ss.sha(ss.canonical(artifact).encode())


def assess_review(artifact, review):
    """A layout review NEVER grants legal/search/public reuse permission."""
    if review is None: return 'needs_independent_review'
    if (not isinstance(review,dict) or review.get('schema_version')!=1 or review.get('artifact_sha256')!=artifact_digest(artifact)
        or review.get('profile_sha256')!=artifact['profile_sha256']
        or review.get('source_sha256')!=artifact['source_sha256']
        or review.get('parser_version')!=PARSER_VERSION or review.get('pages')!=[23,24]):
        return 'invalid_review_binding'
    reviewer=review.get('reviewer',{})
    if not isinstance(reviewer,dict) or not reviewer.get('id') or reviewer.get('independent_of_implementation') is not True:
        return 'invalid_review_provenance'
    if review.get('decision')=='changes_requested':return 'changes_requested'
    if review.get('decision')=='accept_layout' and review.get('findings')==[]:
        return 'layout_reviewed_not_search_admitted'
    return 'invalid_review_decision'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,default=DEFAULT_PROFILE)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'data/import/schedules')
    parser.add_argument('--review',type=Path,help='optional separately authored review record')
    args=parser.parse_args(argv)
    try:
        profile=json.loads(args.profile.read_text())
        # Bounded known fixture, not an arbitrary path supplied by a profile.
        raw=(ROOT/'data/discovery/rti-2005-pdf.body').read_bytes()
        artifact=parse(raw,profile);digest=artifact_digest(artifact)
        review=json.loads(args.review.read_text()) if args.review else None
        status=assess_review(artifact,review)
        args.output_dir.mkdir(parents=True,exist_ok=True)
        path=args.output_dir/(digest+'.json')
        encoded=(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n').encode()
        with tempfile.NamedTemporaryFile(dir=args.output_dir,delete=False) as f:
            temporary=Path(f.name)
            try:
                f.write(encoded);f.flush();os.fsync(f.fileno())
                try:os.link(temporary,path)
                except FileExistsError:
                    if path.read_bytes()!=encoded:raise ValueError('existing artifact is corrupt')
            finally:temporary.unlink(missing_ok=True)
        print(json.dumps(dict(artifact=str(path),artifact_sha256=digest,review_status=status,search_admitted=False)))
        return 0 if status in ('needs_independent_review','layout_reviewed_not_search_admitted') else 1
    except (OSError,ValueError,KeyError,TypeError,ET.ParseError,subprocess.SubprocessError) as exc:
        print(f'schedule_layout: {type(exc).__name__}: {exc}',file=sys.stderr);return 1


def payload_digest(artifact):
    return ss.sha(ss.canonical({k:v for k,v in artifact.items() if k!='profile_sha256'}).encode())


if __name__=='__main__':raise SystemExit(main())
