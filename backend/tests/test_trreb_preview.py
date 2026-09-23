import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import trreb_preview as api
from app.services.trreb_preview import MUNICIPALITIES, read_resale
from etl.trreb_history import connect
from etl.pilot_trreb import FIELDS


def fixture_db(root):
    path=root/'trreb.sqlite'
    db=connect(path)
    with db:
        db.execute("INSERT INTO reports(id,family,period,sha256,source_url,local_file,retrieved_at,parsed_at,source_page,status) VALUES (1,'resale_annual','2025','hash','https://trreb.ca/report.pdf','report.pdf','now','now',5,'validated')")
        values={key:1 for key in FIELDS}
        values['median_price']=123456
        db.execute(f'INSERT INTO resale VALUES ({",".join("?" for _ in range(len(FIELDS)+3))})',
                   [1,'City of Toronto','all_home_types',*(values[k] for k in FIELDS)])
    db.close()
    (root/'full-audit.json').write_text(json.dumps({'errors':[],'database_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
    return path


def test_municipalities_match_scope_and_parent_regions():
    seed=json.loads((Path(__file__).parents[1]/'app/data/demo_seed.json').read_text())
    municipalities={r['geoid']:r for r in seed['geographies'] if r['type']=='municipality'}
    assert set(MUNICIPALITIES)==set(municipalities)
    aliases={'Toronto':'City of Toronto','Whitchurch-Stouffville':'Stouffville'}
    for geoid,(area,parent) in MUNICIPALITIES.items():
        assert municipalities[geoid]['county']==parent
        assert aliases.get(municipalities[geoid]['name'],municipalities[geoid]['name'])==area


def test_read_is_audited_and_does_not_modify_database(tmp_path):
    path=fixture_db(tmp_path)
    before=path.read_bytes()
    result=read_resale(path,'3520005',2025,None)
    assert result['median_price']==123456
    assert result['source_page']==5
    assert result['period_type']=='year'
    assert path.read_bytes()==before
    with pytest.raises(ValueError):
        read_resale(path,'5350403.16',2025,None)


def test_unreviewed_changes_invalidate_preview(tmp_path):
    path=fixture_db(tmp_path)
    db=connect(path)
    with db:
        db.execute("UPDATE resale SET median_price=999")
    db.close()
    with pytest.raises(ValueError,match='fresh successful audit'):
        read_resale(path,'3520005',2025,None)


def client(monkeypatch,tmp_path,env='development',enabled='1',host='testclient'):
    monkeypatch.setattr(api,'settings',SimpleNamespace(app_env=env))
    monkeypatch.setenv('TRREB_PREVIEW_ENABLED',enabled)
    monkeypatch.setenv('TRREB_DATABASE',str(fixture_db(tmp_path)))
    app=FastAPI()
    app.include_router(api.router)
    return TestClient(app,client=(host,50000))


@pytest.mark.parametrize('env,enabled,host',[('production','1','testclient'),('development','0','testclient'),('development','1','203.0.113.1')])
def test_preview_is_closed_outside_explicit_local_development(monkeypatch,tmp_path,env,enabled,host):
    c=client(monkeypatch,tmp_path,env,enabled,host)
    assert c.get('/api/trreb-preview/3520005').status_code==404


def test_preview_returns_source_and_rejects_bad_inputs(monkeypatch,tmp_path):
    c=client(monkeypatch,tmp_path)
    r=c.get('/api/trreb-preview/3520005?year=2025')
    assert r.status_code==200
    assert r.headers['cache-control']=='no-store'
    assert r.json()['preview_only'] is True
    assert c.get('/api/trreb-preview/3520005?year=2019').status_code==422
    assert c.get('/api/trreb-preview/3520005?month=13').status_code==422
    assert c.get('/api/trreb-preview/5350403.16').status_code==404
    assert c.get('/api/trreb-preview/3520005?year=2025&month=1').status_code==503
