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
    assert len(payload["features"]) >= 6
    assert "geometry" in payload["features"][0]


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


def test_invalid_metric_returns_400(client):
    response = client.get("/api/map-data?metric=not_a_metric")
    assert response.status_code == 400
