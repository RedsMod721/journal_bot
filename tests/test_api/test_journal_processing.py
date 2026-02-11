"""API tests for journal entry creation and processing flow."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config_loader import get_config
from app.core.events import get_event_bus
from app.core.orchestrator import JournalProcessingOrchestrator
from app.main import app
from app.models.journal_entry import JournalEntry
from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest
from app.models.skill import Skill
from app.models.theme import Theme
from app.models.user import User
from app.utils.database import Base, get_db


class StubOrchestrator:
    """Simple orchestrator stub used for deterministic API tests."""

    def __init__(self, result: dict | None = None, raises: Exception | None = None) -> None:
        self._result = result or {
            "entry_id": "stub-entry-id",
            "status": "completed",
            "xp_summary": {"awards": []},
            "quests_updated": [],
            "titles_awarded": [],
        }
        self._raises = raises
        self.called = False

    def process_entry(self, db, entry):  # noqa: ANN001
        self.called = True
        if self._raises:
            raise self._raises
        output = dict(self._result)
        output["entry_id"] = entry.id
        return output


@pytest.fixture
def api_db_session():
    """Create an in-memory DB session shared across threads for TestClient."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(api_db_session):
    """FastAPI TestClient using the function-scoped shared DB session."""

    def override_get_db():
        yield api_db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def user(api_db_session):
    created = User(username="api_test_user", email="api_test_user@example.com")
    api_db_session.add(created)
    api_db_session.commit()
    api_db_session.refresh(created)
    return created


@pytest.fixture
def theme(api_db_session, user):
    created = Theme(user_id=user.id, name="Education")
    api_db_session.add(created)
    api_db_session.commit()
    api_db_session.refresh(created)
    return created


@pytest.fixture
def skill(api_db_session, user, theme):
    created = Skill(user_id=user.id, theme_id=theme.id, name="Python")
    api_db_session.add(created)
    api_db_session.commit()
    api_db_session.refresh(created)
    return created


def test_create_entry_triggers_processing(client, user):
    stub = StubOrchestrator()
    client.app.state.orchestrator = stub

    response = client.post(
        "/api/v1/journal/entry",
        json={
            "user_id": user.id,
            "content": "I worked on my goals today.",
            "entry_type": "text",
        },
    )

    assert response.status_code == 201
    assert stub.called is True


def test_create_entry_returns_processing_summary(client, user):
    stub = StubOrchestrator(
        result={
            "entry_id": "ignored",
            "status": "completed",
            "xp_summary": {
                "awards": [
                    {"type": "theme", "name": "Education", "xp": 25.0},
                    {"type": "skill", "name": "Python", "xp": 25.0},
                ]
            },
            "quests_updated": [
                {
                    "quest_id": "123e4567-e89b-12d3-a456-426614174000",
                    "progress": 50,
                    "status": "in_progress",
                }
            ],
            "titles_awarded": [],
        }
    )
    client.app.state.orchestrator = stub

    response = client.post(
        "/api/v1/journal/entry",
        json={
            "user_id": user.id,
            "content": "Learned Python generators.",
            "entry_type": "text",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "entry" in data
    assert "processing_summary" in data
    assert data["processing_summary"]["xp_distributed"] == {
        "theme:Education": 25.0,
        "skill:Python": 25.0,
    }
    assert len(data["processing_summary"]["quests_updated"]) == 1
    assert data["processing_summary"]["total_processing_time_ms"] >= 0


def test_create_entry_with_categories_distributes_xp(
    client,
    api_db_session,
    user,
    theme,
    skill,
):
    orchestrator = JournalProcessingOrchestrator(get_event_bus(), get_config())
    orchestrator._stub_categorize = lambda entry: {  # type: ignore[method-assign]
        "themes": [{"id": theme.id, "name": theme.name}],
        "skills": [{"id": skill.id, "name": skill.name}],
        "sentiment": "positive",
    }
    client.app.state.orchestrator = orchestrator

    response = client.post(
        "/api/v1/journal/entry",
        json={
            "user_id": user.id,
            "content": "Studied algorithms and practiced Python.",
            "entry_type": "text",
        },
    )

    assert response.status_code == 201
    data = response.json()
    xp = data["processing_summary"]["xp_distributed"]
    assert xp[f"theme:{theme.name}"] > 0
    assert xp[f"skill:{skill.name}"] > 0

    api_db_session.refresh(theme)
    api_db_session.refresh(skill)
    assert theme.xp > 0
    assert skill.xp > 0


def test_create_entry_matches_quests(client, api_db_session, user):
    template = MissionQuestTemplate(
        name="Python Practice",
        completion_condition={"type": "keyword_match", "keywords": ["python"]},
    )
    api_db_session.add(template)
    api_db_session.commit()

    quest = UserMissionQuest(
        user_id=user.id,
        template_id=template.id,
        name="Practice Python",
        status="in_progress",
    )
    api_db_session.add(quest)
    api_db_session.commit()

    client.app.state.orchestrator = JournalProcessingOrchestrator(
        get_event_bus(), get_config()
    )

    response = client.post(
        "/api/v1/journal/entry",
        json={
            "user_id": user.id,
            "content": "Today I practiced python for an hour.",
            "entry_type": "text",
        },
    )

    assert response.status_code == 201
    data = response.json()
    quests = data["processing_summary"]["quests_updated"]
    assert len(quests) == 1
    assert quests[0]["quest_id"] == quest.id


def test_create_entry_processing_error_still_creates_entry(client, api_db_session, user):
    client.app.state.orchestrator = StubOrchestrator(raises=RuntimeError("processing exploded"))

    response = client.post(
        "/api/v1/journal/entry",
        json={
            "user_id": user.id,
            "content": "This entry should still be persisted.",
            "entry_type": "text",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    entry_id = payload["entry"]["id"]

    created = api_db_session.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    assert created is not None
    assert created.content == "This entry should still be persisted."


def test_create_entry_emits_event(client, user, monkeypatch):
    mock_bus = MagicMock()
    mock_bus.emit.return_value = []
    monkeypatch.setattr("app.api.v1.journal.get_event_bus", lambda: mock_bus)

    client.app.state.orchestrator = StubOrchestrator()
    response = client.post(
        "/api/v1/journal/entry",
        json={
            "user_id": user.id,
            "content": "Event emission test",
            "entry_type": "text",
        },
    )

    assert response.status_code == 201
    assert mock_bus.emit.call_count == 1
    event_type, payload = mock_bus.emit.call_args.args
    assert event_type == "journal_entry.created"
    assert payload["user_id"] == user.id
    assert payload["content"] == "Event emission test"
    assert "entry_id" in payload


def test_create_entry_without_orchestrator_returns_server_error(api_db_session, user):
    def override_get_db():
        yield api_db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as local_client:
            if hasattr(local_client.app.state, "orchestrator"):
                delattr(local_client.app.state, "orchestrator")

            response = local_client.post(
                "/api/v1/journal/entry",
                json={
                    "user_id": user.id,
                    "content": "No orchestrator configured",
                    "entry_type": "text",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500


def test_create_entry_with_voice_type_and_empty_content_is_rejected(
    client,
    api_db_session,
    user,
):
    before_count = api_db_session.query(JournalEntry).count()

    response = client.post(
        "/api/v1/journal/entry",
        json={
            "user_id": user.id,
            "content": "   ",
            "entry_type": "voice",
        },
    )

    assert response.status_code == 422
    after_count = api_db_session.query(JournalEntry).count()
    assert after_count == before_count
