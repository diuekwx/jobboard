from datetime import datetime, timedelta, timezone

import pytest

from backend.api import gmail as gmail_api
from backend.models.db_application import Application
from backend.models.db_applicationsync import ApplicationSync
from backend.models.db_processedmessage import ProcessedMessage
from backend.models.db_response import RecruiterResponse
from backend.service import sync_service
from backend.tests.gmail_stub import message, sync
from backend.tests.test_sync_rejection_flow import CONFIRMATION, REJECTION


def _newsletter(index: int):
    return message(
        f"m{index}",
        f"t{index}",
        "News <news@example.com>",
        f"Newsletter {index}",
        "Here is the general company newsletter.",
        datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(minutes=index),
    )


def test_large_backlog_crosses_pages_and_scan_limits(
    db, connected, stub_gmail, monkeypatch
):
    monkeypatch.setattr(gmail_api, "MAX_MESSAGES_PER_SYNC", 150)
    monkeypatch.setattr(gmail_api, "_CHUNK", 25)
    stub_gmail([_newsletter(index) for index in range(205, 0, -1)])

    first = sync(db, connected)

    assert first["not_application"] == 150
    assert db.query(ProcessedMessage).count() == 150
    assert db.query(ApplicationSync).one().last_synced_at is None

    second = sync(db, connected)

    assert second["not_application"] == 55
    assert db.query(ProcessedMessage).count() == 205
    assert db.query(ApplicationSync).one().last_synced_at is not None

    third = sync(db, connected)

    assert third["not_application"] == 0
    assert db.query(ProcessedMessage).count() == 205


def test_moving_start_date_backward_resets_the_checkpoint(db, user_id):
    initial = datetime(2026, 8, 1, tzinfo=timezone.utc)
    earlier = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row = sync_service.sync(db, user_id, initial)
    row.last_synced_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    db.commit()

    changed = sync_service.sync(db, user_id, earlier)

    assert changed.start_date == earlier
    assert changed.last_synced_at is None
    assert sync_service.search_after_datetime(changed) < initial


def test_failed_fetch_is_retried_before_checkpoint_advances(
    db, connected, stub_gmail
):
    failed = _newsletter(1)
    failed["fetch_error"] = True
    stub_gmail([failed])

    first = sync(db, connected)

    assert first["failed"] == 1
    assert db.query(ProcessedMessage).count() == 0
    assert db.query(ApplicationSync).one().last_synced_at is None

    retry = _newsletter(1)
    stub_gmail([retry])
    second = sync(db, connected)

    assert second["failed"] == 0
    assert second["not_application"] == 1
    assert db.query(ProcessedMessage).count() == 1
    assert db.query(ApplicationSync).one().last_synced_at is not None


def test_deferred_message_is_retried_before_checkpoint_advances(
    db, connected, stub_gmail, monkeypatch
):
    original = gmail_api.classify_emails
    calls = 0

    def defer_once(emails, llm_budget):
        nonlocal calls
        calls += 1
        if calls == 1:
            decision = type("Decision", (), {"method": "deferred"})()
            return {email.key: decision for email in emails}
        return original(emails, llm_budget=llm_budget)

    monkeypatch.setattr(gmail_api, "classify_emails", defer_once)
    stub_gmail([_newsletter(1)])

    first = sync(db, connected)

    assert first["deferred"] == 1
    assert db.query(ProcessedMessage).count() == 0
    assert db.query(ApplicationSync).one().last_synced_at is None

    second = sync(db, connected)

    assert second["not_application"] == 1
    assert db.query(ProcessedMessage).count() == 1
    assert db.query(ApplicationSync).one().last_synced_at is not None


def test_newest_first_results_are_applied_in_received_order(
    db, connected, stub_gmail
):
    confirmation = message(
        "m1",
        "t1",
        "Acme Careers <no-reply@acme.com>",
        "Thank you for applying to Acme",
        CONFIRMATION,
        datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    rejection = message(
        "m2",
        "t2",
        "Acme Careers <no-reply@acme.com>",
        "Update on your application",
        REJECTION,
        datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    stub_gmail([rejection, confirmation])

    result = sync(db, connected)

    assert len(result["created"]) == 1
    assert len(result["rejected"]) == 1
    assert result["rejected"][0]["was_tracked"] is True
    assert db.query(Application).count() == 1
    assert db.query(Application).one().status == "rejected"


def test_interrupted_scan_keeps_committed_chunks_and_resumes(
    db, connected, stub_gmail, monkeypatch
):
    monkeypatch.setattr(gmail_api, "_CHUNK", 1)
    original = gmail_api.classify_emails
    calls = 0

    def interrupt_second_chunk(emails, llm_budget):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated interruption")
        return original(emails, llm_budget=llm_budget)

    monkeypatch.setattr(gmail_api, "classify_emails", interrupt_second_chunk)
    stub_gmail([_newsletter(2), _newsletter(1)])

    with pytest.raises(RuntimeError, match="simulated interruption"):
        sync(db, connected)

    assert db.query(ProcessedMessage).count() == 1
    assert db.query(ApplicationSync).one().last_synced_at is None

    monkeypatch.setattr(gmail_api, "classify_emails", original)
    result = sync(db, connected)

    assert result["not_application"] == 1
    assert db.query(ProcessedMessage).count() == 2
    assert db.query(ApplicationSync).one().last_synced_at is not None


def test_duplicate_run_does_not_duplicate_side_effects(
    db, connected, stub_gmail
):
    confirmation = message(
        "m1",
        "t1",
        "Acme Careers <no-reply@acme.com>",
        "Thank you for applying to Acme",
        CONFIRMATION,
        datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    rejection = message(
        "m2",
        "t2",
        "Acme Careers <no-reply@acme.com>",
        "Update on your application",
        REJECTION,
        datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    stub_gmail([rejection, confirmation])

    sync(db, connected)
    sync(db, connected)

    assert db.query(ProcessedMessage).count() == 2
    assert db.query(Application).count() == 1
    assert db.query(RecruiterResponse).count() == 1
