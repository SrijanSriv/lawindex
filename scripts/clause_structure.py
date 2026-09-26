"""Exact, reviewed boundary profiles; no generic numbering inference.

Children are contextual annotations of a reviewed section. They receive no
public alias, independent admission, or standalone search passage.
"""
import re

try:
    from scripts import structural_store as ss
except ModuleNotFoundError:
    import structural_store as ss


def parse(text, profile, source_sha256):
    if (profile.get('schema_version') != 1 or profile.get('status') != 'reviewed_boundaries'
        or profile.get('body_sha256') != ss.sha(text.encode())
        or profile.get('source_sha256') != source_sha256
        or not profile.get('reviewer') or profile.get('independent_legal_expert') is not False):
        raise ValueError('structure profile does not attest this exact source and text')
    nodes = []
    seen = set()
    for rule in profile['nodes']:
        path = rule['path']
        if not re.fullmatch(r'[0-9a-z]+(?:/[0-9a-z]+)*',path) or path in seen:
            raise ValueError('duplicate or invalid structural path')
        parent = path.rpartition('/')[0] or None
        if parent and parent not in seen:
            raise ValueError('parent must precede child')
        anchor = rule['start_text']
        if not anchor.startswith('(' + path.split('/')[-1] + ')') or text.count(anchor) != 1:
            raise ValueError('ambiguous or inconsistent boundary anchor')
        start = text.index(anchor)
        if nodes and start <= nodes[-1]['start']:
            raise ValueError('boundary ordering changed')
        nodes.append(dict(path=path,parent=parent,kind=rule['kind'],start=start,end=None))
        seen.add(path)
    by_path = {n['path']:n for n in nodes}
    for n in nodes:
        siblings = [s for s in nodes if s['parent']==n['parent']]
        ordinal = siblings.index(n)
        n['ordinal'] = ordinal
        n['end'] = siblings[ordinal+1]['start'] if ordinal+1<len(siblings) else (
            by_path[n['parent']]['end'] if n['parent'] else len(text))
        parent_start = by_path[n['parent']]['start'] if n['parent'] else 0
        parent_end = by_path[n['parent']]['end'] if n['parent'] else len(text)
        if not parent_start <= n['start'] < n['end'] <= parent_end:
            raise ValueError('child lies outside its parent')
        if n['kind'] not in ('subsection','clause'):
            raise ValueError('unsupported boundary kind')
        n['text'] = text[n['start']:n['end']]
    return nodes


def schedule_outcome(text):
    """Recognize difficult retained schedule layouts and refuse unsafe splitting."""
    if 'THE FIRST SCHEDULE' in text and 'swear in the name of God' in text and 'solemnly affirm' in text:
        return dict(status='quarantined_structure',reason='stacked_oath_alternatives',children=[])
    if 'THE SECOND SCHEDULE' in text and ('Subs. by notification' in text or 'Ins. by notification' in text):
        return dict(status='quarantined_structure',reason='amendment_markers_and_footnote_numbering',children=[])
    return dict(status='unsupported_structure',reason='no_reviewed_schedule_profile',children=[])
