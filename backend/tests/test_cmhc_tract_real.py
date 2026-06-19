"""Step 2: real CMHC census-tract SCSS values are served (labeled official)
where CMHC publishes them, and the labeled allocation estimate is kept elsewhere.
"""


def _feature(payload, geoid):
    return next(
        (f for f in payload["features"] if f["properties"]["geoid"] == geoid), None
    )


def test_seed_loads_real_cmhc_tract_rows(db_session):
    from app.models import CmhcTractMetric

    assert db_session.query(CmhcTractMetric).count() > 5000
    # Known real value: Toronto tract 5350017.01 starts 2023 == 2304.
    row = (
        db_session.query(CmhcTractMetric)
        .filter(CmhcTractMetric.geoid == "5350017.01", CmhcTractMetric.year == 2023)
        .one()
    )
    assert row.housing_starts_total == 2304


def test_covered_tract_serves_real_starts_labeled_official(client):
    payload = client.get(
        "/api/map-data?metric=housing_starts_total&type=census_tract&detail=display&year=2023"
    ).json()
    f = _feature(payload, "5350017.01")
    assert f is not None
    # Real CMHC value, not an allocation estimate.
    assert f["properties"]["value"] == 2304
    cmhc = f["properties"]["cmhc_metrics"]
    assert cmhc["housing_starts_total"] == 2304
    # Per-metric provenance: starts is the real published value.
    assert cmhc["starts_source"] == "official"
    # (The record's overall `allocated` flag still reflects that RATE metrics
    # like vacancy/rent are inherited for this tract — the per-metric
    # *_source keys are the authoritative signal for the count metrics.)


def test_uncovered_tract_keeps_estimated_allocation(client):
    payload = client.get(
        "/api/map-data?metric=housing_starts_total&type=census_tract&detail=display&year=2023"
    ).json()
    f = _feature(payload, "5320002.01")  # not in CMHC CT coverage
    assert f is not None
    cmhc = f["properties"]["cmhc_metrics"]
    # Still served (allocation), but clearly marked estimated, not official.
    assert cmhc["starts_source"] == "estimated"


def test_badge_is_mixed_for_count_metric_in_tract_mode(client):
    payload = client.get(
        "/api/map-data?metric=housing_starts_total&type=census_tract&detail=display&year=2023"
    ).json()
    dq = payload["metadata"]["data_quality"]
    # Some tracts real, some estimated -> mixed provenance.
    assert dq["metric_status"] == "mixed"
    assert "official" in dq["description"].lower() and "estimat" in dq["description"].lower()


def test_real_value_replaces_allocation_not_adds_to_it(client):
    # The covered tract's served value equals the real CMHC value exactly,
    # never the renter-share allocation of the municipal total.
    payload = client.get(
        "/api/map-data?metric=housing_completions&type=census_tract&detail=display&year=2022"
    ).json()
    # 5350016.00 completions 2022 == 1011 (real published value); assert it is
    # used verbatim (source official) rather than allocated.
    f = _feature(payload, "5350016.00")
    assert f is not None
    assert f["properties"]["value"] == 1011
    assert f["properties"]["cmhc_metrics"]["housing_completions"] == 1011
    assert f["properties"]["cmhc_metrics"]["completions_source"] == "official"
