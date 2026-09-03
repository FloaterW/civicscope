from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


_routes_cache: dict[str, Any] | None = None
_manifest_cache: dict[str, Any] | None = None


def load_transit_routes() -> dict[str, Any]:
    global _routes_cache
    if _routes_cache is None:
        path = files("app.data").joinpath("transit_routes.geojson")
        _routes_cache = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.is_file()
            else {"type": "FeatureCollection", "features": []}
        )
    return _routes_cache


def load_transit_manifest() -> dict[str, Any]:
    global _manifest_cache
    if _manifest_cache is None:
        path = files("app.data").joinpath("transit_manifest.json")
        _manifest_cache = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.is_file()
            else {
                "schema_version": 1,
                "coverage_status": "unknown",
                "included_agencies": [],
                "missing_agencies": [],
            }
        )
    return _manifest_cache


def transit_data_source() -> str:
    manifest = load_transit_manifest()
    agencies = ", ".join(
        agency["name"] for agency in manifest.get("included_agencies", [])
    ) or "no identified agencies"
    coverage = manifest.get("coverage_status", "unknown")
    return (
        f"Derived from the packaged {coverage} GTFS snapshot covering {agencies}. "
        "Unique scheduled routes are counted within 800m of each census tract boundary."
    )


def transit_data_quality() -> dict[str, str]:
    manifest = load_transit_manifest()
    agencies = ", ".join(
        agency["name"] for agency in manifest.get("included_agencies", [])
    ) or "no identified agencies"
    missing = ", ".join(
        agency["name"] for agency in manifest.get("missing_agencies", [])
    )
    return {
        "metric_status": "derived",
        "label": "Derived GTFS transit accessibility",
        "description": (
            f"Derived from the packaged GTFS snapshot for {agencies}. "
            "Unique routes within 800m are counted and normalized to a 0-100 score."
            + (f" The snapshot does not include {missing}." if missing else "")
        ),
    }
