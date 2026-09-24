"""Import actual year-end YTD statistics, never average monthly medians."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .pilot_trreb import FIELDS, number, validate
from .trreb_history import connect
from .trreb_tables import glyph_rows, legacy_rows
from .trreb_parser_version import parser_version

ANNUAL_FIELDS = ('sales','dollar_volume','average_price','median_price','new_listings',
                 'sale_to_list_pct','listing_days','property_days')


def annual_rows(page, year):
    text = page.extract_text() or ''
    heading = (page.crop((0,0,page.width,75)).extract_text() or '').upper()
    if f'ALL HOME TYPES, YEAR-TO-DATE {year}' not in heading or 'SUMMARY OF EXISTING HOME TRANSACTIONS' not in heading:
        raise ValueError('Not the requested annual YTD summary')
    for name in ('Dollar Volume','Average Price','Median Price','New Listings','SP/LP','LDOM','PDOM'):
        if name not in text:
            raise ValueError(f'Unexpected annual columns: {name}')
    if abs(page.width-792)<1 and abs(page.height-612)<1:
        table = glyph_rows(page,96.48,85.3,8,93,overprinted=True)
    elif 835<=page.width<=843 and abs(page.height-612)<1:
        table = legacy_rows(page,8)
    else:
        raise ValueError('Unsupported annual layout')
    rows = [{'source_area': name, **dict.fromkeys(FIELDS),
             **dict(zip(ANNUAL_FIELDS,map(number,cells,ANNUAL_FIELDS)))} for name,cells in table]
    validate(rows,collect_total_issues=True)
    return rows


def import_annual(db, root, entry):
    import pdfplumber
    path=(root/entry['file']).resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
        raise ValueError('Invalid source artifact')
    year=entry['period'][:4]
    if entry['period'] != year+'-12':
        raise ValueError('Annual import requires December report')
    with pdfplumber.open(path) as document:
        rows=annual_rows(document.pages[4],year)
    with db:
        db.execute('''INSERT INTO reports(family,period,sha256,source_url,local_file,retrieved_at,parsed_at,source_page,status,parser_version)
            VALUES ('resale_annual',?,?,?,?,?,?,5,'validated',?) ON CONFLICT(family,period,sha256) DO UPDATE SET
            parsed_at=excluded.parsed_at,parser_version=excluded.parser_version,status='validated',error=NULL''',
            (year,entry['sha256'],entry['source_url'],entry['file'],entry['retrieved_at'],datetime.now(timezone.utc).isoformat(),parser_version('resale_annual')))
        report_id=db.execute("SELECT id FROM reports WHERE family='resale_annual' AND period=? AND sha256=?",(year,entry['sha256'])).fetchone()[0]
        db.execute('DELETE FROM resale WHERE report_id=?',(report_id,))
        db.execute('DELETE FROM quality_issues WHERE report_id=?',(report_id,))
        for row in rows:
            db.execute(f'INSERT INTO resale VALUES ({",".join("?" for _ in range(len(FIELDS)+3))})',
                       [report_id,row['source_area'],'all_home_types',*(row[f] for f in FIELDS)])
        for issue in validate(rows,collect_total_issues=True):
            db.execute('INSERT INTO quality_issues VALUES (?,?,?,?,?,?)',
                       [report_id,*(issue[k] for k in ('area','field','reported','children_sum','difference'))])
    return len(rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    entries=json.loads((args.root/'resale-downloads.json').read_text())
    with connect(args.root/'trreb.sqlite') as db:
        for entry in entries:
            if entry['period'].endswith('-12') and entry['status']=='downloaded':
                print(entry['period'][:4],import_annual(db,args.root,entry),flush=True)
