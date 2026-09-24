"""Read-only coverage, provenance, revision and reconciliation audit."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3

from .pilot_trreb import GROUPS, EXPECTED
from .trreb_parser_version import parser_version
from .trreb_rental import BEDROOMS, expected_rental_areas


def audit_history(root):
    db = sqlite3.connect((root / 'trreb.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    expected = {'resale': {f'{y}-{m:02}' for y in range(2020,2026) for m in range(1,13)},
                'rental': {f'{y}-Q{q}' for y in range(2020,2026) for q in range(1,5)},
                'resale_annual': {str(y) for y in range(2020,2026)}}
    report_rows = [dict(row) for row in db.execute('SELECT * FROM reports')]
    errors, coverage, versions = [], {}, defaultdict(list)
    for row in report_rows:
        versions[(row['family'],row['period'])].append(row['sha256'])
        path=(root/row['local_file']).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            errors.append(f"Invalid source hash: {row['family']}/{row['period']}")
        if row['status']!='validated':
            errors.append(f"Failed parse: {row['family']}/{row['period']}: {row['error']}")
        if row.get('parser_version') != parser_version(row['family']):
            errors.append(f"Stale parser: {row['family']}/{row['period']}; re-import required")
        if row['family'] in {'resale', 'resale_annual'}:
            names = {r[0] for r in db.execute('SELECT source_area FROM resale WHERE report_id=?', (row['id'],))}
            if names != EXPECTED:
                errors.append(f"Unexpected resale areas: {row['family']}/{row['period']}")
    for family, periods in expected.items():
        found={row['period'] for row in report_rows if row['family']==family and row['status']=='validated'}
        coverage[family]={'expected':len(periods),'imported':len(found),'missing':sorted(periods-found),'unexpected':sorted(found-periods)}
        if found != periods:
            errors.append(f'Incomplete or unexpected periods: {family}')
    ambiguous=[{'family':f,'period':p,'hashes':v} for (f,p),v in versions.items() if len(v)>1]
    if ambiguous:
        errors.append('Multiple vintages require explicit selection; no implicit latest version')
    integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
    foreign_keys=[tuple(r) for r in db.execute('PRAGMA foreign_key_check')]
    if integrity!='ok' or foreign_keys:
        errors.append('Database integrity failure')
    monthly=db.execute("SELECT count(*) FROM resale s JOIN reports r ON r.id=s.report_id WHERE family='resale'").fetchone()[0]
    annual=db.execute("SELECT count(*) FROM resale s JOIN reports r ON r.id=s.report_id WHERE family='resale_annual'").fetchone()[0]
    if monthly!=72*41 or annual!=6*41:
        errors.append('Unexpected resale row coverage')
    rental_coverage=[]
    rental_issues=[]
    for report in [r for r in report_rows if r['family']=='rental' and r['status']=='validated']:
        rows={r['source_area']:dict(r) for r in db.execute('SELECT * FROM rental WHERE report_id=?',(report['id'],))}
        if set(rows) != expected_rental_areas(report['period']):
            errors.append(f"Unexpected rental areas: {report['period']}")
        for area in rows:
            bedrooms = {r[0] for r in db.execute('SELECT bedroom FROM rental_bedrooms WHERE report_id=? AND source_area=?', (report['id'], area))}
            if bedrooms != set(BEDROOMS):
                errors.append(f"Missing rental bedroom rows: {report['period']}/{area}")
        rental_coverage.append({'period':report['period'],'areas':len(rows),'not_reported':sorted(EXPECTED-set(rows))})
        for parent,children in {**GROUPS,'All TRREB Areas':list(GROUPS)}.items():
            if parent not in rows or not set(children).issubset(rows):
                continue # Absent source rows are unknown, never assumed zero.
            for field in ('total_listed','total_leased'):
                if all(rows[n][field] is not None for n in [parent,*children]):
                    delta=rows[parent][field]-sum(rows[n][field] for n in children)
                    if delta:
                        rental_issues.append({'period':report['period'],'area':parent,'field':field,'difference':delta})
    for r in db.execute('''SELECT report_id,source_area,sum(leased) as bedrooms FROM rental_bedrooms GROUP BY report_id,source_area'''):
        total=db.execute('SELECT total_leased FROM rental WHERE report_id=? AND source_area=?',(r['report_id'],r['source_area'])).fetchone()[0]
        if r['bedrooms']!=total:
            errors.append('Rental bedroom total mismatch')
    invalid_rents=db.execute('SELECT count(*) FROM rental_bedrooms WHERE (leased=0 OR leased IS NULL) AND average_rent IS NOT NULL').fetchone()[0]
    if invalid_rents:
        errors.append('Rent shown without transactions')
    revisions=[dict(r) for r in db.execute('''SELECT a.period AS year,s.source_area,s.sales AS december_ytd_sales,
            (SELECT SUM(m.sales) FROM resale m JOIN reports b ON b.id=m.report_id
             WHERE b.family='resale' AND substr(b.period,1,4)=a.period AND m.source_area=s.source_area) AS archived_monthly_sales
            FROM resale s JOIN reports a ON a.id=s.report_id WHERE a.family='resale_annual' ORDER BY a.period,s.source_area''')]
    revision_differences=[dict(r,difference=r['december_ytd_sales']-r['archived_monthly_sales']) for r in revisions
                          if r['december_ytd_sales'] is not None and r['archived_monthly_sales'] is not None and r['december_ytd_sales']!=r['archived_monthly_sales']]
    source_issues=[dict(r) for r in db.execute('SELECT r.family,r.period,q.* FROM quality_issues q JOIN reports r ON r.id=q.report_id ORDER BY r.period')]
    result={'status':'blocked' if errors else 'extraction_complete_with_source_warnings',
            'integrity':integrity,'errors':errors,'coverage':coverage,'ambiguous_vintages':ambiguous,
            'monthly_resale_rows':monthly,'annual_resale_rows':annual,
            'rental_area_rows':db.execute('SELECT count(*) FROM rental').fetchone()[0],
            'rental_bedroom_rows':db.execute('SELECT count(*) FROM rental_bedrooms').fetchone()[0],
            'rental_coverage':rental_coverage,'resale_source_total_discrepancies':source_issues,
            'rental_source_total_discrepancies':rental_issues,'year_end_revision_differences':revision_differences,
            'public_display_enabled':False,'public_export_enabled':False}
    db.close()
    result['database_sha256']=hashlib.sha256((root/'trreb.sqlite').read_bytes()).hexdigest()
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    result=audit_history(args.root)
    (args.root/'full-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'rental_coverage','resale_source_total_discrepancies','rental_source_total_discrepancies','year_end_revision_differences'}},indent=2))
    print('Resale discrepancies:',len(result['resale_source_total_discrepancies']),
          'Rental discrepancies:',len(result['rental_source_total_discrepancies']),
          'Year-end revision differences:',len(result['year_end_revision_differences']))
    raise SystemExit(1 if result['errors'] else 0)
