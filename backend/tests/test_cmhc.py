import pytest
from sqlalchemy.exc import IntegrityError

from app.models import CmhcMetric, Geography
from app.services.seed import load_cmhc_seed, seed_cmhc_data


def test_seed_cmhc_data_reseeds_when_a_value_changed(db_session):
    # The CMHC freshness check must catch value-to-value drift, not only
    # null-to-value. Otherwise a stale Docker volume keeps superseded CMHC
    # values (e.g. an old vacancy rate) until a manual FORCE_RESEED.
    seed = load_cmhc_seed()
    target = next(m for m in seed["metrics"] if m.get("vacancy_rate") is not None)
    row = (
        db_session.query(CmhcMetric)
        .filter(CmhcMetric.geoid == target["geoid"], CmhcMetric.year == target["year"])
        .one()
    )
    official = row.vacancy_rate
    row.vacancy_rate = official + 5.0
    db_session.commit()

    reseeded = seed_cmhc_data(db_session)  # no force
    assert reseeded > 0

    restored = (
        db_session.query(CmhcMetric)
        .filter(CmhcMetric.geoid == target["geoid"], CmhcMetric.year == target["year"])
        .one()
    )
    assert restored.vacancy_rate == official


def test_seed_cmhc_data_reseeds_when_a_value_becomes_null(db_session):
    seed = load_cmhc_seed()
    target = next(m for m in seed["metrics"] if m.get("vacancy_rate") is None)
    row = (
        db_session.query(CmhcMetric)
        .filter(CmhcMetric.geoid == target["geoid"], CmhcMetric.year == target["year"])
        .one()
    )
    row.vacancy_rate = 12.3
    db_session.commit()

    reseeded = seed_cmhc_data(db_session)
    assert reseeded > 0

    restored = (
        db_session.query(CmhcMetric)
        .filter(CmhcMetric.geoid == target["geoid"], CmhcMetric.year == target["year"])
        .one()
    )
    assert restored.vacancy_rate is None


def test_seed_cmhc_data_removes_rows_no_longer_in_seed(db_session):
    geoid = load_cmhc_seed()["metrics"][0]["geoid"]
    db_session.add(CmhcMetric(geoid=geoid, year=2099, rms_surveyed=False))
    db_session.commit()

    reseeded = seed_cmhc_data(db_session)

    assert reseeded > 0
    assert (
        db_session.query(CmhcMetric)
        .filter(CmhcMetric.geoid == geoid, CmhcMetric.year == 2099)
        .one_or_none()
        is None
    )


def test_cmhc_metric_creation(db_session):
    metric = CmhcMetric(
        geoid="3520005",
        year=2010,
        vacancy_rate=2.5,
        average_rent_total=1850.0,
        average_rent_bachelor=1200.0,
        average_rent_1br=1600.0,
        average_rent_2br=1950.0,
        average_rent_3br_plus=2400.0,
        turnover_rate=15.3,
        availability_rate=3.1,
        rental_universe=45000,
        housing_starts_total=3200,
        housing_starts_single=400,
        housing_starts_semi=150,
        housing_starts_row=250,
        housing_starts_apartment=2400,
        housing_completions=2900,
        units_under_construction=8500,
        unabsorbed_units=350,
        rms_surveyed=True,
    )
    db_session.add(metric)
    db_session.flush()

    db_session.expire(metric)
    loaded = db_session.get(CmhcMetric, metric.id)

    assert loaded is not None
    assert loaded.geoid == "3520005"
    assert loaded.year == 2010
    assert loaded.vacancy_rate == pytest.approx(2.5)
    assert loaded.average_rent_total == pytest.approx(1850.0)
    assert loaded.average_rent_bachelor == pytest.approx(1200.0)
    assert loaded.average_rent_1br == pytest.approx(1600.0)
    assert loaded.average_rent_2br == pytest.approx(1950.0)
    assert loaded.average_rent_3br_plus == pytest.approx(2400.0)
    assert loaded.turnover_rate == pytest.approx(15.3)
    assert loaded.availability_rate == pytest.approx(3.1)
    assert loaded.rental_universe == 45000
    assert loaded.housing_starts_total == 3200
    assert loaded.housing_starts_single == 400
    assert loaded.housing_starts_semi == 150
    assert loaded.housing_starts_row == 250
    assert loaded.housing_starts_apartment == 2400
    assert loaded.housing_completions == 2900
    assert loaded.units_under_construction == 8500
    assert loaded.unabsorbed_units == 350
    assert loaded.rms_surveyed is True


def test_cmhc_metric_nullable_fields(db_session):
    metric = CmhcMetric(
        geoid="3520005",
        year=2011,
        vacancy_rate=1.8,
    )
    db_session.add(metric)
    db_session.flush()

    db_session.expire(metric)
    loaded = db_session.get(CmhcMetric, metric.id)

    assert loaded.vacancy_rate == pytest.approx(1.8)
    assert loaded.average_rent_total is None
    assert loaded.average_rent_bachelor is None
    assert loaded.average_rent_1br is None
    assert loaded.average_rent_2br is None
    assert loaded.average_rent_3br_plus is None
    assert loaded.turnover_rate is None
    assert loaded.availability_rate is None
    assert loaded.rental_universe is None
    assert loaded.housing_starts_total is None
    assert loaded.housing_starts_single is None
    assert loaded.housing_starts_semi is None
    assert loaded.housing_starts_row is None
    assert loaded.housing_starts_apartment is None
    assert loaded.housing_completions is None
    assert loaded.units_under_construction is None
    assert loaded.unabsorbed_units is None
    assert loaded.rms_surveyed is False


def test_cmhc_metric_unique_constraint(db_session):
    metric_a = CmhcMetric(geoid="3520005", year=2012, vacancy_rate=3.0)
    metric_b = CmhcMetric(geoid="3520005", year=2012, vacancy_rate=4.0)
    db_session.add(metric_a)
    db_session.flush()

    db_session.add(metric_b)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_geography_cmhc_metrics_relationship(db_session):
    # Fixture seeds years 2018-2025 (8 rows); add 2 more outside that range
    metric_a = CmhcMetric(geoid="3520005", year=2013, vacancy_rate=3.0)
    metric_b = CmhcMetric(geoid="3520005", year=2014, vacancy_rate=2.8)
    db_session.add_all([metric_a, metric_b])
    db_session.flush()

    geo = db_session.query(Geography).filter(Geography.geoid == "3520005").one()
    # 2 new + 8 from seed (2018-2025) = 10 total
    assert len(geo.cmhc_metrics) == 10


from app.services.metric_calculations import (
    CMHC_METRICS, VALID_METRICS, is_cmhc_metric, metric_value, normalize_metric_name,
)
from app.services.seed import load_cmhc_seed, seed_cmhc_data


def test_cmhc_metrics_are_valid():
    for key in CMHC_METRICS:
        assert key in VALID_METRICS


def test_cmhc_aliases():
    assert normalize_metric_name("vacancy") == "vacancy_rate"
    assert normalize_metric_name("starts") == "housing_starts_total"
    assert normalize_metric_name("completions") == "housing_completions"
    assert normalize_metric_name("rent_cmhc") == "average_rent_total"
    assert normalize_metric_name("turnover") == "turnover_rate"
    assert normalize_metric_name("availability") == "availability_rate"
    assert normalize_metric_name("universe") == "rental_universe"


def test_is_cmhc_metric():
    assert is_cmhc_metric("vacancy_rate") is True
    assert is_cmhc_metric("housing_starts_total") is True
    assert is_cmhc_metric("median_income") is False


def test_metric_value_reads_cmhc_row(db_session):
    from app.models import CmhcMetric
    cmhc = CmhcMetric(geoid="3520005", year=2015, vacancy_rate=2.1, average_rent_total=1850)
    db_session.add(cmhc)
    db_session.flush()
    loaded = db_session.query(CmhcMetric).filter(CmhcMetric.geoid == "3520005", CmhcMetric.year == 2015).one()
    assert metric_value("vacancy_rate", loaded) == 2.1
    assert metric_value("average_rent_total", loaded) == 1850
    assert metric_value("housing_starts_total", loaded) is None


def test_load_cmhc_seed_returns_dict():
    seed = load_cmhc_seed()
    assert "metadata" in seed
    assert "metrics" in seed
    assert isinstance(seed["metrics"], list)


def test_seed_cmhc_data_inserts_rows(db_session):
    # Fixture already seeds CMHC data, so delete first to test insertion
    db_session.query(CmhcMetric).delete()
    db_session.flush()
    count = seed_cmhc_data(db_session)
    assert count > 0
    rows = db_session.query(CmhcMetric).all()
    assert len(rows) > 0


def test_seed_cmhc_data_skips_when_exists(db_session):
    # Fixture already seeds CMHC data, so calling again should skip
    count = seed_cmhc_data(db_session)
    assert count == 0


def test_seed_cmhc_data_force_reloads(db_session):
    # Force reload should work regardless of existing data
    count = seed_cmhc_data(db_session, force=True)
    assert count > 0


# ---------------------------------------------------------------------------
# API endpoint tests for CMHC metrics
# ---------------------------------------------------------------------------


def test_map_data_cmhc_vacancy_rate(client):
    response = client.get("/api/map-data?metric=vacancy_rate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["metadata"]["metric"] == "vacancy_rate"
    assert payload["metadata"]["data_quality"]["label"] == "CMHC Rental Market Survey"
    assert "available_years" in payload["metadata"]
    assert isinstance(payload["metadata"]["available_years"], list)
    features_with_data = [f for f in payload["features"] if f["properties"]["value"] is not None]
    assert len(features_with_data) >= 1


def test_map_data_cmhc_housing_starts(client):
    response = client.get("/api/map-data?metric=starts")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["metric"] == "housing_starts_total"


def test_map_data_cmhc_metric_with_non_census_year(client):
    """CMHC metrics should return features even for years with no census data.

    Census data only exists for 2021, but CMHC data spans 2018-2025.
    Requesting year=2022 must still produce features (using census 2021
    geometry with CMHC 2022 values).
    """
    response = client.get("/api/map-data?metric=housing_completions&year=2022")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["metric"] == "housing_completions"
    assert payload["metadata"]["year"] == 2022
    assert len(payload["features"]) >= 1
    features_with_data = [f for f in payload["features"] if f["properties"]["value"] is not None]
    assert len(features_with_data) >= 1


def test_map_data_census_metric_unchanged(client):
    response = client.get("/api/map-data?metric=rent_burden")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["metric"] == "rent_burden_pct"
    assert payload["metadata"]["data_quality"]["metric_status"] == "official"
    assert len(payload["features"]) >= 6


def test_summary_includes_cmhc_fields(client):
    response = client.get("/api/summary")
    assert response.status_code == 200
    payload = response.json()
    assert "vacancy_rate" in payload
    assert "housing_starts_total" in payload


def test_compare_includes_cmhc_metrics(client):
    response = client.get("/api/compare?ids=3520005,3521005")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert "cmhc_metrics" in items[0]
    assert items[0]["cmhc_metrics"]["vacancy_rate"] is not None


def test_census_tract_cmhc_allocation(client):
    """Census tracts still get the renter-share allocation as a labeled estimate
    fallback (used where CMHC has no real tract value, e.g. the latest CMHC year
    which has no published tract data yet)."""
    response = client.get("/api/map-data?metric=housing_starts_total&type=census_tract")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["metric"] == "housing_starts_total"
    # Real-tract metric -> mixed provenance badge.
    assert payload["metadata"]["data_quality"]["metric_status"] == "mixed"
    features_with_value = [f for f in payload["features"] if f["properties"]["value"] is not None]
    assert len(features_with_value) >= 1
    # At least one tract is served via the allocation estimate fallback.
    estimated = [
        f for f in payload["features"]
        if f["properties"].get("cmhc_metrics", {}).get("starts_source") == "estimated"
    ]
    assert estimated
    assert estimated[0]["properties"]["cmhc_metrics"]["housing_starts_total"] is not None


def test_census_tract_compare_allocation(client):
    """Compare endpoint allocates CMHC count metrics for census tracts."""
    # Use a Toronto tract (geoid starts with 535) — Toronto has RMS coverage
    response = client.get("/api/map-data?metric=vacancy_rate&type=census_tract")
    assert response.status_code == 200
    toronto_tracts = [
        f for f in response.json()["features"]
        if f["properties"].get("county") == "Toronto"
    ]
    assert len(toronto_tracts) >= 1
    tract_geoid = toronto_tracts[0]["properties"]["geoid"]
    response = client.get(f"/api/compare?ids={tract_geoid}&type=census_tract")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    cmhc = items[0]["cmhc_metrics"]
    assert cmhc is not None
    assert cmhc["allocated"] is True
    assert cmhc["vacancy_rate"] is not None
    assert cmhc["housing_starts_total"] is not None


def test_municipality_cmhc_not_allocated(client):
    """Municipality-level CMHC metrics should not have the allocated flag."""
    response = client.get("/api/compare?ids=3520005")
    assert response.status_code == 200
    items = response.json()["items"]
    cmhc = items[0]["cmhc_metrics"]
    assert cmhc["allocated"] is False
    assert cmhc["housing_starts_total"] is not None


def test_combined_zone_municipality_discloses_shared_survey_zone(client):
    # Richmond Hill (3519038) is reported by CMHC as part of a combined RMS zone
    # with Vaughan and King, so the API discloses survey_zone.
    rh = client.get("/api/compare?ids=3519038").json()["items"][0]["cmhc_metrics"]
    assert rh["survey_zone"] == "Richmond Hill / Vaughan / King"
    # Vaughan (3519028) shares the same zone AND the same rental values.
    van = client.get("/api/compare?ids=3519028").json()["items"][0]["cmhc_metrics"]
    assert van["survey_zone"] == "Richmond Hill / Vaughan / King"
    assert van["average_rent_total"] == rh["average_rent_total"]
    assert van["vacancy_rate"] == rh["vacancy_rate"]


def test_standalone_municipality_has_no_survey_zone(client):
    # Toronto is its own set of zones (aggregated), not a shared combined zone.
    tor = client.get("/api/compare?ids=3520005").json()["items"][0]["cmhc_metrics"]
    assert tor["survey_zone"] is None


def test_summary_no_cmhc_blend_for_unresolvable_tract_parent(client, db_session):
    # If a selected tract's parent municipality cannot be resolved (null county),
    # the summary must NOT silently fall back to ALL-municipality CMHC aggregates
    # (GTA-wide data attributed to one tract). Regression for code-review #7.
    from app.models import Geography

    tract = (
        db_session.query(Geography)
        .filter(Geography.type == "census_tract", Geography.geoid == "5350001.00")
        .one()
    )
    tract.county = None
    db_session.commit()

    payload = client.get("/api/summary?type=census_tract&ids=5350001.00").json()
    assert payload["region_count"] == 1
    assert payload["vacancy_rate"] is None
    assert payload["average_rent_total"] is None


def test_metrics_endpoint_rejects_cmhc_metric(client):
    response = client.get("/api/metrics?metric=vacancy_rate")
    assert response.status_code == 400
    assert "CMHC metric" in response.json()["detail"]
