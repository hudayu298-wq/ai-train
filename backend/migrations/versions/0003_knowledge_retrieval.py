"""Versioned public knowledge index. Optional pgvector exact search on Postgres."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision='0003_knowledge_retrieval'
down_revision='0002_agent_health'
branch_labels=None
depends_on=None


def upgrade():
    document=sa.JSON().with_variant(JSONB(),'postgresql')
    op.create_table('knowledge_chunks',
        sa.Column('id',sa.String(64),primary_key=True),
        sa.Column('bundle_hash',sa.String(64),nullable=False),
        sa.Column('model_hash',sa.String(64),nullable=False),
        sa.Column('item_id',sa.String(80),nullable=False),
        sa.Column('chunk_key',sa.String(160),nullable=False),
        sa.Column('content',sa.String,nullable=False),
        sa.Column('content_hash',sa.String(64),nullable=False),
        sa.Column('embedding',document,nullable=False),
        sa.Column('payload',document,nullable=False))
    op.create_index('knowledge_chunks_bundle_model','knowledge_chunks',['bundle_hash','model_hash'])
    if op.get_bind().dialect.name=='postgresql':
        # The operator installs/creates the extension as postgres before migration.
        available=op.get_bind().execute(sa.text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='vector')")).scalar()
        if available:
            op.execute('ALTER TABLE knowledge_chunks ADD COLUMN embedding_vector vector')


def downgrade():
    op.drop_table('knowledge_chunks')
