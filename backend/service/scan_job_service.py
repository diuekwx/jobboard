import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.db_scanjob import ScanJob


LEASE_SECONDS = max(30, int(os.getenv("GMAIL_SCAN_LEASE_SECONDS", "120")))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def serialize_scan_job(job: ScanJob) -> dict:
    return {
        "id": str(job.id),
        "status": job.status,
        "phase": job.phase,
        "progress": {
            "discovered": job.discovered_count,
            "fetched": job.fetched_count,
            "classified": job.classified_count,
            "applied": job.applied_count,
            "deferred": job.deferred_count,
            "failed": job.failed_count,
        },
        "message": job.message,
        "error": job.error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "updated_at": job.updated_at,
    }


def active_scan_job(db: Session, user_id: uuid.UUID) -> ScanJob | None:
    return (
        db.query(ScanJob)
        .filter(ScanJob.user_id == user_id, ScanJob.active_slot == 1)
        .order_by(ScanJob.created_at)
        .first()
    )


def create_scan_job(db: Session, user_id: uuid.UUID) -> tuple[ScanJob, bool]:
    existing = active_scan_job(db, user_id)
    if existing:
        return existing, False

    job = ScanJob(user_id=user_id, status="queued", phase="queued", active_slot=1)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        # A simultaneous POST won the unique active-slot race.
        db.rollback()
        existing = active_scan_job(db, user_id)
        if existing:
            return existing, False
        raise
    db.refresh(job)
    return job, True


def latest_scan_job(db: Session, user_id: uuid.UUID) -> ScanJob | None:
    return (
        db.query(ScanJob)
        .filter(ScanJob.user_id == user_id)
        .order_by(ScanJob.created_at.desc())
        .first()
    )


def get_user_scan_job(
    db: Session, user_id: uuid.UUID, job_id: uuid.UUID
) -> ScanJob | None:
    return db.query(ScanJob).filter(
        ScanJob.id == job_id, ScanJob.user_id == user_id
    ).first()


def recover_expired_jobs(db: Session) -> int:
    now = _now()
    expired = db.query(ScanJob).filter(
        ScanJob.status == "running",
        ScanJob.lease_expires_at.is_not(None),
        ScanJob.lease_expires_at < now,
    ).all()
    for job in expired:
        job.status = "queued"
        job.phase = "queued"
        job.lease_owner = None
        job.lease_expires_at = None
        job.message = "Worker restarted; resuming completed progress."
    if expired:
        db.commit()
    return len(expired)


def claim_next_scan_job(db: Session, worker_id: str) -> ScanJob | None:
    recover_expired_jobs(db)
    # ``updated_at`` changes whenever a bounded slice is requeued. Ordering by
    # it lets other users already waiting take a turn before this job resumes.
    query = db.query(ScanJob).filter(ScanJob.status == "queued").order_by(
        ScanJob.updated_at, ScanJob.created_at, ScanJob.id
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    job = query.first()
    if not job:
        return None

    now = _now()
    job.status = "running"
    job.phase = "discovering"
    job.started_at = job.started_at or now
    job.lease_owner = worker_id
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    job.message = "Discovering Gmail messages."
    db.commit()
    db.refresh(job)
    return job


def renew_scan_lease(job: ScanJob) -> None:
    job.lease_expires_at = _now() + timedelta(seconds=LEASE_SECONDS)


def complete_scan_job(db: Session, job: ScanJob, message: str) -> None:
    job.status = "completed"
    job.phase = "completed"
    job.active_slot = None
    job.message = message
    job.error = None
    job.lease_owner = None
    job.lease_expires_at = None
    job.finished_at = _now()
    db.commit()


def requeue_scan_job(db: Session, job: ScanJob, message: str) -> None:
    job.status = "queued"
    job.phase = "queued"
    job.message = message
    job.lease_owner = None
    job.lease_expires_at = None
    db.commit()


def fail_scan_job(
    db: Session,
    job: ScanJob,
    exc: Exception | None = None,
    *,
    message: str | None = None,
    error_code: str | None = None,
) -> None:
    job.status = "failed"
    job.phase = "failed"
    job.active_slot = None
    job.message = message or "The scan failed. Start another scan to retry pending messages."
    job.error = error_code or (f"{type(exc).__name__}: scan failed" if exc else "scan failed")
    job.lease_owner = None
    job.lease_expires_at = None
    job.finished_at = _now()
    db.commit()


def process_claimed_scan_job(db: Session, job: ScanJob) -> dict:
    # Imported lazily to keep HTTP router import order independent of workers.
    from backend.api.gmail import run_gmail_scan

    try:
        result = run_gmail_scan(db, job.user_id, scan_job=job)
        if result.get("error"):
            fail_scan_job(
                db,
                job,
                message=result.get("message"),
                error_code=result.get("error"),
            )
        elif not result.get("scan_complete", True):
            requeue_scan_job(
                db,
                job,
                "A bounded scan slice completed; queued for the remaining messages.",
            )
        else:
            complete_scan_job(db, job, result.get("message") or "Scan completed.")
        return result
    except Exception as exc:
        db.rollback()
        current = db.get(ScanJob, job.id)
        if current is not None:
            fail_scan_job(db, current, exc)
        raise
