"""End-to-end pass through /fetch-applications for next-step e-mails.

Reuses the stubbed Gmail fixtures from the rejection flow test; the LLM is off
so the rules layer decides and the run stays hermetic.
"""

from datetime import datetime, timezone

from backend.models.db_application import Application
from backend.models.db_event import Event
from backend.models.db_processedmessage import ProcessedMessage
from backend.models.db_response import RecruiterResponse
from backend.service.jobs_service import (
    ASSESSMENT_STATUS,
    INTERVIEW_STATUS,
    REJECTED_STATUS,
    list_jobs,
)

from backend.tests.gmail_stub import message as _message, sync
from backend.tests.test_sync_rejection_flow import CONFIRMATION, REJECTION

ACME = "Acme Careers <no-reply@acme.com>"

ASSESSMENT = (
    "Thanks for applying to Acme. The next step is a short online assessment. "
    "Please complete the coding challenge within 48 hours."
)
INTERVIEW = (
    "We would like to invite you to an interview with the Acme team on "
    "March 17, 2026 at 2:00 PM UTC. The conversation will run 45 minutes."
)

FEB = datetime(2026, 2, 1, tzinfo=timezone.utc)
MAR = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)


def _apply(db, connected, stub_gmail):
    """Get one tracked, still-open Acme application on the board."""
    stub_gmail([_message(
        "m1", "t1", ACME, "Thank you for applying to Acme", CONFIRMATION, FEB,
    )])
    sync(db, connected)
    return db.query(Application).one()


def test_an_assessment_moves_a_sent_application_into_process(db, connected, stub_gmail):
    app = _apply(db, connected, stub_gmail)
    assert app.status == "sent"

    stub_gmail([_message(
        "m2", "t2", ACME, "Your Acme online assessment", ASSESSMENT, MAR,
    )])
    result = sync(db, connected)

    assert len(result["advanced"]) == 1
    moved = result["advanced"][0]
    assert moved["stage"] == ASSESSMENT_STATUS
    assert moved["from"] == "sent"
    assert moved["was_tracked"] is True
    assert result["created"] == []
    assert db.query(Application).count() == 1

    db.refresh(app)
    assert app.status == ASSESSMENT_STATUS
    # the mail itself is kept, and the deadline becomes a dated event
    assert db.query(RecruiterResponse).count() == 1
    event = db.query(Event).one()
    assert event.event_type == ASSESSMENT_STATUS
    assert event.start_time.replace(tzinfo=timezone.utc) == datetime(
        2026, 3, 12, 9, 0, tzinfo=timezone.utc
    )
    assert event.end_time is None


def test_an_interview_invite_records_the_slot_and_its_length(db, connected, stub_gmail):
    app = _apply(db, connected, stub_gmail)

    stub_gmail([_message(
        "m2", "t2", ACME, "Interview invitation - Acme", INTERVIEW, MAR,
    )])
    result = sync(db, connected)

    assert result["advanced"][0]["stage"] == INTERVIEW_STATUS
    db.refresh(app)
    assert app.status == INTERVIEW_STATUS

    event = db.query(Event).one()
    assert event.event_type == INTERVIEW_STATUS
    assert event.start_time.replace(tzinfo=timezone.utc) == datetime(
        2026, 3, 17, 14, 0, tzinfo=timezone.utc
    )
    assert event.end_time.replace(tzinfo=timezone.utc) == datetime(
        2026, 3, 17, 14, 45, tzinfo=timezone.utc
    )

    listed = next(a for a in result["applications"] if a["id"] == str(app.id))
    assert listed["status"] == INTERVIEW_STATUS
    assert listed["next_event"]["type"] == INTERVIEW_STATUS
    assert listed["next_event"]["at"].startswith("2026-03-17T14:00")


def test_the_stage_never_walks_backwards(db, connected, stub_gmail):
    app = _apply(db, connected, stub_gmail)

    stub_gmail([_message("m2", "t2", ACME, "Interview invitation - Acme", INTERVIEW, MAR)])
    sync(db, connected)
    db.refresh(app)
    assert app.status == INTERVIEW_STATUS

    # a stray assessment reminder arrives afterwards
    stub_gmail([_message(
        "m3", "t3", ACME, "Reminder: your Acme assessment", ASSESSMENT,
        datetime(2026, 3, 11, tzinfo=timezone.utc),
    )])
    result = sync(db, connected)

    assert result["advanced"] == []
    assert result["skipped"] == 1
    db.refresh(app)
    assert app.status == INTERVIEW_STATUS
    # the mail is still filed, and its deadline still lands on the board
    assert db.query(RecruiterResponse).count() == 2
    assert db.query(Event).count() == 2


def test_the_same_invite_is_never_logged_twice(db, connected, stub_gmail):
    _apply(db, connected, stub_gmail)
    message = _message("m2", "t2", ACME, "Interview invitation - Acme", INTERVIEW, MAR)

    stub_gmail([message])
    sync(db, connected)
    second = sync(db, connected)  # same message id still in the search results

    assert second["advanced"] == []
    assert db.query(Event).count() == 1
    assert db.query(RecruiterResponse).count() == 1


def test_an_invite_with_nothing_tracked_stands_a_row_up(db, connected, stub_gmail):
    stub_gmail([_message(
        "m1", "t1", "Globex Talent <careers@globex.com>",
        "Interview invitation - Globex", INTERVIEW.replace("Acme", "Globex"), MAR,
    )])
    result = sync(db, connected)

    assert result["unmatched_advances"] == 1
    assert [a["was_tracked"] for a in result["advanced"]] == [False]
    assert result["needs_review"] == 1

    app = db.query(Application).one()
    assert app.status == INTERVIEW_STATUS
    assert app.company_name == "Globex"
    assert app.needs_review is True
    assert db.query(Event).count() == 1


def test_an_unmatched_invite_is_dropped_when_creation_is_disabled(
    db, connected, stub_gmail, monkeypatch
):
    from backend.api import gmail as gmail_api

    monkeypatch.setattr(gmail_api, "CREATE_FROM_ADVANCE", False)
    stub_gmail([_message(
        "m1", "t1", "Globex Talent <careers@globex.com>",
        "Interview invitation - Globex", INTERVIEW.replace("Acme", "Globex"), MAR,
    )])
    result = sync(db, connected)

    assert result["unmatched_advances"] == 1
    assert db.query(Application).count() == 0
    assert db.query(ProcessedMessage).one().outcome == "advance_unmatched"


def test_an_invite_does_not_reopen_a_rejected_application(db, connected, stub_gmail):
    app = _apply(db, connected, stub_gmail)
    stub_gmail([_message(
        "m2", "t2", ACME, "Update on your application", REJECTION,
        datetime(2026, 2, 20, tzinfo=timezone.utc),
    )])
    sync(db, connected)
    db.refresh(app)
    assert app.status == REJECTED_STATUS

    # a fresh requisition at the same company invites the candidate to interview
    stub_gmail([_message(
        "m3", "t3", ACME, "Interview invitation - Acme", INTERVIEW, MAR,
    )])
    result = sync(db, connected)

    db.refresh(app)
    assert app.status == REJECTED_STATUS  # the recorded outcome survives
    assert db.query(Application).count() == 2
    fresh = db.query(Application).filter(Application.id != app.id).one()
    assert fresh.status == INTERVIEW_STATUS
    assert result["unmatched_advances"] == 1


def test_an_interview_still_lands_when_the_email_names_no_date(db, connected, stub_gmail):
    app = _apply(db, connected, stub_gmail)
    stub_gmail([_message(
        "m2", "t2", ACME, "Next steps at Acme",
        "We would like to invite you to an interview. Details to follow.", MAR,
    )])
    result = sync(db, connected)

    assert result["advanced"][0]["when"] is None
    db.refresh(app)
    assert app.status == INTERVIEW_STATUS
    assert db.query(Event).count() == 0

    listed = next(a for a in list_jobs(db, connected) if a["id"] == str(app.id))
    assert listed["next_event"] is None
