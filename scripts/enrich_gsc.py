#!/usr/bin/env python3
"""Enrich index.html with real Google Search Console data (clicks, impressions,
CTR, average position, top search queries and top pages) per tracked site, using
a service account. Merges a "gsc" block into the embedded dashboard data without
touching anything else, so it composes with refresh_data.py.

Usage:
    python3 scripts/enrich_gsc.py --key path/to/sa.json [options]

Setup (once per property): in Search Console → Settings → Users and permissions,
add the service account's client_email (…iam.gserviceaccount.com) as a user
(Restricted is enough). Do this for every property you want in the dashboard, or
grant one service account access to all of them.

The script auto-discovers which properties the service account can read and
matches them to the dashboard's sites by hostname (it tries sc-domain: and
https:// URL-prefix forms). Override the match with --map.

Options:
  --key KEY_JSON        service-account key (required)
  --days N              days of history to pull (default 90)
  --queries N           top search queries per site to keep (default 25)
  --pages N             top pages per site to keep (default 25)
  --map HOST=PROPERTY   force a site→property mapping (repeatable), e.g.
                        --map silverdrive.nl=sc-domain:silverdrive.nl
  --sites A,B,C         only these hostnames (default: all sites in index.html)
  --dry-run             print what would be fetched, write nothing
"""
import argparse
import datetime
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gauth import get_access_token, load_sa  # noqa: E402

INDEX = Path(__file__).resolve().parent.parent / 'index.html'
GSC_SCOPE = 'https://www.googleapis.com/auth/webmasters.readonly'
API = 'https://searchconsole.googleapis.com/webmasters/v3'


def api_call(token, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Authorization': f'Bearer {token}'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method='POST' if data is not None else 'GET')
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def list_properties(token):
    """Return {siteUrl: permissionLevel} the service account can read."""
    try:
        res = api_call(token, f'{API}/sites')
    except urllib.error.HTTPError as e:
        sys.exit(f'Could not list Search Console properties ({e.code}): '
                 f'{e.read().decode(errors="replace")}\n'
                 'Is the Search Console API enabled in the key\'s Google Cloud project?')
    out = {}
    for entry in res.get('siteEntry', []):
        if entry.get('permissionLevel') != 'siteUnverifiedUser':
            out[entry['siteUrl']] = entry.get('permissionLevel', '')
    return out


def host_of_property(site_url):
    if site_url.startswith('sc-domain:'):
        return site_url[len('sc-domain:'):].lower()
    try:
        return (urllib.parse.urlparse(site_url).hostname or '').lower().removeprefix('www.')
    except ValueError:
        return ''


def match_property(host, available, overrides):
    if host in overrides:
        return overrides[host]
    # prefer an exact host match among the properties the account can read
    candidates = [p for p in available if host_of_property(p) == host]
    if not candidates:
        return None
    # prefer a domain property, then https, then anything
    candidates.sort(key=lambda p: (not p.startswith('sc-domain:'),
                                   not p.startswith('https://'), len(p)))
    return candidates[0]


def query(token, prop, start, end, dimensions, row_limit):
    url = f'{API}/sites/{urllib.parse.quote(prop, safe="")}/searchAnalytics/query'
    body = {'startDate': start, 'endDate': end, 'dimensions': dimensions,
            'rowLimit': row_limit, 'dataState': 'final'}
    try:
        res = api_call(token, url, body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors='replace')
        if e.code == 403:
            raise PermissionError(detail)
        raise RuntimeError(f'{e.code}: {detail}')
    except (urllib.error.URLError, TimeoutError) as e:
        # a transient network blip on one site should skip it, not kill the run
        raise RuntimeError(f'network error: {getattr(e, "reason", e)}')
    return res.get('rows', [])


def metrics(row):
    return {
        'clicks': int(round(row.get('clicks', 0))),
        'impressions': int(round(row.get('impressions', 0))),
        'ctr': round(row.get('ctr', 0), 4),
        'position': round(row.get('position', 0), 1),
    }


def fetch_site(token, prop, start, end, n_queries, n_pages):
    # GSC returns a row only for days that had impressions. Fill the gaps with
    # zeros from the first day with data through `end`, so the daily series is a
    # contiguous calendar range — the dashboard's day/week roll-ups assume that.
    rows = {r['keys'][0]: metrics(r) for r in query(token, prop, start, end, ['date'], 1000)}
    daily = []
    if rows:
        zero = {'clicks': 0, 'impressions': 0, 'ctr': 0, 'position': 0}
        d = datetime.date.fromisoformat(min(rows))
        end_d = datetime.date.fromisoformat(end)
        while d <= end_d:
            iso = d.isoformat()
            daily.append({'date': iso, **rows.get(iso, zero)})
            d += datetime.timedelta(days=1)
    queries = [{'query': r['keys'][0], **metrics(r)}
               for r in query(token, prop, start, end, ['query'], n_queries)]
    pages = [{'page': r['keys'][0], **metrics(r)}
             for r in query(token, prop, start, end, ['page'], n_pages)]
    return {'property': prop, 'daily': daily, 'queries': queries, 'pages': pages}


def read_sites_from_index():
    html = INDEX.read_text()
    m = re.search(r'<script id="seo-data" type="application/json">(.*?)</script>', html, flags=re.S)
    if not m:
        sys.exit('Could not find the seo-data block in index.html — run refresh_data.py first.')
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        sys.exit('The seo-data block in index.html is not valid JSON.')
    return data.get('sites', []), html


def embed_gsc(html, gsc):
    m = re.search(r'<script id="seo-data" type="application/json">(.*?)</script>', html, flags=re.S)
    data = json.loads(m.group(1))
    data['gsc'] = gsc
    payload = json.dumps(data, separators=(',', ':')).replace('</', r'<\/')
    new_html = re.sub(
        r'(<script id="seo-data" type="application/json">).*?(</script>)',
        lambda mm: mm.group(1) + payload + mm.group(2),
        html, count=1, flags=re.S)
    INDEX.write_text(new_html)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--key', required=True, metavar='KEY_JSON')
    ap.add_argument('--days', type=int, default=90)
    ap.add_argument('--queries', type=int, default=25)
    ap.add_argument('--pages', type=int, default=25)
    ap.add_argument('--map', action='append', default=[], metavar='HOST=PROPERTY')
    ap.add_argument('--sites', help='comma-separated hostnames (default: all in index.html)')
    ap.add_argument('--today', help='override end date (YYYY-MM-DD), for testing')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    overrides = {}
    for pair in args.map:
        if '=' not in pair:
            ap.error(f'--map expects HOST=PROPERTY, got {pair!r}')
        host, prop = pair.split('=', 1)
        overrides[host.strip().lower().removeprefix('www.')] = prop.strip()

    index_sites, html = read_sites_from_index()
    sites = ([s.strip().lower().removeprefix('www.') for s in args.sites.split(',')]
             if args.sites else index_sites)
    if not sites:
        sys.exit('No sites to enrich — is index.html populated?')

    # GSC data lags ~2 days; end two days back, start `days` before that.
    end_d = (datetime.date.fromisoformat(args.today) if args.today
             else datetime.date.today()) - datetime.timedelta(days=2)
    start_d = end_d - datetime.timedelta(days=args.days)
    start, end = start_d.isoformat(), end_d.isoformat()

    sa = load_sa(args.key)
    token = get_access_token(sa, GSC_SCOPE)
    available = list_properties(token)
    print(f'{sa["client_email"]} can read {len(available)} propert'
          f'{"y" if len(available) == 1 else "ies"}: {", ".join(available) or "(none)"}')

    out, skipped = {}, []
    for host in sites:
        prop = match_property(host, available, overrides)
        if not prop:
            skipped.append((host, 'no matching property the account can read'))
            continue
        if args.dry_run:
            print(f'  {host} -> {prop}  ({start} … {end})')
            continue
        try:
            out[host] = fetch_site(token, prop, start, end, args.queries, args.pages)
            d = out[host]['daily']
            tot = sum(x['clicks'] for x in d)
            print(f'  {host} -> {prop}: {len(d)} days, {tot} clicks, '
                  f'{len(out[host]["queries"])} queries, {len(out[host]["pages"])} pages')
        except PermissionError:
            skipped.append((host, f'{prop}: account lacks access (add it as a user in Search Console)'))
        except RuntimeError as e:
            skipped.append((host, f'{prop}: {e}'))

    for host, why in skipped:
        print(f'  skipped {host}: {why}', file=sys.stderr)

    if args.dry_run:
        return
    if not out:
        sys.exit('No sites enriched — grant the service account access to at least one property.')

    gsc = {
        'generatedAt': datetime.date.today().isoformat(),
        'range': {'start': start, 'end': end},
        'sites': out,
    }
    embed_gsc(html, gsc)
    print(f'Embedded Search Console data for {len(out)} site(s) into {INDEX.name}')


if __name__ == '__main__':
    main()
