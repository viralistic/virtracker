#!/usr/bin/env python3
"""Embed the client-facing report cover pages (front + closing) into index.html
as CSS custom properties holding base64 data URIs, so the report stays a single
self-contained file.

Usage:
    python3 scripts/embed_report_art.py FRONT.(jpg|png) CLOSING.(jpg|png)

Get the images from the brand PDFs, e.g.:
    pdftoppm -jpeg -r 150 -f 1 -l 1 "Front page SEO Rapport.pdf" front
    pdftoppm -jpeg -r 150 -f 1 -l 1 "Closing Page SEO rapport.pdf" closing
    python3 scripts/embed_report_art.py front-1.jpg closing-1.jpg
"""
import base64
import mimetypes
import re
import sys
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / 'index.html'


def data_uri(path):
    mime = mimetypes.guess_type(path)[0] or 'image/jpeg'
    b64 = base64.b64encode(Path(path).read_bytes()).decode('ascii')
    return f'data:{mime};base64,{b64}'


def main(front, closing):
    front_uri = data_uri(front)
    closing_uri = data_uri(closing)
    block = (':root{--front-art:url(' + front_uri + ');'
             '--closing-art:url(' + closing_uri + ');}')
    html = INDEX.read_text()
    new_html, n = re.subn(
        r'(<style id="report-art">).*?(</style>)',
        lambda m: m.group(1) + block + m.group(2),
        html, count=1, flags=re.S)
    if n != 1:
        sys.exit('Could not find <style id="report-art"> in index.html')
    INDEX.write_text(new_html)
    kb = (len(front_uri) + len(closing_uri)) / 1024
    print(f'Embedded front ({front}) + closing ({closing}) cover art '
          f'({kb:.0f} KB base64) into {INDEX.name}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
