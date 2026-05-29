from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


SUPPORTED_GEOGRAPHY_TYPES = {"municipality", "census_tract"}

_GEOMETRY_EXPRS = {
    "display": "ST_AsGeoJSON(ST_SimplifyPreserveTopology(g.geom, :tolerance), 5)",
    "full": "ST_AsGeoJSON(g.geom, 8)",
}


def supports_postgis(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def has_geom_column(db: Session) -> bool:
    if not supports_postgis(db):
        return False

    return bool(
        db.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'geographies'
                      AND column_name = 'geom'
                )
                """
            )
        ).scalar()
    )


def sync_geography_geoms(db: Session) -> int:
    if not has_geom_column(db):
        return 0

    result = db.execute(
        text(
            """
            UPDATE geographies
            SET geom = ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON(geometry::text)), 4326)
            WHERE geometry IS NOT NULL
            """
        )
    )
    return int(result.rowcount or 0)


def load_postgis_map_geometries(
    db: Session,
    *,
    year: int,
    detail: str,
    geography_type: str | None = None,
) -> dict[str, dict[str, Any]]:
    if not has_geom_column(db):
        return {}

    if geography_type is not None and geography_type not in SUPPORTED_GEOGRAPHY_TYPES:
        raise ValueError(f"Invalid geography_type: {geography_type!r}")

    geometry_sql = _GEOMETRY_EXPRS.get(detail)
    if geometry_sql is None:
        raise ValueError(f"Invalid detail level: {detail!r}")

    geography_filter = "AND g.type = :geography_type" if geography_type else ""

    rows = db.execute(
        text(
            f"""
            SELECT g.geoid, {geometry_sql} AS geometry
            FROM geographies g
            JOIN metrics m ON m.geoid = g.geoid
            WHERE m.year = :year
              {geography_filter}
              AND g.geom IS NOT NULL
            """
        ),
        {
            "year": year,
            "tolerance": display_tolerance(geography_type),
            "geography_type": geography_type,
        },
    ).mappings()

    return {
        str(row["geoid"]): json.loads(str(row["geometry"]))
        for row in rows
        if row["geometry"] is not None
    }


def display_tolerance(geography_type: str | None) -> float:
    if geography_type == "census_tract":
        return 0.00035
    return 0.00008
