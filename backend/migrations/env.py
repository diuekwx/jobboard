import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

from backend.db.base_class import Base
from backend.models import (  # noqa: F401
    db_users, db_application, db_applicationsync, db_response,
    db_event, db_integrationtokens, db_processedmessage, db_scanjob,
)


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata,
                      compare_type=True, render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Migrations require an online connection for data validation")
elif context.config.attributes.get("connection") is not None:
    run(context.config.attributes["connection"])
else:
    load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL before running migrations")
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        run(connection)
