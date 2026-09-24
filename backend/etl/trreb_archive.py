"""Collect official report links into an immutable local cache. No scheduled job."""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, build_opener

ARCHIVES = {
    'resale': 'https://trreb.ca/market-data/market-watch/market-watch-archive/',
    'rental': 'https://trreb.ca/market-data/rental-market-report/rental-market-report-archive/',
}


def official_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'trreb.ca', 'www.trreb.ca', 'public.trreb.ca'} or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError('Only public official HTTPS TRREB URLs are accepted')
    return url


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    with build_opener(OfficialRedirect()).open(official_url(url), timeout=45) as response:
        data = response.read(25_000_001)
    if len(data) > 25_000_000:
        raise ValueError('Report exceeds download size limit')
    return data


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.links.append(href.strip())


def inventory(html, family, start, end):
    parser = Links()
    parser.feed(html)
    found = {}
    for href in parser.links:
        url = urljoin(ARCHIVES[family], href)
        filename = urlparse(url).path.rsplit('/', 1)[-1]
        match = re.fullmatch(r'mw(\d{2})(\d{2})\.pdf', filename) if family == 'resale' else re.fullmatch(r'rental_report_Q([1-4])-(20\d{2})\.pdf', filename)
        if not match:
            continue
        if family == 'resale':
            year, month = 2000 + int(match[1]), int(match[2])
            if not 1 <= month <= 12:
                continue
            period = f'{year}-{month:02}'
        else:
            year = int(match[2])
            period = f'{year}-Q{match[1]}'
        if start <= year <= end:
            official_url(url)
            if period in found and found[period] != url:
                raise ValueError(f'Ambiguous archive links: {period}')
            found[period] = url
    return found


def collect(root, family, start, end, *, refresh=False):
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / f'{family}-downloads.json'
    previous = json.loads(index_path.read_text()) if index_path.exists() else []
    cache = {(r['period'], r['source_url']): r for r in previous if r['status'] == 'downloaded'}
    archive = fetch(ARCHIVES[family])
    digest = hashlib.sha256(archive).hexdigest()
    archive_path = root / f'{family}-archive-{digest}.html'
    if not archive_path.exists():
        archive_path.write_bytes(archive)
    links = inventory(archive.decode('utf-8'), family, start, end)
    periods = [f'{year}-{month:02}' for year in range(start, end + 1) for month in range(1, 13)] if family == 'resale' else [f'{year}-Q{quarter}' for year in range(start, end + 1) for quarter in range(1, 5)]
    result = []
    for period in periods:
        row = {'family': family, 'period': period, 'source_url': links.get(period),
               'archive_sha256': digest, 'retrieved_at': datetime.now(timezone.utc).isoformat()}
        try:
            if not row['source_url']:
                raise ValueError('No report link in official archive')
            old = cache.get((period, row['source_url']))
            if not refresh and old and (root / old['file']).is_file() and hashlib.sha256((root / old['file']).read_bytes()).hexdigest() == old['sha256']:
                result.append(old)
                continue
            data = fetch(row['source_url'])
            if not data.startswith(b'%PDF-'):
                raise ValueError('Response is not a PDF')
            sha = hashlib.sha256(data).hexdigest()
            path = root / f'{family}-{period}-{sha}.pdf'
            if not path.exists():
                path.write_bytes(data)
            elif hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
                raise ValueError('Existing immutable cache artifact is corrupt; manual review required')
            row.update(status='downloaded', sha256=sha, file=path.name)
        except Exception as exc:
            row.update(status='failed', error=str(exc))
        result.append(row)
        print(f"{family} {period}: {row['status']}", flush=True)
        time.sleep(0.25)
    index_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'{sum(r["status"] == "downloaded" for r in result)}/{len(periods)} downloaded', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--family', choices=ARCHIVES, required=True)
    parser.add_argument('--start', type=int, default=2020)
    parser.add_argument('--end', type=int, default=2025)
    parser.add_argument('--refresh', action='store_true', help='Explicitly recheck report URLs for new fingerprints; preserves old PDF files')
    args = parser.parse_args()
    if not 2020 <= args.start <= args.end <= 2025:
        parser.error('This collection is scoped to 2020–2025')
    collect(args.root, args.family, args.start, args.end, refresh=args.refresh)
