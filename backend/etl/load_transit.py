"""Compute transit accessibility scores from GTFS feeds for GTA census tracts.

Downloads GTFS static feeds from GTA transit agencies (TTC, MiWay, GO Transit,
Brampton Transit, Durham Region Transit), parses stop-route relationships, loads
stops into a temporary PostGIS table, and performs a spatial join to count unique
transit routes within 800m of each census tract boundary. Results are normalized
to a 0-100 score using decile clamping and written to the metrics table.

Usage:
  python etl/load_transit.py                     # full run (download + compute)
  python etl/load_transit.py --skip-download      # reuse cached GTFS zips
  python etl/load_transit.py --generate-csv       # write CSV instead of DB
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import os
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

GTFS_CACHE_DIR = PROJECT_ROOT / "app" / "data" / "gtfs_cache"

GTFS_FEEDS: dict[str, str] = {
    "ttc": "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/7795b45e-e65a-4465-81fc-c36b9dfff169/resource/cfb6b2b8-6191-41e3-bda1-b175c51148cb/download/TTC%20Routes%20and%20Schedules%20Data.zip",
    "miway": "https://www.miapp.ca/GTFS/google_transit.zip",
    "go_transit": "https://assets.metrolinx.com/raw/upload/Documents/Metrolinx/Open%20Data/GO-GTFS.zip",
    "brampton": "https://www.brampton.ca/EN/City-Hall/OpenGov/Open-Data-Catalogue/Documents/Google_Transit.zip",
    "durham": "https://maps.durham.ca/OpenDataGTFS/GTFS_Durham_TXT.zip",
}

BUFFER_METERS = 800


def download_feed(agency: str, url: str) -> Path:
    GTFS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = GTFS_CACHE_DIR / f"{agency}.zip"
    if dest.exists():
        print(f"  [cache hit] {agency}")
        return dest
    print(f"  Downloading {agency} GTFS feed...")
    try:
        with urlopen(url, timeout=60) as resp:
            dest.write_bytes(resp.read())
        print(f"  [ok] {agency} ({dest.stat().st_size / 1024:.0f} KB)")
    except Exception as e:
        print(f"  [skip] {agency}: {e}")
        return dest
    return dest


def parse_gtfs_stop_routes(zip_path: Path) -> dict[tuple[float, float], set[str]]:
    """Parse a GTFS zip and return {(lat, lon): set_of_route_ids}."""
    if not zip_path.exists() or zip_path.stat().st_size == 0:
        return {}

    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        print(f"  [skip] Bad zip: {zip_path.name}")
        return {}

    names = {n.split("/")[-1]: n for n in zf.namelist()}

    def read_csv(filename: str) -> list[dict[str, str]]:
        full = names.get(filename)
        if full is None:
            for n in names:
                if n.endswith(filename):
                    full = n
                    break
        if full is None:
            return []
        raw = zf.read(full)
        text_data = raw.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text_data)))

    stops_raw = read_csv("stops.txt")
    stop_times_raw = read_csv("stop_times.txt")
    trips_raw = read_csv("trips.txt")
    routes_raw = read_csv("routes.txt")

    if not stops_raw or not stop_times_raw or not trips_raw:
        return {}

    route_name_map = {}
    for r in routes_raw:
        rid = r.get("route_id", "")
        route_name_map[rid] = r.get("route_short_name") or r.get("route_long_name") or rid

    trip_to_route: dict[str, str] = {}
    for t in trips_raw:
        trip_to_route[t["trip_id"]] = t["route_id"]

    stop_to_routes: dict[str, set[str]] = {}
    for st in stop_times_raw:
        sid = st["stop_id"]
        tid = st["trip_id"]
        rid = trip_to_route.get(tid)
        if rid:
            stop_to_routes.setdefault(sid, set()).add(rid)

    result: dict[tuple[float, float], set[str]] = {}
    agency_tag = zip_path.stem
    for s in stops_raw:
        sid = s.get("stop_id", "")
        lat_s = s.get("stop_lat", "")
        lon_s = s.get("stop_lon", "")
        if not lat_s or not lon_s:
            continue
        try:
            lat, lon = float(lat_s), float(lon_s)
        except ValueError:
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        routes = stop_to_routes.get(sid, set())
        tagged = {f"{agency_tag}:{r}" for r in routes}
        key = (round(lat, 6), round(lon, 6))
        result.setdefault(key, set()).update(tagged)

    zf.close()
    return result


def merge_stop_routes(
    all_feeds: dict[str, dict[tuple[float, float], set[str]]],
) -> dict[tuple[float, float], set[str]]:
    merged: dict[tuple[float, float], set[str]] = {}
    for stops in all_feeds.values():
        for coord, routes in stops.items():
            merged.setdefault(coord, set()).update(routes)
    return merged


def compute_scores_postgis(
    stop_routes: dict[tuple[float, float], set[str]],
    db_url: str,
) -> dict[str, tuple[int, float]]:
    """Use PostGIS spatial join to count unique routes per census tract.

    Returns {geoid: (route_count, score_0_100)}.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(db_url)

    with Session(engine) as db:
        db.execute(text("DROP TABLE IF EXISTS _gtfs_stops"))
        db.execute(text("""
            CREATE TEMP TABLE _gtfs_stops (
                id SERIAL PRIMARY KEY,
                lat DOUBLE PRECISION NOT NULL,
                lon DOUBLE PRECISION NOT NULL,
                route_id TEXT NOT NULL,
                geom GEOMETRY(Point, 4326)
            )
        """))

        rows = []
        for (lat, lon), routes in stop_routes.items():
            for route in routes:
                rows.append({"lat": lat, "lon": lon, "route_id": route})

        batch_size = 5000
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            db.execute(
                text("""
                    INSERT INTO _gtfs_stops (lat, lon, route_id, geom)
                    VALUES (:lat, :lon, :route_id, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
                """),
                batch,
            )

        db.execute(text("CREATE INDEX ON _gtfs_stops USING GIST (geom)"))

        result = db.execute(text("""
            SELECT g.geoid, COUNT(DISTINCT s.route_id) as route_count
            FROM geographies g
            JOIN _gtfs_stops s ON ST_DWithin(
                g.geom::geography,
                s.geom::geography,
                :buffer
            )
            WHERE g.type = 'census_tract' AND g.geom IS NOT NULL
            GROUP BY g.geoid
        """), {"buffer": BUFFER_METERS}).mappings().all()

        counts = {r["geoid"]: int(r["route_count"]) for r in result}

        db.execute(text("DROP TABLE IF EXISTS _gtfs_stops"))
        db.commit()

    if not counts:
        return {}

    values = sorted(counts.values())
    n = len(values)

    def percentile(sorted_vals: list[int], pct: float) -> float:
        k = (n - 1) * pct / 100.0
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return float(sorted_vals[int(k)])
        return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)

    p10 = percentile(values, 10)
    p90 = percentile(values, 90)

    scores: dict[str, tuple[int, float]] = {}
    for geoid, count in counts.items():
        if p90 <= p10:
            score = 50.0
        else:
            score = max(0.0, min(100.0, (count - p10) / (p90 - p10) * 100))
        scores[geoid] = (count, round(score, 1))

    return scores


def write_csv(scores: dict[str, tuple[int, float]], path: Path) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["geoid", "transit_route_count", "transit_score"])
        for geoid in sorted(scores):
            count, score = scores[geoid]
            w.writerow([geoid, count, score])
    print(f"Wrote {len(scores)} rows to {path}")


def update_db(scores: dict[str, tuple[int, float]], db_url: str) -> int:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(db_url)
    updated = 0
    with Session(engine) as db:
        for geoid, (count, score) in scores.items():
            r = db.execute(
                text("""
                    UPDATE metrics
                    SET transit_route_count = :count, transit_score = :score
                    WHERE geoid = :geoid
                """),
                {"count": count, "score": score, "geoid": geoid},
            )
            updated += r.rowcount
        db.commit()
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Load GTFS transit scores")
    parser.add_argument("--skip-download", action="store_true", help="Use cached GTFS zips")
    parser.add_argument("--generate-csv", action="store_true", help="Write CSV instead of updating DB")
    parser.add_argument("--db-url", default=None, help="Database URL (default: from env/settings)")
    args = parser.parse_args()

    db_url = args.db_url or os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://civicscope:civicscope@localhost:5432/civicscope",
    )

    print("=== GTFS Transit Scoring ===")

    if not args.skip_download:
        print("\n1. Downloading GTFS feeds...")
        for agency, url in GTFS_FEEDS.items():
            download_feed(agency, url)
    else:
        print("\n1. Using cached GTFS feeds")

    print("\n2. Parsing stop-route relationships...")
    all_feeds: dict[str, dict[tuple[float, float], set[str]]] = {}
    for agency in GTFS_FEEDS:
        zip_path = GTFS_CACHE_DIR / f"{agency}.zip"
        stops = parse_gtfs_stop_routes(zip_path)
        print(f"  {agency}: {len(stops)} stops")
        all_feeds[agency] = stops

    merged = merge_stop_routes(all_feeds)
    total_routes = set()
    for routes in merged.values():
        total_routes.update(routes)
    print(f"\n  Merged: {len(merged)} unique stop locations, {len(total_routes)} unique routes")

    print("\n3. Computing transit scores via PostGIS spatial join...")
    scores = compute_scores_postgis(merged, db_url)
    if not scores:
        print("  No scores computed (PostGIS spatial join returned empty)")
        return

    values = [s[0] for s in scores.values()]
    print(f"  Scored {len(scores)} tracts")
    print(f"  Route count range: {min(values)}-{max(values)}")
    print(f"  Median routes: {sorted(values)[len(values)//2]}")

    if args.generate_csv:
        out = PROJECT_ROOT / "app" / "data" / "transit_scores.csv"
        write_csv(scores, out)
    else:
        print("\n4. Updating metrics table...")
        updated = update_db(scores, db_url)
        print(f"  Updated {updated} metric rows")

    print("\nDone.")


if __name__ == "__main__":
    main()
