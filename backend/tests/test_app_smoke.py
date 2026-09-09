"""Verify startup and the Google-only authentication boundary."""

from fastapi.testclient import TestClient

from backend.main import app


def test_password_auth_routes_are_not_available():
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.post("/api/user/register", json={}).status_code == 404
        assert client.post("/api/user/login", json={}).status_code == 404
        assert client.get("/api/user/me").status_code == 401
