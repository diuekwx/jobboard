"""Matching a rejection e-mail to the application it is about, and recording it."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.models.db_application import Application
from backend.models.db_response import RecruiterResponse
from backend.service.jobs_service import (
    REJECTED_STATUS,
    create_email_application,
    find_application_for_rejection,
    list_jobs,
    mark_application_rejected,
    normalize_company,
)

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def make_app(db, user_id, *, company, role=None, status="sent", thread=None, days_ago=0):
    app = create_email_application(
        db, user_id,
        company=company,
        role=role,
        status=status,
        application_date=NOW - timedelta(days=days_ago),
        gmail_message_id=f"msg-{company}-{role}-{days_ago}",
        gmail_thread_id=thread,
        needs_review=False,
    )
    db.commit()
    return app


@pytest.mark.parametrize(("raw", "expected"), [
    ("Acme", "acme"),
    ("Acme Inc.", "acme"),
    ("ACME, LLC", "acme"),
    ("Acme Technologies Ltd", "acme"),
    ("Acme  Corp", "acme"),
    ("The Co", "theco"),          # all stop-words: falls back to the raw form
    ("Cognition", "cognition"),   # "co" must not be stripped mid-word
    (None, ""),
])
def test_normalize_company(raw, expected):
    assert normalize_company(raw) == expected


def test_matches_on_thread_id_first(db, user_id):
    same_thread = make_app(db, user_id, company="Acme", thread="t-1")
    make_app(db, user_id, company="Acme", role="Other", days_ago=1)

    found = find_application_for_rejection(
        db, user_id, thread_id="t-1", company="Globex", role=None
    )
    assert found.id == same_thread.id


def test_matches_on_company_when_the_thread_is_new(db, user_id):
    app = make_app(db, user_id, company="Acme Inc.")
    found = find_application_for_rejection(
        db, user_id, thread_id="brand-new-thread", company="ACME, LLC", role=None
    )
    assert found.id == app.id


def test_prefers_an_open_application_over_an_already_rejected_one(db, user_id):
    make_app(db, user_id, company="Acme", role="Data Analyst",
             status=REJECTED_STATUS, days_ago=30)
    open_app = make_app(db, user_id, company="Acme", role="Data Analyst", days_ago=2)

    found = find_application_for_rejection(
        db, user_id, thread_id=None, company="Acme", role="Data Analyst"
    )
    assert found.id == open_app.id


def test_prefers_the_matching_role(db, user_id):
    make_app(db, user_id, company="Acme", role="Product Manager", days_ago=1)
    backend = make_app(db, user_id, company="Acme", role="Backend Engineer", days_ago=20)

    found = find_application_for_rejection(
        db, user_id, thread_id=None, company="Acme", role="Backend Engineer Intern"
    )
    assert found.id == backend.id


def test_no_match_returns_none(db, user_id):
    make_app(db, user_id, company="Acme")
    assert find_application_for_rejection(
        db, user_id, thread_id=None, company="Globex", role=None
    ) is None
    assert find_application_for_rejection(
        db, user_id, thread_id=None, company=None, role=None
    ) is None


def test_does_not_reach_across_users(db, user_id):
    from backend.models.db_users import User
    import uuid

    other = User(id=uuid.uuid4(), email="someone@example.com", hashed_password="x")
    db.add(other)
    db.commit()
    make_app(db, other.id, company="Acme")

    assert find_application_for_rejection(
        db, user_id, thread_id=None, company="Acme", role=None
    ) is None


def test_mark_rejected_sets_status_and_files_the_email(db, user_id):
    app = make_app(db, user_id, company="Acme")

    changed = mark_application_rejected(
        db, app,
        sender="Acme Careers <no-reply@acme.com>",
        subject="Update on your application",
        body="We are moving forward with other candidates.",
        received_at=NOW,
    )
    db.commit()

    assert changed is True
    assert db.get(Application, app.id).status == REJECTED_STATUS

    response = db.query(RecruiterResponse).one()
    assert response.application_id == app.id
    assert response.received_at == NOW.replace(tzinfo=None)


def test_a_second_decline_is_filed_but_not_re_reported(db, user_id):
    app = make_app(db, user_id, company="Acme")
    for _ in range(2):
        changed = mark_application_rejected(
            db, app, sender="a@acme.com", subject="s", body="b", received_at=NOW,
        )
    db.commit()

    assert changed is False
    assert db.query(RecruiterResponse).count() == 2
    assert db.get(Application, app.id).status == REJECTED_STATUS


def test_overlong_headers_are_truncated_to_fit_the_column(db, user_id):
    app = make_app(db, user_id, company="Acme")
    mark_application_rejected(
        db, app, sender="x" * 400, subject="y" * 400, body=None, received_at=NOW,
    )
    db.commit()

    response = db.query(RecruiterResponse).one()
    assert len(response.sender_email) == 255
    assert len(response.subject) == 255


def test_list_jobs_exposes_the_rejection_date(db, user_id):
    app = make_app(db, user_id, company="Acme")
    mark_application_rejected(
        db, app, sender="a@acme.com", subject="s", body="b", received_at=NOW,
    )
    db.commit()

    row = next(j for j in list_jobs(db, user_id) if j["id"] == str(app.id))
    assert row["status"] == REJECTED_STATUS
    assert row["rejected_at"].startswith("2026-03-01")


def test_rejected_at_is_null_while_an_application_is_still_open(db, user_id):
    app = make_app(db, user_id, company="Acme")
    row = next(j for j in list_jobs(db, user_id) if j["id"] == str(app.id))
    assert row["rejected_at"] is None
