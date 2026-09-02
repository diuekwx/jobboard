import re
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.models.db_application import Application
from backend.models.db_response import RecruiterResponse
from backend.models.schema import EditApplication, ApplicationCreate

REJECTED_STATUS = "rejected"
# Statuses that still count as live when deciding which application a rejection
# refers to. "sent" comes from the e-mail sync, "applied" from a manual entry.
OPEN_STATUSES = ("sent", "applied", "process", "interview", "offer")


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


# --- rejections -------------------------------------------------------------

_LEGAL_SUFFIXES = re.compile(
    r"\b(?:inc|llc|l\.?l\.?c|ltd|limited|corp|corporation|co|company|gmbh|plc|"
    r"s\.?a|a\.?g|ab|bv|nv|oy|pty|group|holdings?|technologies|technology|labs?|"
    r"software|solutions|the)\b",
    re.I,
)


def normalize_company(name: str | None) -> str:
    """Fold a company name to a comparison key: ``"Acme Corp., Inc."`` -> ``"acme"``.

    Rejections rarely arrive in the confirmation's thread, so the company name
    is the join key - and the two e-mails seldom spell it identically.
    """
    if not name:
        return ""
    base = re.sub(r"[^a-z0-9 ]+", " ", name.lower())
    stripped = re.sub(r"\s+", "", _LEGAL_SUFFIXES.sub(" ", base))
    # a name made entirely of stop-words (e.g. "The Co") keeps its raw form
    return stripped or re.sub(r"\s+", "", base)


def _norm_role(role: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (role or "").lower())


def _date_key(value) -> date:
    """``application_date`` is a Date column but holds a datetime until the row
    round-trips through the database, so normalise before comparing."""
    if isinstance(value, datetime):
        return value.date()
    return value or date.min


def _roles_match(a: str | None, b: str | None) -> bool:
    x, y = _norm_role(a), _norm_role(b)
    if not x or not y:
        return False
    return x == y or x in y or y in x


def find_application_for_rejection(
    db: Session,
    user_id: uuid.UUID,
    *,
    thread_id: str | None,
    company: str | None,
    role: str | None,
) -> Application | None:
    """Best guess at which application a rejection e-mail is about.

    Thread id first (exact, when the decline lands in the confirmation's
    thread), then company name, preferring a still-open application and, among
    those, one whose role lines up and whose application date is most recent.
    Returns ``None`` when nothing plausible matches.
    """
    threaded = get_application_by_thread(db, user_id, thread_id)
    if threaded:
        return threaded

    key = normalize_company(company)
    if not key:
        return None

    candidates = [
        app for app in db.query(Application).filter(Application.user_id == user_id)
        if normalize_company(app.company_name) == key
    ]
    if not candidates:
        return None

    def rank(app: Application):
        return (
            app.status in OPEN_STATUSES,           # open beats already-closed
            _roles_match(role, app.position),      # same role beats a different one
            _date_key(app.application_date),
        )

    return max(candidates, key=rank)


def mark_application_rejected(
    db: Session,
    app: Application,
    *,
    sender: str,
    subject: str,
    body: str | None,
    received_at: datetime,
) -> bool:
    """Record the decline against ``app`` and move it to ``rejected``.

    Returns whether the status actually changed - a second decline on an
    application that is already rejected is still filed as a response, but is
    not reported as a new rejection. Caller owns the commit.
    """
    db.add(RecruiterResponse(
        application_id=app.id,
        sender_email=(sender or "")[:255],
        subject=(subject or "")[:255],
        body=body or None,
        received_at=received_at,
    ))

    if app.status == REJECTED_STATUS:
        return False

    app.status = REJECTED_STATUS
    app.updated_at = datetime.now(timezone.utc)
    db.flush()
    return True


def rejected_at_map(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, datetime]:
    """``{application_id: most recent recruiter-response timestamp}`` for one user."""
    rows = (
        db.query(RecruiterResponse.application_id, func.max(RecruiterResponse.received_at))
        .join(Application, Application.id == RecruiterResponse.application_id)
        .filter(Application.user_id == user_id)
        .group_by(RecruiterResponse.application_id)
        .all()
    )
    return {app_id: received for app_id, received in rows}


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
    responded = rejected_at_map(db, user_id)
    out = []
    for job in jobs:
        replied_at = responded.get(job.id)
        out.append({
            "id": str(job.id),
            "company": job.company_name,
            "role": job.position,
            "date": job.application_date.isoformat() if job.application_date else None,
            "status": job.status,
            "source": job.source,
            "needs_review": job.needs_review,
            "rejected_at": (
                replied_at.isoformat()
                if replied_at and job.status == REJECTED_STATUS else None
            ),
            "permalink": (
                f"https://mail.google.com/mail/u/0/#all/{job.gmail_message_id}"
                if job.gmail_message_id else None
            ),
        })
    return out
