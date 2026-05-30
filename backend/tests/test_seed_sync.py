"""The packaged seed's census-tract metrics must faithfully mirror the official
statcan_ct_metrics.csv: official values verbatim, suppressed values preserved
as null (never silently replaced with an estimate)."""
from etl.load_tract_census import apply_csv_metrics_to_seed


def _seed():
    return {
        "metadata": {"source": "test"},
        "geographies": [
            {
                "geoid": "5320001.00",
                "type": "census_tract",
                # Stale baked-in estimate that must be overwritten.
                "metrics": [{"year": 2021, "median_income": 84400.0, "rent_burden_pct": 35.9}],
            },
            {
                "geoid": "3520005",
                "type": "municipality",
                "metrics": [{"year": 2021, "median_income": 84000.0, "rent_burden_pct": 40.0}],
            },
        ],
    }


def test_sync_replaces_tract_metrics_from_csv_and_preserves_nulls():
    seed = _seed()
    rows = [
        {
            "geoid": "5320001.00",
            "year": "2021",
            "median_income": "68000.0",
            "median_rent": "1150.0",
            "population": "3578",
            "previous_population": "3389",
            "renter_households": "795",
            "rent_burden_pct": "",  # suppressed by Statistics Canada
        }
    ]
    updated = apply_csv_metrics_to_seed(seed, rows)

    assert updated == 1
    tract_metric = seed["geographies"][0]["metrics"][0]
    assert tract_metric["median_income"] == 68000.0
    assert tract_metric["median_rent"] == 1150.0
    assert tract_metric["population"] == 3578
    assert tract_metric["renter_households"] == 795
    # Suppressed official value stays null — no estimate baked into the seed.
    assert tract_metric["rent_burden_pct"] is None


def test_sync_leaves_municipalities_untouched():
    seed = _seed()
    apply_csv_metrics_to_seed(seed, [])
    muni_metric = seed["geographies"][1]["metrics"][0]
    assert muni_metric["median_income"] == 84000.0
    assert muni_metric["rent_burden_pct"] == 40.0


def test_sync_ignores_csv_rows_without_a_matching_seed_tract():
    seed = _seed()
    rows = [{"geoid": "9999999.99", "year": "2021", "median_income": "1.0"}]
    updated = apply_csv_metrics_to_seed(seed, rows)
    assert updated == 0
