"""Build representative route shapes from the same GTFS downloads as scores."""
import csv
import io
import json
import math
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from etl.load_transit import AGENCY_NAMES, GTFS_CACHE_DIR


def route_features(agency: str, path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as archive:
        names = {name.split("/")[-1]: name for name in archive.namelist()}
        def rows(name):
            if name not in names:
                raise ValueError(f"{agency}: missing {name}")
            with archive.open(names[name]) as raw:
                yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))
        routes = {row["route_id"]: row for row in rows("routes.txt")}
        candidates = defaultdict(Counter)
        for trip in rows("trips.txt"):
            if trip.get("shape_id"):
                candidates[trip["route_id"]][trip["shape_id"]] += 1
        chosen = {route: counts.most_common(1)[0][0] for route, counts in candidates.items()}
        wanted = set(chosen.values())
        shapes = defaultdict(list)
        for row in rows("shapes.txt"):
            if row["shape_id"] in wanted:
                lon, lat = float(row["shape_pt_lon"]), float(row["shape_pt_lat"])
                if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError(f"{agency}: invalid route coordinates")
                shapes[row["shape_id"]].append((int(row["shape_pt_sequence"]), [lon, lat]))
        features = []
        for route_id, shape_id in sorted(chosen.items()):
            route = routes[route_id]
            coords = [coord for _, coord in sorted(shapes[shape_id])]
            if len(coords) < 2:
                raise ValueError(f"{agency}: incomplete shape for {route_id}")
            category = {"durham": "durham_rt"}.get(agency, agency)
            if agency == "ttc":
                category = "ttc_subway" if route["route_type"] == "1" else "ttc_other"
            colors = {"ttc_subway": "#C23030", "ttc_other": "#888888", "go_transit": "#5C8A4D", "miway": "#8C7356", "durham_rt": "#7A6B8C", "brampton": "#A36343"}
            features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords}, "properties": {
                "agency": AGENCY_NAMES[agency], "agency_id": agency,
                "route_name": route.get("route_short_name", ""), "route_long_name": route.get("route_long_name", ""),
                "route_type": {"0": "Streetcar", "1": "Subway", "2": "Train", "3": "Bus"}.get(route["route_type"], "Transit"),
                "color": colors[category], "transit_category": category,
            }})
        if not features:
            raise ValueError(f"{agency}: no route shapes")
        return features


def write_routes(agencies: list[str], output: Path) -> int:
    features = [feature for agency in agencies for feature in route_features(agency, GTFS_CACHE_DIR / f"{agency}.zip")]
    output.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    return len(features)
