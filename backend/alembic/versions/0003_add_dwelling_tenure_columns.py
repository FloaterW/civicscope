"""Add dwelling type and tenure columns to metrics table.

Revision ID: 0003_add_dwelling_tenure
Revises: 0002_add_cmhc_metrics
Create Date: 2026-05-12
"""

from __future__ import annotations

from alembic import op

revision = "0003_add_dwelling_tenure"
down_revision = "0002_add_cmhc_metrics"
branch_labels = None
depends_on = None

COLUMNS = [
    ("dwellings_total", "INTEGER"),
    ("dwellings_single_detached", "INTEGER"),
    ("dwellings_semi_detached", "INTEGER"),
    ("dwellings_row_house", "INTEGER"),
    ("dwellings_apt_duplex", "INTEGER"),
    ("dwellings_apt_low_rise", "INTEGER"),
    ("dwellings_apt_high_rise", "INTEGER"),
    ("owner_households", "INTEGER"),
]


def upgrade() -> None:
    for col_name, col_type in COLUMNS:
        op.execute(
            f"ALTER TABLE metrics ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )


def downgrade() -> None:
    for col_name, _ in reversed(COLUMNS):
        op.execute(f"ALTER TABLE metrics DROP COLUMN IF EXISTS {col_name}")
