"""Regression coverage for failures found during independent launch testing."""

import csv
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api import routes
from app.db.base import Base
from app.models import CmhcMetric, Metric
from app.services import seed as seed_service
from etl.load_census import MetricInput, validate_official_metrics


def _official_row():
    return MetricInput(
        geoid="3520005", year=2021, median_income=84000, median_rent=1500,
        population=2794356, previous_population=2731571,
        renter_households=557975, rent_burden_pct=40,
    )


@pytest.mark.parametrize("invalid", ["wrong_year", "duplicate", "unexpected"])
def test_official_census_validation_rejects_identifier_and_vintage_drift(invalid):
    row = _official_row()
    rows = {
        "wrong_year": [replace(row, year=2026)],
        "duplicate": [row, row],
        "unexpected": [row, replace(row, geoid="9999999")],
    }[invalid]
    with pytest.raises(ValueError):
        validate_official_metrics(rows, [row.geoid])


@pytest.mark.parametrize(
    ("field", "corrected"),
    [
        ("rent_burden_pct", 40.1),
        ("rent_burden_pct", None),
        ("dwellings_total", 10001),
        ("dwellings_apt_high_rise", 2501),
        ("owner_households", 5001),
    ],
)
def test_packaged_census_field_corrections_reach_existing_database(
    monkeypatch, field, corrected
):
    # A correction can arrive without any change to population, income, or rent.
    # Use a tiny real database to exercise the public seed operation quickly.
    metric = {
        "year": 2021, "median_income": 84000, "median_rent": 1500,
        "population": 25000, "previous_population": 24000,
        "renter_households": 5000, "rent_burden_pct": 40.0,
        "dwellings_total": 10000, "dwellings_apt_high_rise": 2500,
        "owner_households": 5000,
    }
    packaged = {
        "metadata": {"source": "launch_regression_fixture"},
        "geographies": [{
            "geoid": "3520005", "name": "Toronto", "type": "municipality",
            "geometry": {"type": "Polygon", "coordinates": [[
                [-79.5, 43.6], [-79.4, 43.6], [-79.4, 43.7],
                [-79.5, 43.7], [-79.5, 43.6],
            ]]},
            "bbox": [-79.5, 43.6, -79.4, 43.7],
            "geometry_source": "Test fixture", "metrics": [metric],
        }],
    }
    monkeypatch.setattr(seed_service, "load_demo_seed", lambda: packaged)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            assert seed_service.seed_demo_data(db) > 0
            metric[field] = corrected
            assert seed_service.seed_demo_data(db) > 0
            db.expire_all()
            actual = db.query(Metric).filter_by(geoid="3520005", year=2021).one()
            assert getattr(actual, field) == corrected
            assert seed_service.seed_demo_data(db) == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("year", "vacancy", "rent", "source"),
    [
        (2023, 1.2, 1500.0, "survey_zone"),
        (2024, 2.4, 1700.0, "survey_zone"),
        (2018, 0.8, 1100.0, "inherited_municipality"),
        (2025, 0.8, 1100.0, "inherited_municipality"),
    ],
)
def test_tract_zone_rates_only_override_matching_observation_year(
    tmp_path, monkeypatch, year, vacancy, rent, source
):
    (tmp_path / "cmhc_zone_rms.csv").write_text(
        "zone_name,year,vacancy_rate,average_rent_total,rental_universe\n"
        "Test zone,2023,1.2,1500,1000\n"
        "Test zone,2024,2.4,1700,1100\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(routes, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(routes, "ZONE_RMS", routes._load_zone_rms())
    municipal = CmhcMetric(
        geoid="3520005", year=year, vacancy_rate=0.8,
        average_rent_total=1100.0, rms_surveyed=True,
    )
    payload = routes.serialize_cmhc_metric(
        municipal, tract_inherited=True, zone_name="Test zone"
    )
    assert payload["year"] == year
    assert payload["vacancy_rate"] == vacancy
    assert payload["average_rent_total"] == rent
    assert payload["vacancy_rate_source"] == source
    assert payload["average_rent_total_source"] == source


@pytest.mark.parametrize("year", [2018, 2024, 2025])
def test_tract_map_and_compare_use_selected_year_for_zone_rates(
    client, db_session, year
):
    geoid = "5350017.01"
    zone = routes.TRACT_ZONE_CROSSWALK[geoid]
    with (Path(__file__).parents[1] / "app/data/cmhc_zone_rms.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        matching = next((
            row for row in csv.DictReader(handle)
            if row["zone_name"] == zone and int(row["year"]) == year
        ), None)
    municipal = db_session.query(CmhcMetric).filter_by(
        geoid="3520005", year=year
    ).one()
    expected = {
        "vacancy_rate": float(matching["vacancy_rate"])
        if matching and matching["vacancy_rate"] else municipal.vacancy_rate,
        "average_rent_total": float(matching["average_rent_total"])
        if matching and matching["average_rent_total"] else municipal.average_rent_total,
    }
    compare_response = client.get(
        f"/api/compare?type=census_tract&ids={geoid}&year={year}"
    )
    assert compare_response.status_code == 200
    compared = compare_response.json()["items"][0]["cmhc_metrics"]
    for metric_key, expected_value in expected.items():
        response = client.get(
            f"/api/map-data?metric={metric_key}&type=census_tract"
            f"&detail=display&year={year}"
        )
        assert response.status_code == 200
        payload = response.json()
        feature = next(
            f for f in payload["features"] if f["properties"]["geoid"] == geoid
        )
        mapped = feature["properties"]["cmhc_metrics"]
        expected_source = (
            "survey_zone" if matching and matching[metric_key]
            else "inherited_municipality"
        )
        assert payload["metadata"]["year"] == year
        assert ("survey-zone" in payload["metadata"]["data_quality"]["label"]) == bool(matching)
        assert feature["properties"]["value"] == expected_value
        assert mapped[metric_key] == expected_value
        assert compared[metric_key] == expected_value
        assert mapped[f"{metric_key}_source"] == expected_source
        assert compared[f"{metric_key}_source"] == expected_source
