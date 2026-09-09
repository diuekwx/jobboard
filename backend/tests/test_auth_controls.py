"""Authentication lifecycle, CSRF, and ownership boundary regression tests."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.api import oatuh as oauth_api
from backend.api import user as user_api
from backend.core.auth import create_access_token
from backend.core.config import ConfigurationError, validate_security_config
from backend.db.session import get_db
from backend.main import app
from backend.models.db_application import Application
from backend.models.db_applicationsync import ApplicationSync
from backend.models.db_event import Event
from backend.models.db_integrationtokens import IntegrationToken
from backend.models.db_processedmessage import ProcessedMessage
from backend.models.db_response import RecruiterResponse
from backend.models.db_scanjob import ScanJob
from backend.models.db_users import User
from backend.security.encryption import blind_index


def _client(db, user: User):
    app.dependency_overrides[get_db] = lambda: db
    csrf = "test-csrf-token"
    token = create_access_token(
        {"sub": str(user.id), "email": user.email, "csrf": csrf}
    )
    client = TestClient(app)
    client.cookies.set("access_token", token)
    client.cookies.set("csrf_token", csrf)
    return client, {"X-CSRF-Token": csrf}


def test_csrf_required_for_cookie_authenticated_mutation(db):
    user = User(email="csrf@example.com")
    db.add(user)
    db.commit()
    client, headers = _client(db, user)
    try:
        payload = {"company": "Example", "position": "Engineer"}
        assert client.post("/job/create", json=payload).status_code == 403
        assert client.post("/job/create", json=payload, headers=headers).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_logout_requires_csrf_and_clears_session_cookies(db):
    user = User(email="logout@example.com")
    db.add(user)
    db.commit()
    client, headers = _client(db, user)
    try:
        assert client.post("/api/user/logout").status_code == 403
        response = client.post("/api/user/logout", headers=headers)
        assert response.status_code == 204
        set_cookie = response.headers.get_list("set-cookie")
        assert any("access_token=" in value and "Max-Age=0" in value for value in set_cookie)
        assert any("csrf_token=" in value and "Max-Age=0" in value for value in set_cookie)
    finally:
        app.dependency_overrides.clear()


def test_cross_user_data_and_scan_status_are_isolated(db):
    owner = User(email="owner@example.com")
    other = User(email="other@example.com")
    db.add_all([owner, other])
    db.flush()
    db.add_all([
        Application(user_id=owner.id, company_name="Owner Co", position="One"),
        Application(user_id=other.id, company_name="Other Co", position="Two"),
    ])
    other_job = ScanJob(user_id=other.id)
    db.add(other_job)
    db.commit()

    client, _headers = _client(db, owner)
    try:
        response = client.get("/job/list")
        assert response.status_code == 200
        assert [item["company"] for item in response.json()["applications"]] == ["Owner Co"]
        other_app = db.query(Application).filter_by(user_id=other.id).one()
        assert client.patch(
            f"/job/{other_app.id}",
            json={"status": "interview"},
            headers=_headers,
        ).status_code == 404
        assert client.get(f"/gmail-service/scans/{other_job.id}").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_disconnect_removes_only_calling_users_token(db, monkeypatch):
    owner = User(email="disconnect@example.com")
    other = User(email="still-connected@example.com")
    db.add_all([owner, other])
    db.flush()
    db.add_all([
        IntegrationToken(user_id=owner.id, provider="gmail", access_token="one", expires_at=datetime(2030, 1, 1)),
        IntegrationToken(user_id=other.id, provider="gmail", access_token="two", expires_at=datetime(2030, 1, 1)),
    ])
    db.commit()
    monkeypatch.setattr(user_api, "revoke_google_credentials", lambda token: True)

    client, headers = _client(db, owner)
    try:
        response = client.post("/api/user/gmail/disconnect", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"disconnected": True, "provider_revoked": True}
        remaining = db.query(IntegrationToken).all()
        assert len(remaining) == 1
        assert remaining[0].user_id == other.id
    finally:
        app.dependency_overrides.clear()


def test_account_deletion_removes_owned_rows_and_preserves_other_user(db, monkeypatch):
    owner = User(email="delete@example.com")
    other = User(email="preserve@example.com")
    db.add_all([owner, other])
    db.flush()
    app_row = Application(user_id=owner.id, company_name="Private", position="Role")
    db.add(app_row)
    db.flush()
    db.add_all([
        IntegrationToken(user_id=owner.id, provider="gmail", access_token="secret", expires_at=datetime(2030, 1, 1)),
        ScanJob(user_id=owner.id),
        ApplicationSync(user_id=owner.id, start_date=datetime(2026, 1, 1)),
        Event(
            application_id=app_row.id,
            event_type="interview",
            title="Private interview",
            start_time=datetime(2026, 1, 2),
        ),
        RecruiterResponse(
            application_id=app_row.id,
            sender_email="recruiter@example.com",
            subject="Private update",
            received_at=datetime(2026, 1, 2),
        ),
        ProcessedMessage(
            user_id=owner.id,
            gmail_message_id="message-1",
            gmail_message_lookup=blind_index(
                "message-1", context="processed_messages.gmail_message_id"
            ),
            outcome="created",
            application_id=app_row.id,
        ),
    ])
    db.commit()
    owner_id = owner.id
    other_id = other.id
    monkeypatch.setattr(user_api, "revoke_google_credentials", lambda token: True)

    client, headers = _client(db, owner)
    headers["X-Confirm-Account-Deletion"] = "delete"
    try:
        response = client.delete("/api/user/me", headers=headers)
        assert response.status_code == 204
        db.expire_all()
        assert db.get(User, owner_id) is None
        assert db.get(User, other_id) is not None
        assert db.query(Application).filter_by(user_id=owner_id).count() == 0
        assert db.query(ProcessedMessage).filter_by(user_id=owner_id).count() == 0
        assert db.query(ScanJob).filter_by(user_id=owner_id).count() == 0
        assert db.query(ApplicationSync).filter_by(user_id=owner_id).count() == 0
        assert db.query(IntegrationToken).filter_by(user_id=owner_id).count() == 0
        assert db.query(Event).count() == 0
        assert db.query(RecruiterResponse).count() == 0
    finally:
        app.dependency_overrides.clear()


def test_oauth_state_is_single_use(monkeypatch, capsys):
    class FakeFlow:
        def authorization_url(self, **_kwargs):
            return "https://accounts.example/authorize", "expected-state"

    monkeypatch.setattr(oauth_api, "_flow", lambda: FakeFlow())
    with TestClient(app) as client:
        assert client.get("/gmail/auth/google").status_code == 200
        assert client.get(
            "/gmail/auth/google/callback",
            params={"code": "code", "state": "wrong-state"},
        ).status_code == 400
        assert client.get(
            "/gmail/auth/google/callback",
            params={"code": "code", "state": "expected-state"},
        ).status_code == 400
    assert "expected-state" not in capsys.readouterr().out


def test_expired_session_is_rejected(db):
    user = User(email="expired@example.com")
    db.add(user)
    db.commit()
    token = create_access_token(
        {"sub": str(user.id), "csrf": "expired"},
        expires_delta=timedelta(seconds=-1),
    )
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            client.cookies.set("access_token", token)
            assert client.get("/api/user/me").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_production_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "short")
    monkeypatch.setenv("SESSION_SECRET_KEY", "short")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://example.com/callback")
    monkeypatch.setenv("FRONTEND_REDIRECT", "http://example.com/dashboard")
    monkeypatch.setenv("CORS_ORIGINS", "http://example.com")
    try:
        validate_security_config()
    except ConfigurationError as exc:
        assert "Unsafe production configuration" in str(exc)
    else:
        raise AssertionError("insecure production configuration was accepted")
