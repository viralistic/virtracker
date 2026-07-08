#!/usr/bin/env python3
"""Refresh the data embedded in index.html from a CSV export of the
"Snapshots" tab of the "SEO Rapporting" Google Sheet.

Usage:
    python3 scripts/refresh_data.py path/to/snapshots.csv

Get the CSV: open the sheet, select the Snapshots tab, then
File -> Download -> Comma Separated Values (.csv).
"""
import csv
import datetime
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

SHEET_URL = 'https://docs.google.com/spreadsheets/d/1lTLFb-eC4ElEpzX684X-XQvJTNBPR7Jv0D1WGKnqH7E/edit?gid=380445228'
INDEX = Path(__file__).resolve().parent.parent / 'index.html'


def num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def parse_date(v):
    """Accept ISO datetimes/dates or Excel/Sheets serial numbers."""
    v = (v or '').strip()
    m = re.match(r'(\d{4}-\d{2}-\d{2})', v)
    if m:
        return m.group(1)
    serial = num(v)
    if serial is None:
        raise ValueError(f'unparseable runDate: {v!r}')
    return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(serial))).isoformat()


def site_of(url):
    try:
        return (urlparse(url).hostname or '').removeprefix('www.')
    except ValueError:
        return ''


def main(csv_path):
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    flags = [r for r in rows if r.get('rowType') == 'flag']
    summaries = [r for r in rows if r.get('rowType') == 'summary']
    if not flags:
        sys.exit('No flag rows found — is this a CSV export of the Snapshots tab?')

    dates = sorted({parse_date(r['runDate']) for r in rows if r.get('runDate')})
    sites = [s for s, _ in Counter(site_of(r['page']) for r in flags).most_common() if s]

    daily = {d: {'scanned': 0, 'flagged': 0} for d in dates}
    for r in summaries:
        d = parse_date(r['runDate'])
        daily[d]['scanned'] += int(num(r.get('pagesScanned'), 0))
        daily[d]['flagged'] += int(num(r.get('pagesFlagged'), 0))

    counts = defaultdict(lambda: defaultdict(Counter))
    for r in flags:
        counts[parse_date(r['runDate'])][site_of(r['page'])][r['flag']] += 1

    latest = dates[-1]
    latest_flags = []
    for r in flags:
        if parse_date(r['runDate']) != latest:
            continue
        latest_flags.append({
            'page': r['page'], 'site': site_of(r['page']), 'flag': r['flag'],
            'clicks': num(r.get('clicks'), 0), 'impressions': num(r.get('impressions'), 0),
            'ctr': num(r.get('ctr'), 0), 'position': num(r.get('position')),
            'prevClicks': num(r.get('prevClicks')), 'prevPosition': num(r.get('prevPosition')),
            'clickPct': num(r.get('clickPct')), 'imprPct': num(r.get('imprPct')),
            'posDelta': num(r.get('posDelta')), 'severity': int(num(r.get('severity'), 0)),
            'isNew': r.get('isNew') == '1',
        })

    types = [t for t, _ in Counter(r['flag'] for r in flags).most_common()]
    data = {
        'generatedAt': datetime.date.today().isoformat(),
        'sheetUrl': SHEET_URL,
        'dates': dates, 'sites': sites, 'types': types,
        'daily': [{'date': d, **daily[d]} for d in dates],
        'counts': [
            {'date': d, 'site': s, 'byType': dict(counts[d][s])}
            for d in dates for s in sites if counts[d][s]
        ],
        'latestDate': latest,
        'latestFlags': latest_flags,
    }

    payload = json.dumps(data, separators=(',', ':')).replace('</', r'<\/')
    html = INDEX.read_text()
    new_html, n = re.subn(
        r'(<script id="seo-data" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + payload + m.group(2),
        html, count=1, flags=re.S)
    if n != 1:
        sys.exit('Could not find the seo-data block in index.html')
    INDEX.write_text(new_html)
    print(f'Embedded {len(flags)} flags across {len(dates)} days '
          f'({dates[0]} -> {latest}) into {INDEX.name}')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
