import os

import pytest
from sqlalchemy import create_engine, text


POSTGIS_TEST_DATABASE_URL = os.getenv("POSTGIS_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not POSTGIS_TEST_DATABASE_URL,
    reason="POSTGIS_TEST_DATABASE_URL is required for PostGIS integration tests",
)


@pytest.fixture(scope="module")
def postgis_engine():
    engine = create_engine(POSTGIS_TEST_DATABASE_URL)
    try:
        yield engine
    finally:
        engine.dispose()


def test_postgis_extension_and_geometry_column(postgis_engine):
    with postgis_engine.connect() as connection:
        version = connection.execute(text("SELECT PostGIS_Version()")).scalar_one()
        geom_type = connection.execute(
            text(
                """
                SELECT type
                FROM geometry_columns
                WHERE f_table_name = 'geographies' AND f_geometry_column = 'geom'
                """
            )
        ).scalar_one()

    assert version
    assert geom_type == "GEOMETRY"


def test_seeded_geographies_have_valid_postgis_geometry(postgis_engine):
    with postgis_engine.connect() as connection:
        row_count, invalid_count, missing_count = connection.execute(
            text(
                """
                SELECT
                    COUNT(*),
                    COUNT(*) FILTER (WHERE geom IS NOT NULL AND NOT ST_IsValid(geom)),
                    COUNT(*) FILTER (WHERE geom IS NULL)
                FROM geographies
                """
            )
        ).one()

    assert row_count > 0
    assert invalid_count == 0
    assert missing_count == 0
