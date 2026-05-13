"""Add rms_surveyed column to cmhc_metrics table.

Revision ID: 0005_add_rms_surveyed
Revises: 0004_add_unabsorbed
Create Date: 2026-05-12
"""

from __future__ import annotations

from alembic import op

revision = "0005_add_rms_surveyed"
down_revision = "0004_add_unabsorbed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE cmhc_metrics ADD COLUMN IF NOT EXISTS rms_surveyed BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cmhc_metrics DROP COLUMN IF EXISTS rms_surveyed")
