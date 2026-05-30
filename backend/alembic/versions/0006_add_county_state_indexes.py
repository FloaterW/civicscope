"""Add indexes on geographies.county and geographies.state.

The Geography model declares ``index=True`` on ``county`` and ``state``, and
SQLite test databases (built via ``Base.metadata.create_all``) get those
indexes. Postgres deployments are managed solely by Alembic, where the initial
schema (0001) created indexes only for geoid/name/type. This migration brings
the Postgres schema in line with the model so a fresh ``alembic upgrade head``
matches what the ORM expects. Idempotent (IF NOT EXISTS).

Revision ID: 0006_add_county_state_indexes
Revises: 0005_add_rms_surveyed
Create Date: 2026-05-30

"""
from __future__ import annotations

from alembic import op

revision = "0006_add_county_state_indexes"
down_revision = "0005_add_rms_surveyed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_geographies_county ON geographies (county)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_geographies_state ON geographies (state)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_geographies_county")
    op.execute("DROP INDEX IF EXISTS ix_geographies_state")
