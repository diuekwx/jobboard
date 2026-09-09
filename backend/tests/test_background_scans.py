from datetime import datetime, timedelta, timezone
import uuid

from backend.api import gmail as gmail_api
from backend.models.db_application import Application
from backend.models.db_scanjob import ScanJob
from backend.models.db_users import User
from backend.service.scan_job_service import (
    claim_next_scan_job,
    complete_scan_job,
    create_scan_job,
    process_claimed_scan_job,
    recover_expired_jobs,
    requeue_scan_job,
)
from backend.tests.gmail_stub import message
from backend.tests.test_sync_rejection_flow import CONFIRMATION


def test_only_one_active_scan_is_created_per_user(db, user_id):
    first, created = create_scan_job(db, user_id)
    duplicate, duplicate_created = create_scan_job(db, user_id)

    assert created is True
    assert duplicate_created is False
    assert duplicate.id == first.id
    assert db.query(ScanJob).count() == 1

    claimed = claim_next_scan_job(db, "worker-1")
    complete_scan_job(db, claimed, "done")
    next_job, next_created = create_scan_job(db, user_id)

    assert next_created is True
    assert next_job.id != first.id
    assert db.query(ScanJob).count() == 2


def test_expired_worker_lease_requeues_a_job(db, user_id):
    job, _ = create_scan_job(db, user_id)
    claimed = claim_next_scan_job(db, "dead-worker")
    claimed.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    assert recover_expired_jobs(db) == 1
    db.refresh(job)
    assert job.status == "queued"
    assert job.active_slot == 1
    assert job.lease_owner is None

    resumed = claim_next_scan_job(db, "replacement-worker")
    assert resumed.id == job.id
    assert resumed.started_at is not None


def test_worker_updates_progress_and_completes_durable_scan(
    db, connected, stub_gmail
):
    stub_gmail([
        message(
            "m1",
            "t1",
            "Acme Careers <no-reply@acme.com>",
            "Thank you for applying to Acme",
            CONFIRMATION,
            datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
    ])
    job, _ = create_scan_job(db, connected)
    claimed = claim_next_scan_job(db, "worker-1")

    result = process_claimed_scan_job(db, claimed)

    db.refresh(job)
    assert len(result["created"]) == 1
    assert db.query(Application).count() == 1
    assert job.status == "completed"
    assert job.phase == "completed"
    assert job.active_slot is None
    assert job.discovered_count == 1
    assert job.fetched_count == 1
    assert job.classified_count == 1
    assert job.applied_count == 1
    assert job.finished_at is not None


def test_bounded_slice_requeues_and_resumes_same_job(
    db, connected, stub_gmail, monkeypatch
):
    monkeypatch.setattr(gmail_api, "MAX_MESSAGES_PER_SYNC", 1)
    stub_gmail([
        message(
            f"m{number}", f"t{number}", "News <news@example.com>",
            f"Newsletter {number}", "A general company newsletter.",
            datetime(2026, 2, number, tzinfo=timezone.utc),
        )
        for number in (2, 1)
    ])
    job, _ = create_scan_job(db, connected)

    first = claim_next_scan_job(db, "worker-1")
    process_claimed_scan_job(db, first)
    db.refresh(job)
    assert job.status == "queued"
    assert job.applied_count == 1
    assert job.discovered_count == 1

    second = claim_next_scan_job(db, "worker-1")
    process_claimed_scan_job(db, second)
    db.refresh(job)
    assert job.status == "completed"
    assert job.applied_count == 2
    assert job.discovered_count == 2


def test_requeued_slice_yields_to_another_user(db, user_id):
    first, _ = create_scan_job(db, user_id)
    other = User(id=uuid.uuid4(), email="second@example.com")
    db.add(other)
    db.commit()
    second, _ = create_scan_job(db, other.id)

    claimed = claim_next_scan_job(db, "worker-1")
    assert claimed.id == first.id
    requeue_scan_job(db, claimed, "more remains")

    next_claimed = claim_next_scan_job(db, "worker-1")
    assert next_claimed.id == second.id
