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
from backend.service.classification_service import (
    ADVANCING_KINDS,
    KIND_CONFIRMATION,
    KIND_REJECTION,
    EmailInput,
    classify_emails,
)
from backend.service.gmail_service import build_query, extract_body_text, get_header
from backend.service.jobs_service import (
    advance_application,
    create_email_application,
    get_application_by_thread,
    list_jobs,
    mark_application_rejected,
    match_application_for_email,
)
from backend.service.oauth_service import refresh_google_token
from backend.security.encryption import blind_index
from backend.service.sync_service import get_or_create_sync, mark_synced, search_after_datetime

logger = logging.getLogger(__name__)
router = APIRouter(tags=["gmail"])

MAX_MESSAGES_PER_SYNC = int(os.getenv("GMAIL_MAX_MESSAGES", "200"))
# Cap LLM classification calls per sync so one big run can't blow the provider's
# rate limit. Overflow is deferred (nothing persisted) and picked up next sync.
LLM_BUDGET_PER_SYNC = int(os.getenv("GMAIL_LLM_BUDGET_PER_SYNC", "40"))
# Messages processed + committed per checkpoint (keep it a multiple of the
# classifier batch size so each chunk maps to one LLM request).
_CHUNK = int(os.getenv("GMAIL_SYNC_CHUNK", "10"))
# A rejection for a company with no tracked application usually means the
# application predates the scan window. Recording it (flagged for review) is
# more useful than dropping it; set to 0 to only ever update existing rows.
CREATE_FROM_REJECTION = os.getenv("GMAIL_CREATE_APP_FROM_REJECTION", "1") not in (
    "", "0", "false", "False",
)
# Same reasoning for an assessment or interview invite with nothing tracked
# behind it: the invite proves an application exists, so stand a row up for it
# already at that stage rather than losing a live opportunity off the board.
CREATE_FROM_ADVANCE = os.getenv("GMAIL_CREATE_APP_FROM_ADVANCE", "1") not in (
    "", "0", "false", "False",
)


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


def _list_candidate_ids(
    service,
    query: str,
    db: Session,
    user_id,
) -> tuple[list[str], bool]:
    ids: list[str] = []
    seen: set[str] = set()
    page_token = None
    while True:
        resp = service.users().messages().list(
            userId="me",
            q=query,
            pageToken=page_token,
            maxResults=100,
        ).execute()
        page_ids = [
            message["id"]
            for message in resp.get("messages", [])
            if message.get("id") and message["id"] not in seen
        ]
        seen.update(page_ids)

        lookups = {
            blind_index(mid, context="processed_messages.gmail_message_id"): mid
            for mid in page_ids
        }
        processed = {
            value
            for (value,) in db.query(ProcessedMessage.gmail_message_lookup).filter(
                ProcessedMessage.user_id == user_id,
                ProcessedMessage.gmail_message_lookup.in_(lookups),
            )
        } if lookups else set()

        for lookup, mid in lookups.items():
            if lookup in processed:
                continue
            ids.append(mid)
            if len(ids) == MAX_MESSAGES_PER_SYNC:
                page_token = resp.get("nextPageToken")
                page_complete = mid == page_ids[-1]
                return ids, page_complete and not page_token

        page_token = resp.get("nextPageToken")
        if not page_token:
            return ids, True


@router.get("/fetch-applications")
def fetch_job_applications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sync_row = get_or_create_sync(db, current_user.id)
    checkpoint_at = datetime.now(timezone.utc)
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
    candidate_ids, scan_complete = _list_candidate_ids(
        service,
        build_query(after_epoch),
        db,
        current_user.id,
    )

    summary = {"created": [], "rejected": [], "advanced": [], "needs_review": 0,
               "skipped": 0, "not_application": 0, "unmatched_rejections": 0,
               "unmatched_advances": 0, "ambiguous_matches": 0,
               "deferred": 0, "failed": 0}
    classification = {
        "mode": "rules_only" if LLM_BUDGET_PER_SYNC <= 0 else "llm_fallback",
        "pending_by_reason": {
            "budget": 0,
            "model_unavailable": 0,
            "invalid_model_output": 0,
        },
        "metrics": {
            "attempted_requests": 0,
            "attempted_emails": 0,
            "retries": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "elapsed_ms": 0,
            "request_failures": 0,
            "invalid_responses": 0,
        },
    }

    if not candidate_ids:
        if scan_complete:
            mark_synced(db, current_user.id, checkpoint_at)
        return {"message": "No new job application emails found.", "applications": list_jobs(db, current_user.id), "classification": classification, **summary}

    # --- phase 1: fetch + extract every candidate message ---
    records = []  # (mid, from, subject, thread_id, body, received)
    for mid in candidate_ids:
        try:
            full = service.users().messages().get(userId="me", id=mid, format="full").execute()
        except Exception:
            logger.exception("failed to fetch a Gmail message")
            summary["failed"] += 1
            continue

        payload = full.get("payload", {}) or {}
        headers = payload.get("headers", []) or []
        try:
            received = datetime.fromtimestamp(int(full["internalDate"]) / 1000, tz=timezone.utc)
        except (KeyError, TypeError, ValueError):
            received = datetime.now(timezone.utc)

        records.append((
            mid,
            get_header(headers, "From"),
            get_header(headers, "Subject"),
            full.get("threadId"),
            extract_body_text(payload),
            received,
        ))

    records.sort(key=lambda record: (record[5], record[0]))

    # --- phase 2+3: classify and apply in chunks, committing progress per chunk ---
    # so an interrupted/timed-out sync keeps what it finished and never re-sends
    # those emails to the LLM.
    llm_used = 0
    for start in range(0, len(records), _CHUNK):
        chunk = records[start:start + _CHUNK]
        decisions = classify_emails(
            [EmailInput(mid, frm, subj, body, rec) for (mid, frm, subj, _t, body, rec) in chunk],
            use_llm=LLM_BUDGET_PER_SYNC > 0,
            llm_budget=max(0, LLM_BUDGET_PER_SYNC - llm_used),
        )
        run_metrics = getattr(decisions, "metrics", None)
        if run_metrics is not None:
            values = run_metrics.as_dict()
            for name, value in values.items():
                classification["metrics"][name] += value
            llm_used += values["attempted_emails"]
            classification["mode"] = getattr(decisions, "mode", classification["mode"])

        for mid, from_header, subject, thread_id, body, received in chunk:
            decision = decisions[mid]

            # over this run's LLM budget - persist nothing, reclassify next sync
            if decision.method == "deferred":
                summary["deferred"] += 1
                reason = getattr(decision, "pending_reason", None)
                if reason in classification["pending_by_reason"]:
                    classification["pending_by_reason"][reason] += 1
                continue

            ledger = ProcessedMessage(
                user_id=current_user.id,
                gmail_message_id=mid,
                gmail_thread_id=thread_id,
                gmail_message_lookup=blind_index(
                    mid, context="processed_messages.gmail_message_id"
                ),
                gmail_thread_lookup=blind_index(
                    thread_id, context="processed_messages.gmail_thread_id"
                ),
            )

            if decision.kind not in (KIND_CONFIRMATION, KIND_REJECTION, *ADVANCING_KINDS):
                ledger.outcome = "not_application"
                ledger.detail = decision.method
                db.add(ledger)
                summary["not_application"] += 1
                continue

            if decision.is_advance:
                # An interview invite that only matches a closed application is
                # a new requisition, not a reopening - open_only keeps the old
                # outcome intact and sends this down the "create" path instead.
                match = match_application_for_email(
                    db, current_user.id,
                    thread_id=thread_id,
                    company=decision.company,
                    role=decision.role,
                    open_only=True,
                )
                target = match.application
                invented = target is None

                if invented:
                    if not (CREATE_FROM_ADVANCE and decision.company):
                        ledger.outcome = "advance_unmatched"
                        ledger.detail = decision.method
                        db.add(ledger)
                        summary["unmatched_advances"] += 1
                        continue
                    target = create_email_application(
                        db,
                        current_user.id,
                        company=decision.company,
                        role=decision.role,
                        status="applied",
                        application_date=received,
                        gmail_message_id=mid,
                        gmail_thread_id=thread_id,
                        needs_review=True,
                    )
                    summary["unmatched_advances"] += 1
                    summary["needs_review"] += 1

                if match.ambiguous:
                    summary["ambiguous_matches"] += 1
                if decision.needs_review or match.ambiguous:
                    if not target.needs_review:
                        summary["needs_review"] += 1
                    target.needs_review = True

                previous = target.status
                moved = advance_application(
                    db, target,
                    stage=decision.kind,
                    sender=from_header,
                    subject=subject,
                    received_at=received,
                    when=decision.when,
                    duration=decision.duration,
                    source_message_id=mid,
                )
                ledger.application_id = target.id
                ledger.outcome = decision.kind if moved else "stage_duplicate"
                ledger.detail = decision.method
                db.add(ledger)

                if moved:
                    summary["advanced"].append({
                        "id": str(target.id),
                        "company": target.company_name,
                        "role": target.position,
                        "stage": decision.kind,
                        "from": previous,
                        "when": decision.when.isoformat() if decision.when else None,
                        "date": received.isoformat(),
                        "was_tracked": not invented,
                        "method": decision.method,
                    })
                else:
                    # already at this stage or further along; the mail is filed
                    # and any date it carried has been folded into the event
                    summary["skipped"] += 1
                continue

            if decision.kind == KIND_REJECTION:
                match = match_application_for_email(
                    db, current_user.id,
                    thread_id=thread_id,
                    company=decision.company,
                    role=decision.role,
                )
                target = match.application
                invented = target is None

                if invented:
                    if not (CREATE_FROM_REJECTION and decision.company):
                        ledger.outcome = "rejection_unmatched"
                        ledger.detail = decision.method
                        db.add(ledger)
                        summary["unmatched_rejections"] += 1
                        continue
                    # Nothing tracked for this company - the decline is the only
                    # trace of the application, so stand a row up for it. It is
                    # created open and closed below, on the one code path.
                    target = create_email_application(
                        db,
                        current_user.id,
                        company=decision.company,
                        role=decision.role,
                        status="applied",
                        application_date=received,
                        gmail_message_id=mid,
                        gmail_thread_id=thread_id,
                        needs_review=True,
                    )
                    summary["unmatched_rejections"] += 1
                    summary["needs_review"] += 1

                if match.ambiguous:
                    summary["ambiguous_matches"] += 1
                if decision.needs_review or match.ambiguous:
                    if not target.needs_review:
                        summary["needs_review"] += 1
                    target.needs_review = True

                changed = mark_application_rejected(
                    db, target,
                    sender=from_header,
                    subject=subject,
                    received_at=received,
                )
                ledger.application_id = target.id
                ledger.outcome = "rejected" if changed else "rejection_duplicate"
                ledger.detail = decision.method
                db.add(ledger)

                if changed:
                    summary["rejected"].append({
                        "id": str(target.id),
                        "company": target.company_name,
                        "role": target.position,
                        "date": received.isoformat(),
                        "was_tracked": not invented,
                        "method": decision.method,
                    })
                else:
                    # already rejected - the response is filed, nothing moved
                    summary["skipped"] += 1
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
                status="applied",
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

        db.commit()  # checkpoint progress after every chunk

    # Only advance the watermark once nothing is left deferred, so a deferred
    # email older than the lookback window can't fall outside the next query.
    if scan_complete and summary["deferred"] == 0 and summary["failed"] == 0:
        sync_row.last_synced_at = checkpoint_at
        db.commit()

    parts = [f"added {len(summary['created'])}"]
    if summary["advanced"]:
        parts.append(f"{len(summary['advanced'])} in process")
    if summary["rejected"]:
        parts.append(f"{len(summary['rejected'])} rejected")
    if summary["deferred"]:
        parts.append(f"{summary['deferred']} deferred (Refresh again)")
    if summary["failed"]:
        parts.append(f"{summary['failed']} failed (Refresh again)")
    return {
        "message": (
            f"Scanned {len(candidate_ids)} new email(s) — "
            + ", ".join(parts) + "."
        ),
        "applications": list_jobs(db, current_user.id),
        "classification": classification,
        **summary,
    }
