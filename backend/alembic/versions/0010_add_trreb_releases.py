"""Immutable approved TRREB releases and deliberate publication pointer."""
from alembic import op
import sqlalchemy as sa

revision = '0010_add_trreb_releases'
down_revision = '0009_add_transit_columns'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('trreb_releases',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('archive_sha256', sa.String(64), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('audit_summary', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('trreb_observations',
        sa.Column('release_id', sa.String(64), sa.ForeignKey('trreb_releases.id'), primary_key=True),
        sa.Column('geoid', sa.String(7), primary_key=True),
        sa.Column('period', sa.String(7), primary_key=True),
        sa.Column('payload', sa.JSON(), nullable=False))
    op.create_table('trreb_publication',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('release_id', sa.String(64), sa.ForeignKey('trreb_releases.id'), nullable=True),
        sa.CheckConstraint('id = 1', name='trreb_publication_singleton'))
    op.execute(sa.text('INSERT INTO trreb_publication (id, release_id) VALUES (1, NULL)'))
    op.create_table('trreb_publication_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('release_id', sa.String(64), sa.ForeignKey('trreb_releases.id'), nullable=True),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('trreb_publication_events')
    op.drop_table('trreb_publication')
    op.drop_table('trreb_observations')
    op.drop_table('trreb_releases')
