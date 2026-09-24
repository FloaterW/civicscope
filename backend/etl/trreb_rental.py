"""Separate quarterly MLS apartment-lease importer, never CMHC rental stock."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from .pilot_trreb import EXPECTED, GROUPS, number
from .trreb_history import connect
from .trreb_tables import glyph_rows, legacy_rows
from .trreb_parser_version import parser_version

BEDROOMS = ('bachelor', 'one', 'two', 'three')


def expected_rental_areas(period):
    """Reviewed 2020–2025 corpus coverage; new periods/layouts need review."""
    if not re.fullmatch(r'202[0-5]-Q[1-4]', period):
        raise ValueError('Unreviewed rental period')
    omitted = set()
    if period.startswith('2025'):
        omitted = {'Adjala-Tosorontio', 'Brock', 'Essa', 'Scugog'}
        if period in {'2025-Q1', '2025-Q2'}:
            omitted.add('Georgina')
        if period == '2025-Q1':
            omitted.add('Uxbridge')
    return EXPECTED - omitted


def rental_rows(page, period):
    match = re.fullmatch(r'(20\d{2})-Q([1-4])', period)
    if not match:
        raise ValueError('Expected quarterly period')
    year, quarter = match.groups()
    text = page.extract_text() or ''
    header = (page.crop((0, 0, page.width, 78)).extract_text() or '').upper()
    label = f'{("FIRST", "SECOND", "THIRD", "FOURTH")[int(quarter)-1]} QUARTER {year}'
    if not (f'APARTMENTS, {year} Q{quarter}' in header or f'APARTMENTS, {label}' in header) or 'SUMMARY OF RENTAL TRANSACTIONS' not in header:
        raise ValueError('Wrong rental universe or quarter')
    for column in ('Total Listed', 'Total Leased', 'Bachelor', 'Bedroom', 'Lease Rate'):
        if column not in text:
            raise ValueError(f'Unexpected rental columns: {column}')
    if ('TREB Total' in text or 'TRREB Total' in text) and 790 <= page.width <= 843 and abs(page.height-612)<1:
        table = legacy_rows(page, 10)
    elif abs(page.width - 792) < 1 and abs(page.height - 612) < 1:
        table = glyph_rows(page, 92.16, 67.1, 10, 114, overprinted=True)
    elif 835 <= page.width <= 843 and abs(page.height - 612) < 1:
        table = legacy_rows(page, 10)
    else:
        raise ValueError('Unsupported rental page dimensions')
    names = {name for name, _ in table}
    if not set(GROUPS).issubset(names) or 'All TRREB Areas' not in names:
        raise ValueError('Missing rental regional totals')
    if names != expected_rental_areas(period):
        raise ValueError(f'Unreviewed rental area coverage for {period}')
    rows = []
    for name, cells in table:
        listed, leased = (number(c or '-', 'sales') for c in cells[:2])
        if listed is None or leased is None:
            raise ValueError(f'Missing required listed/leased counts: {name}')
        bedrooms = []
        for i, bedroom in enumerate(BEDROOMS):
            count = number(cells[2 + i*2] or '-', 'sales')
            raw_rent = number(cells[3 + i*2] or '-', 'average_price')
            # Zero transactions cannot support an observed average rent.
            rent = None if count in (0, None) else raw_rent
            bedrooms.append({'bedroom': bedroom, 'leased': count, 'average_rent': rent,
                             'raw_average_rent': raw_rent,
                             'quality': 'no_transactions' if count == 0 else 'missing' if rent is None else 'reported'})
        if leased is not None and all(b['leased'] is not None for b in bedrooms) and sum(b['leased'] for b in bedrooms) != leased:
            raise ValueError(f'Bedroom lease counts do not sum: {name}')
        rows.append({'source_area': name, 'total_listed': listed, 'total_leased': leased, 'bedrooms': bedrooms})
    return rows


def parse_rental(path, period):
    import pdfplumber
    with pdfplumber.open(path) as document:
        return rental_rows(document.pages[1], period)


def import_rental(db, root, entry):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS rental (
            report_id INTEGER REFERENCES reports(id), source_area TEXT NOT NULL,
            total_listed INTEGER CHECK(total_listed>=0), total_leased INTEGER CHECK(total_leased>=0),
            PRIMARY KEY(report_id,source_area));
        CREATE TABLE IF NOT EXISTS rental_bedrooms (
            report_id INTEGER, source_area TEXT, bedroom TEXT CHECK(bedroom IN ('bachelor','one','two','three')),
            leased INTEGER CHECK(leased>=0), average_rent INTEGER CHECK(average_rent>=0),
            raw_average_rent INTEGER CHECK(raw_average_rent>=0), quality TEXT NOT NULL,
            PRIMARY KEY(report_id,source_area,bedroom),
            FOREIGN KEY(report_id,source_area) REFERENCES rental(report_id,source_area));
    ''')
    path = (root / entry['file']).resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('Invalid source artifact')
    rows, error = [], None
    try:
        rows = parse_rental(path, entry['period'])
    except Exception as exc:
        error = str(exc)
    with db:
        db.execute('''INSERT INTO reports(family,period,sha256,source_url,local_file,retrieved_at,parsed_at,source_page,status,error,parser_version)
            VALUES ('rental',?,?,?,?,?,?,2,?,?,?) ON CONFLICT(family,period,sha256) DO UPDATE SET
            parsed_at=excluded.parsed_at,status=excluded.status,error=excluded.error,parser_version=excluded.parser_version''',
            (entry['period'], entry['sha256'], entry['source_url'], entry['file'], entry['retrieved_at'],
             datetime.now(timezone.utc).isoformat(), 'failed' if error else 'validated', error, parser_version('rental')))
        report_id = db.execute("SELECT id FROM reports WHERE family='rental' AND period=? AND sha256=?", (entry['period'], entry['sha256'])).fetchone()[0]
        db.execute('DELETE FROM rental_bedrooms WHERE report_id=?', (report_id,))
        db.execute('DELETE FROM rental WHERE report_id=?', (report_id,))
        if not error:
            for row in rows:
                db.execute('INSERT INTO rental VALUES (?,?,?,?)', (report_id,row['source_area'],row['total_listed'],row['total_leased']))
                for b in row['bedrooms']:
                    db.execute('INSERT INTO rental_bedrooms VALUES (?,?,?,?,?,?,?)',
                               (report_id,row['source_area'],*(b[k] for k in ('bedroom','leased','average_rent','raw_average_rent','quality'))))
    return error or f'validated ({len(rows)} areas)'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    entries = json.loads((args.root / 'rental-downloads.json').read_text())
    with connect(args.root / 'trreb.sqlite') as db:
        for entry in entries:
            if entry['status'] == 'downloaded':
                print(entry['period'], import_rental(db, args.root, entry), flush=True)
        statuses = db.execute("SELECT status,count(*) FROM reports WHERE family='rental' GROUP BY status").fetchall()
        print(statuses)
    return int(any(e['status'] != 'downloaded' for e in entries) or any(s != 'validated' for s, _ in statuses))


if __name__ == '__main__':
    raise SystemExit(main())
