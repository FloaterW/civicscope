"""Audit contracts use synthetic fixtures; no publisher data is shipped to CI."""
import hashlib
import sqlite3

import pytest

from etl.audit_trreb import audit_history
from etl.trreb_history import connect, import_report
from etl.trreb_parser_version import parser_version
from etl.trreb_rental import import_rental, expected_rental_areas, BEDROOMS
from etl.pilot_trreb import EXPECTED, FIELDS


@pytest.fixture
def archive(tmp_path, monkeypatch):
    payload = b'%PDF-synthetic-audit-fixture'
    (tmp_path / 'source.pdf').write_bytes(payload)
    entry = {'family': 'resale', 'file': 'source.pdf', 'sha256': hashlib.sha256(payload).hexdigest(),
             'source_url': 'https://trreb.ca/synthetic.pdf', 'retrieved_at': 'test'}
    rows = [{'source_area': name, **dict.fromkeys(FIELDS, 0)} for name in EXPECTED]
    monkeypatch.setattr('etl.trreb_history.parse_resale', lambda *args: (rows, 3))
    monkeypatch.setattr('etl.trreb_rental.parse_rental', lambda path, period: [
        {'source_area': name, 'total_listed': 0, 'total_leased': 0,
         'bedrooms': [{'bedroom': b, 'leased': 0, 'average_rent': None,
                       'raw_average_rent': 0, 'quality': 'no_transactions'} for b in BEDROOMS]}
        for name in expected_rental_areas(period)])
    db = connect(tmp_path / 'trreb.sqlite')
    for year in range(2020, 2026):
        for month in range(1, 13):
            assert import_report(db, tmp_path, dict(entry, period=f'{year}-{month:02}')) == 'validated'
        for quarter in range(1, 5):
            import_rental(db, tmp_path, dict(entry, period=f'{year}-Q{quarter}'))
        with db:
            cursor = db.execute('''INSERT INTO reports(family,period,sha256,source_url,local_file,retrieved_at,
                source_page,status,parser_version) VALUES ('resale_annual',?,?,?,?,?,5,'validated',?)''',
                (str(year), entry['sha256'], entry['source_url'], entry['file'], 'test', parser_version('resale_annual')))
            for row in rows:
                db.execute(f'INSERT INTO resale VALUES ({",".join("?" for _ in range(len(FIELDS)+3))})',
                           [cursor.lastrowid, row['source_area'], 'all_home_types', *(row[f] for f in FIELDS)])
    db.close()
    return tmp_path


def test_complete_archive_passes(archive):
    assert audit_history(archive)['errors'] == []


@pytest.mark.parametrize('mutation,expected', [
    ("UPDATE reports SET parser_version='old' WHERE id=1", 'Stale parser'),
    ("DELETE FROM rental_bedrooms WHERE source_area='Ajax' AND bedroom='bachelor'", 'Missing rental bedroom'),
    ("UPDATE resale SET source_area='Unknown' WHERE source_area='Ajax' AND report_id=1", 'Unexpected resale areas'),
])
def test_audit_blocks_stale_or_incomplete_extractions(archive, mutation, expected):
    with sqlite3.connect(archive / 'trreb.sqlite') as db:
        db.execute(mutation)
    assert any(expected in error for error in audit_history(archive)['errors'])
