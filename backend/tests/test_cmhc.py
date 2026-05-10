import pytest
from sqlalchemy.exc import IntegrityError

from app.models import CmhcMetric, Geography


def test_cmhc_metric_creation(db_session):
    metric = CmhcMetric(
        geoid="3520005",
        year=2024,
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
    assert loaded.year == 2024
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
        year=2023,
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
    metric_a = CmhcMetric(geoid="3520005", year=2022, vacancy_rate=3.0)
    metric_b = CmhcMetric(geoid="3520005", year=2022, vacancy_rate=4.0)
    db_session.add(metric_a)
    db_session.flush()

    db_session.add(metric_b)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_geography_cmhc_metrics_relationship(db_session):
    metric_a = CmhcMetric(geoid="3520005", year=2022, vacancy_rate=3.0)
    metric_b = CmhcMetric(geoid="3520005", year=2021, vacancy_rate=2.8)
    db_session.add_all([metric_a, metric_b])
    db_session.flush()

    geo = db_session.query(Geography).filter(Geography.geoid == "3520005").one()
    assert len(geo.cmhc_metrics) == 2
