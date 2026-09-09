"""User-driven application correction, history, merge, and undo workflows."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.db_application import Application
from backend.models.db_applicationaction import ApplicationAction
from backend.models.db_event import Event
from backend.models.db_processedmessage import ProcessedMessage
from backend.models.db_response import RecruiterResponse


def owned_application(db: Session, user_id: uuid.UUID, app_id: uuid.UUID) -> Application:
    app = db.query(Application).filter(
        Application.id == app_id, Application.user_id == user_id
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


def snapshot(app: Application) -> dict:
    return {
        "company_name": app.company_name,
        "position": app.position,
        "status": app.status,
        "notes": app.notes,
        "application_date": app.application_date.isoformat() if app.application_date else None,
        "needs_review": app.needs_review,
        "archived_at": app.archived_at.isoformat() if app.archived_at else None,
    }


def restore_snapshot(app: Application, state: dict) -> None:
    for key in ("company_name", "position", "status", "notes", "needs_review"):
        setattr(app, key, state.get(key))
    app.application_date = date.fromisoformat(state["application_date"]) if state.get("application_date") else None
    app.archived_at = datetime.fromisoformat(state["archived_at"]) if state.get("archived_at") else None
    app.updated_at = datetime.now(timezone.utc)


def record_action(
    db: Session,
    user_id: uuid.UUID,
    app_id: uuid.UUID | None,
    action: str,
    summary: str,
    payload: dict | None = None,
) -> ApplicationAction:
    row = ApplicationAction(
        user_id=user_id,
        application_id=app_id,
        action=action,
        summary=summary,
        undo_payload=json.dumps(payload, separators=(",", ":")) if payload else None,
    )
    db.add(row)
    db.flush()
    return row


def archive_application(db: Session, user_id: uuid.UUID, app_id: uuid.UUID, archived: bool) -> Application:
    app = owned_application(db, user_id, app_id)
    before = snapshot(app)
    app.archived_at = datetime.now(timezone.utc) if archived else None
    app.updated_at = datetime.now(timezone.utc)
    record_action(
        db, user_id, app.id, "archive" if archived else "restore",
        "Application archived" if archived else "Application restored",
        {"kind": "snapshot", "application_id": str(app.id), "before": before},
    )
    db.commit()
    db.refresh(app)
    return app


def merge_applications(db: Session, user_id: uuid.UUID, source_id: uuid.UUID, target_id: uuid.UUID) -> ApplicationAction:
    if source_id == target_id:
        raise HTTPException(status_code=400, detail="Choose a different application to merge into")
    source = owned_application(db, user_id, source_id)
    target = owned_application(db, user_id, target_id)
    if source.archived_at or target.archived_at:
        raise HTTPException(status_code=409, detail="Archived applications cannot be merged")

    events = db.query(Event).filter(Event.application_id == source.id).all()
    responses = db.query(RecruiterResponse).filter(RecruiterResponse.application_id == source.id).all()
    messages = db.query(ProcessedMessage).filter(
        ProcessedMessage.user_id == user_id,
        ProcessedMessage.application_id == source.id,
    ).all()
    payload = {
        "kind": "merge",
        "source_id": str(source.id),
        "target_id": str(target.id),
        "source_before": snapshot(source),
        "target_before": snapshot(target),
        "event_ids": [str(row.id) for row in events],
        "response_ids": [str(row.id) for row in responses],
        "message_ids": [str(row.id) for row in messages],
    }
    for row in (*events, *responses, *messages):
        row.application_id = target.id
    source.archived_at = datetime.now(timezone.utc)
    source.needs_review = False
    target.needs_review = False
    action = record_action(
        db, user_id, target.id, "merge",
        f"Merged duplicate application from {source.company_name}", payload,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Applications have conflicting source history") from None
    db.refresh(action)
    return action


def undo_action(db: Session, user_id: uuid.UUID, action_id: uuid.UUID) -> ApplicationAction:
    action = db.query(ApplicationAction).filter(
        ApplicationAction.id == action_id,
        ApplicationAction.user_id == user_id,
        ApplicationAction.undone_at.is_(None),
    ).first()
    if not action or not action.undo_payload:
        raise HTTPException(status_code=404, detail="Undo action not found")
    payload = json.loads(action.undo_payload)
    if payload["kind"] == "snapshot":
        app = owned_application(db, user_id, uuid.UUID(payload["application_id"]))
        restore_snapshot(app, payload["before"])
    elif payload["kind"] == "merge":
        source = owned_application(db, user_id, uuid.UUID(payload["source_id"]))
        target = owned_application(db, user_id, uuid.UUID(payload["target_id"]))
        restore_snapshot(source, payload["source_before"])
        restore_snapshot(target, payload["target_before"])
        mappings = (
            (Event, payload["event_ids"]),
            (RecruiterResponse, payload["response_ids"]),
            (ProcessedMessage, payload["message_ids"]),
        )
        for model, ids in mappings:
            if ids:
                db.query(model).filter(model.id.in_([uuid.UUID(value) for value in ids])).update(
                    {model.application_id: source.id}, synchronize_session=False
                )
    else:
        raise HTTPException(status_code=409, detail="This action cannot be undone")
    action.undone_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(action)
    return action


def application_history(db: Session, user_id: uuid.UUID, app_id: uuid.UUID) -> list[dict]:
    app = owned_application(db, user_id, app_id)
    rows = [{
        "id": f"created-{app.id}", "kind": "created", "summary": "Application created",
        "at": app.created_at.isoformat(), "source_url": (
            f"https://mail.google.com/mail/u/0/#all/{app.gmail_message_id}" if app.gmail_message_id else None
        ), "undoable": False,
    }]
    for message in db.query(ProcessedMessage).filter(
        ProcessedMessage.user_id == user_id,
        ProcessedMessage.application_id == app.id,
    ).all():
        rows.append({
            "id": str(message.id), "kind": message.outcome,
            "summary": message.outcome.replace("_", " ").capitalize(),
            "at": message.processed_at.isoformat(),
            "source_url": f"https://mail.google.com/mail/u/0/#all/{message.gmail_message_id}",
            "undoable": False,
        })
    actions = db.query(ApplicationAction).filter(ApplicationAction.user_id == user_id).all()
    for action in actions:
        include = action.application_id == app.id
        if not include and action.action == "merge" and action.undo_payload:
            include = json.loads(action.undo_payload).get("source_id") == str(app.id)
        if include:
            rows.append({
                "id": str(action.id), "kind": action.action, "summary": action.summary,
                "at": action.created_at.isoformat(), "source_url": None,
                "undoable": bool(action.undo_payload and not action.undone_at),
                "undone": bool(action.undone_at),
            })
    return sorted(rows, key=lambda row: row["at"], reverse=True)
