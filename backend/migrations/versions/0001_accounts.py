"""Accounts, rotating sessions, catalog and owner-scoped business documents.

The initial business-document table preserves existing API payloads. Subsequent
revisions can normalize meal/workout queries without a single-user compatibility mode.
"""
from alembic import op
from backend.migrations.schema_v1 import metadata

revision = '0001_accounts'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind())


def downgrade():
    raise RuntimeError('Account migration is not automatically reversible; restore a verified backup explicitly.')
