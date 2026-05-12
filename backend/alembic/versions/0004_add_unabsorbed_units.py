"""Add unabsorbed_units column to cmhc_metrics table.

Revision ID: 0004_add_unabsorbed
Revises: 0003_add_dwelling_tenure
Create Date: 2026-05-12
"""

from __future__ import annotations

from alembic import op

revision = "0004_add_unabsorbed"
down_revision = "0003_add_dwelling_tenure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE cmhc_metrics ADD COLUMN IF NOT EXISTS unabsorbed_units INTEGER"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cmhc_metrics DROP COLUMN IF EXISTS unabsorbed_units")
