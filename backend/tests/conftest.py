"""In-memory SQLite fixtures. Nothing here touches the real DATABASE_URL."""

import os
import sys
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# backend.db.session builds an engine at import time; the tests never use it,
# but importing the API modules would fail without a URL to hand it.
os.environ.setdefault("DATABASE_URL", "sqlite://")

from backend.db.base_class import Base  # noqa: E402
from backend.models import (  # noqa: E402,F401  (imported for table registration)
    db_users,
    db_application,
    db_applicationsync,
    db_response,
    db_event,
    db_integrationtokens,
    db_processedmessage,
)
from backend.models.db_users import User  # noqa: E402


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=True)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user_id(db):
    user = User(id=uuid.uuid4(), email="applicant@example.com", hashed_password="x")
    db.add(user)
    db.commit()
    return user.id
