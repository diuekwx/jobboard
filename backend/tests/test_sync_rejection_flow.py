"""End-to-end pass through /fetch-applications for confirmations and declines.

The stubbed Gmail API, the connected user and the ``sync`` helper all come
from conftest, which also switches the LLM off so the rules layer decides.
"""

from datetime import datetime, timezone

from backend.models.db_application import Application
from backend.models.db_processedmessage import ProcessedMessage
from backend.models.db_response import RecruiterResponse
from backend.service.jobs_service import REJECTED_STATUS
from backend.tests.gmail_stub import message as _message, sync

CONFIRMATION = (
    "Thank you for applying to the Backend Engineer position at Acme. "
    "We have received your application and will be in touch."
)
REJECTION = (
    "Thank you for your interest in Acme. After careful review we have decided "
    "to move forward with other candidates whose experience more closely "
    "matches what the role requires."
)


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
    from backend.api import gmail as gmail_api

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
