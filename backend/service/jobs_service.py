import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.models.db_application import Application
from backend.models.schema import EditApplication, ApplicationCreate


def create_job_service(db: Session, user_id: uuid.UUID, data: ApplicationCreate):
    existing_job = db.query(Application).filter(
        Application.company_name == data.company,
        Application.position == data.position,
        Application.user_id == user_id,
    ).first()
    if existing_job:
        raise HTTPException(status_code=400, detail="Job already added")

    new_job = Application(
        user_id=user_id,
        company_name=data.company,
        position=data.position,
        status=data.status,
        application_date=data.time or datetime.now(timezone.utc),
        source="manual",
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job


def get_application_by_thread(db: Session, user_id: uuid.UUID, thread_id: str | None):
    if not thread_id:
        return None
    return db.query(Application).filter(
        Application.user_id == user_id,
        Application.gmail_thread_id == thread_id,
    ).first()


def create_email_application(
    db: Session,
    user_id: uuid.UUID,
    *,
    company: str | None,
    role: str | None,
    status: str,
    application_date: datetime,
    gmail_message_id: str,
    gmail_thread_id: str | None,
    needs_review: bool,
) -> Application:
    """Insert an application discovered from e-mail. Caller owns the commit.

    Never raises on a duplicate company — de-duplication is the caller's job
    (via :func:`get_application_by_thread` and the ProcessedMessage ledger).
    """
    job = Application(
        user_id=user_id,
        company_name=company or "Company Name Not Found",
        position=role,
        status=status,
        application_date=application_date,
        source="email",
        gmail_message_id=gmail_message_id,
        gmail_thread_id=gmail_thread_id,
        needs_review=needs_review,
    )
    db.add(job)
    db.flush()  # populate job.id without ending the transaction
    return job


def find_job(db: Session, user_id: uuid.UUID, company: str, position: str):
    job = db.query(Application).filter(
        Application.company_name == company,
        Application.position == position,
        Application.user_id == user_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Application not found")
    return job.id


def update_job_application(db: Session, app_id: uuid.UUID, data: EditApplication, user_id: uuid.UUID):
    app = db.query(Application).filter(
        Application.id == app_id, Application.user_id == user_id
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    updates = data.model_dump(exclude_unset=True)
    if "company" in updates:  # schema field -> column name
        updates["company_name"] = updates.pop("company")
    for key, value in updates.items():
        if hasattr(app, key):
            setattr(app, key, value)

    db.commit()
    db.refresh(app)
    return app


def list_jobs(db: Session, user_id: uuid.UUID):
    jobs = db.query(Application).filter(Application.user_id == user_id).all()
    out = []
    for job in jobs:
        out.append({
            "id": str(job.id),
            "company": job.company_name,
            "role": job.position,
            "date": job.application_date.isoformat() if job.application_date else None,
            "status": job.status,
            "source": job.source,
            "needs_review": job.needs_review,
            "permalink": (
                f"https://mail.google.com/mail/u/0/#all/{job.gmail_message_id}"
                if job.gmail_message_id else None
            ),
        })
    return out
