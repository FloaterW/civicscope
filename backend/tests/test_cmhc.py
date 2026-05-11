import pytest
from sqlalchemy.exc import IntegrityError

from app.models import CmhcMetric, Geography


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


def test_metrics_endpoint_rejects_cmhc_metric(client):
    response = client.get("/api/metrics?metric=vacancy_rate")
    assert response.status_code == 400
    assert "CMHC metric" in response.json()["detail"]
