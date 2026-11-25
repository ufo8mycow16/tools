"""EPUB reader (standard library only - no extra installs).

read_epub(path) -> {
    'title', 'author', 'description', 'language', 'series',
    'cover': (bytes, '.jpg') or None,
    'chapters': [{'title', 'kind': 'chapter'|'front'|'back', 'blocks': [{'kind': 'p'|'h'|'break', 'text'}]}],
}
Works for EPUB 2 (toc.ncx) and EPUB 3 (nav.xhtml). Front/back matter (copyright, contents, about the author,
"also by", excerpts...) is marked so the app leaves it out of the audiobook unless Glen ticks it back in.
"""
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile

from .textproc import normalise, is_scene_break

NS = {
    'c': 'urn:oasis:names:tc:opendocument:xmlns:container',
    'opf': 'http://www.idpf.org/2007/opf',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'ncx': 'http://www.daisy.org/z3986/2005/ncx/',
    'xhtml': 'http://www.w3.org/1999/xhtml',
    'epub': 'http://www.idpf.org/2007/ops',
}

FRONT_WORDS = ('copyright', 'contents', 'table of contents', 'title page', 'titlepage', 'half title', 'dedication',
               'epigraph', 'cover', 'also by', 'books by', 'other books', 'praise for', 'acknowledg', 'map',
               'dramatis personae', 'cast of characters', 'historian', 'timeline', 'about the publisher', 'imprint',
               'colophon', 'frontmatter', 'front matter')
BACK_WORDS = ('about the author', 'about the authors', 'afterword by', 'excerpt', 'preview', 'coming soon',
              'look for', 'sneak peek', 'newsletter', 'backmatter', 'back matter', 'notes on the', 'bibliography',
              'index', 'advertisement', 'ad card')

BLOCK_TAGS = {'p', 'div', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre', 'dd', 'dt', 'td', 'figcaption',
              'section', 'article', 'header', 'footer', 'aside'}
SKIP_TAGS = {'script', 'style', 'head', 'title', 'svg', 'math', 'nav'}


class _Blocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.buf = []
        self.kind = 'p'
        self.skip = 0
        self.sup = 0
        self.headings = []

    def _flush(self):
        text = normalise(''.join(self.buf))
        self.buf = []
        if not text:
            return
        if is_scene_break(text):
            self.blocks.append({'kind': 'break', 'text': ''})
        else:
            self.blocks.append({'kind': self.kind, 'text': text})
        self.kind = 'p'

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP_TAGS:
            self.skip += 1
            return
        if a.get('epub:type', '') in ('footnote', 'endnote', 'pagebreak', 'noteref') or \
                'pagebreak' in (a.get('role', '') or ''):
            if tag not in ('br', 'hr', 'img'):
                self.skip += 1
                self._skipped_tag = tag
            return
        if tag == 'sup':
            self.sup += 1
        if tag in BLOCK_TAGS:
            self._flush()
            if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                self.kind = 'h'
        elif tag == 'br':
            self.buf.append(' ')
        elif tag == 'hr':
            self._flush()
            if not self.blocks or self.blocks[-1]['kind'] != 'break':
                self.blocks.append({'kind': 'break', 'text': ''})

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS or (self.skip and getattr(self, '_skipped_tag', None) == tag):
            self.skip = max(0, self.skip - 1)
            return
        if tag == 'sup':
            self.sup = max(0, self.sup - 1)
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self.skip:
            return
        if self.sup and re.fullmatch(r'\s*[\d*†‡]+\s*', data):
            return  # footnote markers
        self.buf.append(data)

    def close(self):
        super().close()
        self._flush()


def html_blocks(html):
    p = _Blocks()
    try:
        p.feed(html)
        p.close()
    except Exception:
        pass
    # merge "kind=h" runs ("Chapter 1" + "The Bridge") into one heading
    out = []
    for b in p.blocks:
        if b['kind'] == 'h' and out and out[-1]['kind'] == 'h' and len(out[-1]['text']) < 40:
            out[-1]['text'] += ': ' + b['text']
        else:
            out.append(b)
    while out and out[0]['kind'] == 'break':
        out.pop(0)
    while out and out[-1]['kind'] == 'break':
        out.pop()
    return out


def _read(z, name):
    try:
        return z.read(name)
    except KeyError:
        # some books have different case in the manifest than in the zip
        low = {n.lower(): n for n in z.namelist()}
        return z.read(low[name.lower()])


def _text(el):
    return normalise(''.join(el.itertext())) if el is not None else ''


def _decode(raw):
    for enc in ('utf-8', 'utf-16', 'cp1252', 'latin-1'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'replace')


def classify(title, blocks, position, count):
    t = (title or '').lower()
    words = sum(len(b['text'].split()) for b in blocks)
    first = ' '.join(b['text'] for b in blocks[:6]).lower()
    if any(w in t for w in BACK_WORDS) and position > count * 0.6:
        return 'back'
    if any(w in t for w in FRONT_WORDS) and position < count * 0.4:
        return 'front'
    if words < 120 and position < count * 0.25:
        if any(w in first for w in ('copyright', 'all rights reserved', 'isbn', 'published by', 'printed in',
                                    'this book is a work of fiction', 'for ', 'to my', 'contents')):
            return 'front'
    if words < 400 and position > count * 0.8 and any(w in first for w in ('about the author', 'also by',
                                                                           'excerpt', 'turn the page')):
        return 'back'
    if 'all rights reserved' in first or ('isbn' in first and words < 600):
        return 'front'
    return 'chapter'


def read_epub(path):
    with zipfile.ZipFile(path) as z:
        container = ET.fromstring(_read(z, 'META-INF/container.xml'))
        rootfile = container.find('.//c:rootfile', NS).get('full-path')
        base = posixpath.dirname(rootfile)
        opf = ET.fromstring(_read(z, rootfile))

        def full(href):
            return posixpath.normpath(posixpath.join(base, unquote(href.split('#')[0]))) if href else ''

        md = opf.find('opf:metadata', NS)
        title = _text(md.find('dc:title', NS)) if md is not None else ''
        author = ', '.join(_text(e) for e in md.findall('dc:creator', NS)) if md is not None else ''
        description = _text(md.find('dc:description', NS)) if md is not None else ''
        if '<' in description:
            description = ' '.join(b['text'] for b in html_blocks(description))
        language = _text(md.find('dc:language', NS)) if md is not None else 'en'
        series, cover_id = '', ''
        if md is not None:
            for m in md.findall('opf:meta', NS):
                if m.get('name') == 'calibre:series':
                    series = m.get('content', '')
                if m.get('name') == 'cover':
                    cover_id = m.get('content', '')
                if m.get('property') == 'belongs-to-collection':
                    series = series or (m.text or '')

        manifest = {}
        for it in opf.findall('opf:manifest/opf:item', NS):
            manifest[it.get('id')] = {'href': full(it.get('href')), 'type': it.get('media-type', ''),
                                      'props': it.get('properties', '')}

        # cover picture
        cover = None
        cover_href = ''
        for iid, it in manifest.items():
            if 'cover-image' in it['props']:
                cover_href = it['href']
        if not cover_href and cover_id in manifest:
            cover_href = manifest[cover_id]['href']
        if not cover_href:
            for iid, it in manifest.items():
                if it['type'].startswith('image/') and 'cover' in (iid + it['href']).lower():
                    cover_href = it['href']
                    break
        if cover_href:
            try:
                cover = (_read(z, cover_href), PurePosixPath(cover_href).suffix.lower() or '.jpg')
            except Exception:
                cover = None

        # titles from the table of contents
        toc = {}
        nav = next((it for it in manifest.values() if 'nav' in it['props'].split()), None)
        if nav:
            try:
                root = ET.fromstring(_read(z, nav['href']))
                nav_base = posixpath.dirname(nav['href'])
                for navel in root.iter('{%s}nav' % NS['xhtml']):
                    if navel.get('{%s}type' % NS['epub'], 'toc') != 'toc':
                        continue
                    for a in navel.iter('{%s}a' % NS['xhtml']):
                        href = posixpath.normpath(posixpath.join(nav_base, unquote(a.get('href', '').split('#')[0])))
                        toc.setdefault(href, _text(a))
            except Exception:
                pass
        if not toc:
            spine_el = opf.find('opf:spine', NS)
            ncx_id = spine_el.get('toc') if spine_el is not None else None
            ncx = manifest.get(ncx_id) or next((it for it in manifest.values()
                                                if it['type'] == 'application/x-dtbncx+xml'), None)
            if ncx:
                try:
                    root = ET.fromstring(_read(z, ncx['href']))
                    ncx_base = posixpath.dirname(ncx['href'])
                    for np_ in root.iter('{%s}navPoint' % NS['ncx']):
                        label = np_.find('ncx:navLabel/ncx:text', NS)
                        content = np_.find('ncx:content', NS)
                        if content is not None:
                            href = posixpath.normpath(posixpath.join(ncx_base, unquote(content.get('src', '').split('#')[0])))
                            toc.setdefault(href, _text(label))
                except Exception:
                    pass

        spine = [manifest[i.get('idref')] for i in opf.findall('opf:spine/opf:itemref', NS)
                 if i.get('idref') in manifest and i.get('linear', 'yes') != 'no']
        spine = [s for s in spine if 'html' in s['type'] or s['href'].lower().endswith(('.html', '.xhtml', '.htm'))]

        raw = []
        for s in spine:
            try:
                blocks = html_blocks(_decode(_read(z, s['href'])))
            except Exception:
                continue
            title_ = toc.get(s['href'], '')
            if not title_:
                h = next((b['text'] for b in blocks[:3] if b['kind'] == 'h'), '')
                title_ = h
            raw.append({'title': title_, 'blocks': blocks, 'href': s['href'], 'in_toc': s['href'] in toc})

    # a spine file that isn't in the table of contents is usually a continuation of the one before it
    chapters = []
    for r in raw:
        if not r['blocks']:
            continue
        if chapters and not r['in_toc'] and toc and chapters[-1]['kind'] != 'front' and \
                sum(len(b['text'].split()) for b in r['blocks']) > 0 and not r['title']:
            chapters[-1]['blocks'].append({'kind': 'break', 'text': ''})
            chapters[-1]['blocks'].extend(r['blocks'])
            continue
        chapters.append({'title': r['title'], 'blocks': r['blocks'], 'kind': 'chapter'})

    n = len(chapters)
    for i, c in enumerate(chapters):
        c['kind'] = classify(c['title'], c['blocks'], i, n)
        if not c['title']:
            c['title'] = f'Part {i + 1}'
        # the chapter heading itself is read out once, as a heading
        if c['blocks'] and c['blocks'][0]['kind'] != 'h' and c['kind'] == 'chapter':
            c['blocks'].insert(0, {'kind': 'h', 'text': c['title']})
    if not title:
        title = PurePosixPath(str(path)).stem
    return {'title': title, 'author': author, 'description': description, 'language': language or 'en',
            'series': series, 'cover': cover, 'chapters': chapters}
