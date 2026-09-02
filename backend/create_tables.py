import sys

from backend.db.session import engine
from backend.db.base_class import Base
from backend.models import (  # noqa: F401  (imported for side effect: table registration)
    db_users,
    db_application,
    db_applicationsync,
    db_response,
    db_event,
    db_integrationtokens,
    db_processedmessage,
)


def create_all_tables():
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")


def drop_all_tables():
    Base.metadata.drop_all(bind=engine)
    print("Tables dropped.")


if __name__ == "__main__":
    if "--drop" in sys.argv:
        drop_all_tables()
    create_all_tables()
