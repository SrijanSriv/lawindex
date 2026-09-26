"""Bounded, resumable acquisition for the explicit 20-Act Phase 3 inventory.

No admission, recursive crawl, redirect following, or canonical database writes.
Successful receipts are reusable only after checking the retained body hash.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://indiacode.gov.in/server/api'
DEST = ROOT / 'data/phase3/acquisition'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, ensure_ascii=False)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as tmp:
        json.dump(value, tmp, indent=2, ensure_ascii=False)
        tmp.write('\n'); tmp.flush(); os.fsync(tmp.fileno())
        name = tmp.name
    os.replace(name, path)


def validate_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.netloc != 'indiacode.gov.in' or
        not p.path.startswith('/server/api/') or p.fragment):
        raise ValueError('unapproved acquisition URL')
    return url


def value(item, key):
    rows = item.get('metadata', {}).get(key, [])
    if len(rows) > 1: raise ValueError('ambiguous metadata: ' + key)
    return rows[0]['value'] if rows else None


def normalized(text): return re.sub(r'[^a-z0-9]', '', text.lower())


def validate_inventory(inventory):
    records = inventory['records']
    if not 1 <= len(records) <= 20: raise ValueError('inventory exceeds 20-Act limit or is empty')
    slugs = [r['slug'] for r in records]
    titles = [normalized(r['title']) for r in records]
    if len(set(slugs)) != len(slugs) or len(set(titles)) != len(titles): raise ValueError('duplicate inventory identity')
    for r in records:
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',r['slug']): raise ValueError('unsafe slug')
    return records


class Capture:
    def __init__(self, dest=DEST):
        self.dest = dest
        self.last = 0
        self.receipts = []

    def get(self, url):
        validate_url(url)
        receipt_path = self.dest / 'receipts' / (sha(url.encode()) + '.json')
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if not re.fullmatch(r'[0-9a-f]{64}', receipt.get('sha256','')): raise ValueError('invalid receipt digest')
            if receipt['url'] != url: raise ValueError('cache URL mismatch')
            if receipt['status'] == 200 and receipt.get('curl_exit') == 0:
                raw = (self.dest / 'blobs' / (receipt['sha256'] + '.body')).read_bytes()
                if sha(raw) != receipt['sha256']: raise ValueError('cached body changed')
                self.receipts.append(dict(url=url,sha256=receipt['sha256'],status=receipt['status'],curl_exit=receipt['curl_exit']))
                return raw
        self.dest.mkdir(parents=True, exist_ok=True)
        for attempt in range(3):
            time.sleep(max(0, 2 - (time.monotonic()-self.last)))
            with tempfile.NamedTemporaryFile(dir=self.dest) as tmp:
                self.last = time.monotonic()
                run = subprocess.run(['curl','--silent','--show-error','--proto','=https',
                    '--max-time','40','--connect-timeout','15','--max-filesize','52428800',
                    '--user-agent','LawIndex/0.3 (personal non-commercial; bounded 20-Act research)',
                    '--output',tmp.name,'--write-out','%{http_code}',url], capture_output=True, timeout=45)
                raw = Path(tmp.name).read_bytes()
            status = int(run.stdout or b'0')
            body_hash = sha(raw)
            blob = self.dest / 'blobs' / (body_hash + '.body')
            blob.parent.mkdir(parents=True,exist_ok=True)
            if blob.exists():
                if blob.read_bytes() != raw: raise ValueError('content-addressed blob corruption')
            else:
                with blob.open('xb') as f: f.write(raw)
            receipt = dict(url=url,status=status,sha256=body_hash,bytes=len(raw),
                fetched_at=datetime.now(timezone.utc).isoformat(),curl_exit=run.returncode,
                error=run.stderr.decode(errors='replace'),attempt=attempt+1)
            # Append-only observations, plus the latest resumable receipt.
            history = self.dest/'observations'/(sha(canonical(receipt).encode())+'.json')
            atomic_json(history,receipt);atomic_json(receipt_path,receipt)
            if status == 200 and run.returncode == 0:
                self.receipts.append(dict(url=url,sha256=receipt['sha256'],status=receipt['status'],curl_exit=receipt['curl_exit']))
                return raw
            if status not in (0,429,500,502,503,504) or attempt==2:
                raise ValueError(f'fetch failed (HTTP {status}, curl {run.returncode}); redirects are not followed')
            time.sleep(2**(attempt+1))
        raise AssertionError('unreachable')

    def json(self, url): return json.loads(self.get(url))


def verify_acquisition(act, dest=DEST):
    """Bind materialized metadata/sections/PDF declarations to retained HTTP bodies."""
    if act.get('status') != 'captured_review_pending' or not act.get('captures'):
        raise ValueError('not a complete evidenced acquisition')
    sections=[];items=[];pdf_captures={};totals=set()
    for capture in act['captures']:
        url=validate_url(capture['url']);digest=capture['sha256']
        if not re.fullmatch(r'[0-9a-f]{64}',digest):raise ValueError('invalid capture digest')
        if capture['status']!=200 or capture['curl_exit']!=0:raise ValueError('unsuccessful capture')
        raw=(dest/'blobs'/(digest+'.body')).read_bytes()
        if sha(raw)!=digest:raise ValueError('retained capture changed')
        if raw.startswith(b'%PDF-'):
            pdf_captures[url]=digest
            continue
        source=json.loads(raw)
        if source.get('uuid')==act['item']['uuid']:items.append(source)
        result=source.get('_embedded',{}).get('searchResult')
        if result is not None:
            found=objects(source)
            items.extend(r for r in found if r.get('uuid')==act['item']['uuid'])
            if 'f.identifier_collection=SECTION' in url:
                totals.add(result['page']['totalElements']);sections.extend(found)
    if not any(canonical(item)==canonical(act['item']) for item in items):
        raise ValueError('Act metadata differs from retained response')
    if totals!={act['section_count']} or len(sections)!=act['section_count']:
        raise ValueError('source section totals do not reconcile')
    if canonical(sorted(sections,key=lambda r:r['uuid']))!=canonical(sorted(act['sections'],key=lambda r:r['uuid'])):
        raise ValueError('section inventory differs from retained responses')
    if len({r['uuid'] for r in sections})!=len(sections):raise ValueError('duplicate section identity')
    if any(value(r,'dc.identifier.act_id')!=value(act['item'],'dc.identifier.act_id') for r in sections):
        raise ValueError('cross-Act section inventory')
    if not act['pdfs']:raise ValueError('no PDF evidence')
    for pdf in act['pdfs']:
        if pdf_captures.get(BASE+'/core/bitstreams/'+pdf['uuid']+'/content')!=pdf['sha256']:
            raise ValueError('PDF declaration differs from captured bitstream')


def objects(page): return [r['_embedded']['indexableObject'] for r in page['_embedded']['searchResult']['_embedded'].get('objects',[])]


def resolve(capture, proposed, prior):
    if prior:
        item = capture.json(BASE+'/core/items/'+prior['uuid'])
    else:
        params = [('f.identifier_collection','ACT,equals'),('f.title',proposed['title'].removeprefix('The ').rstrip('.')+',contains'),('page','0'),('size','100')]
        result = capture.json(BASE+'/discover/search/objects?'+urlencode(params))
        if result['_embedded']['searchResult']['page']['totalElements']>100:raise ValueError('identity search requires narrower scope')
        matches = [item for item in objects(result) if normalized(value(item,'dc.title') or '') == normalized(proposed['title'])
                   and value(item,'dc.identifier.state_name') == 'CENTRAL']
        if len(matches)!=1: raise ValueError(f'expected one exact central Act identity, got {len(matches)}')
        item = matches[0]
    if (normalized(value(item,'dc.title') or '')!=normalized(proposed['title']) or
        value(item,'dc.identifier.collection')!='ACT' or value(item,'dc.identifier.state_name')!='CENTRAL'):
        raise ValueError('resolved item does not match requested central Act')
    return item


def acquire_one(capture, proposed, prior):
    item = resolve(capture,proposed,prior)
    act_id = value(item,'dc.identifier.act_id')
    if not act_id: raise ValueError('Act has no section-join identity')
    sections=[];expected=None
    for number in range(100):
        params=[('f.identifier_collection','SECTION,equals'),('f.act_id',act_id+',equals'),
                ('sort','dc.identifier.order_number,ASC'),('page',str(number)),('size','100')]
        page=capture.json(BASE+'/discover/search/objects?'+urlencode(params))
        info=page['_embedded']['searchResult']['page']
        total=info['totalElements']
        if expected is not None and total!=expected: raise ValueError('section count changed during pagination')
        expected=total
        rows=objects(page)
        if any(value(row,'dc.identifier.act_id') != act_id or value(row,'dc.identifier.collection')!='SECTION' for row in rows):
            raise ValueError('section pagination crossed Act boundary')
        sections.extend(rows)
        if number+1 >= info['totalPages']: break
    else: raise ValueError('pagination limit exceeded')
    if len(sections)!=expected or len({r['uuid'] for r in sections})!=expected:
        raise ValueError('section pagination incomplete or duplicate')
    bundles=capture.json(BASE+'/core/items/'+item['uuid']+'/bundles?size=100')
    if bundles.get('page',{}).get('totalPages',1)>1:raise ValueError('bundle pagination requires explicit handling')
    pdfs=[]
    for bundle in bundles.get('_embedded',{}).get('bundles',[]):
        if bundle['name']!='ORIGINAL':continue
        streams=capture.json(BASE+'/core/bundles/'+bundle['uuid']+'/bitstreams?size=100')
        if streams.get('page',{}).get('totalPages',1)>1:raise ValueError('bitstream pagination requires explicit handling')
        for stream in streams.get('_embedded',{}).get('bitstreams',[]):
            if not stream.get('name','').lower().endswith('.pdf'): continue
            # Both language representations may exist. Retain separately; never infer language from success.
            raw=capture.get(BASE+'/core/bitstreams/'+stream['uuid']+'/content')
            if not raw.startswith(b'%PDF-'):raise ValueError('bitstream is not PDF')
            pdfs.append(dict(uuid=stream['uuid'],name=stream['name'],sha256=sha(raw)))
    if not pdfs:raise ValueError('no original PDF retained')
    return dict(slug=proposed['slug'],status='captured_review_pending',item=item,sections=sections,
                section_count=expected,pdfs=pdfs,search_admitted=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--act',action='append',help='explicit inventory slug; omit to acquire all selected Acts')
    args=parser.parse_args(argv)
    inventory=json.loads((ROOT/'data/phase3/inventory.v1.json').read_text())
    records=validate_inventory(inventory)
    if args.act and set(args.act)-{r['slug'] for r in records}:parser.error('Act is outside selected inventory')
    prior={r['slug']:r for r in json.loads((ROOT/'data/discovery/corpus-manifest.json').read_text())['records']}
    DEST.mkdir(parents=True,exist_ok=True)
    with (DEST/'writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        capture=Capture()
        failures=0
        for proposed in records:
            if args.act and proposed['slug'] not in args.act:continue
            capture.receipts=[]
            try:result=acquire_one(capture,proposed,prior.get(proposed['slug']))
            except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as error:
                result=dict(slug=proposed['slug'],status='acquisition_failed',error=str(error),search_admitted=False)
            failures += result['status']=='acquisition_failed'
            result['captures']=capture.receipts
            result['inventory_sha256']=sha(canonical(inventory).encode())
            atomic_json(DEST/'act-history'/(sha(canonical(result).encode())+'.json'),result)
            atomic_json(DEST/'acts'/(proposed['slug']+'.json'),result)
            print(canonical({k:v for k,v in result.items() if k not in ('item','sections','captures')}),flush=True)

    return 1 if failures else 0

if __name__=='__main__':raise SystemExit(main())
