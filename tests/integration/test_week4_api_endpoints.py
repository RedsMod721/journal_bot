"""Integration checks for Week 4 UI-facing src API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.core.themes import CANONICAL_THEME_NAMES
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.global_kb import GlobalSkill
from src.db.models.journal_entry import JournalEntry
from src.db.models.quest import Quest
from src.db.models.skill import Skill, SkillThemeMapping, Theme
from src.db.models.user import User
from src.db.models.user_skill_state import UserSkillState
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
    lv0_global_skill = GlobalSkill(
        id="99999999-9999-9999-9999-999999999999",
        source_skill_id="skill_test_lv0",
        canonical_name="Test Lv0 Skill",
        hierarchy_level=1,
        parent_skill_ids_json="[]",
    )
    db_session.add(lv0_global_skill)
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
    lv0_skill = Skill(
        id="22222222-2222-2222-2222-222222222223",
        user_id=user_id,
        name="Test Lv0 Skill",
        canonical_name="test lv0 skill",
        global_skill_id=lv0_global_skill.id,
        xp=0,
        level=1,
    )
    db_session.add(lv0_skill)

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


@pytest.fixture
def demo_user_id(db_session: Session) -> str:
    user_id = "37b80e12-c72a-4c2c-979a-68b02caae381"
    user = User(
        id=user_id,
        username="leo_connector",
        email="leo_connector@placeholder.local",
        password_hash="hash",
        timezone="UTC",
        home_country="FR",
    )
    db_session.add(user)
    db_session.commit()
    return user_id


def test_users_list_endpoint(client: TestClient, seeded_user_id: str):
    response = client.get("/api/users")
    assert response.status_code == 200
    data = response.json()
    assert any(u["id"] == seeded_user_id for u in data)


def test_user_preferences_endpoint_defaults(client: TestClient, seeded_user_id: str):
    response = client.get(f"/api/users/{seeded_user_id}/preferences")
    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == seeded_user_id
    assert payload["realm"]["scope"] == {
        "visual": True,
        "naming": False,
        "messages": False,
        "llm": False,
    }
    assert payload["realm"]["ranks_wording"]["preset"] == "standard"
    assert payload["skill_hierarchy"]["default_blocked_preference"] is False


def test_user_preferences_endpoint_updates(client: TestClient, seeded_user_id: str):
    update_payload = {
        "realm": {
            "scope": {
                "visual": True,
                "naming": True,
                "messages": True,
                "llm": False,
            },
            "ranks_wording": {"preset": "arcane_magic_system"},
        }
    }

    response = client.put(
        f"/api/users/{seeded_user_id}/preferences",
        json=update_payload,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["realm"]["scope"]["naming"] is True
    assert payload["realm"]["scope"]["messages"] is True
    assert payload["realm"]["ranks_wording"]["preset"] == "arcane_magic_system"

    verify = client.get(f"/api/users/{seeded_user_id}/preferences")
    assert verify.status_code == 200
    verify_payload = verify.json()
    assert verify_payload["realm"]["scope"]["naming"] is True
    assert verify_payload["realm"]["scope"]["messages"] is True
    assert verify_payload["realm"]["ranks_wording"]["preset"] == "arcane_magic_system"


def test_user_preferences_endpoint_updates_default_blocked_preference(
    client: TestClient, seeded_user_id: str
):
    update_payload = {
        "skill_hierarchy": {
            "default_blocked_preference": True,
        }
    }

    response = client.put(
        f"/api/users/{seeded_user_id}/preferences",
        json=update_payload,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["skill_hierarchy"]["default_blocked_preference"] is True

    verify = client.get(f"/api/users/{seeded_user_id}/preferences")
    assert verify.status_code == 200
    verify_payload = verify.json()
    assert verify_payload["skill_hierarchy"]["default_blocked_preference"] is True


def test_realm_rank_wording_presets_endpoint(client: TestClient):
    response = client.get("/api/users/preferences/realm/rank-wording-presets")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 5

    by_preset = {item["preset"]: item for item in payload}
    assert "standard" in by_preset
    assert "cultivation_realm" in by_preset

    standard = by_preset["standard"]
    standard_ranks = {row["rank"]: row["wording"] for row in standard["ranks"]}
    assert standard_ranks["F"] == "Beginner"
    assert standard_ranks["SSS"] == "Legend"


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


def test_legacy_journal_entry_processing_routes_are_absent(
    client: TestClient,
    seeded_user_id: str,
):
    submit_response = client.post(
        "/api/journal/entries",
        json={
            "user_id": seeded_user_id,
            "raw_text": "I practiced Python today.",
        },
    )
    assert submit_response.status_code == 404

    status_response = client.get(
        "/api/journal/entries/nonexistent-entry",
        params={"user_id": seeded_user_id},
    )
    assert status_response.status_code == 404


def test_openapi_exposes_canonical_entry_processing_paths_only(client: TestClient):
    response = client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    assert "/api/v1/entries" in paths
    assert "/api/v1/entry-jobs/{job_id}" in paths
    assert "/api/journal/entries" not in paths
    assert "/api/journal/entries/{entry_id}" not in paths
    assert "/api/v1/journal/entries" not in paths
    assert "/api/entries" not in paths


def test_user_stats_endpoint_uses_demo_profile_fallback(
    client: TestClient, demo_user_id: str
):
    response = client.get(f"/api/users/{demo_user_id}/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["user_id"] == demo_user_id
    assert stats["journal_entries"] == 7
    assert stats["current_streak"] == 7
    assert stats["active_quests"] == 3
    assert stats["total_xp"] == 13260


def test_skills_endpoint(client: TestClient, seeded_user_id: str):
    response = client.get("/api/skills", params={"user_id": seeded_user_id})
    assert response.status_code == 200
    skills = response.json()
    assert len(skills) == 2

    by_name = {skill["canonical_name"]: skill for skill in skills}

    leveled_skill = by_name["Python Programming"]
    assert leveled_skill["current_level"] == 4
    assert leveled_skill["total_xp"] == 1200
    assert leveled_skill["rank"] is not None
    assert leveled_skill["current_level_xp"] >= 0
    assert leveled_skill["next_level_xp"] > 0

    lv0_skill = by_name["Test Lv0 Skill"]
    assert lv0_skill["total_xp"] == 0
    assert lv0_skill["current_level"] == 0
    assert lv0_skill["rank"] is None
    assert lv0_skill["current_level_xp"] == 0
    assert lv0_skill["next_level_xp"] > 0


def test_skills_hierarchy_endpoint_returns_lv0_for_zero_xp(
    client: TestClient, seeded_user_id: str
):
    response = client.get("/api/skills/hierarchy", params={"user_id": seeded_user_id})
    assert response.status_code == 200
    nodes = response.json()

    lv0_nodes = [node for node in nodes if node["total_xp"] == 0]
    assert lv0_nodes, "Expected at least one zero-XP hierarchy node."
    assert all(node["current_level"] == 0 for node in lv0_nodes)
    assert all(node["rank"] is None for node in lv0_nodes)
    assert all(node["current_level_xp"] == 0 for node in lv0_nodes)
    assert all(node["next_level_xp"] > 0 for node in lv0_nodes)


def test_skill_states_endpoint_uses_lv0_for_missing_skill_rows(
    client: TestClient, db_session: Session, seeded_user_id: str
):
    db_session.add(
        UserSkillState(
            user_id=seeded_user_id,
            skill_id="77777777-7777-7777-7777-777777777777",
            state="activated",
        )
    )
    db_session.commit()

    response = client.get(
        "/api/skills/states",
        params={"user_id": seeded_user_id, "include_hidden": True},
    )
    assert response.status_code == 200
    states = response.json()
    assert states

    target = next(
        state
        for state in states
        if state["skill_id"] == "skill_professional_professional_growth"
    )
    assert target["total_xp"] == 0
    assert target["current_level"] == 0
    assert target["rank"] is None


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


def test_themes_endpoint_returns_canonical_order_and_related_skill_counts(
    client: TestClient, seeded_user_id: str
):
    response = client.get("/api/themes", params={"user_id": seeded_user_id})
    assert response.status_code == 200

    themes = response.json()
    assert len(themes) == 12
    assert [row["name"] for row in themes] == list(CANONICAL_THEME_NAMES)

    by_name = {row["name"]: row for row in themes}
    assert by_name["Professional"]["related_skills_count"] == 1
    assert by_name["Professional"]["related_skill_names"] == ["Programming"]
    assert by_name["Physical"]["related_skills_count"] == 0
    assert all("theme_id" in row for row in themes)
    assert all("current_level_xp" in row for row in themes)
    assert all("next_level_xp" in row for row in themes)


def test_themes_endpoint_repairs_missing_skill_theme_mappings_on_read(
    client: TestClient, db_session: Session, seeded_user_id: str
):
    global_skill = GlobalSkill(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        source_skill_id="skill_physical_running",
        canonical_name="Running",
        hierarchy_level=2,
        parent_skill_ids_json='["skill_physical_physical_health"]',
        related_themes_json='["Physical", "Discipline"]',
    )
    db_session.add(global_skill)
    db_session.flush()

    running_skill = Skill(
        id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        user_id=seeded_user_id,
        name="Running",
        canonical_name="running",
        global_skill_id=global_skill.id,
        xp=250,
        level=2,
    )
    db_session.add(running_skill)
    db_session.commit()

    response = client.get("/api/themes", params={"user_id": seeded_user_id})
    assert response.status_code == 200

    themes = response.json()
    by_name = {row["name"]: row for row in themes}

    assert by_name["Physical"]["related_skills_count"] == 1
    assert by_name["Physical"]["related_skill_names"] == ["Running"]
    assert by_name["Discipline"]["related_skills_count"] == 1
    assert by_name["Discipline"]["related_skill_names"] == ["Running"]

    persisted_pairs = {
        (mapping.skill_id, mapping.theme.name)
        for mapping in db_session.query(SkillThemeMapping).all()
        if mapping.theme is not None
    }
    assert (running_skill.id, "Physical") in persisted_pairs
    assert (running_skill.id, "Discipline") in persisted_pairs


def test_themes_endpoint_is_available_on_v1_prefix(
    client: TestClient, seeded_user_id: str
):
    response = client.get("/api/v1/themes", params={"user_id": seeded_user_id})
    assert response.status_code == 200
    themes = response.json()
    assert len(themes) == 12
