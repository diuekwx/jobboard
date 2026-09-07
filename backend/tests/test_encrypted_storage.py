from datetime import datetime, timezone
import shutil

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.db.base_class import Base
from backend.models.db_application import Application
from backend.models.db_event import Event
from backend.models.db_integrationtokens import IntegrationToken
from backend.models.db_processedmessage import ProcessedMessage
from backend.models.db_response import RecruiterResponse
from backend.models.db_users import User
from backend.security.encryption import blind_index


def test_sensitive_model_values_are_ciphertext_at_rest(db, user_id):
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    app = Application(
        user_id=user_id,
        company_name="PRIVATE-COMPANY-92831",
        position="PRIVATE-ROLE-92831",
        notes="PRIVATE-NOTE-92831",
        gmail_message_id="PRIVATE-APP-MESSAGE-92831",
        gmail_thread_id="PRIVATE-THREAD-92831",
        gmail_message_lookup=blind_index(
            "PRIVATE-APP-MESSAGE-92831", context="applications.gmail_message_id"
        ),
        gmail_thread_lookup=blind_index(
            "PRIVATE-THREAD-92831", context="applications.gmail_thread_id"
        ),
    )
    db.add(app)
    db.flush()
    db.add_all([
        IntegrationToken(
            user_id=user_id,
            provider="gmail",
            external_user_id="PRIVATE-GOOGLE-USER-92831",
            access_token="PRIVATE-ACCESS-TOKEN-92831",
            refresh_token="PRIVATE-REFRESH-TOKEN-92831",
            expires_at=now,
        ),
        RecruiterResponse(
            application_id=app.id,
            sender_email="PRIVATE-SENDER-92831@example.com",
            subject="PRIVATE-SUBJECT-92831",
            received_at=now,
        ),
        Event(
            application_id=app.id,
            event_type="interview",
            title="PRIVATE-EVENT-92831",
            start_time=now,
            source_message_id="PRIVATE-EVENT-MESSAGE-92831",
            source_message_lookup=blind_index(
                "PRIVATE-EVENT-MESSAGE-92831", context="events.source_message_id"
            ),
        ),
        ProcessedMessage(
            user_id=user_id,
            gmail_message_id="PRIVATE-PROCESSED-MESSAGE-92831",
            gmail_thread_id="PRIVATE-PROCESSED-THREAD-92831",
            gmail_message_lookup=blind_index(
                "PRIVATE-PROCESSED-MESSAGE-92831",
                context="processed_messages.gmail_message_id",
            ),
            gmail_thread_lookup=blind_index(
                "PRIVATE-PROCESSED-THREAD-92831",
                context="processed_messages.gmail_thread_id",
            ),
            outcome="created",
            detail="rules",
        ),
    ])
    db.commit()

    raw_values = []
    for query in (
        "SELECT company_name, position, notes, gmail_message_id, gmail_thread_id FROM applications",
        "SELECT external_user_id, access_token, refresh_token FROM integration_tokens",
        "SELECT sender_email, subject FROM recruiter_responses",
        "SELECT title, source_message_id FROM events",
        "SELECT gmail_message_id, gmail_thread_id FROM processed_messages",
    ):
        raw_values.extend(str(value) for row in db.execute(text(query)) for value in row if value)
    raw_export = "\n".join(raw_values)

    assert "PRIVATE-" not in raw_export
    assert all(value.startswith("enc:v1:") for value in raw_values)
    sql_dump = "\n".join(db.connection().connection.driver_connection.iterdump())
    assert "PRIVATE-" not in sql_dump

    db.refresh(app)
    assert app.company_name == "PRIVATE-COMPANY-92831"
    assert app.position == "PRIVATE-ROLE-92831"
    assert app.notes == "PRIVATE-NOTE-92831"


def test_database_copy_is_recoverable_with_the_matching_key(tmp_path):
    database_path = tmp_path / "encrypted.db"
    backup_path = tmp_path / "encrypted.backup.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="recovery@example.com", hashed_password="x")
        session.add(user)
        session.flush()
        session.add(Application(
            user_id=user.id,
            company_name="RECOVERY-COMPANY-92831",
            position="RECOVERY-ROLE-92831",
        ))
        session.commit()
    engine.dispose()

    shutil.copy2(database_path, backup_path)
    restored_engine = create_engine(f"sqlite:///{backup_path}")
    with Session(restored_engine) as session:
        restored = session.query(Application).one()
        assert restored.company_name == "RECOVERY-COMPANY-92831"
        assert restored.position == "RECOVERY-ROLE-92831"
    restored_engine.dispose()
