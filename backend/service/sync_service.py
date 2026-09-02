import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.models.db_applicationsync import ApplicationSync

# How far before the last watermark to re-scan, so e-mails on the boundary are
# never missed. Safe to overlap because ProcessedMessage dedups on message id.
LOOKBACK_DAYS = int(os.getenv("GMAIL_LOOKBACK_DAYS", "2"))
# Where to start scanning for a user who has never set a start date.
DEFAULT_START_DAYS = int(os.getenv("GMAIL_DEFAULT_START_DAYS", "90"))


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def sync(db: Session, user_id: uuid.UUID, day: datetime):
    """Set (or move) the user's scan start date."""
    now = datetime.now(timezone.utc)
    row = db.query(ApplicationSync).filter(ApplicationSync.user_id == user_id).first()

    if row:
        if row.start_date != day:
            row.start_date = day
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return row

    row = ApplicationSync(
        user_id=user_id,
        start_date=day,
        last_synced_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_or_create_sync(db: Session, user_id: uuid.UUID) -> ApplicationSync:
    row = db.query(ApplicationSync).filter(ApplicationSync.user_id == user_id).first()
    if row:
        return row

    now = datetime.now(timezone.utc)
    row = ApplicationSync(
        user_id=user_id,
        start_date=now - timedelta(days=DEFAULT_START_DAYS),
        last_synced_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def search_after_datetime(row: ApplicationSync) -> datetime:
    """The point to pass to Gmail's ``after:`` — watermark minus the lookback overlap."""
    base = row.last_synced_at or row.start_date
    return _aware(base) - timedelta(days=LOOKBACK_DAYS)


def mark_synced(db: Session, user_id: uuid.UUID) -> None:
    row = db.query(ApplicationSync).filter(ApplicationSync.user_id == user_id).first()
    if row:
        row.last_synced_at = datetime.now(timezone.utc)
        db.commit()


def get_start_date(db: Session, user_id: uuid.UUID):
    row = db.query(ApplicationSync).filter(ApplicationSync.user_id == user_id).first()
    return row.start_date if row else None


def get_last_updated(db: Session, user_id: uuid.UUID):
    return db.query(ApplicationSync).filter(ApplicationSync.user_id == user_id).first()
