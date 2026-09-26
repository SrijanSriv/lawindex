#!/usr/bin/env python3
"""Per-Act sampled review plans (option 2): full automated checks on every
aligned candidate, visual review of a risk-weighted sample.

A plan is built deterministically from the candidate report, so the same
inputs always select the same sections and nobody can quietly re-roll a
sample until an easy one comes up. It selects:

  * mandatory -- every aligned candidate carrying a footnote or a
    page-break footnote gap. These are the cases where PDF text extraction
    can be wrong in ways whole-body character agreement cannot detect.
  * stratified sample -- the remaining candidates are grouped by the most
    tolerant normalization level they needed ("exact" when none), and each
    group contributes max(2, 10%) sections. Every normalization class an
    Act actually uses is therefore looked at by a human/agent reviewer.

The plan records the population with its output digests, so it is complete
evidence of what a passing review authorizes. It admits nothing by itself:
admission still goes through the canonical importer, one review record per
provision, each with its own expected-output digest.

Offline; reads retained candidate reports and PDFs only.
"""
import argparse
import collections
import hashlib
import json
import math
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from scripts.acquire_phase3 import DEST, atomic_json, canonical, sha  # noqa: E402
from scripts.phase3_candidates import GAP_SKIP, VERSION as PARSER_VERSION  # noqa: E402

PLANNER_VERSION = 'phase3-sample-plan-v1'
PLANS = ROOT / 'data/phase3/review-plans'
RENDERS = ROOT / 'data/phase3/review-renders'
ALIGNED = {'agreement_review_pending', 'typographic_agreement_review_pending'}
SAMPLE_SHARE = 0.10
SAMPLE_FLOOR = 2
RENDER_SCALE = '1600'


def stratum(candidate):
    """The most tolerant normalization the candidate needed, as one label."""
    names = [n for n in (candidate.get('normalizations') or []) if n != GAP_SKIP]
    return names[-1] if names else 'exact'


def build_plan(slug, root=ROOT):
    report = json.loads((root / 'data/phase3/candidates' / (slug + '.json')).read_text())
    if report.get('status') == 'parse_failed':
        raise ValueError('candidate extraction failed for this Act: ' + report['reason'])
    candidates_sha = sha(canonical(report).encode())
    population = []
    for c in report['candidates']:
        if c['status'] not in ALIGNED:
            continue
        population.append(dict(
            key=c['key'], section_number=c['label'], heading=c['heading'],
            status=c['status'], stratum=stratum(c),
            normalizations=c.get('normalizations') or [],
            pdf_page_from=c['pdf_page_from'], pdf_page_to=c['pdf_page_to'],
            body_text_sha256=c['body_text_sha256'], footnote_text_sha256=c.get('footnote_text_sha256'),
            footnote_normalization_level=c.get('footnote_normalization_level'),
            has_footnote=bool(c.get('footnote_text')),
            page_break_gap_count=len(c.get('pdf_page_break_gaps') or []),
            source_item_uuid=c['source_item_uuid']))
    population.sort(key=lambda p: p['key'])
    if not population:
        raise ValueError('no aligned candidates to review for this Act')

    mandatory = [p['key'] for p in population if p['has_footnote'] or p['page_break_gap_count']]
    remaining = [p for p in population if p['key'] not in set(mandatory)]
    groups = collections.defaultdict(list)
    for p in remaining:
        groups[p['stratum']].append(p['key'])
    # Seeded only by inputs that are themselves hash-bound evidence.
    seed = sha((PLANNER_VERSION + '|' + slug + '|' + candidates_sha).encode())
    sampled, strata = [], {}
    for name in sorted(groups):
        keys = sorted(groups[name])
        take = min(len(keys), max(SAMPLE_FLOOR, math.ceil(len(keys) * SAMPLE_SHARE)))
        chosen = sorted(random.Random(seed + '|' + name).sample(keys, take))
        strata[name] = dict(population=len(keys), sampled=take, keys=chosen)
        sampled += chosen
    selected = sorted(set(mandatory) | set(sampled))

    return dict(
        schema_version=1, planner_version=PLANNER_VERSION, parser_version=PARSER_VERSION,
        act_slug=slug, candidates_sha256=candidates_sha, pdf_sha256=report['pdf']['sha256'],
        source_acquisition_sha256=report['source_acquisition_sha256'], seed=seed,
        selection_rule=dict(
            mandatory='every aligned candidate with a footnote or a page-break footnote gap',
            stratified=f'per most-tolerant-normalization stratum, max({SAMPLE_FLOOR}, ceil({SAMPLE_SHARE:.0%}))',
            deterministic='seed = sha256(planner_version|act_slug|candidates_sha256); re-running cannot re-roll the sample'),
        population=population, population_count=len(population),
        mandatory_keys=mandatory, sampled_keys=sorted(sampled), selected_keys=selected,
        strata=strata, renders={}, render_sha256={},
        status='awaiting_render', review=None,
        admits_nothing_note=('A passing review authorizes admission of this Act\'s aligned candidates through the '
                             'canonical importer under review class text_agreement_sampled_visual. Provisions not in '
                             'selected_keys are admitted on automated whole-body agreement plus this sample, and must '
                             'never be presented as individually reviewed.'))


def render_plan(plan, root=ROOT):
    """Render every selected section's PDF pages once, and hash each render."""
    pdf = DEST / 'blobs' / (plan['pdf_sha256'] + '.body')
    if sha(pdf.read_bytes()) != plan['pdf_sha256']:
        raise ValueError('retained PDF blob does not match the plan')
    out = RENDERS / plan['act_slug']
    out.mkdir(parents=True, exist_ok=True)
    by_key, pages_needed = {}, set()
    for entry in plan['population']:
        if entry['key'] not in set(plan['selected_keys']):
            continue
        pages = list(range(entry['pdf_page_from'], entry['pdf_page_to'] + 1))
        by_key[entry['key']] = [f"data/phase3/review-renders/{plan['act_slug']}/page-{p}.png" for p in pages]
        pages_needed |= set(pages)
    digests = {}
    for page in sorted(pages_needed):
        target = out / f'page-{page}.png'
        if not target.exists():
            subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-scale-to', RENDER_SCALE,
                            '-png', '-singlefile', str(pdf), str(target.with_suffix(''))],
                           check=True, capture_output=True)
        digests[f"data/phase3/review-renders/{plan['act_slug']}/page-{page}.png"] = sha(target.read_bytes())
    plan['renders'] = by_key
    plan['render_sha256'] = digests
    plan['status'] = 'awaiting_review'
    return plan


def plan_path(slug, root=ROOT):
    return root / 'data/phase3/review-plans' / (slug + '.json')


def load_plan(slug, root=ROOT):
    return json.loads(plan_path(slug, root).read_text())


def plan_digest(plan):
    """Digest of the plan excluding nothing: the review outcomes are part of
    what an admission is bound to, so a later edit invalidates admissions."""
    return sha(canonical(plan).encode())


def check_authorizes(plan, provision_key, body_sha, footnote_sha):
    """Raise unless a completed, passing plan authorizes this provision."""
    if plan.get('planner_version') != PLANNER_VERSION or plan.get('parser_version') != PARSER_VERSION:
        raise ValueError('sample plan was produced by a different planner/parser version')
    review = plan.get('review')
    if plan.get('status') != 'reviewed' or not review:
        raise ValueError('sample plan has no recorded review')
    if review.get('decision') != 'act_batch_admitted':
        raise ValueError('sample review did not admit this Act batch')
    outcomes = review.get('outcomes') or {}
    selected = plan.get('selected_keys') or []
    if not selected or set(outcomes) != set(selected):
        raise ValueError('sample review outcomes do not cover exactly the selected sections')
    if any(o.get('decision') != 'verified_equivalent' for o in outcomes.values()):
        raise ValueError('a sampled section was not verified equivalent')
    entry = next((p for p in plan['population'] if p['key'] == provision_key), None)
    if entry is None:
        raise ValueError('provision is not in the reviewed population')
    if entry['body_text_sha256'] != body_sha or entry['footnote_text_sha256'] != footnote_sha:
        raise ValueError('provision output digests differ from the reviewed population')
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--act', required=True, help='Act slug, or "all"')
    parser.add_argument('--render', action='store_true', help='also render the selected PDF pages')
    parser.add_argument('--force', action='store_true', help='replace a plan that has no recorded review')
    args = parser.parse_args()
    slugs = ([p.stem for p in sorted((ROOT / 'data/phase3/candidates').glob('*.json'))]
             if args.act == 'all' else [args.act])
    PLANS.mkdir(parents=True, exist_ok=True)
    for slug in slugs:
        path = plan_path(slug)
        if path.exists():
            existing = json.loads(path.read_text())
            if existing.get('review') and not args.force:
                print(f'{slug}: plan already reviewed; refusing to replace', flush=True)
                continue
            if not args.force:
                print(f'{slug}: plan exists; pass --force to rebuild', flush=True)
                continue
        plan = build_plan(slug)
        if args.render:
            plan = render_plan(plan)
        atomic_json(path, plan)
        print(f"{slug}: {plan['population_count']} aligned, {len(plan['mandatory_keys'])} mandatory, "
              f"{len(plan['sampled_keys'])} sampled, {len(plan['selected_keys'])} to review "
              f"({100*len(plan['selected_keys'])/plan['population_count']:.0f}%), status {plan['status']}", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
