"""Read-only development preview. Never enabled in production or for exports."""
import hashlib
import json
from pathlib import Path
import sqlite3

# Reported municipal units, reviewed against their parent-region table grouping.
# These link detail context only, not geometric overlays or tract allocations.
MUNICIPALITIES = {
    '3520005': ('City of Toronto','Toronto'),
    '3521005': ('Mississauga','Peel Region'), '3521010': ('Brampton','Peel Region'),
    '3521024': ('Caledon','Peel Region'),
    '3519028': ('Vaughan','York Region'), '3519036': ('Markham','York Region'),
    '3519038': ('Richmond Hill','York Region'), '3519046': ('Aurora','York Region'),
    '3519048': ('Newmarket','York Region'), '3519049': ('King','York Region'),
    '3519044': ('Stouffville','York Region'), '3519054': ('East Gwillimbury','York Region'),
    '3519070': ('Georgina','York Region'),
    '3518001': ('Pickering','Durham Region'), '3518005': ('Ajax','Durham Region'),
    '3518009': ('Whitby','Durham Region'), '3518013': ('Oshawa','Durham Region'),
    '3518017': ('Clarington','Durham Region'), '3518029': ('Uxbridge','Durham Region'),
    '3518020': ('Scugog','Durham Region'), '3518039': ('Brock','Durham Region'),
    '3524001': ('Oakville','Halton Region'), '3524002': ('Burlington','Halton Region'),
    '3524009': ('Milton','Halton Region'), '3524015': ('Halton Hills','Halton Region'),
}


def read_resale(path: Path, geoid: str, year: int, month: int | None):
    if geoid not in MUNICIPALITIES or not 2020<=year<=2025 or (month is not None and not 1<=month<=12):
        raise ValueError('Unsupported geography or period')
    manifest=json.loads(path.with_name('full-audit.json').read_text())
    if manifest.get('errors') != [] or manifest.get('database_sha256')!=hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError('Historical database requires a fresh successful audit')
    family='resale_annual' if month is None else 'resale'
    period=str(year) if month is None else f'{year}-{month:02}'
    area,parent=MUNICIPALITIES[geoid]
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:
        reports=db.execute("SELECT * FROM reports WHERE family=? AND period=? AND status='validated'",(family,period)).fetchall()
        if len(reports)!=1:
            raise ValueError('Missing or ambiguous report vintage')
        report=dict(reports[0])
        row=db.execute('SELECT * FROM resale WHERE report_id=? AND source_area=?',(report['id'],area)).fetchone()
        if row is None:
            raise ValueError('No published value for this source area')
        warnings=[dict(r) for r in db.execute('SELECT area,field,reported,children_sum,difference FROM quality_issues WHERE report_id=? AND area IN (?,?)',(report['id'],area,parent))]
        return {'geoid':geoid,'source_area':area,'period':period,'period_type':'year' if month is None else 'month',
                'property_type':'All home types','median_price':row['median_price'],'sales':row['sales'],
                'property_days':row['property_days'],'listing_days':row['listing_days'],
                'source_url':report['source_url'],'source_page':report['source_page'],
                'source_sha256':report['sha256'],'warnings':warnings,'preview_only':True,
                'geography_note':'TRREB municipal reporting area; Census boundary equivalence is not certified. No tract allocation.',
                'vintage_note':'Year-end tables include revisions. Monthly figures retain their archived report vintage.'}
    finally:
        db.close()
