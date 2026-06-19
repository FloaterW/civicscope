"""Add cmhc_tract_metrics table for real census-tract SCSS data.

Revision ID: 0007_add_cmhc_tract_metrics
Revises: 0006_add_county_state_indexes
Create Date: 2026-06-01
"""

from __future__ import annotations

from alembic import op

revision = "0007_add_cmhc_tract_metrics"
down_revision = "0006_add_county_state_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cmhc_tract_metrics (
            id SERIAL PRIMARY KEY,
            geoid VARCHAR(20) NOT NULL REFERENCES geographies(geoid) ON DELETE CASCADE,
            year INTEGER NOT NULL,
            housing_starts_total INTEGER,
            housing_completions INTEGER,
            CONSTRAINT uq_cmhc_tract_metrics_geoid_year UNIQUE (geoid, year)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_cmhc_tract_metrics_geoid ON cmhc_tract_metrics (geoid)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cmhc_tract_metrics_year ON cmhc_tract_metrics (year)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cmhc_tract_metrics_id ON cmhc_tract_metrics (id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cmhc_tract_metrics")
