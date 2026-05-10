from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def supports_postgis(db: Session) -> bool:
    return db.bind is not None and db.bind.dialect.name == "postgresql"


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
) -> dict[str, dict[str, Any]]:
    if not has_geom_column(db):
        return {}

    if detail == "display":
        geometry_sql = "ST_AsGeoJSON(ST_SimplifyPreserveTopology(g.geom, :tolerance), 5)"
    else:
        geometry_sql = "ST_AsGeoJSON(g.geom, 8)"

    rows = db.execute(
        text(
            f"""
            SELECT g.geoid, {geometry_sql} AS geometry
            FROM geographies g
            JOIN metrics m ON m.geoid = g.geoid
            WHERE m.year = :year
              AND g.geom IS NOT NULL
            """
        ),
        {"year": year, "tolerance": 0.00008},
    ).mappings()

    return {
        str(row["geoid"]): json.loads(str(row["geometry"]))
        for row in rows
        if row["geometry"] is not None
    }
