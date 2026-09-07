"""Verify runtime imports and password login without external services."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.base_class import Base
from backend.db.session import get_db
from backend.main import app


def test_register_login_and_current_user():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def test_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            assert client.get("/").status_code == 200
            credentials = {"email": "baseline@example.com", "password": "local-test-password"}
            assert client.post("/api/user/register", json=credentials).status_code == 200
            assert client.post("/api/user/login", json={**credentials, "password": "wrong"}).status_code == 400
            assert client.post("/api/user/login", json=credentials).status_code == 200
            response = client.get("/api/user/me")
            assert response.status_code == 200
            assert response.json()["email"] == credentials["email"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
