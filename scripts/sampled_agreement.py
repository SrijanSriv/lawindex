"""Act-sampled admission (option 2): automated whole-body agreement for every
provision, plus a recorded visual review of that Act's risk-weighted sample.

This method NEVER decides on its own that a provision is equivalent. It
re-proves, at import time:

  * the capture bytes, Act identity, section item UUID, number and heading
    (shared with the individually reviewed path);
  * that the body still aligns with the retained PDF at exactly the
    normalization level the review recorded, on exactly the recorded pages,
    and that the recorded level matches the enumerated ladder prefix;
  * that a completed sample plan, unchanged since the review, authorizes
    this Act batch and lists this provision with these output digests.

Whether this particular provision was one of the visually reviewed sections
is recorded per provision and surfaced in search; it is never implied.
"""
import json

VERSION = 'phase3-sampled-agreement-v1'
REVIEW_CLASS = 'text_agreement_sampled_visual'
CHECKED_SCOPE = 'act_sample_plus_whole_body_automated_agreement'


def extract(review, captures, manifest, root=None):
    try:
        from scripts.reviewed_html import source_fields
        from scripts.phase3_candidates import (GAP_SKIP, NORMALIZATION_NAMES, locate,
                                               locate_across_footnote_blocks)
        from scripts.sample_review_plan import check_authorizes, plan_digest
        from scripts.offline_importer import ROOT, sha256_bytes
    except ModuleNotFoundError:
        from reviewed_html import source_fields
        from phase3_candidates import (GAP_SKIP, NORMALIZATION_NAMES, locate,
                                       locate_across_footnote_blocks)
        from sample_review_plan import check_authorizes, plan_digest
        from offline_importer import ROOT, sha256_bytes
    root = root or ROOT
    block = review['review']
    if block.get('review_class') != REVIEW_CLASS or block.get('checked_scope') != CHECKED_SCOPE:
        raise ValueError('review class/scope is not act-sampled agreement')

    body, footnote, pages, anchor = source_fields(review, captures, manifest)

    agreement = review['agreement']
    level = agreement['normalization_level']
    names = [n for n in agreement['normalizations'] if n != GAP_SKIP]
    if not isinstance(level, int) or not 0 <= level <= len(NORMALIZATION_NAMES):
        raise ValueError('invalid normalization level')
    if names != NORMALIZATION_NAMES[:level]:
        raise ValueError('recorded normalizations are not the ladder prefix for this level')
    uses_gap = GAP_SKIP in agreement['normalizations']
    found = (locate_across_footnote_blocks(body, pages, level) if uses_gap
             else locate(body, pages, level))
    if (found['pdf_page_from'], found['pdf_page_to']) != (anchor['pdf_page_from'], anchor['pdf_page_to']):
        raise ValueError('reviewed PDF page range mismatch')
    # The gap matcher can succeed with zero skipped runs (it also relaxes the
    # word-boundary check), so the count -- not merely the flag -- is what the
    # review recorded and what must still hold.
    if len(found.get('pdf_page_break_gaps') or []) != agreement['page_break_gap_count']:
        raise ValueError('page-break gap count differs from the review record')

    footnote_level = agreement.get('footnote_normalization_level')
    if footnote:
        if not isinstance(footnote_level, int) or footnote_level > level:
            raise ValueError('footnote normalization level missing or above the body level')
        locate(footnote, pages[anchor['pdf_page_from']-1:anchor['pdf_page_to']], footnote_level, footnote=True)
    elif footnote_level is not None:
        raise ValueError('footnote level recorded for a provision with no footnote')

    reference = block['sample_plan']
    plan_bytes = (root / reference['path']).read_bytes()
    if sha256_bytes(plan_bytes) != reference['sha256']:
        raise ValueError('sample plan changed since this provision was authorized')
    plan = json.loads(plan_bytes)
    if plan['act_slug'] != review['act_slug'] or plan_digest(plan) != reference['plan_digest']:
        raise ValueError('sample plan identity mismatch')
    entry = check_authorizes(plan, review['provision_key'],
                             sha256_bytes(body.encode()),
                             sha256_bytes(footnote.encode()) if footnote else None)
    if bool(block.get('visually_reviewed')) != (entry['key'] in plan['selected_keys']):
        raise ValueError('visually_reviewed does not match the plan selection')
    return body, footnote
