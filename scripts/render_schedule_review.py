"""Private, offline HTML viewer for the immutable RTI schedule layout candidate.

Presentation tooling only. It never calls the importer, never writes SQLite,
and never trusts a filesystem/source path recorded inside the artifact: the
retained source is always read from the fixed repository path, and the
supplied artifact is only displayed if it matches a fresh model built from
that source and the current layout profile with the existing parser
(`scripts/schedule_layout.py`). Review acceptance is decided solely by that
module's own `assess_review`; this script only renders whatever status it
returns and never claims acceptance on the reviewer's behalf.
"""
import argparse
import html
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from scripts import schedule_layout as sl
except ModuleNotFoundError:
    import schedule_layout as sl

ROOT = sl.ROOT
SOURCE_PATH = ROOT / 'data/discovery/rti-2005-pdf.body'
DEFAULT_OUTPUT_DIR = ROOT / 'data/import/schedule-viewer'

STATUS_TEXT = {
    'needs_independent_review': (
        'Implementation candidate — independent review pending.',
        'No independent reviewer has accepted this layout yet. Treat everything '
        'below as an unreviewed implementation draft.'),
    'layout_reviewed_not_search_admitted': (
        'Independently reviewed layout — not search-admitted.',
        'A separate reviewer accepted this exact layout with no findings. This '
        'still grants no search admission, no public reuse permission, and no '
        'claim that the wording shown is legally current.'),
    'changes_requested': (
        'Independent reviewer requested changes.',
        'The bound review record raised findings against this exact artifact. '
        'See the findings listed below; do not treat this candidate as accepted.'),
    'invalid_review_binding': (
        'Review report present but does not match this artifact — treated as pending.',
        'The supplied review file does not bind to this artifact/profile/source '
        'digest, so it cannot certify anything about it.'),
    'invalid_review_provenance': (
        'Review report present but its reviewer provenance is invalid — treated as pending.',
        'The supplied review file does not declare an independent reviewer, so '
        'it cannot certify anything about this artifact.'),
    'invalid_review_decision': (
        'Review report present but its decision is unrecognized — treated as pending.',
        'The supplied review file bound correctly but its decision/findings shape '
        'is not one this tool recognizes as acceptance or change request.'),
}


class ViewerError(ValueError):
    pass


def load_json(path, what):
    try:
        return json.loads(path.read_text())
    except OSError as exc:
        raise ViewerError(f'cannot read {what}: {exc}') from exc
    except json.JSONDecodeError as exc:
        raise ViewerError(f'{what} is not valid JSON: {exc}') from exc


REQUIRED_ARTIFACT_KEYS = {
    'schema_version', 'parser_version', 'source_sha256', 'profile_sha256',
    'source_capture', 'source_path', 'coordinate_system', 'pages',
    'search_admitted', 'limitations',
}


def verify_artifact(candidate):
    """Revalidate a supplied artifact against a fresh model of the current
    retained source and layout profile. Never reads source_path from the
    candidate; the retained source is always the fixed repository path."""
    if not isinstance(candidate, dict) or not REQUIRED_ARTIFACT_KEYS <= candidate.keys():
        raise ViewerError('artifact does not have the expected schedule layout shape')
    if candidate.get('schema_version') != 1 or candidate.get('parser_version') != sl.PARSER_VERSION:
        raise ViewerError('unsupported artifact schema/parser version')
    if candidate.get('search_admitted') is not False:
        raise ViewerError('artifact claims search admission; refusing to display')
    profile = load_json(sl.DEFAULT_PROFILE, 'layout profile')
    raw = SOURCE_PATH.read_bytes()
    fresh = sl.parse(raw, profile)
    if sl.artifact_digest(fresh) != sl.artifact_digest(candidate):
        raise ViewerError(
            'supplied artifact differs from a fresh model of the current source/profile; '
            'rebuild with scripts/schedule_layout.py')
    return fresh, raw


def render_page_images(raw, out_dir):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pdf_path = tmp_path / 'source.pdf'
        pdf_path.write_bytes(raw)
        prefix = tmp_path / 'page'
        try:
            subprocess.run(['pdftoppm', '-f', '23', '-l', '24', '-r', '150', '-png',
                             str(pdf_path), str(prefix)],
                            check=True, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ViewerError(f'could not render source page images: {exc}') from exc
        for page in (23, 24):
            rendered = tmp_path / f'page-{page}.png'
            if not rendered.exists():
                raise ViewerError(f'expected rendered image for page {page} was not produced')
            shutil.copyfile(rendered, out_dir / f'page-{page}.png')


def esc(text):
    return html.escape(text, quote=True)


def safe_json_for_script(data):
    """Serialize JSON for embedding in a <script type="application/json">
    element without ever letting extracted text be interpreted as markup or
    break out of the script element, including via a literal closing tag."""
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return (encoded.replace('&', '\\u0026')
                    .replace('<', '\\u003c')
                    .replace('>', '\\u003e'))


def word_index(page):
    return {w['id']: w for w in page['words']}


def group_index(page):
    return {g['id']: g for g in page['groups']}


def page_svg(page, note_of_word):
    word_role = {}
    for g in page['groups']:
        for wid in g['word_ids']:
            word_role[wid] = g['role']
    parts = [
        f'<svg class="schedule-svg" viewBox="0 0 {page["width"]:.2f} {page["height"]:.2f}" '
        f'role="img" aria-label="{esc("Word positions for retained source page " + str(page["page"]))}">'
    ]
    for g in page['groups']:
        x0, y0, x1, y1 = g['bbox']
        # A partial amendment must never shade the whole containing entry.
        notes = sorted(set.intersection(*(set(note_of_word.get(w, ())) for w in g['word_ids'])))
        note_attr = f' data-note="{esc(",".join(notes))}"' if notes else ''
        parts.append(
            f'<rect class="group-box role-{esc(g["role"])}" data-group="{esc(g["id"])}"{note_attr} '
            f'x="{x0:.2f}" y="{y0:.2f}" width="{(x1 - x0):.2f}" height="{(y1 - y0):.2f}"/>')
    for w in page['words']:
        x0, y0, x1, y1 = w['bbox']
        font_size = max(4.0, (y1 - y0))
        baseline = y1 - (y1 - y0) * 0.15
        notes = sorted(note_of_word.get(w['id'], ()))
        note_attr = f' data-note="{esc(",".join(notes))}"' if notes else ''
        role = word_role.get(w['id'], '')
        parts.append(
            f'<text class="word role-{esc(role)}" data-word="{esc(w["id"])}"{note_attr} '
            f'x="{x0:.2f}" y="{baseline:.2f}" font-size="{font_size:.2f}">{esc(w["text"])}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def notes_of_words_for_page24(page, relations):
    groups = group_index(page)
    note_of_word = {}
    for r in relations:
        note = r['note_id']
        note_of_word.setdefault(r['marker_word_id'], set()).add(note)
        for wid in r['affected_word_ids']:
            note_of_word.setdefault(wid, set()).add(note)
    for g in groups.values():
        if g['role'] == 'footnote':
            note = g['id']
            for wid in g['word_ids']:
                note_of_word.setdefault(wid, set()).add(note)
    return note_of_word


def group_text(page, group_id):
    words = word_index(page)
    groups = group_index(page)
    return ' '.join(words[w]['text'] for w in groups[group_id]['word_ids'])


def build_first_schedule_section(page23):
    groups = group_index(page23)
    prefix = esc(group_text(page23, 'prefix'))
    oath = esc(group_text(page23, 'oath'))
    affirmation = esc(group_text(page23, 'affirmation'))
    continuation = esc(group_text(page23, 'continuation'))
    svg = page_svg(page23, {})
    return f'''
<section aria-labelledby="first-schedule-heading">
  <h2 id="first-schedule-heading">First Schedule &mdash; form of oath or affirmation</h2>
  <p>The source prints two mutually exclusive alternatives inside one shared sentence.
  Neither is shown as a default; both are printed exactly as extracted, with the shared
  wording that surrounds them.</p>
  <p><strong>Shared prefix:</strong> {prefix}</p>
  <div class="alternatives">
    <div class="alt-box" data-group="oath">
      <h3>Alternative 1 &mdash; oath</h3>
      <p class="alt-text"><strong>{oath}</strong></p>
    </div>
    <div class="alt-box" data-group="affirmation">
      <h3>Alternative 2 &mdash; affirmation</h3>
      <p class="alt-text"><strong>{affirmation}</strong></p>
    </div>
  </div>
  <p><strong>Shared continuation:</strong> {continuation}</p>
  <p class="note">These two panels are separate presentational alternatives built only from
  the model's own word groups; they are not a merged paragraph and not a synthesized oath.
  The shared "that I will&hellip;" continuation is printed once, starting on the oath's own
  printed line, and belongs to both alternatives equally.</p>
  <figure>
    <figcaption>Word positions, retained source page 23 (SVG; not a font/graphic reconstruction)</figcaption>
    {svg}
  </figure>
  <figure>
    <figcaption>Source page image, retained source page 23 (visual reference)</figcaption>
    <img src="page-23.png" alt="Scanned retained source, page 23" class="page-image">
  </figure>
  <p><a href="schedule.pdf#page=23">Open the private byte-identical PDF copy at page 23</a></p>
</section>
'''


def build_second_schedule_section(page24, relations):
    groups = group_index(page24)
    entry_ids = [f'entry-{i}' for i in range(1, 28)]
    note_ids = [f'note-{i}' for i in range(1, 12)]
    note_of_word = notes_of_words_for_page24(page24, relations)
    rel_by_note = {}
    for r in relations:
        rel_by_note.setdefault(r['note_id'], []).append(r)

    omission_text = esc(group_text(page24, 'omitted-block'))
    entry_rows = []
    for eid in entry_ids:
        text = esc(group_text(page24, eid))
        entry_rows.append(f'<li data-group="{esc(eid)}"><span class="entry-text">{text}</span></li>')
        if eid == 'entry-21':
            entry_rows.append(f'</ol><div class="omission" data-group="omitted-block">'
                              f'<h3>Separate omitted block (unnumbered, follows serial 21)</h3>'
                              f'<p class="entry-text">{omission_text}</p></div><ol class="entries" start="22">')
    omission_text = esc(group_text(page24, 'omitted-block'))

    note_buttons = []
    for nid in note_ids:
        label = esc(group_text(page24, nid))
        scopes = sorted({g for r in rel_by_note.get(nid, []) for g in r['scope_groups']})
        note_buttons.append(
            f'<li><button type="button" class="note-toggle" data-note="{esc(nid)}" '
            f'aria-pressed="false">Highlight {esc(nid)}</button> '
            f'<span class="note-text">{label}</span> '
            f'<span class="note-scope">(refers to {esc(", ".join(scopes))})</span></li>')

    svg = page_svg(page24, note_of_word)
    data = {
        'notes': note_ids,
        'relations': [
            {'note_id': r['note_id'], 'marker_word_id': r['marker_word_id'],
             'scope_groups': r['scope_groups'], 'affected_word_ids': r['affected_word_ids']}
            for r in relations
        ],
    }
    return f'''
<section aria-labelledby="second-schedule-heading">
  <h2 id="second-schedule-heading">Second Schedule</h2>
  <p>All 27 printed serial positions, in original order and wording. Brackets and
  omission marks are preserved exactly as extracted; nothing is renumbered or
  interpreted as currently in force.</p>
  <ol class="entries">
    {''.join(entry_rows)}
  </ol>
  <h3>Footnotes (select to highlight matching source markers and affected words)</h3>
  <ul class="notes">
    {''.join(note_buttons)}
  </ul>
  <figure>
    <figcaption>Word positions, retained source page 24 (SVG; not a font/graphic reconstruction)</figcaption>
    {svg}
  </figure>
  <figure>
    <figcaption>Source page image, retained source page 24 (visual reference)</figcaption>
    <img src="page-24.png" alt="Scanned retained source, page 24" class="page-image">
  </figure>
  <p><a href="schedule.pdf#page=24">Open the private byte-identical PDF copy at page 24</a></p>
  <script id="viewer-data-p24" type="application/json">{safe_json_for_script(data)}</script>
</section>
'''


STYLE = '''
:root{color-scheme:light;background:#fff;color:#111;font-family:system-ui,sans-serif;line-height:1.45}
body{margin:0 auto;max-width:920px;padding:1.5rem;}
.status-banner{border:2px solid;border-radius:.5rem;padding:.75rem 1rem;margin-bottom:1rem}
.status-pending{border-color:#a66a00;background:#fff6e5}
.status-accepted{border-color:#1a7f37;background:#e9f9ee}
.status-changes,.status-invalid{border-color:#b31d28;background:#fdeef0}
figure{margin:1rem 0}
.schedule-svg{width:100%;border:1px solid #888;background:#fff}
.page-image{max-width:100%;border:1px solid #888}
.word{fill:#111}
.word.role-nonlegal_watermark{fill:#999;font-style:italic}
.group-box{fill:transparent;stroke:transparent}
.group-box[data-note].note-active{fill:#ffe36699;stroke:#a66a00}
.word[data-note].note-active{fill:#a66a00;font-weight:700}
.alternatives{display:flex;gap:1rem;flex-wrap:wrap}
.alt-box{border:1px solid #888;border-radius:.4rem;padding:.75rem;flex:1 1 300px}
.entries{list-style:none;padding-left:0}
.entries li,.notes li{margin:.35rem 0}
.note-toggle{cursor:pointer}
.note-toggle[aria-pressed="true"]{outline:3px solid #a66a00}
.legend{font-size:.9rem;border-top:1px solid #888;margin-top:2rem;padding-top:1rem}
'''

SCRIPT = '''
document.addEventListener('click', function (ev) {
  var btn = ev.target.closest('.note-toggle');
  if (!btn) return;
  var note = btn.getAttribute('data-note');
  var nowActive = btn.getAttribute('aria-pressed') !== 'true';
  document.querySelectorAll('.note-toggle').forEach(function (b) {
    b.setAttribute('aria-pressed', 'false');
  });
  document.querySelectorAll('[data-note]').forEach(function (el) {
    el.classList.remove('note-active');
  });
  if (nowActive) {
    btn.setAttribute('aria-pressed', 'true');
    var selector = '[data-note]';
    document.querySelectorAll(selector).forEach(function (el) {
      var notes = (el.getAttribute('data-note') || '').split(',');
      if (notes.indexOf(note) !== -1) el.classList.add('note-active');
    });
  }
});
'''


def build_html(artifact, review, status, digest):
    title = 'RTI Act 2005 — schedule layout review (private, non-search-admitted)'
    banner_class, (headline, detail) = {
        'needs_independent_review': ('status-pending', STATUS_TEXT['needs_independent_review']),
        'layout_reviewed_not_search_admitted': ('status-accepted', STATUS_TEXT['layout_reviewed_not_search_admitted']),
        'changes_requested': ('status-changes', STATUS_TEXT['changes_requested']),
        'invalid_review_binding': ('status-invalid', STATUS_TEXT['invalid_review_binding']),
        'invalid_review_provenance': ('status-invalid', STATUS_TEXT['invalid_review_provenance']),
        'invalid_review_decision': ('status-invalid', STATUS_TEXT['invalid_review_decision']),
    }[status]
    findings_html = ''
    if review and status == 'changes_requested':
        findings = review.get('findings') or []
        items = ''.join(f'<li>{esc(json.dumps(f, ensure_ascii=False))}</li>' for f in findings)
        findings_html = f'<h3>Reviewer findings</h3><ul>{items}</ul>' if items else ''

    disclosure_html = ''
    if isinstance(review, dict) and isinstance(review.get('reviewer'), dict):
        reviewer = review['reviewer']
        disclosure = {key: reviewer.get(key, 'not supplied') for key in
                      ('id', 'type', 'independent_of_implementation', 'independent_legal_expert')}
        disclosure_html = ('<p>Supplied reviewer disclosure (self-declared, not credential verification): '
                           '<code>' + esc(json.dumps(disclosure, ensure_ascii=False)) + '</code></p>')
    page23, page24 = artifact['pages']
    body = (
        build_first_schedule_section(page23) +
        build_second_schedule_section(page24, page24['relations'])
    )
    limitations = ''.join(f'<li>{esc(item)}</li>' for item in artifact['limitations'])
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{STYLE}</style>
</head>
<body>
<h1>{esc(title)}</h1>
<div class="status-banner {banner_class}" role="status">
  <p><strong>{esc(headline)}</strong></p>
  <p>{esc(detail)}</p>
  <p>Artifact digest: <code>{esc(digest)}</code>. Source capture: <code>{esc(artifact["source_capture"])}</code>,
  pages 23&ndash;24, source SHA-256 <code>{esc(artifact["source_sha256"])}</code>.</p>
  {disclosure_html}
  {findings_html}
</div>
{body}
<section class="legend">
  <h2>Legend and limitations</h2>
  <ul>{limitations}</ul>
  <p>This viewer is local presentation tooling for source review. It is not a search
  result, not a public page, and not a determination that any shown text is legally
  current. The SVG word layer shows the model's own extracted words at their original
  PDF-point positions and does not recreate every font, rule, or graphic; the page
  image and the linked byte-identical PDF copy are the actual visual reference. The
  diagonal background watermark (shown faint and italic) is stored only as
  axis-aligned per-word boxes, so its rotated letters appear as separate stacked
  boxes in the SVG layer rather than as a diagonal line; the page image shows its
  true appearance.</p>
</section>
<script>{SCRIPT}</script>
</body>
</html>
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True,
                         help='path to a schedule_layout.py artifact JSON file')
    parser.add_argument('--review', type=Path,
                         help='optional path to a separately authored independent review report')
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT_DIR,
                         help='directory to write the private local viewer into')
    args = parser.parse_args(argv)
    try:
        candidate = load_json(args.artifact, 'schedule artifact')
        fresh, raw = verify_artifact(candidate)
        review = load_json(args.review, 'independent review report') if args.review else None
        status = sl.assess_review(fresh, review)
        digest = sl.artifact_digest(fresh)
        out_dir = args.output_dir / digest
        out_dir.mkdir(parents=True, exist_ok=True)
        render_page_images(raw, out_dir)
        (out_dir / 'schedule.pdf').write_bytes(raw)
        html_path = out_dir / 'index.html'
        html_path.write_text(build_html(fresh, review, status, digest), encoding='utf-8')
        print(json.dumps(dict(viewer=str(html_path), artifact_sha256=digest,
                               review_status=status, search_admitted=False)))
        return 0
    except (ViewerError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f'render_schedule_review: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
