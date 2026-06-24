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


def test_compact_geometry_preserves_small_rings():
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
    assert len(compacted["coordinates"][0]) == len(geometry["coordinates"][0])
    assert compacted["coordinates"][0][0] == [-79.2, 43.6]


def test_compact_geometry_simplifies_large_rings():
    ring = []
    for i in range(10):
        ring.append([-79.0 + i * 0.001, 43.6])
    for i in range(10):
        ring.append([-79.0 + 0.009, 43.6 + i * 0.001])
    for i in range(10):
        ring.append([-79.0 + 0.009 - i * 0.001, 43.6 + 0.009])
    ring.append(ring[0])
    geometry = {"type": "Polygon", "coordinates": [ring]}

    compacted = compact_geometry(geometry, tolerance=0.0005, precision=5)

    assert len(compacted["coordinates"][0]) < len(ring)
    assert compacted["coordinates"][0][0] == compacted["coordinates"][0][-1]


def test_compact_geometry_never_drops_below_three_vertices():
    ring = [[-79.0 + i * 0.0001, 43.6 + (i % 2) * 0.0001] for i in range(25)]
    ring.append(ring[0])
    geometry = {"type": "Polygon", "coordinates": [ring]}

    compacted = compact_geometry(geometry, tolerance=10.0, precision=5)

    assert len(compacted["coordinates"][0]) >= 4
