def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_summary_endpoint(client):
    response = client.get("/api/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["region_count"] >= 6
    assert payload["population"] > 0
    assert payload["rent_to_income_ratio"] is not None


def test_map_data_endpoint(client):
    response = client.get("/api/map-data?metric=rent_burden")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["metadata"]["metric"] == "rent_burden_pct"
    assert payload["metadata"]["geography_type"] == "municipality"
    assert payload["metadata"]["data_quality"]["metric_status"] == "official"
    assert len(payload["features"]) >= 6
    assert "geometry" in payload["features"][0]


def test_map_data_endpoint_supports_census_tracts(client):
    response = client.get("/api/map-data?metric=rent_burden&type=census_tract&detail=display")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["geography_type"] == "census_tract"
    # Rent burden has an estimated fallback, so the badge must NOT claim every
    # value is official.
    assert payload["metadata"]["data_quality"]["metric_status"] == "mixed"
    assert len(payload["features"]) > 1000
    assert all(feature["properties"]["type"] == "census_tract" for feature in payload["features"])
    # Most tracts carry official income; at least one does.
    assert any(
        feature["properties"]["metrics"]["median_income"] is not None
        for feature in payload["features"]
    )


def test_tract_metrics_expose_field_level_provenance(client):
    response = client.get("/api/map-data?metric=median_income&type=census_tract&detail=display")
    payload = response.json()
    sample = payload["features"][0]["properties"]["metrics"]
    quality = sample["data_quality"]
    expected_keys = {
        "median_income",
        "median_rent",
        "population",
        "previous_population",
        "renter_households",
        "rent_burden_pct",
        "population_growth_pct",
        "affordability_index",
    }
    assert expected_keys <= set(quality)
    for status in quality.values():
        assert status in {"official", "estimated", "unavailable", "low_confidence"}


def test_tract_missing_value_is_unavailable_not_fabricated(client):
    response = client.get("/api/map-data?metric=median_rent&type=census_tract&detail=display")
    features = response.json()["features"]
    missing = [
        f for f in features if f["properties"]["metrics"]["median_rent"] is None
    ]
    assert missing, "expected at least one tract with suppressed median rent"
    for feature in missing:
        assert feature["properties"]["metrics"]["data_quality"]["median_rent"] == "unavailable"


def test_tract_rent_burden_estimate_is_distinguishable_from_official(client):
    response = client.get("/api/map-data?metric=rent_burden&type=census_tract&detail=display")
    metrics = [f["properties"]["metrics"] for f in response.json()["features"]]

    official = [m for m in metrics if m["data_quality"]["rent_burden_pct"] == "official"]
    estimated = [m for m in metrics if m["data_quality"]["rent_burden_pct"] == "estimated"]
    unavailable = [m for m in metrics if m["data_quality"]["rent_burden_pct"] == "unavailable"]

    assert official and estimated, "both official and estimated rent burden must exist"
    # Estimated rows still carry a usable value computed from rent and income.
    for m in estimated:
        assert m["rent_burden_pct"] is not None
        assert m["median_rent"] is not None and m["median_income"] is not None
    # Unavailable rows must not fabricate a number.
    for m in unavailable:
        assert m["rent_burden_pct"] is None


def test_tract_low_denominator_growth_is_flagged(client):
    response = client.get("/api/map-data?metric=population&type=census_tract&detail=display")
    metrics = [f["properties"]["metrics"] for f in response.json()["features"]]
    flagged = [m for m in metrics if m["data_quality"]["population_growth_pct"] == "low_confidence"]
    assert flagged, "tracts with tiny previous populations must be flagged low_confidence"
    for m in flagged:
        assert m["previous_population"] is not None and m["previous_population"] < 100


def test_compare_tract_cmhc_count_matches_map_data_allocation(client):
    # CMHC count metrics must be allocated by each tract's share of ALL its
    # municipality's tracts. The comparison endpoint must not hand a single
    # selected tract the full municipal total (regression: shares were computed
    # over only the selected subset, so one tract got share == 1.0).
    map_payload = client.get(
        "/api/map-data?metric=housing_starts_total&type=census_tract&detail=display"
    ).json()
    target = next(
        f
        for f in map_payload["features"]
        if (f["properties"].get("cmhc_metrics") or {}).get("housing_starts_total")
    )
    geoid = target["properties"]["geoid"]
    map_value = target["properties"]["cmhc_metrics"]["housing_starts_total"]

    compare_payload = client.get(f"/api/compare?type=census_tract&ids={geoid}").json()
    compare_value = compare_payload["items"][0]["cmhc_metrics"]["housing_starts_total"]

    assert compare_value == map_value


def test_census_map_data_ignores_year_param(client):
    # Census data is a single 2021 vintage. Passing a non-2021 year to a census
    # metric must NOT return an empty map; it should fall back to the latest
    # census year so direct API callers always get data.
    base = client.get("/api/map-data?metric=median_income&type=census_tract&detail=display")
    future = client.get(
        "/api/map-data?metric=median_income&type=census_tract&detail=display&year=2025"
    )
    assert base.status_code == 200 and future.status_code == 200
    assert len(future.json()["features"]) == len(base.json()["features"]) > 1000
    assert future.json()["metadata"]["year"] == base.json()["metadata"]["year"]


def test_growth_map_domain_excludes_low_denominator_outliers(client):
    # Tracts with a tiny 2016 base produce absurd growth percentages; they must
    # not define the map's color scale (they are still shown, flagged, on click).
    payload = client.get(
        "/api/map-data?metric=population_growth_pct&type=census_tract&detail=display"
    ).json()
    domain = payload["metadata"]["domain"]
    features = payload["features"]

    reliable = [
        f["properties"]["metrics"]["population_growth_pct"]
        for f in features
        if f["properties"]["metrics"]["data_quality"]["population_growth_pct"] != "low_confidence"
        and f["properties"]["metrics"]["population_growth_pct"] is not None
    ]
    outliers = [
        f["properties"]["metrics"]["population_growth_pct"]
        for f in features
        if f["properties"]["metrics"]["data_quality"]["population_growth_pct"] == "low_confidence"
    ]
    assert domain["max"] == max(reliable)
    # The outliers still carry their real (larger) value for the detail panel.
    assert outliers and max(outliers) > domain["max"]


def test_cmhc_metric_on_tracts_labeled_estimated_and_allocated(client):
    response = client.get("/api/map-data?metric=housing_starts_total&type=census_tract&detail=display")
    payload = response.json()
    assert payload["metadata"]["data_quality"]["metric_status"] == "estimated"
    allocated = [
        f
        for f in payload["features"]
        if f["properties"].get("cmhc_metrics", {}).get("allocated")
    ]
    assert allocated, "count CMHC metrics must be allocated to tracts and flagged"


def test_map_data_display_detail_compacts_geometry(client):
    full_response = client.get("/api/map-data?metric=rent_burden&detail=full")
    display_response = client.get("/api/map-data?metric=rent_burden&detail=display")
    assert full_response.status_code == 200
    assert display_response.status_code == 200
    assert len(display_response.content) < len(full_response.content)


def test_geography_endpoint_accepts_numeric_geoid(client):
    response = client.get("/api/geographies/3520005")
    assert response.status_code == 200
    payload = response.json()
    assert payload["geoid"] == "3520005"
    assert "geometry" in payload
    assert payload["metrics"]["median_income"] is not None
    # Field-level provenance survives the response model on the detail endpoint.
    assert payload["metrics"]["data_quality"]["median_income"] == "official"


def test_compare_endpoint_preserves_requested_ids(client):
    response = client.get("/api/compare?ids=3520005,3521005")
    assert response.status_code == 200
    payload = response.json()
    assert payload["cmhc_year"] >= 2021
    items = payload["items"]
    assert [item["geoid"] for item in items] == ["3520005", "3521005"]


def test_summary_endpoint_filters_to_census_tracts(client):
    response = client.get("/api/summary?type=census_tract")
    assert response.status_code == 200
    payload = response.json()
    assert payload["region_count"] > 1000
    assert payload["population"] > 0


def test_invalid_metric_returns_400(client):
    response = client.get("/api/map-data?metric=not_a_metric")
    assert response.status_code == 400


def test_geographies_list_defaults_to_municipalities(client):
    response = client.get("/api/geographies")
    assert response.status_code == 200
    payload = response.json()
    assert payload["year"] == 2021
    assert len(payload["items"]) == 25
    assert all(item["type"] == "municipality" for item in payload["items"])


def test_geographies_list_excludes_full_geometry(client):
    response = client.get("/api/geographies")
    assert response.status_code == 200
    items = response.json()["items"]
    for item in items:
        assert item["geoid"]
        assert item["name"]
        assert "geometry" not in item


def test_geographies_search_filters_by_name(client):
    response = client.get("/api/geographies?search=Toronto")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 1
    assert any("Toronto" in item["name"] for item in items)


def test_geographies_search_returns_empty_for_no_match(client):
    response = client.get("/api/geographies?search=Nonexistent999")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_geography_not_found_returns_404(client):
    response = client.get("/api/geographies/9999999")
    assert response.status_code == 404


def test_compare_defaults_to_top_by_population(client):
    response = client.get("/api/compare")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) <= 6
    assert len(items) >= 1
    populations = [item["metrics"]["population"] for item in items]
    assert populations == sorted(populations, reverse=True)


def test_compare_with_census_tracts(client):
    response = client.get("/api/compare?type=census_tract")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 1
    assert all(item["type"] == "census_tract" for item in items)


def test_summary_with_selected_geography(client):
    response = client.get("/api/summary?ids=3520005")
    assert response.status_code == 200
    payload = response.json()
    assert payload["region_count"] == 1
    assert payload["selected_geographies"][0]["name"] == "Toronto"


def test_summary_nonexistent_ids_returns_404(client):
    response = client.get("/api/summary?ids=9999999")
    assert response.status_code == 404


def test_invalid_geography_type_returns_400(client):
    response = client.get("/api/geographies?type=invalid_type")
    assert response.status_code == 400


def test_health_reports_database_status(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["database"] == "ok"
    assert payload["service"] == "civicscope-api"
