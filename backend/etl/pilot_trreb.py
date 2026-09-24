"""Staging-only Market Watch parser. Never writes production data.

Optional extraction dependency: pdfplumber==0.11.9. Layout contract: landscape
2026 all-home-types monthly summary. Unknown layouts fail closed.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

FIELDS = ('sales', 'dollar_volume', 'average_price', 'median_price',
          'new_listings', 'snlr_trend_pct', 'active_listings',
          'months_inventory_trend', 'sale_to_list_pct', 'listing_days', 'property_days')
GROUPS = {
    'Halton Region': ['Burlington', 'Halton Hills', 'Milton', 'Oakville'],
    'Peel Region': ['Brampton', 'Caledon', 'Mississauga'],
    'City of Toronto': ['Toronto West', 'Toronto Central', 'Toronto East'],
    'York Region': ['Aurora', 'East Gwillimbury', 'Georgina', 'King', 'Markham',
                    'Newmarket', 'Richmond Hill', 'Vaughan', 'Stouffville'],
    'Durham Region': ['Ajax', 'Brock', 'Clarington', 'Oshawa', 'Pickering',
                      'Scugog', 'Uxbridge', 'Whitby'],
    'Dufferin County': ['Orangeville'],
    'Simcoe County': ['Adjala-Tosorontio', 'Bradford', 'Essa', 'Innisfil', 'New Tecumseth'],
}
EXPECTED = {'All TRREB Areas', *GROUPS, *(n for names in GROUPS.values() for n in names)}


def number(value, field):
    if value in {'-', '--', 'N/A', '*', '**'}:
        return None
    pattern = r'(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)(?:\.\d+)?'
    if not re.fullmatch(r'\$?' + pattern + r'%?', value):
        raise ValueError(f'Invalid {field}: {value!r}')
    if ('$' in value and field not in {'dollar_volume', 'average_price', 'median_price'}) or (
        '%' in value and field not in {'snlr_trend_pct', 'sale_to_list_pct'}
    ):
        raise ValueError(f'Unexpected unit for {field}')
    parsed = Decimal(value.replace('$', '').replace(',', '').replace('%', ''))
    if field in {'snlr_trend_pct', 'months_inventory_trend', 'sale_to_list_pct'}:
        return float(parsed)
    if parsed != parsed.to_integral_value():
        raise ValueError(f'Noninteger {field}')
    return int(parsed)


def validate(rows, *, collect_total_issues=False):
    issues = []
    indexed = {r['source_area']: r for r in rows}
    if len(indexed) != len(rows) or set(indexed) != EXPECTED:
        raise ValueError('Duplicate, missing or unexpected areas; layout requires review')
    for row in rows:
        if row['sales'] and row['dollar_volume'] is not None and row['average_price'] is not None:
            if abs(row['dollar_volume'] / row['sales'] - row['average_price']) > 1:
                raise ValueError(f"Price reconciliation failed: {row['source_area']}")
    for parent, children in {**GROUPS, 'All TRREB Areas': list(GROUPS)}.items():
        for field in ('sales', 'dollar_volume', 'new_listings', 'active_listings'):
            values = [indexed[n][field] for n in children]
            # Missing values stay missing; never reconstruct them from a total.
            if indexed[parent][field] is not None and all(v is not None for v in values):
                # Dollar totals are printed to whole dollars; independently
                # rounded children can differ by at most half a dollar each.
                tolerance = (len(children) + 1) / 2 if field == 'dollar_volume' else 0
                if abs(sum(values) - indexed[parent][field]) > tolerance:
                    if not collect_total_issues:
                        raise ValueError(f'Total reconciliation failed: {parent}/{field}')
                    issues.append({'area': parent, 'field': field, 'reported': indexed[parent][field],
                                   'children_sum': sum(values), 'difference': indexed[parent][field] - sum(values)})
    return issues


def extract_page(page, period, *, collect_total_issues=False):
    heading = page.crop((0, 0, page.width, 75)).extract_text() or ''
    label = datetime.strptime(period, '%Y-%m').strftime('%B %Y')
    if f'All Home Types, {label}' not in heading or 'SUMMARY OF EXISTING HOME TRANSACTIONS' not in heading:
        raise ValueError('Not the requested monthly all-home-types summary')
    if abs(page.width - 792) > 1 or abs(page.height - 612) > 1:
        raise ValueError('Unsupported page dimensions')
    header = page.crop((0, 75, 792, 93)).extract_text() or ''
    for expected in ('Sales', 'Dollar Volume', 'Average Price', 'Median Price', 'New Listings',
                     'SNLR Trend', 'Active Listings', 'Mos Inv', 'SP/LP', 'LDOM', 'PDOM'):
        if expected not in header:
            raise ValueError(f'Unsupported columns: missing {expected}')
    # Small body glyphs only: excludes large invisible Tableau "Abc" marks.
    chars = [c for c in page.chars if 5 < c['size'] < 8 and 93 < c['top'] < 578]
    names = defaultdict(list)
    for c in chars:
        if c['x0'] < 75:
            names[round(c['top'], 1)].append(c)
    rows = []
    for baseline, name_chars in sorted(names.items()):
        name = ' '.join(''.join(c['text'] for c in sorted(name_chars, key=lambda c: c['x0'])).split())
        if not name:
            continue
        if name not in EXPECTED:
            raise ValueError(f'Unknown area: {name!r}')
        cells = []
        for index in range(11):
            left, right = 75 + index * 64, 75 + (index + 1) * 64
            cell = ''.join(c['text'] for c in sorted(chars, key=lambda c: c['x0'])
                           if left <= c['x0'] < right and abs(c['top'] - baseline) < 0.2).strip()
            cells.append(cell)
        rows.append({'source_area': name, **dict(zip(FIELDS, map(number, cells, FIELDS)))})
    validate(rows, collect_total_issues=collect_total_issues)
    return rows


def build_candidate(pdf, period, source_url):
    import pdfplumber  # Optional pilot dependency, not required by the API.
    url = urlparse(source_url)
    if url.scheme != 'https' or url.hostname not in {'trreb.ca', 'public.trreb.ca', 'www.trreb.ca'} or url.username or url.password:
        raise ValueError('Expected an official HTTPS TRREB source URL')
    if not re.fullmatch(r'20\d{2}-(?:0[1-9]|1[0-2])', period):
        raise ValueError('Expected YYYY-MM')
    with pdfplumber.open(pdf) as document:
        matches = []
        for i, page in enumerate(document.pages):
            heading = page.crop((0, 0, page.width, min(75, page.height))).extract_text() or ''
            label = datetime.strptime(period, '%Y-%m').strftime('%B %Y')
            if f'All Home Types, {label}' in heading and 'SUMMARY OF EXISTING HOME TRANSACTIONS' in heading and 'ALL TRREB AREAS' in heading:
                matches.append((i + 1, page))
        if len(matches) != 1:
            raise ValueError('Expected exactly one monthly summary; refusing YTD or ambiguous tables')
        page_number, page = matches[0]
        rows = extract_page(page, period)
    return {'schema_version': 1, 'status': 'staging_only', 'public_display_enabled': False,
            'public_export_enabled': False, 'permission': 'user_reports_written_permission; conditions_unreviewed',
            'source_url': source_url, 'source_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
            'extracted_at': datetime.now(timezone.utc).isoformat(), 'source_page': page_number,
            'period': period, 'period_type': 'month', 'property_type': 'all_home_types',
            'universe': 'TRREB MLS resale transactions', 'vintage': 'as_published_static_report',
            'geography_mapping': 'unverified_source_labels_only', 'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--period', required=True)
    parser.add_argument('--source-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    candidate = build_candidate(args.pdf, args.period, args.source_url)
    # Exclusive creation protects existing candidates and production artifacts.
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(candidate, handle, indent=2)
    print(f"Validated {len(candidate['rows'])} source areas; staging only")


if __name__ == '__main__':
    main()
