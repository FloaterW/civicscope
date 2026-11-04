"""Correct only the 90 audited CMHC bedroom-rent cells, without reseeding.

Known old values on the original municipal boundaries are replaced in place.
Missing rows, custom boundaries and newer/custom values are preserved and logged.
An empty database is safe: normal initial seeding supplies the corrected values.
If startup seeding is enabled, unexplained production drift will require operator
review rather than destructive replacement. Downgrade never restores bad data.
"""

import hashlib
import json
import logging
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0012_cmhc_bedroom_weights"
down_revision = "0011_add_tenure_renter"
branch_labels = None
depends_on = None

CORRECTION_SHA256 = "25cb2242f7c6e236c87e266c89895e0d553ffaa526d7e034f89fd6d77f482543"
CORRECTION_FILE = "cmhc_bedroom_corrections_20261104.json"
CORRECTED_FIELDS = (
    "average_rent_bachelor", "average_rent_1br", "average_rent_2br",
    "average_rent_3br_plus",
)
GEOIDS = ("3520005", "3521005", "3521010")
GEOMETRY_SOURCE = (
    "Statistics Canada 2021 cartographic census subdivision boundary, "
    "filtered to GTA municipalities."
)
logger = logging.getLogger("alembic.runtime.migration")


def load_corrections():
    path = Path(__file__).resolve().parents[2] / "app/data" / CORRECTION_FILE
    contents = path.read_bytes()
    if hashlib.sha256(contents).hexdigest() != CORRECTION_SHA256:
        raise ValueError("CMHC correction snapshot does not match its audited hash")
    return json.loads(contents)


def _validated_records(snapshot):
    records = snapshot.get("corrections", [])
    if snapshot.get("schema_version") != 1 or len(records) != 90:
        raise ValueError("CMHC correction snapshot must contain 90 audited cells")
    seen = set()
    for row in records:
        key = (row["geoid"], row["year"], row["field"])
        if key in seen:
            raise ValueError("Duplicate CMHC correction cell")
        seen.add(key)
        if (
            row["geoid"] not in GEOIDS
            or type(row["year"]) is not int
            or not 2018 <= row["year"] <= 2025
            or row["field"] not in CORRECTED_FIELDS
        ):
            raise ValueError("CMHC correction outside the audited scope")
        before, after = row["before"], row["after"]
        if (
            type(before) is not int or before < 0
            or (after is not None and (type(after) is not int or after < 0))
            or before == after
        ):
            raise ValueError("Invalid CMHC correction values")
    if {(row["geoid"], row["year"]) for row in records} != {
        (geoid, year) for geoid in GEOIDS for year in range(2018, 2026)
    }:
        raise ValueError("CMHC correction snapshot must cover the 24 audited rows")
    return records


def apply_cmhc_corrections(connection, snapshot):
    # Validate the entire batch before writing; identifiers below are whitelisted.
    records = _validated_records(snapshot)
    result = {key: 0 for key in (
        "applied", "already_corrected", "missing", "skipped_context", "skipped_conflict",
    )}
    for record in records:
        field = record["field"]
        params = {**record, "geometry_source": GEOMETRY_SOURCE}
        current = connection.execute(text(
            f"SELECT m.{field} AS value, g.type, g.geometry_source "
            "FROM cmhc_metrics m LEFT JOIN geographies g ON g.geoid = m.geoid "
            "WHERE m.geoid = :geoid AND m.year = :year"
        ), params).mappings().one_or_none()
        if current is None:
            status = "missing"
        elif current["type"] != "municipality" or current["geometry_source"] != GEOMETRY_SOURCE:
            status = "skipped_context"
        elif current["value"] == record["after"]:
            status = "already_corrected"
        elif current["value"] != record["before"]:
            status = "skipped_conflict"
        else:
            updated = connection.execute(text(
                f"UPDATE cmhc_metrics SET {field} = :after "
                f"WHERE geoid = :geoid AND year = :year AND {field} = :before "
                "AND EXISTS (SELECT 1 FROM geographies g WHERE g.geoid = :geoid "
                "AND g.type = 'municipality' AND g.geometry_source = :geometry_source)"
            ), params).rowcount
            status = "applied" if updated == 1 else "skipped_conflict"
        result[status] += 1
        if status.startswith("skipped"):
            logger.warning(
                "CMHC correction %s: geoid=%s year=%s field=%s; retained existing data",
                status, record["geoid"], record["year"], field,
            )
    logger.info("Audited CMHC bedroom corrections: %s", result)
    return result


def upgrade() -> None:
    apply_cmhc_corrections(op.get_bind(), load_corrections())


def downgrade() -> None:
    # Data corrections are intentionally irreversible: do not restore errors.
    pass
