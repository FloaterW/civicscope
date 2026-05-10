from app.services.postgis import (
    has_geom_column,
    load_postgis_map_geometries,
    supports_postgis,
    sync_geography_geoms,
)


def test_postgis_helpers_are_noops_on_sqlite(db_session):
    assert supports_postgis(db_session) is False
    assert has_geom_column(db_session) is False
    assert sync_geography_geoms(db_session) == 0
    assert load_postgis_map_geometries(db_session, year=2021, detail="display") == {}
