import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from backend.adopt_database import adopt, baseline_metadata
from backend.db.base_class import Base
from backend.models.db_application import Application
from backend.models.db_users import User
from backend.models.schema import ApplicationCreate, EditApplication
from backend.service.jobs_service import update_job_application


def config(connection):
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.attributes["connection"] = connection
    return cfg


@pytest.mark.parametrize("existing", [False, True])
def test_fresh_and_existing_converge(existing):
    with create_engine("sqlite://").begin() as conn:
        if existing:
            baseline_metadata().create_all(conn)
            conn.execute(text("INSERT INTO users VALUES (:id, 'legacy@example.com', NULL, '2020-01-01 12:00:00')"), {"id": uuid.uuid4().hex})
            adopt(conn)
        command.upgrade(config(conn), "head")
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
        command.upgrade(config(conn), "head")
        if existing:
            assert conn.scalar(text("SELECT count(*) FROM users")) == 1


def test_adoption_refuses_schema_drift():
    with create_engine("sqlite://").begin() as conn:
        baseline_metadata().create_all(conn)
        conn.execute(text("ALTER TABLE users ADD COLUMN unexpected TEXT"))
        with pytest.raises(RuntimeError, match="Schema differs"):
            adopt(conn)


def test_legacy_status_and_duplicate_preflight():
    with create_engine("sqlite://").begin() as conn:
        command.upgrade(config(conn), "0001")
        uid = uuid.uuid4().hex
        conn.execute(text("INSERT INTO users VALUES (:id, 'legacy@example.com', NULL, '2020-01-01')"), {"id": uid})
        conn.execute(text("""INSERT INTO applications
            (id,user_id,company_name,application_date,status,source,needs_review,created_at,updated_at)
            VALUES (:id,:uid,'Example','2020-01-01','sent','email',0,'2020-01-01','2020-01-01')"""), {"id": uuid.uuid4().hex, "uid": uid})
        for i in (1, 2):
            conn.execute(text("""INSERT INTO integration_tokens
                (id,user_id,provider,access_token,expires_at,created_at,updated_at)
                VALUES (:id,:uid,'gmail','synthetic','2030-01-01','2020-01-01','2020-01-01')"""), {"id": i, "uid": uid})
        with pytest.raises(RuntimeError, match="duplicate user/provider"):
            command.upgrade(config(conn), "head")
        assert conn.scalar(text("SELECT status FROM applications")) == "sent"
        conn.execute(text("DELETE FROM integration_tokens WHERE id=2"))
        command.upgrade(config(conn), "head")
        assert conn.scalar(text("SELECT status FROM applications")) == "applied"
        assert conn.scalar(text("SELECT company_name FROM applications")) != "Example"
        assert conn.scalar(text("SELECT company_name FROM applications")).startswith("enc:v1:")
        assert conn.scalar(text("SELECT access_token FROM integration_tokens")) != "synthetic"
        assert conn.scalar(text("SELECT access_token FROM integration_tokens")).startswith("enc:v1:")
        with pytest.raises(IntegrityError):
            conn.execute(text("UPDATE applications SET status='unknown'"))


def test_id_edits_and_ownership(db, user_id):
    apps = [Application(user_id=user_id, company_name="Same", position="Same") for _ in range(2)]
    db.add_all(apps)
    db.commit()
    update_job_application(db, apps[1].id, EditApplication(notes="Changed"), user_id)
    assert apps[0].notes is None
    assert apps[1].notes == "Changed"
    with pytest.raises(HTTPException) as exc:
        update_job_application(db, apps[1].id, EditApplication(notes="Wrong owner"), uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.parametrize("payload", [{}, {"status": "sent"}, {"status": None}, {"company": " "}, {"company": "a" * 201}, {"user_id": str(uuid.uuid4())}])
def test_invalid_patch(payload):
    with pytest.raises(ValidationError):
        EditApplication(**payload)


def test_invalid_create():
    with pytest.raises(ValidationError):
        ApplicationCreate(company="", position="Engineer", status="unknown")


def test_defaults_and_utc_roundtrip(db):
    first = User(email="first@example.com")
    db.add(first)
    db.commit()
    second = User(email="second@example.com")
    db.add(second)
    db.commit()
    assert second.created_at > first.created_at
    second.created_at = datetime(2025, 1, 1, 12, tzinfo=timezone(timedelta(hours=2)))
    db.commit()
    db.refresh(second)
    assert second.created_at.isoformat() == "2025-01-01T10:00:00+00:00"
