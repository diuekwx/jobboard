"""End-to-end pass through /fetch-applications with a stubbed Gmail API.

The LLM is switched off (``_get_client`` returns None) so the rules layer
decides, which keeps the test hermetic.
"""

import base64
from datetime import datetime, timezone

import pytest

from backend.api import gmail as gmail_api
from backend.models.db_application import Application
from backend.models.db_integrationtokens import IntegrationToken
from backend.models.db_processedmessage import ProcessedMessage
from backend.models.db_response import RecruiterResponse
from backend.service import classification_service
from backend.service.jobs_service import REJECTED_STATUS

CONFIRMATION = (
    "Thank you for applying to the Backend Engineer position at Acme. "
    "We have received your application and will be in touch."
)
REJECTION = (
    "Thank you for your interest in Acme. After careful review we have decided "
    "to move forward with other candidates whose experience more closely "
    "matches what the role requires."
)


def _message(mid, thread, from_header, subject, body, received):
    return {
        "id": mid,
        "threadId": thread,
        "internalDate": str(int(received.timestamp() * 1000)),
        "payload": {
            "headers": [
                {"name": "From", "value": from_header},
                {"name": "Subject", "value": subject},
            ],
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()},
        },
    }


class _Exec:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class _Messages:
    def __init__(self, messages):
        self._messages = messages

    def list(self, **_kw):
        return _Exec({"messages": [{"id": m["id"]} for m in self._messages]})

    def get(self, *, userId, id, format):
        return _Exec(next(m for m in self._messages if m["id"] == id))


class _FakeGmail:
    def __init__(self, messages):
        self._messages = _Messages(messages)

    def users(self):
        return self

    def messages(self):
        return self._messages


@pytest.fixture()
def stub_gmail(monkeypatch):
    """Returns a setter: hand it a list of raw messages for the next sync."""
    monkeypatch.setattr(classification_service, "_get_client", lambda: None)
    monkeypatch.setattr(gmail_api, "refresh_google_token", lambda db, token: token)

    box: list = []
    monkeypatch.setattr(gmail_api, "_build_gmail", lambda token: _FakeGmail(box))

    def load(messages):
        box[:] = messages
    return load


class _User:
    """Only ``.id`` is read off the user inside the endpoint."""

    def __init__(self, user_id):
        self.id = user_id


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


def sync(db, user_id):
    return gmail_api.fetch_job_applications(current_user=_User(user_id), db=db)


def test_confirmation_then_rejection_moves_the_application(db, connected, stub_gmail):
    stub_gmail([_message(
        "m1", "t1", "Acme Careers <no-reply@acme.com>",
        "Thank you for applying to Acme", CONFIRMATION,
        datetime(2026, 2, 1, tzinfo=timezone.utc),
    )])
    first = sync(db, connected)
    assert len(first["created"]) == 1
    assert first["rejected"] == []

    app = db.query(Application).one()
    assert app.status == "sent"

    # the decline arrives later, in its own thread
    stub_gmail([_message(
        "m2", "t2", "Acme Careers <no-reply@acme.com>",
        "Update on your application", REJECTION,
        datetime(2026, 2, 20, tzinfo=timezone.utc),
    )])
    second = sync(db, connected)

    assert len(second["rejected"]) == 1
    assert second["rejected"][0]["was_tracked"] is True
    assert second["unmatched_rejections"] == 0
    assert second["created"] == []
    assert db.query(Application).count() == 1

    db.refresh(app)
    assert app.status == REJECTED_STATUS
    assert db.query(RecruiterResponse).count() == 1

    listed = next(a for a in second["applications"] if a["id"] == str(app.id))
    assert listed["status"] == REJECTED_STATUS
    assert listed["rejected_at"].startswith("2026-02-20")


def test_unmatched_rejection_creates_a_rejected_row_for_review(db, connected, stub_gmail):
    stub_gmail([_message(
        "m1", "t1", "Globex Talent <careers@globex.com>",
        "Your application to Globex", REJECTION.replace("Acme", "Globex"),
        datetime(2026, 2, 20, tzinfo=timezone.utc),
    )])
    result = sync(db, connected)

    assert result["unmatched_rejections"] == 1
    assert [r["was_tracked"] for r in result["rejected"]] == [False]
    assert result["needs_review"] == 1

    app = db.query(Application).one()
    assert app.status == REJECTED_STATUS
    assert app.company_name == "Globex"
    assert app.needs_review is True
    assert db.query(RecruiterResponse).count() == 1


def test_unmatched_rejection_is_dropped_when_creation_is_disabled(
    db, connected, stub_gmail, monkeypatch
):
    monkeypatch.setattr(gmail_api, "CREATE_FROM_REJECTION", False)
    stub_gmail([_message(
        "m1", "t1", "Globex Talent <careers@globex.com>",
        "Your application to Globex", REJECTION.replace("Acme", "Globex"),
        datetime(2026, 2, 20, tzinfo=timezone.utc),
    )])
    result = sync(db, connected)

    assert result["unmatched_rejections"] == 1
    assert db.query(Application).count() == 0
    assert db.query(ProcessedMessage).one().outcome == "rejection_unmatched"


def test_the_same_rejection_is_never_applied_twice(db, connected, stub_gmail):
    message = _message(
        "m1", "t1", "Acme Careers <no-reply@acme.com>",
        "Update on your application", REJECTION,
        datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    stub_gmail([message])
    sync(db, connected)
    second = sync(db, connected)  # same message id still in the search results

    assert second["rejected"] == []
    assert db.query(Application).count() == 1
    assert db.query(RecruiterResponse).count() == 1
