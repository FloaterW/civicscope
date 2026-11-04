"""Construction banners must describe the selected field's served observations."""

from collections import Counter

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models import CmhcMetric, CmhcTractMetric, Geography, Metric


SOURCE_FIELDS = {
    "housing_starts_total": "starts_source",
    "housing_completions": "completions_source",
}


@pytest.mark.parametrize("metric,year,status", [
    ("housing_starts_total", 2024, "mixed"),
    ("housing_starts_total", 2025, "estimated"),
    ("housing_completions", 2022, "mixed"),
    ("housing_completions", 2024, "estimated"),
    ("housing_completions", 2025, "estimated"),
])
def test_packaged_construction_quality_tracks_selected_year(client, metric, year, status):
    response = client.get("/api/map-data", params={
        "metric": metric, "type": "census_tract", "detail": "display", "year": year,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["year"] == year
    quality = payload["metadata"]["data_quality"]
    assert quality["metric_status"] == status
    assert payload["metadata"]["metric_catalog"][metric]["data_quality"] == quality
    sources = Counter()
    for feature in payload["features"]:
        properties = feature["properties"]
        counts = properties.get("cmhc_metrics", {})
        assert properties["value"] == counts.get(metric)
        if counts.get(metric) is not None:
            sources[counts[SOURCE_FIELDS[metric]]] += 1
    assert sum(sources.values()) == 1334
    assert ("official" in sources) == (status == "mixed")
    assert "estimated" in sources
    print(f"{year} {metric}: {dict(sources)}")


def test_census_map_catalog_uses_latest_construction_coverage(client):
    payload = client.get("/api/map-data", params={
        "metric": "population", "type": "census_tract", "detail": "display",
    }).json()
    assert payload["metadata"]["year"] == 2021
    assert payload["metadata"]["cmhc_year"] == 2025
    assert payload["metadata"]["data_quality"]["metric_status"] == "official"
    for metric in SOURCE_FIELDS:
        assert payload["metadata"]["metric_catalog"][metric]["data_quality"]["metric_status"] == "estimated"


@pytest.fixture()
def construction_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        geometry = {"type": "Polygon", "coordinates": [[
            [-79.5, 43.6], [-79.4, 43.6], [-79.4, 43.7], [-79.5, 43.6],
        ]]}
        for geoid, kind, name, county in [
            ("3520005", "municipality", "Toronto", None),
            ("5350001.00", "census_tract", "First tract", "Toronto"),
            ("5350002.00", "census_tract", "Second tract", "Toronto"),
        ]:
            db.add(Geography(
                geoid=geoid, name=name, type=kind, county=county,
                geometry=geometry, bbox=[-79.5, 43.6, -79.4, 43.7],
            ))
            db.add(Metric(geoid=geoid, year=2021, population=1000, renter_households=100))
        db.commit()
        yield db
    engine.dispose()


def test_census_catalog_reports_unavailable_when_cmhc_is_absent(construction_db):
    app = create_app(auto_initialize=False)
    app.dependency_overrides[get_db] = lambda: construction_db
    with TestClient(app) as client:
        response = client.get("/api/map-data", params={
            "metric": "population", "type": "census_tract",
        })
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["data_quality"]["metric_status"] == "official"
    assert payload["metadata"]["cmhc_year"] is None
    for metric in SOURCE_FIELDS:
        assert payload["metadata"]["metric_catalog"][metric]["data_quality"]["metric_status"] == "unavailable"
    assert all("cmhc_metrics" not in feature["properties"] for feature in payload["features"])


@pytest.mark.parametrize("metric", SOURCE_FIELDS)
def test_missing_construction_year_does_not_use_another_years_sources(construction_db, metric):
    construction_db.add(CmhcMetric(geoid="3520005", year=2025, **{metric: 20}))
    construction_db.add(CmhcTractMetric(
        geoid="5350001.00", year=2025, **{metric: 10, f"{metric}_source": "official"},
    ))
    construction_db.commit()
    app = create_app(auto_initialize=False)
    app.dependency_overrides[get_db] = lambda: construction_db
    with TestClient(app) as client:
        response = client.get("/api/map-data", params={
            "metric": metric, "type": "census_tract", "year": 2024,
        })
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["year"] == 2024
    assert payload["metadata"]["available_years"] == [2025]
    assert payload["metadata"]["domain"] == {"min": None, "max": None}
    quality = payload["metadata"]["data_quality"]
    assert quality["metric_status"] == "unavailable"
    assert payload["metadata"]["metric_catalog"][metric]["data_quality"] == quality
    assert all(feature["properties"]["value"] is None for feature in payload["features"])


def test_municipal_survey_attribution_distinguishes_rental_construction_and_absorption(client):
    expected = {
        "housing_starts_total": "CMHC Starts & Completions Survey",
        "housing_starts_single": "CMHC Starts & Completions Survey",
        "housing_starts_semi": "CMHC Starts & Completions Survey",
        "housing_starts_row": "CMHC Starts & Completions Survey",
        "housing_starts_apartment": "CMHC Starts & Completions Survey",
        "housing_completions": "CMHC Starts & Completions Survey",
        "units_under_construction": "CMHC Starts & Completions Survey",
        "unabsorbed_units": "CMHC Market Absorption Survey",
        "rental_universe": "CMHC Rental Market Survey",
        "average_rent_total": "CMHC Rental Market Survey",
        "vacancy_rate": "CMHC Rental Market Survey",
    }
    response = client.get("/api/map-data", params={
        "metric": "housing_completions", "type": "municipality", "year": 2018,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["year"] == 2018
    for metric, survey in expected.items():
        metadata = payload["metadata"]["metric_catalog"][metric]
        assert metadata["data_quality"]["label"] == survey
        assert metadata["data_quality"]["metric_status"] == "official"
        assert metadata["data_quality"]["description"].startswith(f"{survey} data ")
        assert metadata["source"].startswith(f"{survey} data ")
    assert payload["metadata"]["data_quality"] == payload["metadata"]["metric_catalog"]["housing_completions"]["data_quality"]
    mississauga = next(feature["properties"] for feature in payload["features"] if feature["properties"]["geoid"] == "3521005")
    assert mississauga["value"] == mississauga["cmhc_metrics"]["housing_completions"]


@pytest.mark.parametrize("metric", SOURCE_FIELDS)
@pytest.mark.parametrize("total,observations,status,expected", [
    (None, [(None, "official"), (None, "official")], "unavailable", [None, None]),
    (None, [(0, "official"), (None, "official")], "official", [0, None]),
    (0, [(None, "official"), (None, "official")], "estimated", [0, 0]),
    (8, [(0, "official"), (None, "official")], "mixed", [0, 8]),
    (6, [(4, "estimated_parent"), (2, "estimated_parent")], "estimated", [4, 2]),
    (6, [(4, "official"), (2, "estimated_parent")], "mixed", [4, 2]),
    (6, [(4, "official"), (2, "official")], "official", [4, 2]),
])
def test_quality_uses_non_null_field_provenance(
    construction_db, metric, total, observations, status, expected,
):
    other_metric = next(candidate for candidate in SOURCE_FIELDS if candidate != metric)
    construction_db.add(CmhcMetric(
        geoid="3520005", year=2025, **{metric: total, other_metric: 18},
    ))
    for geoid, (value, source) in zip(["5350001.00", "5350002.00"], observations):
        construction_db.add(CmhcTractMetric(
            geoid=geoid, year=2025, **{
                metric: value, f"{metric}_source": source,
                other_metric: 9, f"{other_metric}_source": "official",
            },
        ))
    construction_db.commit()
    app = create_app(auto_initialize=False)
    app.dependency_overrides[get_db] = lambda: construction_db
    with TestClient(app) as client:
        response = client.get("/api/map-data", params={
            "metric": metric, "type": "census_tract", "year": 2025,
        })
    assert response.status_code == 200
    payload = response.json()
    quality = payload["metadata"]["data_quality"]
    assert quality["metric_status"] == status
    assert payload["metadata"]["metric_catalog"][metric]["data_quality"] == quality
    assert payload["metadata"]["metric_catalog"][other_metric]["data_quality"]["metric_status"] == "official"
    features = sorted(payload["features"], key=lambda feature: feature["properties"]["geoid"])
    assert [feature["properties"]["value"] for feature in features] == expected
    assert [feature["properties"]["cmhc_metrics"][metric] for feature in features] == expected
    if status == "unavailable":
        assert quality["label"] == "No CMHC tract values"
        assert payload["metadata"]["domain"] == {"min": None, "max": None}
