from pathlib import Path

import pytest

from etl.load_census import (
    build_profile_url,
    csduid_to_dguid,
    dguid_to_csduid,
    MetricInput,
    parse_metric_csv,
    parse_profile_csv_text,
    validate_official_metrics,
)
from etl.load_geo import GTA_MUNICIPALITIES, build_statcan_query_url, normalize_feature


def test_statcan_csd_dguid_builder():
    assert csduid_to_dguid("3520005") == "2021A00053520005"
    assert dguid_to_csduid("2021A00053520005") == "3520005"


def test_profile_url_uses_df_csd_and_characteristics():
    url = build_profile_url(["3520005"], ["1", "2"])
    assert "STC_CP,DF_CSD" in url
    assert "2021A00053520005" in url
    assert ".1%2B2." not in url
    assert ".1+2." in url


def test_parse_metric_csv_accepts_normalized_statcan_extract(tmp_path: Path):
    csv_path = tmp_path / "metrics.csv"
    csv_path.write_text(
        "csduid,year,median_household_income,median_monthly_rent,population_2021,"
        "population_2016,tenant_households,shelter_cost_burden_pct\n"
        "3520005,2021,88000,1850,2794000,2731571,650000,43.0\n",
        encoding="utf-8",
    )

    rows = parse_metric_csv(csv_path)

    assert rows[0].geoid == "3520005"
    assert rows[0].median_income == 88000
    assert rows[0].median_rent == 1850
    assert rows[0].rent_burden_pct == 43.0


def test_parse_official_profile_csv_maps_characteristics():
    rows = parse_profile_csv_text(
        "\n".join(
            [
                "DATAFLOW,FREQ,TIME_PERIOD,REF_AREA,GENDER,CHARACTERISTIC,STATISTIC,OBS_VALUE",
                "STC_CP:DF_CSD(1.3),A5,2021,2021A00053520005,1,1,1,2794356",
                "STC_CP:DF_CSD(1.3),A5,2021,2021A00053520005,1,2,1,2731571",
                "STC_CP:DF_CSD(1.3),A5,2021,2021A00053520005,1,229,1,84000",
                "STC_CP:DF_CSD(1.3),A5,2021,2021A00053520005,1,1476,1,557975",
                "STC_CP:DF_CSD(1.3),A5,2021,2021A00053520005,1,1478,1,40.0",
                "STC_CP:DF_CSD(1.3),A5,2021,2021A00053520005,1,1480,1,1500",
            ]
        )
    )

    assert rows[0].geoid == "3520005"
    assert rows[0].population == 2794356
    assert rows[0].previous_population == 2731571
    assert rows[0].median_income == 84000
    assert rows[0].renter_households == 557975
    assert rows[0].rent_burden_pct == 40.0
    assert rows[0].median_rent == 1500


def test_official_metric_validation_rejects_missing_characteristics():
    metrics = [
        MetricInput(
            geoid="3520005",
            year=2021,
            median_income=84000,
            median_rent=None,
            population=2794356,
            previous_population=2731571,
            renter_households=557975,
            rent_burden_pct=40.0,
        )
    ]

    with pytest.raises(ValueError, match="median_rent"):
        validate_official_metrics(metrics, ["3520005"])


def test_geo_loader_normalizes_statcan_feature():
    feature = {
        "type": "Feature",
        "properties": {"CSDUID": "3520005", "CSDNAME": "Toronto", "CDNAME": "Toronto"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-79.2, 43.6],
                    [-79.1, 43.6],
                    [-79.1, 43.7],
                    [-79.2, 43.7],
                    [-79.2, 43.6],
                ]
            ],
        },
    }

    geography = normalize_feature(feature)

    assert geography["geoid"] == "3520005"
    assert geography["state"] == "ON"
    assert geography["bbox"] == [-79.2, 43.6, -79.1, 43.7]


def test_geo_query_url_targets_statcan_cartographic_csd_layer():
    url = build_statcan_query_url(["3520005", "3521005"])
    assert "geo.statcan.gc.ca" in url
    assert "MapServer%2F9" not in url
    assert "CSDUID+IN" in url


def test_gta_municipality_ids_match_known_statcan_csdids():
    assert GTA_MUNICIPALITIES["3519044"][0] == "Whitchurch-Stouffville"
    assert GTA_MUNICIPALITIES["3519054"][0] == "East Gwillimbury"
    assert GTA_MUNICIPALITIES["3518020"][0] == "Scugog"
    assert GTA_MUNICIPALITIES["3518039"][0] == "Brock"
