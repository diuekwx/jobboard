"""In-memory SQLite fixtures and a stubbed Gmail API.

Nothing here touches the real DATABASE_URL, the network, or the LLM.
"""

import os
import sys
import uuid
from datetime import datetime

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


# --- stubbed Gmail --------------------------------------------------------

from backend.api import gmail as gmail_api  # noqa: E402
from backend.models.db_integrationtokens import IntegrationToken  # noqa: E402
from backend.service import classification_service  # noqa: E402
from backend.tests.gmail_stub import FakeGmail  # noqa: E402


@pytest.fixture()
def stub_gmail(monkeypatch):
    """Returns a setter: hand it a list of raw messages for the next sync.

    The LLM is switched off (``_get_client`` returns None) so the rules layer
    decides on its own.
    """
    monkeypatch.setattr(classification_service, "_get_client", lambda: None)
    monkeypatch.setattr(gmail_api, "refresh_google_token", lambda db, token: token)

    box: list = []
    monkeypatch.setattr(gmail_api, "_build_gmail", lambda token: FakeGmail(box))

    def load(messages):
        box[:] = messages
    return load


@pytest.fixture()
def connected(db, user_id):
    """A user with a Gmail token on file, which the endpoint requires."""
    db.add(IntegrationToken(
        user_id=user_id,
        provider="gmail",
        access_token="a",
        refresh_token="r",
        expires_at=datetime(2030, 1, 1),
    ))
    db.commit()
    return user_id
