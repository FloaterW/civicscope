"""Real Postgres release lifecycle, isolated from seeded application tables."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.trreb import TrrebRelease, TrrebObservation, TrrebPublication, TrrebPublicationEvent
from app.services.trreb_public import read_public_resale
from etl.trreb_release import activate_release, draft_manifest, import_release, prepare_release
from test_trreb_release import archive  # noqa: F401 - shared synthetic fixture


@pytest.mark.skipif(not os.getenv('POSTGIS_TEST_DATABASE_URL'), reason='Dedicated PostGIS test database required')
def test_postgres_import_activation_read_and_rollback(archive):
    url = os.environ['POSTGIS_TEST_DATABASE_URL']
    # Only this random schema is created/dropped; never modify public app data.
    schema = 'trreb_test_' + uuid.uuid4().hex
    control = create_engine(url)
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    try:
        with control.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        for model in (TrrebRelease, TrrebObservation, TrrebPublication, TrrebPublicationEvent):
            model.__table__.create(engine)
        with engine.begin() as connection:
            connection.execute(TrrebPublication.__table__.insert().values(id=1, release_id=None))
        release = prepare_release(archive, draft_manifest(archive))
        release_id = import_release(engine, release)
        assert import_release(engine, release) == release_id
        barrier = Barrier(2)
        def competing_activation():
            barrier.wait(timeout=10)
            try:
                activate_release(engine, release_id, expected_active=None, reason='Concurrent lifecycle verification')
                return 'activated'
            except ValueError as exc:
                assert 'changed' in str(exc)
                return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: competing_activation(), range(2)))
        assert sorted(results) == ['activated', 'rejected']
        with Session(engine) as session:
            result = read_public_resale(session, '3520005', 2020, 1)
            assert result['period'] == '2020-01'
            assert result['release_id'] == release_id
        with pytest.raises(ValueError, match='changed'):
            activate_release(engine, None, expected_active=None, reason='Stale writer')
        activate_release(engine, None, expected_active=release_id, reason='Rollback rehearsal')
        with Session(engine) as session:
            with pytest.raises(ValueError, match='No active'):
                read_public_resale(session, '3520005', 2020, 1)
        # Fault a payload, verify no activation and no partial pointer change.
        with engine.begin() as connection:
            connection.execute(text('DELETE FROM trreb_observations WHERE geoid=:geoid AND period=:period'),
                               {'geoid': '3520005', 'period': '2020'})
        with pytest.raises(ValueError, match='hash mismatch'):
            activate_release(engine, release_id, expected_active=None, reason='Reject broken release')
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        control.dispose()
