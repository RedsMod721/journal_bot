"""End-to-end integration tests for the complete Week 2 processing system."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config_loader import get_config
from app.core.events import EventBus
from app.core.orchestrator import JournalProcessingOrchestrator
from app.core.titles.awarder import TitleAwarder
from app.main import app
from app.models.journal_entry import JournalEntry
from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest
from app.models.skill import Skill
from app.models.theme import Theme
from app.models.title import TitleTemplate, UserTitle
from app.models.user import User
from app.utils.database import Base, get_db


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a thread-safe in-memory DB session for TestClient integration tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_local()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session: Session):
    """FastAPI test client wired to the integration-test DB session."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _capture_events(event_bus: EventBus, event_types: list[str]) -> list[tuple[str, dict]]:
    """Subscribe event listeners and return the shared event capture list."""
    captured: list[tuple[str, dict]] = []

    for event_type in event_types:
        event_bus.subscribe(
            event_type,
            lambda payload, name=event_type: captured.append((name, payload)),
        )

    return captured


def _make_user(db_session: Session) -> User:
    user = User(username="week2_user", email="week2_user@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_orchestrator_with_categories(
    event_bus: EventBus,
    theme: Theme,
    skill: Skill,
) -> JournalProcessingOrchestrator:
    orchestrator = JournalProcessingOrchestrator(event_bus, get_config())
    orchestrator._stub_categorize = lambda entry: {  # type: ignore[method-assign]
        "themes": [{"id": theme.id, "name": theme.name}],
        "skills": [{"id": skill.id, "name": skill.name}],
        "sentiment": "positive",
    }
    return orchestrator


def test_complete_week2_flow_journal_to_title(
    db_session: Session,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Test complete flow:
    Journal entry -> XP distribution -> Level up -> Quest match -> Title unlock
    """
    user = _make_user(db_session)

    # Setup: theme level 9 (close to level-up), skill level 4
    theme_xp_to_next = 100.0 * (1.15 ** 9)
    theme = Theme(
        user_id=user.id,
        name="Education",
        level=9,
        xp=theme_xp_to_next - 20.0,  # +27.5 XP from journal (with multiplier) reaches lv10
        xp_to_next_level=theme_xp_to_next,
    )
    skill = Skill(
        user_id=user.id,
        theme_id=None,
        name="Python",
        level=4,
    )
    db_session.add_all([theme, skill])
    db_session.commit()
    db_session.refresh(theme)
    db_session.refresh(skill)

    # Setup: frequency quest
    quest_template = MissionQuestTemplate(
        name="Exercise 3 times this week",
        type="weekly",
        completion_condition={"type": "frequency", "target": 3, "period": "week"},
    )
    db_session.add(quest_template)
    db_session.commit()
    db_session.refresh(quest_template)

    user_quest = UserMissionQuest(
        user_id=user.id,
        template_id=quest_template.id,
        name="Exercise 3 times this week",
        status="in_progress",
    )
    db_session.add(user_quest)

    # Setup: title to unlock at theme level 10
    unlock_title = TitleTemplate(
        name="Dedicated Learner",
        rank="B",
        effect={"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.0},
        unlock_condition={"type": "theme_level", "theme": "Education", "value": 10},
    )

    # Setup: equipped +10% Education XP title to validate multiplier path
    bonus_title = TitleTemplate(
        name="Focus Buff",
        rank="C",
        effect={"type": "xp_multiplier", "scope": "theme", "target": "Education", "value": 1.10},
        unlock_condition={"type": "journal_count", "value": 9999},
    )
    db_session.add_all([unlock_title, bonus_title])
    db_session.commit()
    db_session.refresh(unlock_title)
    db_session.refresh(bonus_title)

    equipped_bonus = UserTitle(
        user_id=user.id,
        title_template_id=bonus_title.id,
        is_equipped=True,
    )
    db_session.add(equipped_bonus)
    db_session.commit()

    titles_before = db_session.query(UserTitle).filter(UserTitle.user_id == user.id).count()

    event_bus = EventBus()
    captured = _capture_events(
        event_bus,
        [
            "xp.awarded",
            "theme.leveled_up",
            "title.unlocked",
            "quest.progress_updated",
        ],
    )

    monkeypatch.setattr("app.api.v1.journal.get_event_bus", lambda: event_bus)
    client.app.state.orchestrator = _make_orchestrator_with_categories(
        event_bus, theme, skill
    )

    response = client.post(
        "/api/v1/journal/entry",
        json={
            "user_id": user.id,
            "content": "Studied Python for 2 hours, went to gym",
            "entry_type": "text",
        },
    )
    assert response.status_code == 201

    payload = response.json()
    created_entry = db_session.get(JournalEntry, payload["entry"]["id"])
    assert created_entry is not None
    assert created_entry.processing_status == "completed"

    db_session.refresh(theme)
    db_session.refresh(user_quest)
    assert theme.level == 10
    assert theme.theme_metadata["xp_breakdown"]["journal"] > 0

    titles_after = db_session.query(UserTitle).filter(UserTitle.user_id == user.id).count()
    assert titles_after == titles_before + 1

    unlocked = (
        db_session.query(UserTitle)
        .filter(
            UserTitle.user_id == user.id,
            UserTitle.title_template_id == unlock_title.id,
        )
        .first()
    )
    assert unlocked is not None

    assert user_quest.completion_progress > 0

    event_names = [name for name, _ in captured]
    assert "xp.awarded" in event_names
    assert "theme.leveled_up" in event_names
    assert "title.unlocked" in event_names
    assert "quest.progress_updated" in event_names

    first_xp_idx = event_names.index("xp.awarded")
    level_up_idx = event_names.index("theme.leveled_up")
    quest_progress_idx = event_names.index("quest.progress_updated")
    title_unlock_idx = event_names.index("title.unlocked")

    assert first_xp_idx < level_up_idx < title_unlock_idx
    assert first_xp_idx < quest_progress_idx < title_unlock_idx


def test_week2_system_handles_voice_entry_gracefully(db_session: Session):
    """Test voice entry without transcript."""
    user = _make_user(db_session)
    event_bus = EventBus()
    orchestrator = JournalProcessingOrchestrator(event_bus, get_config())

    # `content=""` represents a persisted voice entry that still has no transcript.
    voice_entry = JournalEntry(
        user_id=user.id,
        entry_type="voice",
        content="",
    )
    db_session.add(voice_entry)
    db_session.commit()
    db_session.refresh(voice_entry)

    failed_result = orchestrator.process_entry(db_session, voice_entry)
    db_session.refresh(voice_entry)

    assert failed_result["status"] == "failed"
    assert voice_entry.processing_status == "failed"
    assert db_session.get(JournalEntry, voice_entry.id) is not None

    voice_entry.content = "Transcript added manually after upload."
    db_session.commit()

    success_result = orchestrator.process_entry(db_session, voice_entry)
    db_session.refresh(voice_entry)

    assert success_result["status"] == "completed"
    assert voice_entry.processing_status == "completed"


def test_week2_system_with_multiple_concurrent_entries(
    db_session: Session,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Test processing multiple entries in sequence."""
    user = _make_user(db_session)

    theme = Theme(user_id=user.id, name="Education")
    skill = Skill(user_id=user.id, name="Python")
    db_session.add_all([theme, skill])
    db_session.commit()
    db_session.refresh(theme)
    db_session.refresh(skill)

    event_bus = EventBus()
    xp_events: list[dict] = []
    event_bus.subscribe("xp.awarded", lambda payload: xp_events.append(payload))

    monkeypatch.setattr("app.api.v1.journal.get_event_bus", lambda: event_bus)
    client.app.state.orchestrator = _make_orchestrator_with_categories(
        event_bus, theme, skill
    )

    entry_ids: list[str] = []
    for index in range(10):
        response = client.post(
            "/api/v1/journal/entry",
            json={
                "user_id": user.id,
                "content": f"Entry {index}: worked on python fundamentals.",
                "entry_type": "text",
            },
        )
        assert response.status_code == 201
        entry_ids.append(response.json()["entry"]["id"])

    entries = (
        db_session.query(JournalEntry)
        .filter(JournalEntry.id.in_(entry_ids))
        .all()
    )
    assert len(entries) == 10
    assert all(entry.processing_status == "completed" for entry in entries)

    db_session.refresh(theme)
    db_session.refresh(skill)
    assert theme.theme_metadata["xp_breakdown"]["journal"] == pytest.approx(250.0)
    assert skill.skill_metadata["xp_breakdown"]["journal"] == pytest.approx(250.0)

    assert len(xp_events) == 20
    assert [event["target_type"] for event in xp_events] == ["theme", "skill"] * 10


def test_week2_cascade_awards_multiple_titles(db_session: Session):
    """Test single level-up unlocks multiple titles."""
    user = _make_user(db_session)

    theme_xp_to_next = 100.0 * (1.15 ** 9)
    theme = Theme(
        user_id=user.id,
        name="Education",
        level=9,
        xp=theme_xp_to_next - 1.0,
        xp_to_next_level=theme_xp_to_next,
    )
    db_session.add(theme)

    title_templates = [
        TitleTemplate(
            name="Dedicated Learner I",
            rank="D",
            effect={},
            unlock_condition={"type": "theme_level", "theme": "Education", "value": 10},
        ),
        TitleTemplate(
            name="Dedicated Learner II",
            rank="C",
            effect={},
            unlock_condition={"type": "theme_level", "theme": "Education", "value": 10},
        ),
        TitleTemplate(
            name="Dedicated Learner III",
            rank="B",
            effect={},
            unlock_condition={"type": "theme_level", "theme": "Education", "value": 10},
        ),
    ]
    db_session.add_all(title_templates)
    db_session.commit()
    db_session.refresh(theme)

    title_events: list[dict] = []
    event_bus = EventBus()
    event_bus.subscribe("title.unlocked", lambda payload: title_events.append(payload))

    # Trigger exactly one level-up.
    theme.add_xp(1.0)
    db_session.commit()
    db_session.refresh(theme)
    assert theme.level == 10

    awarder = TitleAwarder(event_bus)
    new_titles = awarder.check_user_unlocks(db_session, user.id)

    assert len(new_titles) == 3
    assert (
        db_session.query(UserTitle)
        .filter(UserTitle.user_id == user.id)
        .count()
        == 3
    )

    awarded_names = {
        db_session.get(TitleTemplate, user_title.title_template_id).name
        for user_title in new_titles
    }
    assert awarded_names == {
        "Dedicated Learner I",
        "Dedicated Learner II",
        "Dedicated Learner III",
    }

    assert len(title_events) == 3
