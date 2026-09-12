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


def test_full_packaged_seed_populates_application_datasets(postgis_engine):
    with postgis_engine.connect() as connection:
        geography_count = connection.execute(text("SELECT COUNT(*) FROM geographies")).scalar_one()
        metric_count = connection.execute(text("SELECT COUNT(*) FROM metrics")).scalar_one()
        cmhc_count = connection.execute(text("SELECT COUNT(*) FROM cmhc_metrics")).scalar_one()
        cmhc_tract_count = connection.execute(
            text("SELECT COUNT(*) FROM cmhc_tract_metrics")
        ).scalar_one()
        transit_count = connection.execute(
            text("SELECT COUNT(*) FROM metrics WHERE transit_score IS NOT NULL")
        ).scalar_one()

    assert geography_count > 0
    assert metric_count > 0
    assert cmhc_count > 0
    assert cmhc_tract_count > 0
    assert transit_count > 0


def test_transit_spatial_index_preserves_counts_and_zero_service_tracts(postgis_engine):
    from etl.load_transit import compute_scores_postgis, normalize_route_counts

    stops = {
        (43.65, -79.38): {"test:shared", "test:second"},
        (43.6501, -79.3801): {"test:shared"},
        (0.0, 0.0): {"test:outside"},
    }
    # Independently calculate the baseline with a tiny unindexed VALUES table.
    with postgis_engine.connect() as connection:
        rows = connection.execute(text("""
            WITH stops(lat, lon, route_id) AS (VALUES
                (43.65, -79.38, 'test:shared'),
                (43.65, -79.38, 'test:second'),
                (43.6501, -79.3801, 'test:shared'),
                (0.0, 0.0, 'test:outside')
            )
            SELECT g.geoid, COUNT(DISTINCT s.route_id) AS route_count
            FROM geographies g
            LEFT JOIN stops s ON ST_DWithin(
                g.geom::geography,
                ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326)::geography,
                800
            )
            WHERE g.type = 'census_tract' AND g.geom IS NOT NULL
            GROUP BY g.geoid
        """)).mappings().all()
    expected = {row["geoid"]: int(row["route_count"]) for row in rows}
    assert 0 in expected.values()
    assert 2 in expected.values()
    assert max(expected.values()) == 2  # Shared route is counted once.
    assert compute_scores_postgis(stops, POSTGIS_TEST_DATABASE_URL) == normalize_route_counts(expected)
