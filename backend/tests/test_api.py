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
    assert payload["metadata"]["data_quality"]["metric_status"] == "official"
    assert len(payload["features"]) > 1000
    assert all(feature["properties"]["type"] == "census_tract" for feature in payload["features"])
    assert payload["features"][0]["properties"]["metrics"]["median_income"] is not None


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
    assert payload["metrics"]["median_income"] is not None


def test_compare_endpoint_preserves_requested_ids(client):
    response = client.get("/api/compare?ids=3520005,3521005")
    assert response.status_code == 200
    items = response.json()["items"]
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
