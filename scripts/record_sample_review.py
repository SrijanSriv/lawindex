#!/usr/bin/env python3
"""Stamp a sampled-review outcome onto an Act's plan.

The reviewer works through plan['renders'], comparing each selected section's
candidate text against its rendered PDF pages, then records one outcome per
selected section. Coverage is enforced here: a plan cannot be marked admitted
with a section unreviewed, and any discrepancy forces the Act batch to be
rejected rather than quietly dropping the offending section.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from scripts.acquire_phase3 import atomic_json, sha  # noqa: E402
from scripts.sample_review_plan import load_plan, plan_path  # noqa: E402

DECISIONS = {'verified_equivalent', 'discrepancy'}


def record(slug, outcomes, reviewer_ref, session_date, note, root=ROOT):
    plan = load_plan(slug, root)
    if plan.get('review'):
        raise ValueError('this plan already carries a review; withdraw it explicitly instead')
    if plan.get('status') != 'awaiting_review':
        raise ValueError('plan is not rendered and awaiting review')
    selected = set(plan['selected_keys'])
    if set(outcomes) != selected:
        missing = sorted(selected - set(outcomes))
        extra = sorted(set(outcomes) - selected)
        raise ValueError(f'outcomes must cover exactly the selected sections; missing {missing}, unexpected {extra}')
    for key, outcome in outcomes.items():
        if outcome.get('decision') not in DECISIONS or not outcome.get('note'):
            raise ValueError(f'{key}: each outcome needs a decision in {sorted(DECISIONS)} and a note')
    reviewer = json.loads((root / reviewer_ref).read_text())
    if reviewer.get('is_independent_legal_expert_review') is not False:
        raise ValueError('reviewer record must explicitly disclaim independent legal expert review')
    failures = sorted(k for k, o in outcomes.items() if o['decision'] != 'verified_equivalent')
    plan['review'] = dict(
        reviewer_ref=reviewer_ref, reviewer_sha256=sha((root / reviewer_ref).read_bytes()),
        session_date=session_date,
        outcomes={k: outcomes[k] for k in sorted(outcomes)},
        decision='act_batch_rejected' if failures else 'act_batch_admitted',
        failed_keys=failures, decision_note=note,
        render_evidence=plan['render_sha256'],
        scope_note=('Each selected section was compared whole against its rendered PDF pages: heading, beginning '
                    'and end, numbered parts, provisos and footnotes. Sections outside selected_keys were not '
                    'looked at individually; they rest on automated whole-body agreement plus this sample.'))
    plan['status'] = 'reviewed'
    atomic_json(plan_path(slug, root), plan)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--act', required=True)
    parser.add_argument('--outcomes', required=True, help='JSON file: {provision_key: {decision, note}}')
    parser.add_argument('--reviewer-ref', required=True)
    parser.add_argument('--session-date', required=True)
    parser.add_argument('--note', required=True)
    args = parser.parse_args()
    outcomes = json.loads(Path(args.outcomes).read_text())
    plan = record(args.act, outcomes, args.reviewer_ref, args.session_date, args.note)
    print(f"{args.act}: {plan['review']['decision']} "
          f"({len(plan['review']['outcomes'])} sections reviewed, {len(plan['review']['failed_keys'])} failed)")
    return 0 if plan['review']['decision'] == 'act_batch_admitted' else 1


if __name__ == '__main__':
    sys.exit(main())
