"""Source-aware health observations and versioned research/evaluation records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0002_agent_health'
down_revision = '0001_accounts'
branch_labels = None
depends_on = None


def upgrade():
    payload = sa.JSON().with_variant(JSONB(), 'postgresql')
    op.create_table('health_measurements',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('metric', sa.String(40), nullable=False),
        sa.Column('provider', sa.String(60), nullable=False),
        sa.Column('external_id', sa.String(120), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', payload, nullable=False),
        sa.UniqueConstraint('user_id', 'provider', 'external_id'))
    op.create_index('health_measurements_owner_metric_time', 'health_measurements', ['user_id', 'metric', 'observed_at'])
    op.create_table('research_records',
        sa.Column('kind', sa.String(30), primary_key=True), sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', payload, nullable=False))
    op.create_index('research_records_kind_status', 'research_records', ['kind', 'status'])


def downgrade():
    raise RuntimeError('Health/research records require an explicit backup and retention decision before removal.')
