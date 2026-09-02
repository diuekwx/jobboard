import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError

from backend.core.dependencies import get_db, get_current_user
from backend.models.db_integrationtokens import IntegrationToken
from backend.models.db_processedmessage import ProcessedMessage
from backend.models.db_users import User
from backend.service.classification_service import classify_email
from backend.service.gmail_service import build_query, extract_body_text, get_header
from backend.service.jobs_service import (
    create_email_application,
    get_application_by_thread,
    list_jobs,
)
from backend.service.oauth_service import refresh_google_token
from backend.service.sync_service import get_or_create_sync, mark_synced, search_after_datetime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["gmail"])

MAX_MESSAGES_PER_SYNC = int(os.getenv("GMAIL_MAX_MESSAGES", "200"))


def _build_gmail(token: IntegrationToken):
    scopes = (os.getenv("SCOPES") or "").split() or None
    creds = Credentials(
        token=token.access_token,
        refresh_token=token.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=scopes,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _list_candidate_ids(service, query: str) -> list[str]:
    ids: list[str] = []
    page_token = None
    while len(ids) < MAX_MESSAGES_PER_SYNC:
        resp = service.users().messages().list(
            userId="me",
            q=query,
            pageToken=page_token,
            maxResults=min(100, MAX_MESSAGES_PER_SYNC - len(ids)),
        ).execute()
        ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


@router.get("/fetch-applications")
def fetch_job_applications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sync_row = get_or_create_sync(db, current_user.id)
    after_epoch = int(search_after_datetime(sync_row).timestamp())

    token = db.query(IntegrationToken).filter(
        IntegrationToken.user_id == current_user.id,
        IntegrationToken.provider == "gmail",
    ).first()
    if not token:
        return {"error": "gmail_not_connected", "message": "Gmail is not connected."}

    try:
        token = refresh_google_token(db, token)
    except RefreshError:
        logger.warning("Gmail token refresh failed for user %s", current_user.id)
        return {
            "error": "reconnect_gmail",
            "message": "Gmail authorization expired — please reconnect your account.",
        }

    service = _build_gmail(token)
    candidate_ids = _list_candidate_ids(service, build_query(after_epoch))

    summary = {"created": [], "needs_review": 0, "skipped": 0, "not_application": 0}

    if not candidate_ids:
        mark_synced(db, current_user.id)
        return {"message": "No new job application emails found.", "applications": list_jobs(db, current_user.id), **summary}

    already = {
        mid for (mid,) in db.query(ProcessedMessage.gmail_message_id).filter(
            ProcessedMessage.user_id == current_user.id,
            ProcessedMessage.gmail_message_id.in_(candidate_ids),
        )
    }
    to_process = [mid for mid in candidate_ids if mid not in already]

    for mid in to_process:
        try:
            full = service.users().messages().get(userId="me", id=mid, format="full").execute()
        except Exception:
            logger.exception("failed to fetch Gmail message %s", mid)
            continue

        payload = full.get("payload", {}) or {}
        headers = payload.get("headers", []) or []
        from_header = get_header(headers, "From")
        subject = get_header(headers, "Subject")
        thread_id = full.get("threadId")
        body = extract_body_text(payload)

        try:
            received = datetime.fromtimestamp(int(full["internalDate"]) / 1000, tz=timezone.utc)
        except (KeyError, TypeError, ValueError):
            received = datetime.now(timezone.utc)

        decision = classify_email(from_header, subject, body)

        ledger = ProcessedMessage(
            user_id=current_user.id,
            gmail_message_id=mid,
            gmail_thread_id=thread_id,
        )

        if not decision.is_application:
            ledger.outcome = "not_application"
            ledger.detail = f"{decision.method}: {subject[:180]}"
            db.add(ledger)
            summary["not_application"] += 1
            continue

        existing = get_application_by_thread(db, current_user.id, thread_id)
        if existing:
            ledger.outcome = "duplicate_thread"
            ledger.application_id = existing.id
            ledger.detail = decision.method
            db.add(ledger)
            summary["skipped"] += 1
            continue

        app = create_email_application(
            db,
            current_user.id,
            company=decision.company,
            role=decision.role,
            status="sent",
            application_date=received,
            gmail_message_id=mid,
            gmail_thread_id=thread_id,
            needs_review=decision.needs_review,
        )
        ledger.application_id = app.id
        ledger.outcome = "needs_review" if decision.needs_review else "created"
        ledger.detail = decision.method
        db.add(ledger)

        summary["created"].append({
            "id": str(app.id),
            "company": app.company_name,
            "role": app.position,
            "date": received.isoformat(),
            "needs_review": decision.needs_review,
            "method": decision.method,
        })
        if decision.needs_review:
            summary["needs_review"] += 1

    sync_row.last_synced_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": (
            f"Scanned {len(candidate_ids)} email(s), {len(to_process)} new — "
            f"added {len(summary['created'])}."
        ),
        "applications": list_jobs(db, current_user.id),
        **summary,
    }
