import hashlib
import sqlite3

import pytest

from etl import trreb_history as history
from etl.trreb_archive import inventory, official_url
from etl.trreb_annual import annual_rows
from etl.trreb_rental import rental_rows
from etl.pilot_trreb import EXPECTED, FIELDS, GROUPS
from etl.trreb_tables import glyph_rows, legacy_rows


def synthetic_rows():
    indexed={name:{'source_area':name,**dict.fromkeys(FIELDS,1)} for name in EXPECTED}
    for parent,children in {**GROUPS,'All TRREB Areas':list(GROUPS)}.items():
        for field in ('sales','dollar_volume','new_listings','active_listings'):
            indexed[parent][field]=sum(indexed[n][field] for n in children)
    return list(indexed.values())


def entry(root, payload=b'%PDF-synthetic'):
    path=root/f'source-{hashlib.sha256(payload).hexdigest()}.pdf'
    path.write_bytes(payload)
    return {'family':'resale','period':'2020-01','sha256':hashlib.sha256(payload).hexdigest(),
            'file':path.name,'source_url':'https://trreb.ca/report.pdf','retrieved_at':'2026-09-20T00:00:00Z'}


def test_archive_periods_and_deduplication():
    html='<a href=" /wp-content/files/market-stats/market-watch/mw2001.pdf">x</a>'*2
    assert list(inventory(html,'resale',2020,2025))==['2020-01']
    assert not inventory(html,'resale',2021,2025)
    assert list(inventory('<a href="/rental_report_Q4-2025.pdf">x</a>','rental',2020,2025))==['2025-Q4']


@pytest.mark.parametrize('url',['http://trreb.ca/a','https://example.com/a','https://trreb.ca.evil.test/a',
                               'https://user:pass@trreb.ca/a','file:///tmp/x','https://trreb.ca:8443/a'])
def test_only_official_public_https(url):
    with pytest.raises(ValueError):
        official_url(url)


def test_import_is_idempotent_and_readable(tmp_path,monkeypatch):
    monkeypatch.setattr(history,'parse_resale',lambda *args:(synthetic_rows(),3))
    e=entry(tmp_path)
    db=history.connect(tmp_path/'trreb.sqlite')
    assert history.import_report(db,tmp_path,e)=='validated'
    assert history.import_report(db,tmp_path,e)=='cached'
    assert db.execute('SELECT count(*) FROM resale').fetchone()[0]==41
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert db.execute("SELECT value FROM settings WHERE key='public_display_enabled'").fetchone()[0]=='false'
    db.close()


def test_hash_mismatch_cannot_enter_database(tmp_path):
    e=entry(tmp_path)
    e['sha256']='bad'
    db=history.connect(tmp_path/'trreb.sqlite')
    with pytest.raises(ValueError,match='hash'):
        history.import_report(db,tmp_path,e)
    assert db.execute('SELECT count(*) FROM reports').fetchone()[0]==0
    db.close()


def test_failed_parse_has_no_values(tmp_path,monkeypatch):
    def fail(*args):
        raise ValueError('layout changed')
    monkeypatch.setattr(history,'parse_resale',fail)
    db=history.connect(tmp_path/'trreb.sqlite')
    assert history.import_report(db,tmp_path,entry(tmp_path))=='layout changed'
    assert db.execute('SELECT count(*) FROM resale').fetchone()[0]==0
    assert db.execute('SELECT status FROM reports').fetchone()[0]=='failed'
    db.close()


def test_new_vintage_does_not_replace_old_values(tmp_path,monkeypatch):
    monkeypatch.setattr(history,'parse_resale',lambda *args:(synthetic_rows(),3))
    db=history.connect(tmp_path/'trreb.sqlite')
    e=entry(tmp_path)
    history.import_report(db,tmp_path,e)
    revised=entry(tmp_path,b'%PDF-revised')
    history.import_report(db,tmp_path,revised)
    assert db.execute('SELECT count(*) FROM reports').fetchone()[0]==2
    assert db.execute('SELECT count(*) FROM resale').fetchone()[0]==82
    db.close()


def test_source_discrepancy_is_preserved_not_repaired(tmp_path,monkeypatch):
    rows=synthetic_rows()
    next(r for r in rows if r['source_area']=='Durham Region')['new_listings']+=1
    monkeypatch.setattr(history,'parse_resale',lambda *args:(rows,3))
    db=history.connect(tmp_path/'trreb.sqlite')
    history.import_report(db,tmp_path,entry(tmp_path))
    assert db.execute('SELECT count(*) FROM quality_issues').fetchone()[0]==2
    assert db.execute("SELECT new_listings FROM resale WHERE source_area='Durham Region'").fetchone()[0]==9
    db.close()


class TextPage:
    width,height=836.88,612

    def __init__(self,header,body):
        self.header,self.body=header,body
        self.cropped=False

    def crop(self,box):
        return TextPage(self.header,self.header)

    def extract_text(self):
        return self.body


def test_rental_zero_transactions_do_not_mean_free_rent():
    body='Total Listed Total Leased Bachelor One Bedroom Avg. Lease Rate\n'+'\n'.join(
        name+' 0 0 0 $0 0 $0 0 $0 0 $0' for name in sorted(EXPECTED))
    page=TextPage('SUMMARY OF RENTAL TRANSACTIONS APARTMENTS, FIRST QUARTER 2020',body)
    rows=rental_rows(page,'2020-Q1')
    assert len(rows)==41
    assert rows[0]['bedrooms'][0]['average_rent'] is None
    assert rows[0]['bedrooms'][0]['raw_average_rent']==0
    assert rows[0]['bedrooms'][0]['quality']=='no_transactions'
    with pytest.raises(ValueError):
        rental_rows(page,'2020-Q2')


def test_annual_is_not_monthly_median_average():
    rows=synthetic_rows()
    body='Dollar Volume Average Price Median Price New Listings SP/LP LDOM PDOM\n'
    for row in rows:
        body+=row['source_area']+' '+ ' '.join(str(row[f]) for f in ('sales','dollar_volume','average_price','median_price','new_listings','sale_to_list_pct','listing_days','property_days'))+'\n'
    page=TextPage('SUMMARY OF EXISTING HOME TRANSACTIONS ALL HOME TYPES, YEAR-TO-DATE 2020',body)
    result=annual_rows(page,'2020')
    assert len(result)==41
    assert all(r['active_listings'] is None for r in result)
    with pytest.raises(ValueError):
        annual_rows(page,'2021')


def test_overprinted_rental_rows_use_visible_runs_and_numeric_anchor():
    page=SimpleGlyphPage()
    page.add('All TRREB Areas',25,120)
    page.add('999',115,119.28)
    page.add('123',115,119.28)  # later painted value replaces old value
    page.add('All TRREB Areas',25,132)
    page.add('Halton Region',25,132)  # later painted label replaces displaced mark
    page.add('23',115,131.28)
    assert glyph_rows(page,92,67,1,114,overprinted=True)==[
        ('All TRREB Areas',['123']),('Halton Region',['23'])]


class SimpleGlyphPage:
    def __init__(self):
        self.chars=[]

    def add(self,text,x,top):
        self.chars.extend({'text':c,'x0':x+i*2,'top':top,'size':6.48} for i,c in enumerate(text))


def test_unknown_numeric_legacy_row_fails_closed():
    page = TextPage('', 'Unrecognized Municipality 1 1 0 $0 1 $2000 0 $0 0 $0')
    with pytest.raises(ValueError, match='Unknown source row'):
        legacy_rows(page, 10)


def test_reviewed_header_footnotes_are_not_data_rows():
    page = TextPage('', '1 2 2 3 2 3 2 3 2 3\nAjax 0 0 0 $0 0 $0 0 $0 0 $0')
    assert legacy_rows(page, 10) == [('Ajax', ['0', '0', '0', '$0', '0', '$0', '0', '$0', '0', '$0'])]


def test_unexpected_missing_rental_municipality_fails_closed():
    body = 'Total Listed Total Leased Bachelor One Bedroom Avg. Lease Rate\n' + '\n'.join(
        name + ' 0 0 0 $0 0 $0 0 $0 0 $0' for name in sorted(EXPECTED - {'Ajax'}))
    page = TextPage('SUMMARY OF RENTAL TRANSACTIONS APARTMENTS, FIRST QUARTER 2020', body)
    with pytest.raises(ValueError, match='coverage'):
        rental_rows(page, '2020-Q1')


@pytest.mark.parametrize('force', [False, True])
def test_reprocess_replaces_values_without_duplicates(tmp_path, monkeypatch, force):
    rows = synthetic_rows()
    monkeypatch.setattr(history, 'parse_resale', lambda *args: (rows, 3))
    db = history.connect(tmp_path / 'trreb.sqlite')
    e = entry(tmp_path)
    history.import_report(db, tmp_path, e)
    for row in rows:
        row['median_price'] = 77
    if not force:
        monkeypatch.setattr(history, 'parser_version', lambda family: 'new-parser')
    assert history.import_report(db, tmp_path, e, reprocess=force) == 'validated'
    assert db.execute('SELECT count(*) FROM resale').fetchone()[0] == 41
    assert db.execute('SELECT DISTINCT median_price FROM resale').fetchall() == [(77,)]
    assert db.execute('SELECT count(*) FROM reports').fetchone()[0] == 1
    db.close()


def test_failed_reprocess_invalidates_stale_values(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'parse_resale', lambda *args: (synthetic_rows(), 3))
    db = history.connect(tmp_path / 'trreb.sqlite')
    e = entry(tmp_path)
    history.import_report(db, tmp_path, e)
    def fail(*args):
        raise ValueError('layout changed')
    monkeypatch.setattr(history, 'parse_resale', fail)
    assert history.import_report(db, tmp_path, e, reprocess=True) == 'layout changed'
    assert db.execute('SELECT count(*) FROM resale').fetchone()[0] == 0
    assert db.execute('SELECT status FROM reports').fetchone()[0] == 'failed'
    assert (tmp_path / e['file']).exists()
    db.close()


def test_cli_returns_failure_on_failed_download(tmp_path, monkeypatch):
    import json
    import sys
    (tmp_path / 'resale-downloads.json').write_text(json.dumps([{'status': 'failed'}]))
    monkeypatch.setattr(sys, 'argv', ['trreb_history', '--root', str(tmp_path)])
    assert history.main() == 1
