"""Reviewed HAL sections: source identity and PDF agreement, never auto-admission.

The review's output digests and decision remain enforced by offline_importer.
This method is deliberately separate from the legacy four-provision extractor.
"""
import json

VERSION = 'phase3-reviewed-html-v1'


_LISTINGS = {}


def _listing_items(digest, raw, uuid):
    """Section items with this UUID in a listing capture. Keyed by the capture
    digest the caller has just verified against these exact bytes; each item
    is stored serialized and decoded afresh, so no caller can alter what
    another caller receives."""
    if digest not in _LISTINGS:
        if len(_LISTINGS) >= 64:
            _LISTINGS.clear()
        index = {}
        for row in json.loads(raw)['_embedded']['searchResult']['_embedded']['objects']:
            item = row['_embedded']['indexableObject']
            index.setdefault(item['uuid'], []).append(json.dumps(item))
        _LISTINGS[digest] = index
    return [json.loads(item) for item in _LISTINGS[digest].get(uuid, [])]


def source_fields(review, captures, manifest):
    """Identity-checked body, footnote and PDF pages for one reviewed section.

    Shared by every reviewed-HAL admission path. It proves the capture bytes,
    the Act, the section item and its labels; it makes no agreement claim and
    no admission decision -- the caller does the PDF comparison its own
    review class requires.
    """
    # Lazy imports avoid the candidate module's legacy PDF-helper import cycle.
    try:
        from scripts.phase3_candidates import plain
        from scripts.offline_importer import clean_pdf_pages, sha256_bytes
    except ModuleNotFoundError:
        from phase3_candidates import plain
        from offline_importer import clean_pdf_pages, sha256_bytes
    src = review['source_representation']
    anchor = review['pdf_anchor']
    act = next(a for a in manifest if a['slug'] == review['act_slug'])
    if (review['provision_key'] != review['act_slug'] + ':' + review['section_number']
            or review['act_uuid'] != act['uuid'] or src['act_id'] != act['act_id']
            or src['kind'] != 'structured_html' or review['selected_representation'] != 'structured_html'
            or src['field'] != 'dc.identifier.section_page_note'):
        raise ValueError('review/source identity mismatch')
    raw = captures[src['capture']]
    pdf = captures[anchor['capture']]
    if sha256_bytes(raw) != src['sha256'] or sha256_bytes(pdf) != anchor['sha256']:
        raise ValueError('reviewed source hash mismatch')
    targets = _listing_items(src['sha256'], raw, src['section_item_uuid'])
    if len(targets) != 1:
        raise ValueError('section UUID missing or duplicated')
    metadata = targets[0]['metadata']

    def field(name, optional=False):
        values = metadata.get(name, [])
        if optional and not values:
            return ''
        if len(values) != 1 or not isinstance(values[0]['value'], str):
            raise ValueError('ambiguous or missing section field: ' + name)
        return values[0]['value']

    for name, expected in [('dc.identifier.act_id', act['act_id']),
                           ('dc.identifier.section_number', review['section_number']),
                           ('dc.title', review['heading']),
                           ('dc.identifier.collection', 'SECTION')]:
        if field(name) != expected:
            raise ValueError('section identity mismatch: ' + name)
    body = plain(field(src['field']))
    footnote = plain(field('dc.identifier.section_footnote', optional=True)) or None
    pages = list(clean_pdf_pages(pdf))
    return body, footnote, pages, anchor


def extract(review, captures, manifest):
    """Individually reviewed sections: exact whitespace-only PDF agreement."""
    try:
        from scripts.phase3_candidates import locate
    except ModuleNotFoundError:
        from phase3_candidates import locate
    body, footnote, pages, anchor = source_fields(review, captures, manifest)
    found = locate(body, pages)
    if (found['pdf_page_from'], found['pdf_page_to']) != (anchor['pdf_page_from'], anchor['pdf_page_to']):
        raise ValueError('reviewed PDF page range mismatch')
    if footnote:
        locate(footnote, pages[anchor['pdf_page_from']-1:anchor['pdf_page_to']])
    if review['review'].get('checked_scope') != 'whole_provision_including_footnotes_and_provisos':
        raise ValueError('whole-provision review required')
    return body, footnote
