"""Validated, versioned SQLite staging database for TRREB report history."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .pilot_trreb import EXPECTED, FIELDS, extract_page, number, validate
from .trreb_parser_version import parser_version

ALIASES = {'TREB Total': 'All TRREB Areas', 'TRREB Total': 'All TRREB Areas',
           'Whitchurch-Stouffville': 'Stouffville', 'Bradford West Gwillimbury': 'Bradford',
           'E. Gwillimbury': 'East Gwillimbury'}


def resale_page(page, period):
    if period == '2022-05' and abs(page.width - 792) <= 1:
        # This report paints a second, full table over an obsolete first table.
        # The visible table starts at its Sales header (x=96.58, y=80.74).
        starts = [i for i, c in enumerate(page.chars) if c['text'] == 'S'
                  and abs(c['x0'] - 96.581) < 0.1 and abs(c['top'] - 80.738) < 0.1]
        if len(starts) != 1:
            raise ValueError('Unrecognized May 2022 layered export')
        retained = {id(c) for c in page.chars[starts[0]:]}
        page = page.filter(lambda obj: obj.get('object_type') != 'char' or id(obj) in retained)
    text = page.extract_text() or ''
    label = datetime.strptime(period, '%Y-%m').strftime('%B %Y').upper()
    heading = (page.crop((0, 0, page.width, 75)).extract_text() or '').upper()
    if f'ALL HOME TYPES, {label}' not in heading or 'SUMMARY OF EXISTING HOME TRANSACTIONS' not in heading:
        raise ValueError('Wrong monthly summary, period or property type')
    if 'ALL TREB AREAS' not in heading and 'ALL TRREB AREAS' not in heading:
        raise ValueError('Not the all-area monthly summary')
    if abs(page.width - 792) <= 1:
        return extract_page(page, period, collect_total_issues=True)
    # Legacy landscape exports have clean text rows, unlike recent Tableau PDFs.
    if not 835 <= page.width <= 843 or abs(page.height - 612) > 1:
        raise ValueError(f'Unsupported legacy dimensions: {page.width} x {page.height}')
    for column in ('Dollar Volume', 'Average Price', 'Median Price', 'New Listings',
                   'SNLR', 'Active Listings', 'Mos Inv', 'SP/LP', 'LDOM', 'PDOM'):
        if column not in text:
            raise ValueError(f'Unsupported legacy columns: {column}')
    labels = EXPECTED | set(ALIASES)
    rows = []
    for line in text.splitlines():
        line = ' '.join(line.split())
        name = next((n for n in sorted(labels, key=len, reverse=True) if line.startswith(n + ' ')), None)
        if name is None:
            continue
        cells = line[len(name):].split()
        if len(cells) != len(FIELDS):
            raise ValueError(f'Wrong legacy cell count: {name}: {len(cells)}')
        rows.append({'source_area': ALIASES.get(name, name),
                     **dict(zip(FIELDS, map(number, cells, FIELDS)))})
    validate(rows, collect_total_issues=True)
    return rows


def parse_resale(path, period):
    import pdfplumber
    with pdfplumber.open(path) as document:
        if len(document.pages) < 3:
            raise ValueError('Missing summary page')
        # Page 3 is a reviewed contract, never fall back to a YTD or type table.
        return resale_page(document.pages[2], period), 3


def connect(path):
    db = sqlite3.connect(path)
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO settings VALUES ('public_display_enabled','false');
        INSERT OR IGNORE INTO settings VALUES ('public_export_enabled','false');
        INSERT OR IGNORE INTO settings VALUES ('vintage','as_published_static_reports');
        CREATE TABLE IF NOT EXISTS reports (
          id INTEGER PRIMARY KEY, family TEXT NOT NULL, period TEXT NOT NULL,
          sha256 TEXT NOT NULL, source_url TEXT NOT NULL, local_file TEXT NOT NULL,
          retrieved_at TEXT NOT NULL, parsed_at TEXT, source_page INTEGER,
          status TEXT NOT NULL CHECK(status IN ('validated','failed')), error TEXT,
          UNIQUE(family, period, sha256));
        CREATE TABLE IF NOT EXISTS quality_issues (
          report_id INTEGER REFERENCES reports(id), area TEXT NOT NULL, field TEXT NOT NULL,
          reported REAL NOT NULL, children_sum REAL NOT NULL, difference REAL NOT NULL,
          PRIMARY KEY(report_id,area,field));
    ''')
    if 'parser_version' not in {row[1] for row in db.execute('PRAGMA table_info(reports)')}:
        db.execute('ALTER TABLE reports ADD COLUMN parser_version TEXT')
    columns = ','.join(f'{field} {"REAL" if field in {"snlr_trend_pct", "months_inventory_trend", "sale_to_list_pct"} else "INTEGER"} CHECK({field} IS NULL OR {field} >= 0)' for field in FIELDS)
    db.execute(f'''CREATE TABLE IF NOT EXISTS resale (
        report_id INTEGER REFERENCES reports(id), source_area TEXT NOT NULL,
        property_type TEXT NOT NULL CHECK(property_type='all_home_types'),
        {columns}, PRIMARY KEY(report_id, source_area))''')
    db.commit()
    return db


def import_report(db, root, entry, *, reprocess=False):
    if entry['family'] != 'resale':
        raise ValueError('Monthly importer requires resale reports')
    path = (root / entry['file']).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Report path escapes archive')
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('Source hash mismatch')
    version = parser_version('resale')
    existing = db.execute('SELECT id,status,parser_version FROM reports WHERE family=? AND period=? AND sha256=?',
                          (entry['family'], entry['period'], entry['sha256'])).fetchone()
    if existing and existing[1] == 'validated' and existing[2] == version and not reprocess:
        return 'cached'
    error, rows, page = None, [], None
    try:
        rows, page = parse_resale(path, entry['period'])
        issues = validate(rows, collect_total_issues=True)
    except Exception as exc:
        error = str(exc)
    status = 'failed' if error else 'validated'
    with db:
        db.execute('''INSERT INTO reports(family,period,sha256,source_url,local_file,retrieved_at,parsed_at,source_page,status,error,parser_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(family,period,sha256) DO UPDATE SET
            parsed_at=excluded.parsed_at, source_page=excluded.source_page,status=excluded.status,error=excluded.error,
            parser_version=excluded.parser_version''',
            (entry['family'], entry['period'], entry['sha256'], entry['source_url'], entry['file'],
             entry['retrieved_at'], datetime.now(timezone.utc).isoformat(), page, status, error, version))
        report_id = db.execute('SELECT id FROM reports WHERE family=? AND period=? AND sha256=?',
                               (entry['family'], entry['period'], entry['sha256'])).fetchone()[0]
        db.execute('DELETE FROM resale WHERE report_id=?', (report_id,))
        db.execute('DELETE FROM quality_issues WHERE report_id=?', (report_id,))
        if not error:
            for row in rows:
                db.execute(f'INSERT INTO resale VALUES ({",".join("?" for _ in range(len(FIELDS) + 3))})',
                           [report_id, row['source_area'], 'all_home_types', *(row[f] for f in FIELDS)])
            for issue in issues:
                db.execute('INSERT INTO quality_issues VALUES (?,?,?,?,?,?)',
                           [report_id, *(issue[k] for k in ('area','field','reported','children_sum','difference'))])
    return error or status


def audit(db):
    result = {'integrity_check': db.execute('PRAGMA integrity_check').fetchone()[0],
              'foreign_key_errors': db.execute('PRAGMA foreign_key_check').fetchall(),
              'reports': db.execute("SELECT period,status,error FROM reports WHERE family='resale' ORDER BY period").fetchall(),
              'row_count': db.execute("SELECT COUNT(*) FROM resale s JOIN reports r ON r.id=s.report_id WHERE r.family='resale'").fetchone()[0],
              'source_total_discrepancies': db.execute('''SELECT r.period,q.area,q.field,q.reported,q.children_sum,q.difference
                  FROM quality_issues q JOIN reports r ON r.id=q.report_id WHERE r.family='resale' ORDER BY r.period,q.area,q.field''').fetchall(),
              'coverage': db.execute('''SELECT substr(period,1,4),COUNT(DISTINCT period) FROM reports
                                        WHERE status='validated' AND family='resale' GROUP BY substr(period,1,4)''').fetchall(),
              'annual_sales_as_published': db.execute('''SELECT substr(r.period,1,4),s.source_area,SUM(s.sales),COUNT(DISTINCT r.period)
                  FROM resale s JOIN reports r ON r.id=s.report_id
                  WHERE r.family='resale' AND NOT EXISTS(SELECT 1 FROM reports x WHERE x.family=r.family AND x.period=r.period AND x.id!=r.id AND x.status='validated')
                  GROUP BY substr(r.period,1,4),s.source_area HAVING COUNT(DISTINCT r.period)=12 ORDER BY 1,2''').fetchall()}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--reprocess', action='store_true', help='Re-extract even with an unchanged parser fingerprint')
    args = parser.parse_args()
    entries = json.loads((args.root / 'resale-downloads.json').read_text())
    with connect(args.root / 'trreb.sqlite') as db:
        for entry in entries:
            if entry['status'] == 'downloaded':
                print(entry['period'], import_report(db, args.root, entry, reprocess=args.reprocess), flush=True)
        result = audit(db)
    (args.root / 'database-audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in {'reports', 'annual_sales_as_published'}}))
    return int(any(e['status'] != 'downloaded' for e in entries) or
               any(row[1] != 'validated' for row in result['reports']))


if __name__ == '__main__':
    raise SystemExit(main())
