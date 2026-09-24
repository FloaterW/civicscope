"""Correct Census ownership and add same-universe renter tenure, without reseeding.

Only audited Census 2021 fields of existing packaged geographies are updated.
No geography, CMHC, transit, TRREB, other vintage, or nonpackaged row is deleted.
Downgrade removes the new column, but intentionally never restores incorrect data.
"""

import hashlib
import json
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0011_add_tenure_renter"
down_revision = "0010_add_trreb_releases"
branch_labels = None
depends_on = None

CORRECTED_FIELDS = (
    "owner_households", "tenure_renter_households", "dwellings_total",
    "dwellings_single_detached", "dwellings_semi_detached", "dwellings_row_house",
    "dwellings_apt_duplex", "dwellings_apt_low_rise", "dwellings_apt_high_rise",
    "rent_burden_pct", "population", "previous_population", "renter_households",
)
CORRECTION_SHA256 = "a91e43fa0f30eb28572007d5fda34e7602ff5ff96abfd0ca6ffe387177b3cc7f"


def apply_census_corrections(connection, seed):
    records = []
    seen = set()
    for geography in seed["geographies"]:
        if geography["geoid"] in seen:
            raise ValueError("Duplicate Census correction geography")
        seen.add(geography["geoid"])
        census = [row for row in geography["metrics"] if row["year"] == 2021]
        if len(census) != 1:
            raise ValueError("Census correction must contain exactly one 2021 row")
        records.append({"geoid": geography["geoid"], "geography_type": geography["type"],
                        "geometry_source": geography["geometry_source"],
                        **{field: census[0][field] for field in CORRECTED_FIELDS}})
    if not records:
        raise ValueError("Empty Census correction snapshot")
    assignments = ", ".join(f"{field} = :{field}" for field in CORRECTED_FIELDS)
    return connection.execute(text(
        f"UPDATE metrics SET {assignments} WHERE geoid = :geoid AND year = 2021 "
        "AND EXISTS (SELECT 1 FROM geographies g WHERE g.geoid = :geoid "
        "AND g.type = :geography_type AND g.geometry_source = :geometry_source)"
    ), records).rowcount


def upgrade() -> None:
    op.execute("ALTER TABLE metrics ADD COLUMN IF NOT EXISTS tenure_renter_households INTEGER")
    data = Path(__file__).resolve().parents[2] / "app/data"
    contents = (data / "census_corrections_20260924.json").read_bytes()
    if hashlib.sha256(contents).hexdigest() != CORRECTION_SHA256:
        raise ValueError("Census correction snapshot does not match its audited hash")
    apply_census_corrections(op.get_bind(), json.loads(contents))


def downgrade() -> None:
    op.execute("ALTER TABLE metrics DROP COLUMN IF EXISTS tenure_renter_households")
