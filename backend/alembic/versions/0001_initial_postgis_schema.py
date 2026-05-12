"""Initial schema with native PostGIS geometry.

Revision ID: 0001_initial_postgis_schema
Revises:
Create Date: 2026-05-09
"""

from __future__ import annotations

from alembic import op

revision = "0001_initial_postgis_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS geographies (
            id SERIAL PRIMARY KEY,
            geoid VARCHAR(20) NOT NULL UNIQUE,
            name VARCHAR(160) NOT NULL,
            type VARCHAR(40) NOT NULL,
            county VARCHAR(120),
            state VARCHAR(2) NOT NULL DEFAULT 'ON',
            geometry JSON NOT NULL,
            bbox JSON NOT NULL,
            geometry_source VARCHAR(240) NOT NULL DEFAULT 'Official boundary geometry loaded from civic ETL.'
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_geographies_geoid ON geographies (geoid)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_geographies_name ON geographies (name)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_geographies_type ON geographies (type)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics (
            id SERIAL PRIMARY KEY,
            geoid VARCHAR(20) NOT NULL REFERENCES geographies(geoid) ON DELETE CASCADE,
            year INTEGER NOT NULL,
            median_income DOUBLE PRECISION,
            median_rent DOUBLE PRECISION,
            population INTEGER,
            previous_population INTEGER,
            renter_households INTEGER,
            rent_burden_pct DOUBLE PRECISION,
            affordability_index DOUBLE PRECISION,
            CONSTRAINT uq_metrics_geoid_year UNIQUE (geoid, year)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_metrics_geoid ON metrics (geoid)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_metrics_year ON metrics (year)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS etl_runs (
            id SERIAL PRIMARY KEY,
            source VARCHAR(120) NOT NULL,
            status VARCHAR(40) NOT NULL,
            started_at TIMESTAMP WITH TIME ZONE NOT NULL,
            completed_at TIMESTAMP WITH TIME ZONE,
            row_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT
        )
        """
    )
    op.execute("ALTER TABLE geographies ADD COLUMN IF NOT EXISTS geom geometry(GEOMETRY, 4326)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_geographies_geom ON geographies USING GIST (geom)")
    op.execute(
        """
        UPDATE geographies
        SET geom = ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON(geometry::text)), 4326)
        WHERE geometry IS NOT NULL AND geom IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_geographies_geom")
    op.execute("ALTER TABLE geographies DROP COLUMN IF EXISTS geom")
    op.execute("DROP TABLE IF EXISTS etl_runs")
    op.execute("DROP TABLE IF EXISTS metrics")
    op.execute("DROP TABLE IF EXISTS geographies")
