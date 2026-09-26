"""Conservative candidate extraction. Agreement produces review candidates, NEVER admission."""
from html.parser import HTMLParser
from functools import lru_cache
import json
from pathlib import Path
import re
import subprocess
import tempfile
import hashlib

try:
    from scripts.acquire_phase3 import ROOT, DEST, atomic_json, value, sha, verify_acquisition
    from scripts.offline_importer import pdftotext_layout, strip_page_footers, strip_watermark
except ModuleNotFoundError:
    from acquire_phase3 import ROOT, DEST, atomic_json, value, sha, verify_acquisition
    from offline_importer import pdftotext_layout, strip_page_footers, strip_watermark

VERSION='phase3-html-pdf-agreement-v2'

# Typographic equivalence tier. Each normalization is applied to BOTH the HTML
# body and the PDF text, is enumerated by name, and is limited to differences
# of typography between the two official representations of the same words:
# dash and quote glyphs, ellipsis glyphs, footnote/amendment reference marks
# (numbered per page in the PDF, per section in the HTML), and hyphenation.
# Levels are cumulative; a candidate records the minimal level that aligns.
# Nothing here folds spelling, punctuation words, numbers or clause markers,
# and nothing here admits: the result is still a review candidate.
NORMALIZATIONS=[
    # A single hyphen directly after , : ; . is a dash in the HTML source
    # ("namely:-", "requires,-"), never a compound-word hyphen.
    ('dash',[(r'-{2,}|[\u2013\u2014\u2015]','\u2014'),(r'(?<=[,:;.])-(?=\s|\(|$)','\u2014'),(r'[\u2010\u2011\u2212]','-')]),
    ('quote',[(r'[\u201c\u201d\u201e\u201f]','"'),(r'[\u2018\u2019\u201a\u201b\u00b4]',"'")]),
    ('ellipsis',[(r'\u2026','...')]),
    # Reference marks: a 1-2 digit number glued to the end of a word/closing
    # bracket, a number (with optional space) directly before an amendment
    # bracket "[", or asterisks after a word. Numbers that stand alone
    # ("section 5", "Act 22", "2005") are untouched.
    ('marker',[(r'(?<=[A-Za-z\)\]"\'])\d{1,2}(?=[\s.,;:\)\]\[\*]|$)',''),(r'(?<!\w)\d{1,2}\s*(?=\[)',''),(r'(?<=[A-Za-z\)\]])\*+','')]),
    # Line-break hyphenation in the PDF ("sub- district") and compound
    # hyphenation differences ("sub-district"/"subdistrict"): letters only,
    # never digits, so "2-3" is not "23".
    ('hyphen',[(r'(?<=[A-Za-z])-\s*(?=[A-Za-z])','')]),
    # Whitespace before closing punctuation / after an opening bracket or
    # em-dash ("Court .]", "tribunal.— (1)", "1 * * *").
    ('punct-space',[(r'\s+(?=[.,;:\)\]\u2014\*])',''),(r'(?<=[\(\[\u2014])\s+','')]),
    # The list-introducing em-dash ("shall— (a)") that one representation
    # omits entirely. Last level, so its use is always visible.
    ('dash-drop',[(r'\u2014',' ')]),
    # Letter case ("Section 58"/"section 58") and spacing inside words
    # ("any place"/"anyplace", "29A.Time"). Symmetric; words and punctuation
    # are untouched, so these cannot equate different wording.
    ('case',[(r'[A-Z]',lambda m:m.group().lower())]),
    # Editorial apparatus one representation omits: the quote marks around a
    # defined term ('"copyright" means' / 'copyright means') and amendment
    # brackets. Marker numbers were already dropped at the marker level.
    ('quote-drop',[(r'"','')]),
    ('bracket-drop',[(r'[\[\]]','')]),
    ('space-drop',[(r'\s+','')]),
]
NORMALIZATION_NAMES=[name for name,_ in NORMALIZATIONS]
MARKER_LEVEL=NORMALIZATION_NAMES.index('marker')+1
FOOTNOTE_NUMBER=re.compile(r'(?:^|(?<=\s))\d{1,2}\.\s+(?=\S)')
FOOTNOTE_BLOCK=re.compile(r'^\s*\d{1,2}\.\s')
GAP_SKIP='footnote-block-skip'
SPACE_DROP_LEVEL=NORMALIZATION_NAMES.index('space-drop')+1
# With whitespace removed, a word boundary cannot be checked; uniqueness of
# the whole body still is, and short bodies are refused at that level.
SPACE_DROP_MIN_CHARS=25


def boundaries_checkable(level):return level<SPACE_DROP_LEVEL


def normalize(text,level):
    for name,rules in NORMALIZATIONS[:level]:
        for pattern,replacement in rules:text=re.sub(pattern,replacement,text)
    return text


@lru_cache(maxsize=256)
def normalized_pages(pages,level):
    """Normalized copy of a whole page tuple. Every provision of an Act is
    located in the same pages, so this is computed once per (pages, level)
    instead of once per provision; it is a pure function of its arguments."""
    return tuple(normalize(p,level) for p in pages)


@lru_cache(maxsize=256)
def compacted_pages(pages):
    return tuple(compact(p) for p in pages)

class LegalHTML(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True);self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag not in {'br','hr','span','i','b','sup','sub','p','div','strong','em','u','center'}:
            raise ValueError('unsupported legal HTML tag: '+tag)
        if tag in {'br','hr','p','div','center'}:self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag not in {'br','hr','span','i','b','sup','sub','p','div','strong','em','u','center'}:
            raise ValueError('unsupported closing tag: '+tag)
        if tag in {'p','div','center'}:self.parts.append('\n')
    def handle_data(self,data):self.parts.append(data)


def plain(html):
    parser=LegalHTML();parser.feed(html);parser.close()
    return re.sub(r'\n\s*\n+', '\n', re.sub(r'[ \t]+',' ',''.join(parser.parts))).strip()


def compact(text):return re.sub(r'\s+',' ',text).strip()


@lru_cache(maxsize=256)
def indexed_pages(pages):
    # Match entire text with whitespace folding only; preserve punctuation,
    # numbers, amendment markers, and spelling. Unique occurrence required.
    joined='\f'.join(pages)
    chars=[];mapping=[]
    for match in re.finditer(r'\S+|\s+',joined):
        part=' ' if match.group().isspace() else match.group()
        chars.extend(part);mapping.extend([match.start()]*len(part) if part==' ' else range(match.start(),match.end()))
    text=''.join(chars)
    return joined,text,mapping


def locate(body,pages,level=0,footnote=False):
    """Whole-body unique alignment. level=0 is exact (whitespace folding only);
    level=k applies the first k NORMALIZATIONS to both sides. Footnotes at or
    above the marker level also drop their leading footnote numbers, which the
    PDF assigns per page and the HTML per section."""
    if not compact(body):raise ValueError('empty body')
    if level:
        body=normalize(body,level);pages=normalized_pages(tuple(pages),level)
    if footnote and level>=MARKER_LEVEL:
        body=FOOTNOTE_NUMBER.sub('',body);pages=tuple(FOOTNOTE_NUMBER.sub('',p) for p in pages)
    joined,text,mapping=indexed_pages(tuple(pages))
    needle=compact(body)
    if not needle:raise ValueError('empty body')
    if text.find(needle[:40])<0:
        raise ValueError('section start absent from PDF text')
    if not boundaries_checkable(level) and len(needle)<SPACE_DROP_MIN_CHARS:
        raise ValueError('body too short for space-insensitive alignment')
    start=text.find(needle)
    if (start<0 or text.find(needle,start+1)>=0 or (boundaries_checkable(level) and (
        (start>0 and text[start-1].isalnum() and needle[0].isalnum()) or
        (start+len(needle)<len(text) and text[start+len(needle)].isalnum() and needle[-1].isalnum())))):raise ValueError('full body absent or not uniquely aligned to PDF')
    left=mapping[start];right=mapping[start+len(needle)-1]+1
    return dict(pdf_page_from=joined[:left].count('\f')+1,pdf_page_to=joined[:right].count('\f')+1,
                agreement='entire body, whitespace folding only' if not level else
                'entire body after typographic normalization: '+', '.join(NORMALIZATION_NAMES[:level]),
                normalization_level=level,normalizations=NORMALIZATION_NAMES[:level])


def locate_across_footnote_blocks(body,pages,level):
    """Whole-body alignment where the PDF layout interleaves a footnote block
    at a page break. Every character of the body must still match, in order;
    the only tolerance is a skipped run of text that (a) is the entire rest
    of a page and (b) starts like a footnote ("1. Ins. by ..."). Each skipped
    run is recorded for the reviewer. Uniqueness is required of the opening."""
    if level:body=normalize(body,level);pages=normalized_pages(tuple(pages),level)
    needle=compact(body);texts=compacted_pages(tuple(pages))
    if len(needle)<80:raise ValueError('body too short for page-break alignment')
    head=needle[:80]
    # The opening may be quoted again in a footnote ("for '(1) No enterprise
    # ...'"), so every occurrence is tried and exactly one complete match is
    # required.
    hits=[(i,m.start()) for i,t in enumerate(texts) for m in re.finditer(re.escape(head),t)]
    if not hits:raise ValueError('section opening absent from PDF')
    matches=[]
    for i,o in hits:
        try:matches.append(_follow(needle,texts,i,o,boundaries_checkable(level)))
        except ValueError:continue
    if len(matches)!=1:raise ValueError('full body absent or not uniquely aligned to PDF')
    return matches[0]


def _follow(needle,texts,i,o,check_boundaries=True):
    if check_boundaries and o>0 and texts[i][o-1].isalnum() and needle[0].isalnum():raise ValueError('section opening not on a word boundary')
    first=i;pos=0;gaps=[]
    while True:
        t=texts[i];n=0
        while pos+n<len(needle) and o+n<len(t) and needle[pos+n]==t[o+n]:n+=1
        if gaps and n<min(20,len(needle)-pos):raise ValueError('body does not resume at the next page start')
        pos+=n
        if pos==len(needle):
            if check_boundaries and o+n<len(t) and t[o+n].isalnum() and needle[-1].isalnum():raise ValueError('section end not on a word boundary')
            return dict(pdf_page_from=first+1,pdf_page_to=i+1,pdf_page_break_gaps=gaps)
        gap=t[o+n:].strip()
        if gap and (not FOOTNOTE_BLOCK.match(gap) or len(gap)>2500):raise ValueError('full body absent or not uniquely aligned to PDF')
        if pos<len(needle) and needle[pos]==' ':pos+=1
        if gap:gaps.append(dict(pdf_page=i+1,skipped_text=gap))
        i+=1;o=0
        if i>=len(texts):raise ValueError('body continues past the last PDF page')
        if len(gaps)>8:raise ValueError('too many page-break gaps')


def divergence(body,pages):
    """Where the HTML body and the PDF text first differ at the most tolerant
    level: a diagnostic for reviewers, never an alignment result."""
    level=len(NORMALIZATIONS)
    needle=compact(normalize(body,level));_,text,_=indexed_pages(normalized_pages(tuple(pages),level))
    lo,hi=0,len(needle)
    while lo<hi:
        mid=(lo+hi+1)//2
        if needle[:mid] in text:lo=mid
        else:hi=mid-1
    at=text.find(needle[:lo]) if lo else -1
    return dict(matched_chars=lo,body_chars=len(needle),
                html=needle[max(0,lo-40):lo+60],pdf=text[at+lo-40:at+lo+60] if at>=0 else None,
                note='first divergence after all typographic normalizations; the exact tier reason is authoritative')


def locate_minimal(body,pages):
    """Exact alignment first; otherwise the smallest cumulative normalization
    level that aligns; otherwise the same ladder allowing footnote-block
    skips at page breaks. The exact tier's error is reported if none does."""
    try:return locate(body,pages)
    except ValueError as exact_error:
        for level in range(1,len(NORMALIZATIONS)+1):
            try:return locate(body,pages,level)
            except ValueError:continue
        for level in range(0,len(NORMALIZATIONS)+1):
            try:
                found=locate_across_footnote_blocks(body,pages,level)
                return dict(found,agreement='entire body across PDF page-break footnote blocks'+(
                    ' after typographic normalization: '+', '.join(NORMALIZATION_NAMES[:level]) if level else ''),
                    normalization_level=level,normalizations=NORMALIZATION_NAMES[:level]+[GAP_SKIP])
            except ValueError:continue
        raise exact_error


def build(act):
    verify_acquisition(act)
    candidates=[]
    english=[pdf for pdf in act.get('pdfs',[]) if not pdf['name'].lower().startswith('h')]
    if len(english)!=1:raise ValueError('English PDF identity requires explicit review')
    pdf=english[0];raw=(DEST/'blobs'/(pdf['sha256']+'.body')).read_bytes()
    if sha(raw)!=pdf['sha256']:raise ValueError('PDF source changed')
    pages=[strip_watermark(p) for p in strip_page_footers(pdftotext_layout(raw))]
    for section in act['sections']:
        label=value(section,'dc.identifier.section_number')
        item=dict(key=act['slug']+':'+str(label),label=label,heading=value(section,'dc.title'),
                  source_item_uuid=section['uuid'],source_item_sha256=sha(json.dumps(section,sort_keys=True).encode()),
                  pdf_sha256=pdf['sha256'],parser_version=VERSION,search_admitted=False)
        body=''
        try:
            body=plain(value(section,'dc.identifier.section_page_note') or '')
            footnote=plain(value(section,'dc.identifier.section_footnote') or '')
            found=locate_minimal(body,pages)
            item.update(found,body_text_sha256=sha(body.encode()))
            footnote_level=None
            if footnote:
                # The footnote gets its own minimal level on the body's pages;
                # the candidate's level is the larger of the two.
                span=pages[item['pdf_page_from']-1:item['pdf_page_to']]
                for level in range(0,len(NORMALIZATIONS)+1):
                    try:locate(footnote,span,level,footnote=True);footnote_level=level;break
                    except ValueError:continue
                if footnote_level is None:
                    raise ValueError('body aligned but footnote text differs from the PDF footnote')
            level=max(found['normalization_level'],footnote_level or 0)
            item.update(normalization_level=level,normalizations=NORMALIZATION_NAMES[:level]+([GAP_SKIP] if GAP_SKIP in found['normalizations'] else []),
                        footnote_normalization_level=footnote_level,
                        status='agreement_review_pending' if not level and GAP_SKIP not in found['normalizations'] else 'typographic_agreement_review_pending',
                        body_text=body,footnote_text=footnote or None,
                        footnote_text_sha256=sha(footnote.encode()) if footnote else None)
        except ValueError as error:
            item.update(status='quarantined',reason=str(error))
            try:
                if compact(body):item['divergence']=divergence(body,pages)
            except (ValueError,NameError):pass
        candidates.append(item)
    return dict(slug=act['slug'],source_acquisition_sha256=sha(json.dumps(act,sort_keys=True).encode()),
                pdf=pdf,candidates=candidates,section_count=len(candidates),search_admitted=False)


def main():
    failures=0
    for path in sorted((DEST/'acts').glob('*.json')):
        act=json.loads(path.read_text())
        if act['status']!='captured_review_pending':continue
        try:
            report=build(act)
            atomic_json(ROOT/'data/phase3/candidates'/(act['slug']+'.json'),report)
            exact=sum(r['status']=='agreement_review_pending' for r in report['candidates'])
            typographic=sum(r['status']=='typographic_agreement_review_pending' for r in report['candidates'])
            print(act['slug'],'exact',exact,'typographic',typographic,'/',len(report['candidates']),flush=True)
        except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as error:
            failures+=1
            atomic_json(ROOT/'data/phase3/candidates'/(act['slug']+'.json'),dict(slug=act['slug'],status='parse_failed',reason=str(error),search_admitted=False))
            print(act['slug'],str(error),flush=True)

    return 1 if failures else 0

if __name__=='__main__':raise SystemExit(main())
