#!/usr/bin/env python3
"""Refresh the data embedded in index.html from the "Snapshots" tab of the
"SEO Rapporting" Google Sheet.

Two ways to get the data in:

  1. CSV export (no credentials needed):
       python3 scripts/refresh_data.py path/to/snapshots.csv
     Get the CSV: open the sheet, select the Snapshots tab, then
     File -> Download -> Comma Separated Values (.csv).

  2. Google service account (no manual download):
       python3 scripts/refresh_data.py --service-account path/to/key.json
     The sheet must be shared (Viewer is enough) with the service account's
     client_email. Requires the `openssl` command (preinstalled on macOS and
     virtually every Linux) — no Python packages needed.

Options:
  --sheet-id ID     override the spreadsheet ID (defaults to the SEO
                    Rapporting sheet)
  --tab NAME        tab to read (default: Snapshots)
  --save-csv PATH   also write the fetched rows to a CSV file
"""
import argparse
import base64
import csv
import datetime
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

SHEET_ID = '1lTLFb-eC4ElEpzX684X-XQvJTNBPR7Jv0D1WGKnqH7E'
SHEET_URL = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid=380445228'
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


# ---------------------------------------------------------------------------
# Google service-account access (stdlib + openssl, no pip installs)
# ---------------------------------------------------------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def sign_jwt(sa: dict, scope: str) -> str:
    """Build and RS256-sign a service-account JWT using the openssl CLI."""
    now = int(time.time())
    header = {'alg': 'RS256', 'typ': 'JWT'}
    claims = {
        'iss': sa['client_email'],
        'scope': scope,
        'aud': sa.get('token_uri', 'https://oauth2.googleapis.com/token'),
        'iat': now,
        'exp': now + 3600,
    }
    signing_input = (_b64url(json.dumps(header).encode()) + '.' +
                     _b64url(json.dumps(claims).encode()))
    with tempfile.NamedTemporaryFile('w', suffix='.pem') as key_file:
        key_file.write(sa['private_key'])
        key_file.flush()
        try:
            proc = subprocess.run(
                ['openssl', 'dgst', '-sha256', '-sign', key_file.name],
                input=signing_input.encode('ascii'),
                capture_output=True, check=True)
        except FileNotFoundError:
            sys.exit('openssl not found — install OpenSSL or use the CSV route instead.')
        except subprocess.CalledProcessError as e:
            sys.exit(f'openssl failed to sign the JWT: {e.stderr.decode().strip()}')
    return signing_input + '.' + _b64url(proc.stdout)


def get_access_token(sa: dict) -> str:
    token_uri = sa.get('token_uri', 'https://oauth2.googleapis.com/token')
    assertion = sign_jwt(sa, 'https://www.googleapis.com/auth/spreadsheets.readonly')
    body = urllib.parse.urlencode({
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': assertion,
    }).encode('ascii')
    req = urllib.request.Request(token_uri, data=body, method='POST',
                                 headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)['access_token']
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors='replace')
        sys.exit(f'Token exchange failed ({e.code}): {detail}\n'
                 'Check that the key file is a valid, non-revoked service-account key.')
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit(f'Could not reach {token_uri}: {getattr(e, "reason", e)} — '
                 'check your internet connection, or use the CSV route instead.')


def fetch_rows_via_service_account(key_path: str, sheet_id: str, tab: str):
    """Return the tab's rows as a list of dicts (header row -> keys)."""
    try:
        sa = json.loads(Path(key_path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f'Could not read service-account key {key_path}: {e}')
    for field in ('client_email', 'private_key'):
        if field not in sa:
            sys.exit(f'{key_path} is missing "{field}" — is this a service-account key JSON?')

    token = get_access_token(sa)
    url = (f'https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}'
           f'/values/{urllib.parse.quote(tab)}'
           '?valueRenderOption=UNFORMATTED_VALUE&majorDimension=ROWS')
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            values = json.load(resp).get('values', [])
    except urllib.error.HTTPError as e:
        if e.code == 403:
            sys.exit(f'403 from the Sheets API: {e.read().decode(errors="replace")}\n'
                     f'If the sheet is not shared with {sa["client_email"]}, share it '
                     '(Viewer) and try again; if the error says the API is disabled, '
                     "enable the Google Sheets API in the service account's Cloud project.")
        if e.code == 404:
            sys.exit(f'404 from the Sheets API — spreadsheet {sheet_id} or tab '
                     f'{tab!r} not found.')
        sys.exit(f'Sheets API error ({e.code}): {e.read().decode(errors="replace")}')
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit(f'Could not reach the Sheets API: {getattr(e, "reason", e)} — '
                 'check your internet connection, or use the CSV route instead.')

    if len(values) < 2:
        sys.exit(f'Tab {tab!r} came back empty.')

    def cell(v):
        if v is None:
            return ''
        if isinstance(v, bool):
            return '1' if v else '0'
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    header = [cell(h).strip() for h in values[0]]
    rows = []
    for raw in values[1:]:
        raw = list(raw) + [''] * (len(header) - len(raw))
        rows.append({h: cell(v) for h, v in zip(header, raw)})
    print(f'Fetched {len(rows)} rows from tab {tab!r} as {sa["client_email"]}')
    return rows


# ---------------------------------------------------------------------------
# Aggregation + embedding
# ---------------------------------------------------------------------------

def build_payload(rows):
    def has_date(r):
        return bool((r.get('runDate') or '').strip())

    flags = [r for r in rows if r.get('rowType') == 'flag' and has_date(r)]
    if not flags:
        sys.exit('No flag rows found — is this the Snapshots tab?')

    dates = sorted({parse_date(r['runDate']) for r in rows if has_date(r)})
    sites = [s for s, _ in Counter(site_of(r['page']) for r in flags).most_common() if s]

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
            # CSV exports of a boolean sheet column say TRUE/FALSE; the API route yields 1/0
            'isNew': str(r.get('isNew') or '').strip().upper() in ('1', '1.0', 'TRUE'),
        })

    # Per-page daily traffic. A page flagged twice on one day repeats the same
    # clicks/impressions, so keep the first row per (date, page).
    date_idx = {d: i for i, d in enumerate(dates)}
    page_idx = {}
    page_days = []
    seen = set()
    for r in flags:
        d = parse_date(r['runDate'])
        key = (d, r['page'])
        if key in seen:
            continue
        seen.add(key)
        pi = page_idx.setdefault(r['page'], len(page_idx))
        pos = num(r.get('position'))
        page_days.append([
            date_idx[d], pi,
            int(round(num(r.get('clicks'), 0))),
            int(round(num(r.get('impressions'), 0))),
            None if pos is None else round(pos, 1),
        ])
    page_days.sort(key=lambda t: (t[0], t[1]))

    types = [t for t, _ in Counter(r['flag'] for r in flags).most_common()]
    return {
        'generatedAt': datetime.date.today().isoformat(),
        'sheetUrl': SHEET_URL,
        'dates': dates, 'sites': sites, 'types': types,
        'counts': [
            {'date': d, 'site': s, 'byType': dict(counts[d][s])}
            for d in dates for s in sites if counts[d][s]
        ],
        'latestDate': latest,
        'latestFlags': latest_flags,
        'pages': list(page_idx),
        'pageDays': page_days,
    }


def embed(data, n_flags):
    payload = json.dumps(data, separators=(',', ':')).replace('</', r'<\/')
    html = INDEX.read_text()
    new_html, n = re.subn(
        r'(<script id="seo-data" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + payload + m.group(2),
        html, count=1, flags=re.S)
    if n != 1:
        sys.exit('Could not find the seo-data block in index.html')
    INDEX.write_text(new_html)
    print(f'Embedded {n_flags} flags across {len(data["dates"])} days '
          f'({data["dates"][0]} -> {data["latestDate"]}) into {INDEX.name}')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('csv', nargs='?', help='CSV export of the Snapshots tab')
    ap.add_argument('--service-account', metavar='KEY_JSON',
                    help='fetch directly from the Sheets API with this service-account key')
    ap.add_argument('--sheet-id', default=SHEET_ID)
    ap.add_argument('--tab', default='Snapshots')
    ap.add_argument('--save-csv', metavar='PATH',
                    help='also save the fetched rows as CSV (service-account mode)')
    args = ap.parse_args()

    if bool(args.csv) == bool(args.service_account):
        ap.error('pass either a CSV path or --service-account key.json (exactly one)')

    if args.service_account:
        rows = fetch_rows_via_service_account(args.service_account, args.sheet_id, args.tab)
        if args.save_csv and rows:
            fieldnames = list(rows[0].keys())
            with open(args.save_csv, 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows)
            print(f'Saved fetched rows to {args.save_csv}')
    else:
        with open(args.csv, newline='', encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))

    data = build_payload(rows)
    embed(data, sum(1 for r in rows if r.get('rowType') == 'flag'))


if __name__ == '__main__':
    main()
