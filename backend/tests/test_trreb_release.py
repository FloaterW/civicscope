"""Release lifecycle and API use invented source data, never publisher data."""
import copy
import hashlib
import json
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.trreb_public import router
from app.db.session import get_db
from app.models.trreb import TrrebRelease, TrrebObservation, TrrebPublication, TrrebPublicationEvent
from etl.trreb_release import (activate_release, draft_manifest, import_release,
    prepare_release, validate_manifest, digest, main)
from etl.trreb_history import connect, import_report
from etl.trreb_rental import import_rental, expected_rental_areas, BEDROOMS
from etl.trreb_parser_version import parser_version
from etl.pilot_trreb import EXPECTED, FIELDS


@pytest.fixture
def archive(tmp_path, monkeypatch):
    payload = b'%PDF-synthetic-release-fixture'
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


@pytest.fixture
def engine():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    tables = [model.__table__ for model in (TrrebRelease, TrrebObservation, TrrebPublication, TrrebPublicationEvent)]
    for table in tables:
        table.create(engine)
    with engine.begin() as connection:
        connection.execute(TrrebPublication.__table__.insert().values(id=1, release_id=None))
    yield engine
    engine.dispose()


def test_prepare_is_deterministic_audited_and_read_only(archive):
    before = (archive / 'trreb.sqlite').read_bytes()
    manifest = draft_manifest(archive)
    release = prepare_release(archive, manifest)
    assert release == prepare_release(archive, manifest)
    assert len(release['observations']) == 1950
    assert len(release['manifest']['reports']) == 102
    assert {row['period_type'] for row in release['observations']} == {'year', 'month'}
    assert (archive / 'trreb.sqlite').read_bytes() == before
    assert release['observations'][0]['geography_note'].endswith('No tract allocation.')


def test_web_export_excludes_private_release_material_and_requires_approval(archive):
    from etl.export_trreb_web import public_archive
    release = prepare_release(archive, draft_manifest(archive))
    exported = public_archive(release, release['release_id'])
    assert set(exported) == {'schema_version', 'source_release', 'observations'}
    assert exported['observations'] == release['observations']
    with pytest.raises(ValueError, match='separately approved'):
        public_archive(release, '0' * 64)
    changed = copy.deepcopy(release)
    changed['observations'][0]['sales'] += 1
    with pytest.raises(ValueError, match='hash mismatch'):
        public_archive(changed, release['release_id'])


@pytest.mark.parametrize('mutation,match', [
    (lambda m: m['reports'].pop(), 'all 102'),
    (lambda m: m['reports'].__setitem__(0, m['reports'][1]), 'duplicate'),
    (lambda m: m.update(revision_policy='latest'), 'revision policy'),
])
def test_manifest_rejects_implicit_partial_or_duplicate_selection(archive, mutation, match):
    manifest = draft_manifest(archive)
    mutation(manifest)
    with pytest.raises(ValueError, match=match):
        validate_manifest(manifest)


def test_hash_tamper_and_stale_parser_fail_closed(archive):
    manifest = draft_manifest(archive)
    (archive / 'source.pdf').write_bytes(b'%PDF-modified')
    with pytest.raises(ValueError, match='Invalid source hash'):
        prepare_release(archive, manifest)
    with sqlite3.connect(archive / 'trreb.sqlite') as db:
        db.execute("UPDATE reports SET parser_version='stale' WHERE id=1")
    with pytest.raises(ValueError, match='Archive changed'):
        prepare_release(archive, manifest)
    with pytest.raises(ValueError, match='Stale parser'):
        prepare_release(archive, draft_manifest(archive))


def test_explicit_revision_selection_retains_original_archive(archive):
    manifest = draft_manifest(archive)
    old_pin = next(row for row in manifest['reports'] if row['family'] == 'resale' and row['period'] == '2020-01')
    revised = b'%PDF-synthetic-revised-report'
    (archive / 'revised.pdf').write_bytes(revised)
    sha = hashlib.sha256(revised).hexdigest()
    with sqlite3.connect(archive / 'trreb.sqlite') as db:
        columns = [row[1] for row in db.execute('PRAGMA table_info(reports)') if row[1] != 'id']
        original = db.execute("SELECT id FROM reports WHERE family='resale' AND period='2020-01'").fetchone()[0]
        record = dict(zip(columns, db.execute(f'SELECT {",".join(columns)} FROM reports WHERE id=?', (original,)).fetchone()))
        record.update(sha256=sha, local_file='revised.pdf')
        inserted = db.execute(f'INSERT INTO reports ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})', [record[key] for key in columns]).lastrowid
        resale_columns = [row[1] for row in db.execute('PRAGMA table_info(resale)') if row[1] != 'report_id']
        db.execute(f'INSERT INTO resale SELECT ?,{",".join(resale_columns)} FROM resale WHERE report_id=?', (inserted, original))
        db.execute('UPDATE resale SET median_price=123456 WHERE report_id=?', (inserted,))
    with pytest.raises(ValueError, match='ambiguous'):
        draft_manifest(archive)
    manifest['archive_sha256'] = hashlib.sha256((archive / 'trreb.sqlite').read_bytes()).hexdigest()
    original_release = prepare_release(archive, manifest)
    old_pin['sha256'] = sha
    revised_release = prepare_release(archive, manifest)
    assert revised_release['release_id'] != original_release['release_id']
    assert {row['median_price'] for row in revised_release['observations'] if row['period'] == '2020-01'} == {123456}
    assert {row['median_price'] for row in original_release['observations'] if row['period'] == '2020-01'} == {0}
    with sqlite3.connect(archive / 'trreb.sqlite') as db:
        assert db.execute('SELECT count(*) FROM reports').fetchone()[0] == 103


def test_import_is_idempotent_and_does_not_activate(archive, engine):
    release = prepare_release(archive, draft_manifest(archive))
    assert import_release(engine, release) == import_release(engine, release)
    with engine.connect() as connection:
        assert connection.execute(select(TrrebPublication.release_id)).scalar_one() is None
        assert len(connection.execute(select(TrrebObservation.geoid)).all()) == 1950
    damaged = copy.deepcopy(release)
    damaged['observations'][0]['median_price'] = 7
    with pytest.raises(ValueError, match='hash mismatch'):
        import_release(engine, damaged)


def test_mid_import_failure_rolls_back_everything(archive, engine):
    release = prepare_release(archive, draft_manifest(archive))
    def fail_rows(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith('INSERT INTO trreb_observations'):
            raise RuntimeError('synthetic write failure')
    event.listen(engine, 'before_cursor_execute', fail_rows)
    try:
        with pytest.raises(RuntimeError, match='synthetic write failure'):
            import_release(engine, release)
    finally:
        event.remove(engine, 'before_cursor_execute', fail_rows)
    with engine.connect() as connection:
        assert connection.execute(select(TrrebRelease.id)).all() == []
        assert connection.execute(select(TrrebObservation.geoid)).all() == []


@pytest.mark.parametrize('field,value,match', [
    ('source_area', 'Unknown', 'reporting area'),
    ('median_price', -1, 'headline'),
    ('source_sha256', '0' * 64, 'selected source vintage'),
    ('period_type', 'quarter', 'period'),
    ('source_url', 'https://example.org/not-trreb.pdf', 'source URL'),
    ('source_page', 0, 'source page'),
    ('warnings', [{'area': 'City of Toronto', 'field': [], 'reported': 1, 'children_sum': 1, 'difference': 0}], 'warning context'),
    ('warnings', [{'area': 'City of Toronto', 'field': 'sales', 'reported': 10**400, 'children_sum': 1, 'difference': 0}], 'warning value'),
])
def test_rehashed_malformed_bundle_cannot_be_imported(archive, engine, field, value, match):
    release = prepare_release(archive, draft_manifest(archive))
    release['observations'][0][field] = copy.deepcopy(value)
    if field == 'warnings':
        for warning in release['observations'][0]['warnings']:
            warning['area'] = release['observations'][0]['source_area']
    release['release_id'] = digest({key: value for key, value in release.items() if key != 'release_id'})
    with pytest.raises(ValueError, match=match):
        import_release(engine, release)


def test_rehashed_incomplete_audit_cannot_be_imported(archive, engine):
    release = prepare_release(archive, draft_manifest(archive))
    release['audit_summary']['coverage']['resale']['missing'] = ['2020-01']
    release['release_id'] = digest({key: value for key, value in release.items() if key != 'release_id'})
    with pytest.raises(ValueError, match='Incomplete audited'):
        import_release(engine, release)


@pytest.mark.parametrize('value', [None, [], 'invalid', 12, True])
def test_bundle_cli_rejects_nonobject_json(tmp_path, monkeypatch, value):
    bundle = tmp_path / 'invalid.json'
    bundle.write_text(json.dumps(value), encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['trreb_release', 'import-bundle', '--bundle', str(bundle),
                                   '--approved-release', '0' * 64])
    with pytest.raises(ValueError, match='separately approved'):
        main()


def test_activation_disable_rollback_and_concurrent_guard(archive, engine):
    release = prepare_release(archive, draft_manifest(archive))
    release_id = import_release(engine, release)
    activate_release(engine, release_id, expected_active=None, reason='Verified initial release')
    with pytest.raises(ValueError, match='changed'):
        activate_release(engine, None, expected_active=None, reason='Stale operator')
    activate_release(engine, None, expected_active=release_id, reason='Rehearse rollback')
    activate_release(engine, release_id, expected_active=None, reason='Restore approved release')
    with engine.connect() as connection:
        assert connection.execute(select(TrrebPublication.release_id)).scalar_one() == release_id
        assert len(connection.execute(select(TrrebPublicationEvent.id)).all()) == 3
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM trreb_observations WHERE geoid='3520005' AND period='2025'"))
    with pytest.raises(ValueError, match='hash mismatch'):
        activate_release(engine, release_id, expected_active=release_id, reason='Cannot republish corruption')


def test_public_api_gates_periods_geography_provenance_and_no_writes(archive, engine, monkeypatch):
    app = FastAPI()
    app.include_router(router)
    def db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = db
    client = TestClient(app)
    monkeypatch.delenv('TRREB_PUBLIC_ENABLED', raising=False)
    assert client.get('/api/trreb/resale/3520005').status_code == 404
    monkeypatch.setenv('TRREB_PUBLIC_ENABLED', '1')
    assert client.get('/api/trreb/resale/3520005').status_code == 503
    release = prepare_release(archive, draft_manifest(archive))
    release_id = import_release(engine, release)
    activate_release(engine, release_id, expected_active=None, reason='Synthetic fixture')
    response = client.get('/api/trreb/resale/3520005?year=2020&month=1')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    body = response.json()
    assert body['release_id'] == release_id
    assert body['preview_only'] is False
    assert body['period'] == '2020-01' and body['source_area'] == 'City of Toronto'
    assert body['source_url'] == 'https://trreb.ca/synthetic.pdf'
    assert body['attribution'].startswith('Source: Toronto Regional Real Estate Board')
    assert client.get('/api/trreb/resale/5350403.16').status_code == 404
    assert client.get('/api/trreb/resale/3520005?year=2019').status_code == 422
    assert client.get('/api/trreb/resale/3520005?month=13').status_code == 422
    assert client.post('/api/trreb/resale/3520005', json={}).status_code == 405
    assert client.get('/api/trreb/rental/3520005').status_code == 404
    with engine.begin() as connection:
        connection.execute(TrrebObservation.__table__.update().where(
            TrrebObservation.geoid == '3520005', TrrebObservation.period == '2025').values(payload={'broken': True}))
    assert client.get('/api/trreb/resale/3520005?year=2025').status_code == 503
    activate_release(engine, None, expected_active=release_id, reason='Disable rehearsal')
    assert client.get('/api/trreb/resale/3520005').status_code == 503
    monkeypatch.setenv('TRREB_PUBLIC_ENABLED', '0')
    assert client.get('/api/trreb/resale/3520005').status_code == 404
