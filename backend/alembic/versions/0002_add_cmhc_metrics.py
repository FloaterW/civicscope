"""Add cmhc_metrics table.

Revision ID: 0002_add_cmhc_metrics
Revises: 0001_initial_postgis_schema
Create Date: 2026-05-10
"""

from __future__ import annotations

from alembic import op

revision = "0002_add_cmhc_metrics"
down_revision = "0001_initial_postgis_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cmhc_metrics (
            id SERIAL PRIMARY KEY,
            geoid VARCHAR(20) NOT NULL REFERENCES geographies(geoid) ON DELETE CASCADE,
            year INTEGER NOT NULL,
            vacancy_rate DOUBLE PRECISION,
            average_rent_total DOUBLE PRECISION,
            average_rent_bachelor DOUBLE PRECISION,
            average_rent_1br DOUBLE PRECISION,
            average_rent_2br DOUBLE PRECISION,
            average_rent_3br_plus DOUBLE PRECISION,
            turnover_rate DOUBLE PRECISION,
            availability_rate DOUBLE PRECISION,
            rental_universe INTEGER,
            housing_starts_total INTEGER,
            housing_starts_single INTEGER,
            housing_starts_semi INTEGER,
            housing_starts_row INTEGER,
            housing_starts_apartment INTEGER,
            housing_completions INTEGER,
            units_under_construction INTEGER,
            CONSTRAINT uq_cmhc_metrics_geoid_year UNIQUE (geoid, year)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_cmhc_metrics_id ON cmhc_metrics (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cmhc_metrics_geoid ON cmhc_metrics (geoid)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cmhc_metrics_year ON cmhc_metrics (year)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cmhc_metrics_year")
    op.execute("DROP INDEX IF EXISTS ix_cmhc_metrics_geoid")
    op.execute("DROP INDEX IF EXISTS ix_cmhc_metrics_id")
    op.execute("DROP TABLE IF EXISTS cmhc_metrics")
