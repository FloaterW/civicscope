"""Add per-metric source columns to cmhc_tract_metrics.

Distinguishes real published census-tract values ("official", incl. parent
tracts that recorded zero) from values allocated off a real CMHC *parent* tract
("estimated_parent"). Tracts absent from the table keep the API's municipal
allocation estimate.

Revision ID: 0008_add_cmhc_tract_source
Revises: 0007_add_cmhc_tract_metrics
Create Date: 2026-06-19
"""

from __future__ import annotations

from alembic import op

revision = "0008_add_cmhc_tract_source"
down_revision = "0007_add_cmhc_tract_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE cmhc_tract_metrics "
        "ADD COLUMN IF NOT EXISTS housing_starts_total_source VARCHAR(20)"
    )
    op.execute(
        "ALTER TABLE cmhc_tract_metrics "
        "ADD COLUMN IF NOT EXISTS housing_completions_source VARCHAR(20)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cmhc_tract_metrics DROP COLUMN IF EXISTS housing_starts_total_source")
    op.execute("ALTER TABLE cmhc_tract_metrics DROP COLUMN IF EXISTS housing_completions_source")
