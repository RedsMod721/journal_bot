"""Integration checks for Week 4 UI-facing src API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.global_kb import GlobalSkill
from src.db.models.journal_entry import JournalEntry
from src.db.models.quest import Quest
from src.db.models.skill import Skill, SkillThemeMapping, Theme
from src.db.models.user import User
from src.db.session import get_db


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session: Session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_user_id(db_session: Session) -> str:
    user_id = "11111111-1111-1111-1111-111111111111"
    user = User(
        id=user_id,
        username="week4_user",
        email="week4@example.com",
        password_hash="hash",
        home_country="US",
    )
    db_session.add(user)

    parent_global_skill = GlobalSkill(
        id="77777777-7777-7777-7777-777777777777",
        source_skill_id="skill_professional_professional_growth",
        canonical_name="Professional Growth",
        hierarchy_level=1,
        parent_skill_ids_json="[]",
    )
    child_global_skill = GlobalSkill(
        id="88888888-8888-8888-8888-888888888888",
        source_skill_id="skill_professional_programming",
        canonical_name="Programming",
        hierarchy_level=2,
        parent_skill_ids_json='["skill_professional_professional_growth"]',
    )
    db_session.add(parent_global_skill)
    db_session.add(child_global_skill)
    db_session.flush()

    skill = Skill(
        id="22222222-2222-2222-2222-222222222222",
        user_id=user_id,
        name="Python Programming",
        canonical_name="python programming",
        global_skill_id=child_global_skill.id,
        xp=1200,
        level=4,
    )
    db_session.add(skill)

    theme = Theme(
        id="55555555-5555-5555-5555-555555555555",
        user_id=user_id,
        name="Professional",
    )
    db_session.add(theme)
    db_session.flush()

    mapping = SkillThemeMapping(
        id="66666666-6666-6666-6666-666666666666",
        user_id=user_id,
        skill_id=skill.id,
        theme_id=theme.id,
    )
    db_session.add(mapping)

    entry = JournalEntry(
        id="33333333-3333-3333-3333-333333333333",
        user_id=user_id,
        content="I practiced Python and built an API.",
        entry_type="text",
        status="completed",
    )
    db_session.add(entry)

    quest = Quest(
        id="44444444-4444-4444-4444-444444444444",
        user_id=user_id,
        skill_id=skill.id,
        name="Ship Python API",
        quest_type="longterm",
        completion_type="one_time",
        base_xp=480,
        status="active",
        required_progress=1,
        current_progress=1,
    )
    db_session.add(quest)

    db_session.commit()
    return user_id


def test_users_list_endpoint(client: TestClient, seeded_user_id: str):
    response = client.get("/api/users")
    assert response.status_code == 200
    data = response.json()
    assert any(u["id"] == seeded_user_id for u in data)


def test_user_stats_endpoint(client: TestClient, seeded_user_id: str):
    response = client.get(f"/api/users/{seeded_user_id}/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["user_id"] == seeded_user_id
    assert stats["total_xp"] >= 0
    assert stats["journal_entries"] == 1
    assert stats["skills_practiced"] == 1
    assert stats["xp_today"] >= 0
    assert stats["xp_this_week"] >= 0
    assert stats["recent_gain"] >= 0


def test_skills_endpoint(client: TestClient, seeded_user_id: str):
    response = client.get("/api/skills", params={"user_id": seeded_user_id})
    assert response.status_code == 200
    skills = response.json()
    assert len(skills) == 1
    assert skills[0]["current_level"] == 4
    assert skills[0]["total_xp"] == 1200
    assert skills[0]["current_level_xp"] >= 0
    assert skills[0]["next_level_xp"] > 0


def test_quest_complete_endpoint(client: TestClient, seeded_user_id: str):
    response = client.post(
        "/api/quests/44444444-4444-4444-4444-444444444444/complete",
        params={"user_id": seeded_user_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"


def test_quests_endpoint_includes_related_skill_and_theme(
    client: TestClient, seeded_user_id: str
):
    response = client.get("/api/quests", params={"user_id": seeded_user_id})
    assert response.status_code == 200
    quests = response.json()
    assert len(quests) == 1
    assert quests[0]["related_skill_name"] == "Python Programming"
    assert quests[0]["related_skill_source_id"] == "skill_professional_programming"
    assert quests[0]["related_skill_hierarchy_level"] == 2
    assert quests[0]["related_skill_ancestor_skills"] == [
        {
            "source_skill_id": "skill_professional_professional_growth",
            "canonical_name": "Professional Growth",
            "hierarchy_level": 1,
        }
    ]
    assert quests[0]["related_themes"] == ["Professional"]
