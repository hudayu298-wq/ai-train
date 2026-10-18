from alembic import context
from backend.database import get_engine, metadata

def run():
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()

run()
