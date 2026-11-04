"""Exercise export through candidate validation and deployment hash verification."""

import csv
from datetime import UTC, datetime
import json
import sys
import zipfile

from app.services.refresh_provenance import packaged_digest, verified_sources
from etl import load_transit, refresh_candidate, transit_routes


def test_generated_transit_candidate_hashes_survive_lf_checkout(tmp_path, monkeypatch):
    cache, candidate, checkout = (tmp_path / name for name in ("feeds", "candidate", "checkout"))
    for folder in (cache, candidate, checkout):
        folder.mkdir()
    feed = cache / "ttc.zip"
    with zipfile.ZipFile(feed, "w") as archive:
        for name, contents in {
            "routes.txt": "route_id,route_type,route_short_name\nr1,3,10\n",
            "trips.txt": "trip_id,route_id,shape_id\nt1,r1,s1\n",
            "stop_times.txt": "trip_id,stop_id\nt1,stop1\n",
            "stops.txt": "stop_id,stop_lat,stop_lon\nstop1,43.7,-79.4\n",
            "shapes.txt": "shape_id,shape_pt_lon,shape_pt_lat,shape_pt_sequence\ns1,-79.4,43.7,0\ns1,-79.3,43.8,1\n",
        }.items():
            archive.writestr(name, contents)
    monkeypatch.setattr(load_transit, "GTFS_FEEDS", {"ttc": "https://example.invalid/feed.zip"})
    monkeypatch.setattr(load_transit, "GTFS_CACHE_DIR", cache)
    monkeypatch.setattr(transit_routes, "GTFS_CACHE_DIR", cache)
    monkeypatch.setattr(load_transit, "MIN_AGENCIES", 1)
    monkeypatch.setattr(load_transit, "download_feed", lambda *args, **kwargs: (feed, True))
    monkeypatch.setattr(load_transit, "compute_scores_postgis", lambda *args: {
        "tract-a": (0, 0.0), "tract-b": (12, 65.5),
    })
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr(sys, "argv", [
        "load_transit", "--generate-csv", "--output", str(candidate / "transit_scores.csv"),
        "--manifest-output", str(candidate / "transit_manifest.json"),
        "--routes-output", str(candidate / "transit_routes.geojson"),
    ])
    load_transit.main()
    with (candidate / "transit_scores.csv").open(newline="", encoding="utf-8") as handle:
        assert list(csv.DictReader(handle)) == [
            {"geoid": "tract-a", "transit_route_count": "0", "transit_score": "0.0"},
            {"geoid": "tract-b", "transit_route_count": "12", "transit_score": "65.5"},
        ]
    names = refresh_candidate.ARTIFACTS["transit"]
    evidence = {"sources": {"transit": {
        "last_checked_at": datetime.now(UTC).isoformat(),
        "artifacts": {name: {"sha256": refresh_candidate.digest(candidate / name)} for name in names},
    }}}
    (candidate / "refresh_manifest.json").write_bytes(json.dumps(evidence).encode())
    for name in (*names, "refresh_manifest.json"):
        raw = (candidate / name).read_bytes()
        assert b"\r\n" not in raw
        # Simulate the repository's `* text=auto eol=lf` checkout policy.
        (checkout / name).write_bytes(raw.replace(b"\r\n", b"\n"))
    seed = {"geographies": [{"geoid": geoid, "type": "census_tract"} for geoid in ("tract-a", "tract-b")]}
    for folder in (candidate, checkout):
        (folder / "demo_seed.json").write_bytes(json.dumps(seed).encode())
    refresh_candidate.validate_candidate("transit", candidate, checkout)
    manifest = json.loads((checkout / "transit_manifest.json").read_bytes())
    for name in names:
        assert evidence["sources"]["transit"]["artifacts"][name]["sha256"] == packaged_digest(checkout / name)
    assert manifest["artifacts"]["transit_scores.csv"]["sha256"] == packaged_digest(checkout / "transit_scores.csv")
    assert "transit" in verified_sources(checkout)
