from __future__ import annotations

from copy import deepcopy
from typing import Any

Coordinate = list[float]
Ring = list[Coordinate]


def geometry_bbox(geometry: dict[str, Any]) -> list[float]:
    coordinates: list[Coordinate] = []

    def walk(value: Any) -> None:
        if isinstance(value, list) and value and isinstance(value[0], (int, float)):
            coordinates.append([float(value[0]), float(value[1])])
            return
        if isinstance(value, list):
            for item in value:
                walk(item)

    walk(geometry.get("coordinates"))
    if not coordinates:
        raise ValueError("Geometry has no coordinates.")

    lngs = [coordinate[0] for coordinate in coordinates]
    lats = [coordinate[1] for coordinate in coordinates]
    return [min(lngs), min(lats), max(lngs), max(lats)]


def compact_geometry(
    geometry: dict[str, Any],
    *,
    tolerance: float = 0.0,
    precision: int = 6,
) -> dict[str, Any]:
    compacted = simplify_geometry(deepcopy(geometry), tolerance) if tolerance > 0 else deepcopy(geometry)
    return round_geometry(compacted, precision)


def round_geometry(geometry: dict[str, Any], precision: int = 6) -> dict[str, Any]:
    def round_coordinates(value: Any) -> Any:
        if isinstance(value, list) and value and isinstance(value[0], (int, float)):
            return [round(float(value[0]), precision), round(float(value[1]), precision)]
        if isinstance(value, list):
            return [round_coordinates(item) for item in value]
        return value

    rounded = deepcopy(geometry)
    rounded["coordinates"] = round_coordinates(rounded.get("coordinates"))
    return rounded


def simplify_geometry(geometry: dict[str, Any], tolerance: float) -> dict[str, Any]:
    if tolerance <= 0:
        return deepcopy(geometry)

    simplified = deepcopy(geometry)
    geometry_type = simplified.get("type")
    coordinates = simplified.get("coordinates")

    if geometry_type == "Polygon":
        simplified["coordinates"] = [_simplify_ring(ring, tolerance) for ring in coordinates]
    elif geometry_type == "MultiPolygon":
        simplified["coordinates"] = [
            [_simplify_ring(ring, tolerance) for ring in polygon]
            for polygon in coordinates
        ]

    return simplified


def _simplify_ring(ring: Ring, tolerance: float) -> Ring:
    if len(ring) <= 20:
        return ring

    is_closed = ring[0] == ring[-1]
    working_ring = ring[:-1] if is_closed else ring
    simplified = _douglas_peucker(working_ring, tolerance)

    if len(simplified) < 3:
        return ring
    if is_closed and simplified[0] != simplified[-1]:
        simplified = [*simplified, simplified[0]]
    return simplified


def _douglas_peucker(points: Ring, tolerance: float) -> Ring:
    if len(points) <= 2:
        return points

    max_dist = 0.0
    max_index = 0
    start = points[0]
    end = points[-1]
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    line_len_sq = dx * dx + dy * dy

    for i in range(1, len(points) - 1):
        if line_len_sq == 0:
            dist = ((points[i][0] - start[0]) ** 2 + (points[i][1] - start[1]) ** 2) ** 0.5
        else:
            t = max(0.0, min(1.0, ((points[i][0] - start[0]) * dx + (points[i][1] - start[1]) * dy) / line_len_sq))
            proj_x = start[0] + t * dx
            proj_y = start[1] + t * dy
            dist = ((points[i][0] - proj_x) ** 2 + (points[i][1] - proj_y) ** 2) ** 0.5
        if dist > max_dist:
            max_dist = dist
            max_index = i

    if max_dist > tolerance:
        left = _douglas_peucker(points[: max_index + 1], tolerance)
        right = _douglas_peucker(points[max_index:], tolerance)
        return left[:-1] + right

    return [points[0], points[-1]]


