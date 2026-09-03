import json

import pytest

from app.models import Geography, Metric
from etl.load_tracts import update_seed_file, upsert_tract_geometries


def _polygon(x0: float, y0: float, x1: float, y1: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
    }


def test_seed_boundary_refresh_preserves_official_metrics(tmp_path):
    seed_path = tmp_path / "seed.json"
    geojson_path = tmp_path / "tracts.geojson"
    official_metrics = [{"year": 2021, "median_income": 123456, "population": 789}]
    seed_path.write_text(
        json.dumps(
            {
                "metadata": {"source": "official"},
                "geographies": [
                    {
                        "geoid": "3520005",
                        "name": "Toronto",
                        "type": "municipality",
                        "county": "Toronto",
                        "geometry": _polygon(-80, 43, -79, 44),
                        "metrics": [{"year": 2021, "population": 1000}],
                    },
                    {
                        "geoid": "5350001.00",
                        "name": "old name",
                        "type": "census_tract",
                        "county": "Toronto",
                        "state": "ON",
                        "geometry": _polygon(-79.8, 43.2, -79.7, 43.3),
                        "bbox": [-79.8, 43.2, -79.7, 43.3],
                        "geometry_source": "old",
                        "metrics": official_metrics,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    geojson_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"CTUID": "5350001.00", "CTNAME": "0001.00"},
                        "geometry": _polygon(-79.9, 43.1, -79.6, 43.4),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert update_seed_file(seed_path, str(geojson_path)) == 1

    refreshed = json.loads(seed_path.read_text(encoding="utf-8"))
    tract = next(g for g in refreshed["geographies"] if g["type"] == "census_tract")
    assert tract["metrics"] == official_metrics
    assert tract["geometry"] == _polygon(-79.9, 43.1, -79.6, 43.4)
    assert refreshed["metadata"]["source"] == "official"
    assert not seed_path.with_suffix(".json.tmp").exists()


def test_seed_boundary_refresh_rejects_unmatched_tracts(tmp_path):
    seed_path = tmp_path / "seed.json"
    geojson_path = tmp_path / "tracts.geojson"
    seed_path.write_text(
        json.dumps(
            {
                "metadata": {},
                "geographies": [
                    {
                        "geoid": "3520005",
                        "name": "Toronto",
                        "type": "municipality",
                        "county": "Toronto",
                        "geometry": _polygon(-80, 43, -79, 44),
                        "metrics": [{"year": 2021, "population": 1000}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    geojson_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"CTUID": "5350001.00", "CTNAME": "0001.00"},
                        "geometry": _polygon(-79.9, 43.1, -79.6, 43.4),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="identifiers do not match"):
        update_seed_file(seed_path, str(geojson_path))


def test_database_boundary_refresh_preserves_metric_values(db_session):
    geographies = db_session.query(Geography).filter(Geography.type == "census_tract").all()
    geography = geographies[0]
    assert geography is not None
    metric = db_session.query(Metric).filter(Metric.geoid == geography.geoid).one()
    original_income = metric.median_income
    rows = []
    for item in geographies:
        item_metric = db_session.query(Metric).filter(Metric.geoid == item.geoid).one()
        rows.append(
            {
                "geoid": item.geoid,
                "name": item.name,
                "type": "census_tract",
                "county": item.county,
                "state": item.state,
                "geometry": (
                    _polygon(-79.9, 43.1, -79.6, 43.4)
                    if item.geoid == geography.geoid
                    else item.geometry
                ),
                "bbox": (
                    [-79.9, 43.1, -79.6, 43.4]
                    if item.geoid == geography.geoid
                    else item.bbox
                ),
                "geometry_source": "refreshed",
                "metrics": [{"year": item_metric.year, "median_income": 1}],
            }
        )

    assert upsert_tract_geometries(db_session, rows) == len(rows)
    db_session.flush()

    assert metric.median_income == original_income
    assert geography.geometry_source == "refreshed"


def test_database_boundary_refresh_rejects_missing_existing_tract(db_session):
    geographies = db_session.query(Geography).filter(Geography.type == "census_tract").all()
    rows = [
        {
            "geoid": item.geoid,
            "name": item.name,
            "type": "census_tract",
            "county": item.county,
            "state": item.state,
            "geometry": item.geometry,
            "bbox": item.bbox,
            "geometry_source": "refreshed",
            "metrics": [],
        }
        for item in geographies[:-1]
    ]

    with pytest.raises(ValueError, match="identifiers do not match"):
        upsert_tract_geometries(db_session, rows)
