from app.services.geojson import compact_geometry, geometry_bbox


def test_geometry_bbox_reads_nested_polygons():
    geometry = {
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
    }

    assert geometry_bbox(geometry) == [-79.2, 43.6, -79.1, 43.7]


def test_compact_geometry_rounds_and_reduces_dense_rings():
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [-79.200001, 43.600001],
                [-79.200002, 43.600002],
                [-79.1, 43.6],
                [-79.1, 43.7],
                [-79.2, 43.7],
                [-79.200001, 43.600001],
            ]
        ],
    }

    compacted = compact_geometry(geometry, tolerance=0.00001, precision=5)

    assert compacted["coordinates"][0][0] == compacted["coordinates"][0][-1]
    assert len(compacted["coordinates"][0]) < len(geometry["coordinates"][0])
    assert compacted["coordinates"][0][0] == [-79.2, 43.6]
