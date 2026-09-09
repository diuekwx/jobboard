import json
import uuid
from datetime import datetime, timezone
from sqlalchemy import text

from backend.models.db_application import Application
from backend.models.db_event import Event
from backend.models.db_processedmessage import ProcessedMessage
from backend.models.schema import ApplicationCreate, EditApplication
from backend.security.encryption import blind_index
from backend.service.classification_service import KIND_OFFER, run_rules
from backend.service.jobs_service import (
    advance_application, create_job_service, list_jobs, update_job_application,
)
from backend.service.workflow_service import (
    application_history, archive_application, merge_applications, undo_action,
)


def test_add_edit_notes_archive_and_undo(db, user_id):
    app = create_job_service(
        db, user_id,
        ApplicationCreate(company="Acme", position="Engineer", notes="First note"),
    )
    action_count = len(application_history(db, user_id, app.id))
    assert action_count == 2  # creation record plus user action history
    assert list_jobs(db, user_id)[0]["notes"] == "First note"

    update_job_application(
        db, app.id,
        EditApplication(status="accepted", notes="Accepted on Friday"),
        user_id,
    )
    assert app.status == "accepted"
    raw = db.execute(text(
        "SELECT summary, undo_payload FROM application_actions WHERE action = 'edit'"
    )).one()
    assert "Application edited" not in raw.summary
    assert "First note" not in raw.undo_payload
    edit = next(item for item in application_history(db, user_id, app.id) if item["kind"] == "edit")
    undo_action(db, user_id, uuid.UUID(edit["id"]))
    assert app.status == "applied"
    assert app.notes == "First note"

    archive_application(db, user_id, app.id, True)
    assert list_jobs(db, user_id) == []
    assert list_jobs(db, user_id, archived=True)[0]["company"] == "Acme"


def test_review_correction_merge_and_undo(db, user_id):
    target = Application(user_id=user_id, company_name="Acme", position="Engineer")
    source = Application(
        user_id=user_id, company_name="Acme Inc", position="Engineer",
        needs_review=True, source="email", gmail_message_id="m1",
    )
    db.add_all([target, source])
    db.flush()
    event = Event(
        application_id=source.id, event_type="interview", title="Interview",
        start_time=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    message = ProcessedMessage(
        user_id=user_id, application_id=source.id, gmail_message_id="m1",
        gmail_message_lookup=blind_index("m1", context="processed_messages.gmail_message_id"),
        outcome="needs_review",
    )
    db.add_all([event, message])
    db.commit()

    update_job_application(
        db, source.id, EditApplication(company="Acme"), user_id, resolve_review=True
    )
    assert source.needs_review is False
    correction = next(item for item in application_history(db, user_id, source.id) if item["kind"] == "correction")
    undo_action(db, user_id, uuid.UUID(correction["id"]))
    assert source.needs_review is True

    merge = merge_applications(db, user_id, source.id, target.id)
    assert source.archived_at is not None
    assert event.application_id == target.id
    assert message.application_id == target.id
    undo_action(db, user_id, merge.id)
    db.refresh(source)
    db.refresh(event)
    assert source.archived_at is None
    assert event.application_id == source.id


def test_history_has_gmail_source_and_exportable_values(db, user_id):
    app = Application(
        user_id=user_id, company_name="Source Co", position="Role",
        source="email", gmail_message_id="source-message",
    )
    db.add(app)
    db.flush()
    db.add(ProcessedMessage(
        user_id=user_id, application_id=app.id,
        gmail_message_id="source-message",
        gmail_message_lookup=blind_index(
            "source-message", context="processed_messages.gmail_message_id"
        ),
        outcome="created",
    ))
    db.commit()
    history = application_history(db, user_id, app.id)
    assert any(item["source_url"].endswith("source-message") for item in history if item["source_url"])
    assert json.dumps(list_jobs(db, user_id))


def test_offer_email_is_a_pipeline_advance():
    result = run_rules(
        "Acme Careers <jobs@acme.com>",
        "Your formal job offer",
        "We are pleased to extend you an offer of employment for the Engineer role.",
    )
    assert result.kind == KIND_OFFER


def test_offer_advances_but_terminal_user_outcome_is_preserved(db, user_id):
    app = Application(user_id=user_id, company_name="Acme", position="Engineer")
    db.add(app)
    db.flush()
    assert advance_application(
        db, app, stage="offer", sender="jobs@acme.test",
        subject="Offer", received_at=datetime.now(timezone.utc),
    ) is True
    assert app.status == "offer"
    app.status = "accepted"
    assert advance_application(
        db, app, stage="offer", sender="jobs@acme.test",
        subject="Offer reminder", received_at=datetime.now(timezone.utc),
    ) is False
    assert app.status == "accepted"
