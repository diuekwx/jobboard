from sqlalchemy.orm import Session
from backend.models.db_applicationsync import ApplicationSync
from datetime import datetime, timezone
from backend.models.db_users import User
import uuid

#change to user_id
def sync(db: Session, user_id: uuid, day: datetime):
    dt_utc = datetime.now(timezone.utc)

    row_to_update = db.query(ApplicationSync).filter(ApplicationSync.user_id == user_id).first()

    # will have to check if any new start_day is after the last_synced_at

    if row_to_update:
        if row_to_update.start_date != day:
            row_to_update.start_date = day
        
        # row_to_update.last_synced_at = dt_utc
        row_to_update.updated_at = dt_utc

        db.commit()
        db.refresh(row_to_update)

        return row_to_update

    else:
        new_sync = ApplicationSync(
            user_id=user_id,
            start_date=day,
            last_synced_at=dt_utc,
            created_at=dt_utc,
            updated_at=dt_utc
        )
        db.add(new_sync)
        db.commit()
        db.refresh(new_sync)

        return new_sync

def get_last_updated(db: Session, user_id: uuid):
    find = db.query(ApplicationSync).filter(ApplicationSync.user_id == user_id).first()
    if find:
        print("found")
        return find
    return None
    
def update_sync_after_fetch(db: Session, user_id: uuid):
    row_to_update = db.query(ApplicationSync).filter(ApplicationSync.user_id == user_id).first()
    row_to_update.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row_to_update)