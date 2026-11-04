"""Run the CMHC correction against Postgres, only in a disposable test schema."""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.models import CmhcMetric, Geography
from test_cmhc_corrections import (
    assert_custom_values_preserved,
    assert_scoped_correction_round_trip,
    migration,
    populate_cmhc,
)


@pytest.mark.skipif(not os.getenv("POSTGIS_TEST_DATABASE_URL"), reason="Dedicated PostGIS test database required")
def test_postgres_cmhc_correction_is_scoped_idempotent_and_preserves_custom_values():
    url = os.environ["POSTGIS_TEST_DATABASE_URL"]
    schema = "cmhc_correction_test_" + uuid.uuid4().hex
    control = create_engine(url)
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with control.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        Geography.__table__.create(engine)
        CmhcMetric.__table__.create(engine)
        with engine.begin() as connection:
            assert migration.apply_cmhc_corrections(connection, migration.load_corrections())["missing"] == 90
            populate_cmhc(connection)
            assert_scoped_correction_round_trip(connection)
            assert_custom_values_preserved(connection)
    finally:
        engine.dispose()
        # Name is generated above; no externally supplied schema can be dropped.
        assert schema.startswith("cmhc_correction_test_") and len(schema) == 53
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        control.dispose()
