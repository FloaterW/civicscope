"""Add transit accessibility columns to metrics.

transit_route_count: number of unique transit routes within 800m of tract boundary
transit_score: 0-100 normalized score (decile-clamped)

Revision ID: 0009_add_transit_columns
Revises: 0008_add_cmhc_tract_source
Create Date: 2026-06-24
"""

from __future__ import annotations

from alembic import op

revision = "0009_add_transit_columns"
down_revision = "0008_add_cmhc_tract_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE metrics ADD COLUMN IF NOT EXISTS transit_route_count INTEGER"
    )
    op.execute(
        "ALTER TABLE metrics ADD COLUMN IF NOT EXISTS transit_score FLOAT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE metrics DROP COLUMN IF EXISTS transit_route_count")
    op.execute("ALTER TABLE metrics DROP COLUMN IF EXISTS transit_score")
