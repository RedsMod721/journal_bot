from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.core.forgiveness_presets import DEFAULT_FORGIVENESS_PRESET
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.user import User
from src.db.session import get_db


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _make_user(db_session: Session, *, user_id: str) -> User:
    user = User(
        id=user_id,
        username=f"user-{user_id}",
        email=f"{user_id}@example.com",
        password_hash="hash",
        timezone="Europe/Paris",
        home_country="US",
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_forgiveness_presets_endpoint_returns_display_names() -> None:
    engine, session_local = _session_factory()
    session = session_local()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/forgiveness/presets")
            assert response.status_code == 200
            payload = response.json()
            by_preset = {item["preset"]: item for item in payload}
            assert by_preset[DEFAULT_FORGIVENESS_PRESET]["name"] == "Balanced"
            assert by_preset["custom"]["name"] == "Custom"
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()


def test_forgiveness_config_defaults_to_balanced() -> None:
    engine, session_local = _session_factory()
    session = session_local()
    user = _make_user(session, user_id="forgive-user")

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/forgiveness/config",
                params={"user_id": user.id},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["preset"] == DEFAULT_FORGIVENESS_PRESET
            assert payload["skill_grace_period_days"] == 7
            assert payload["insight_grace_period_days"] == 3
            session.refresh(user)
            assert user.forgiveness_config_id is not None
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()
