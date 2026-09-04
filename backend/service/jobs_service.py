import re
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.models.db_application import Application
from backend.models.db_event import Event
from backend.models.db_response import RecruiterResponse
from backend.models.schema import EditApplication, ApplicationCreate

REJECTED_STATUS = "rejected"
ASSESSMENT_STATUS = "assessment"
INTERVIEW_STATUS = "interview"

# How far along an application is. A later e-mail may only ever push a status
# up this ladder: recruiters send reminders and calendar updates out of order,
# and a stray assessment reminder must not drag a candidate who has already
# reached the interview stage back down.
STAGE_RANK = {
    "sent": 0,
    "applied": 0,
    "process": 1,
    ASSESSMENT_STATUS: 2,
    INTERVIEW_STATUS: 3,
    "offer": 4,
}

# Statuses that still count as live when deciding which application an e-mail
# refers to. "sent" comes from the e-mail sync, "applied" from a manual entry.
OPEN_STATUSES = tuple(STAGE_RANK)

# The stage an application lands in when a next-step e-mail arrives, keyed by
# the classifier's kind (which is deliberately the same string as the status).
STAGE_STATUSES = (ASSESSMENT_STATUS, INTERVIEW_STATUS)


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


def find_application_for_email(
    db: Session,
    user_id: uuid.UUID,
    *,
    thread_id: str | None,
    company: str | None,
    role: str | None,
    open_only: bool = False,
) -> Application | None:
    """Best guess at which application a follow-up e-mail is about.

    Thread id first (exact, when the mail lands in the confirmation's thread),
    then company name, preferring a still-open application and, among those,
    one whose role lines up and whose application date is most recent.
    Returns ``None`` when nothing plausible matches.

    ``open_only`` refuses a closed application. A decline is happy to land on
    one - filing a second rejection against it is harmless - but an interview
    invite that only matches a rejected row is almost always a fresh
    requisition at the same company, and resurrecting the old row would erase
    a real outcome.
    """
    threaded = get_application_by_thread(db, user_id, thread_id)
    if threaded and not (open_only and threaded.status not in OPEN_STATUSES):
        return threaded

    key = normalize_company(company)
    if not key:
        return None

    candidates = [
        app for app in db.query(Application).filter(Application.user_id == user_id)
        if normalize_company(app.company_name) == key
        and not (open_only and app.status not in OPEN_STATUSES)
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


# Kept for callers that only ever deal with declines.
find_application_for_rejection = find_application_for_email


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


# --- next stage: assessments and interviews ---------------------------------


def _stage_rank(status: str | None) -> int:
    return STAGE_RANK.get((status or "").lower(), -1)


def event_title(stage: str, app: Application) -> str:
    """Short label for the calendar row, e.g. ``"Interview - Acme"``."""
    what = "Interview" if stage == INTERVIEW_STATUS else "Assessment due"
    subject = app.position or app.company_name or ""
    return f"{what} - {subject}".strip(" -")[:100]


def upsert_event(
    db: Session,
    app: Application,
    *,
    event_type: str,
    title: str,
    start_time: datetime,
    end_time: datetime | None,
    source_message_id: str | None,
) -> Event:
    """Record (or correct) the dated thing this application is waiting on.

    Matched on the e-mail it came from, so a re-sync of the same message - or a
    reschedule sent in the same thread - moves the existing row rather than
    leaving two slots on the board. Caller owns the commit.
    """
    query = db.query(Event).filter(Event.application_id == app.id)
    existing = (
        query.filter(Event.source_message_id == source_message_id).first()
        if source_message_id
        else query.filter(
            Event.event_type == event_type, Event.start_time == start_time
        ).first()
    )

    if existing:
        existing.title = title
        existing.start_time = start_time
        existing.end_time = end_time
        return existing

    event = Event(
        application_id=app.id,
        event_type=event_type,
        title=title,
        start_time=start_time,
        end_time=end_time,
        source_message_id=source_message_id,
    )
    db.add(event)
    db.flush()
    return event


def advance_application(
    db: Session,
    app: Application,
    *,
    stage: str,
    sender: str,
    subject: str,
    body: str | None,
    received_at: datetime,
    when: datetime | None = None,
    duration: timedelta | None = None,
    source_message_id: str | None = None,
) -> bool:
    """Move ``app`` into ``stage`` ("assessment" or "interview") and file the mail.

    Returns whether the status actually moved. The mail is always kept as a
    recruiter response, and a dated event is recorded whenever the e-mail named
    a time - both happen even when the status stands still, so a reminder for an
    interview that was already logged can still correct the slot. Never moves a
    rejected application, and never steps backwards down :data:`STAGE_RANK`.
    Caller owns the commit.
    """
    if stage not in STAGE_STATUSES:
        raise ValueError(f"unknown stage {stage!r}")

    db.add(RecruiterResponse(
        application_id=app.id,
        sender_email=(sender or "")[:255],
        subject=(subject or "")[:255],
        body=body or None,
        received_at=received_at,
    ))

    if when is not None:
        upsert_event(
            db, app,
            event_type=stage,
            title=event_title(stage, app),
            start_time=when,
            end_time=(when + duration) if duration else None,
            source_message_id=source_message_id,
        )

    if app.status == REJECTED_STATUS or _stage_rank(stage) <= _stage_rank(app.status):
        return False

    app.status = stage
    app.updated_at = datetime.now(timezone.utc)
    db.flush()
    return True


def events_map(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, list[Event]]:
    """``{application_id: events, soonest first}`` for one user."""
    rows = (
        db.query(Event)
        .join(Application, Application.id == Event.application_id)
        .filter(Application.user_id == user_id)
        .order_by(Event.start_time)
        .all()
    )
    out: dict[uuid.UUID, list[Event]] = {}
    for event in rows:
        out.setdefault(event.application_id, []).append(event)
    return out


def _next_event(events: list[Event], now: datetime) -> dict | None:
    """The soonest event still ahead; failing that, the most recent past one.

    A slot that has already passed is still worth showing - it is why the
    application is sitting in "In Process" - so it is returned flagged rather
    than dropped.
    """
    if not events:
        return None
    upcoming = [e for e in events if _aware(e.start_time) >= now]
    event = upcoming[0] if upcoming else events[-1]
    return {
        "type": event.event_type,
        "title": event.title,
        "at": event.start_time.isoformat() if event.start_time else None,
        "ends_at": event.end_time.isoformat() if event.end_time else None,
        "past": not upcoming,
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


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
    events = events_map(db, user_id)
    now = datetime.now(timezone.utc)
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
            "next_event": _next_event(events.get(job.id, []), now),
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
