"""
Comprehensive quest matcher integration tests.

Tests the full quest matching flow including:
- Instant quest creation and XP apportionment
- Theme XP derivation from skill awards (Section 10.7.3)
- Streak quest contributions and idempotency (Section 10.5.4)
- Learning phase gating (Section 10.3)
- Multi-skill XP distribution (Huntington-Hill)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401 — registers all ORM tables
from src.ai.pipeline_steps.quest_matcher_step import QuestMatcherStep
from src.core.quest_matcher import QuestMatcherService
from src.db.base import Base
from src.db.models.global_kb import GlobalSkill
from src.db.models.journal_entry import JournalEntry
from src.db.models.quest import Quest
from src.db.models.quest_progress import QuestProgress
from src.db.models.skill import Skill, Theme
from src.db.models.user import User
from src.db.models.xp import XpAward

pytestmark = [pytest.mark.integration]

# ── Fixed IDs ──────────────────────────────────────────────────────────────
_USER_ID = "00000000-0000-0000-0000-000000000010"
_SKILL_ID_A = "00000000-0000-0000-0000-000000000011"
_SKILL_ID_B = "00000000-0000-0000-0000-000000000012"
_GLOBAL_SKILL_A_ID = "00000000-0000-0000-0000-000000000013"
_GLOBAL_SKILL_B_ID = "00000000-0000-0000-0000-000000000014"
_THEME_CREATIVE_ID = "00000000-0000-0000-0000-000000000016"
_THEME_INTELLECTUAL_ID = "00000000-0000-0000-0000-000000000017"
_ENTRY_ID = "00000000-0000-0000-0000-000000000015"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session() -> Session:  # type: ignore[misc]
    """Fresh in-memory SQLite DB for each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    LocalSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = LocalSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def test_user(db_session: Session) -> User:
    user = User(
        id=_USER_ID,
        username="questmatcher_user",
        email="questmatcher@example.com",
        password_hash="x",
        home_country="US",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def test_skill_a(db_session: Session, test_user: User) -> Skill:
    """Primary skill — higher weight in tests that use two skills."""
    global_skill = GlobalSkill(
        id=_GLOBAL_SKILL_A_ID,
        source_skill_id="skill_creative_academic_writing",
        canonical_name="Academic Writing",
        category="Creative",
    )
    db_session.add(global_skill)
    db_session.flush()
    skill = Skill(
        id=_SKILL_ID_A,
        user_id=test_user.id,
        name="Academic Writing",
        canonical_name="academic_writing",
        global_skill_id=global_skill.id,
        xp=0,
        level=1,
        rank="F",
    )
    db_session.add(skill)
    db_session.commit()
    return skill


@pytest.fixture()
def test_skill_b(db_session: Session, test_user: User) -> Skill:
    """Secondary skill — lower weight in two-skill tests."""
    global_skill = GlobalSkill(
        id=_GLOBAL_SKILL_B_ID,
        source_skill_id="skill_social_active_listening",
        canonical_name="Active Listening",
        category="Social",
    )
    db_session.add(global_skill)
    db_session.flush()
    skill = Skill(
        id=_SKILL_ID_B,
        user_id=test_user.id,
        name="Active Listening",
        canonical_name="active_listening",
        global_skill_id=global_skill.id,
        xp=0,
        level=1,
        rank="F",
    )
    db_session.add(skill)
    db_session.commit()
    return skill


@pytest.fixture()
def test_themes(db_session: Session, test_user: User) -> dict[str, Theme]:
    """Creative + Intellectual themes for academic_writing derivation."""
    creative = Theme(
        id=_THEME_CREATIVE_ID,
        user_id=test_user.id,
        name="Creative",
        xp=0,
        level=1,
        rank="F",
    )
    intellectual = Theme(
        id=_THEME_INTELLECTUAL_ID,
        user_id=test_user.id,
        name="Intellectual",
        xp=0,
        level=1,
        rank="F",
    )
    db_session.add_all([creative, intellectual])
    db_session.commit()
    return {"Creative": creative, "Intellectual": intellectual}


@pytest.fixture()
def test_entry(db_session: Session, test_user: User, test_skill_a: Skill) -> JournalEntry:
    """Completed journal entry (QuestMatcher requires status='completed')."""
    entry = JournalEntry(
        id=_ENTRY_ID,
        user_id=test_user.id,
        content="Spent two hours on Python, reviewed architecture docs.",
        entry_type="text",
        status="completed",
        question_state="none",
        processed_at=datetime.now(timezone.utc),
    )
    db_session.add(entry)
    db_session.commit()
    return entry


# ── Helpers ────────────────────────────────────────────────────────────────


def _skill_awards(result: dict) -> list[XpAward]:
    return [a for a in result["xp_awards"] if a.distribution_type in ("primary", "secondary")]


def _theme_awards(result: dict) -> list[XpAward]:
    return [a for a in result["xp_awards"] if a.distribution_type == "theme"]


def _skill_total_xp(db_session: Session, user_id: str) -> int:
    return int(
        db_session.query(func.coalesce(func.sum(Skill.xp), 0))
        .filter(Skill.user_id == user_id)
        .scalar()
        or 0
    )


def _theme_total_xp(db_session: Session, user_id: str) -> int:
    return int(
        db_session.query(func.coalesce(func.sum(Theme.xp), 0))
        .filter(Theme.user_id == user_id)
        .scalar()
        or 0
    )


def _write_templates(tmp_path: Path, templates: list[dict]) -> Path:
    path = tmp_path / "quest_templates_v1.json"
    path.write_text(
        json.dumps({"schema_version": 1, "templates": templates}),
        encoding="utf-8",
    )
    return path


def _new_entry(
    db_session: Session,
    test_user: User,
    entry_id: str,
    *,
    processed_at: datetime,
    content: str = "More practice on the same skill.",
) -> JournalEntry:
    entry = JournalEntry(
        id=entry_id,
        user_id=test_user.id,
        content=content,
        entry_type="text",
        status="completed",
        question_state="none",
        processed_at=processed_at,
    )
    db_session.add(entry)
    db_session.commit()
    return entry


def _make_progression_root_skill(db_session: Session, test_user: User) -> Skill:
    global_skill = GlobalSkill(
        id="00000000-0000-0000-0000-000000000901",
        source_skill_id="skill_creative_creativity",
        canonical_name="Creativity",
        category="Creative",
        hierarchy_level=1,
    )
    db_session.add(global_skill)
    db_session.flush()
    skill = Skill(
        id="00000000-0000-0000-0000-000000000902",
        user_id=test_user.id,
        name="Creativity",
        canonical_name="creativity",
        global_skill_id=global_skill.id,
        xp=0,
        level=1,
        rank="F",
    )
    db_session.add(skill)
    db_session.commit()
    return skill


def _seed_global_skill(
    db_session: Session,
    *,
    global_id: str,
    source_skill_id: str,
    canonical_name: str,
    category: str,
) -> GlobalSkill:
    global_skill = GlobalSkill(
        id=global_id,
        source_skill_id=source_skill_id,
        canonical_name=canonical_name,
        category=category,
    )
    db_session.add(global_skill)
    db_session.commit()
    return global_skill


def _seed_running_cardio_globals(db_session: Session) -> dict[str, GlobalSkill]:
    running = _seed_global_skill(
        db_session,
        global_id="00000000-0000-0000-0000-000000000911",
        source_skill_id="skill_physical_running",
        canonical_name="Running",
        category="Physical",
    )
    cardio = _seed_global_skill(
        db_session,
        global_id="00000000-0000-0000-0000-000000000912",
        source_skill_id="skill_physical_cardio_endurance",
        canonical_name="Cardio Endurance",
        category="Physical",
    )
    cardiorespiratory = _seed_global_skill(
        db_session,
        global_id="00000000-0000-0000-0000-000000000913",
        source_skill_id="skill_physical_cardiorespiratory_fitness",
        canonical_name="Cardiorespiratory Fitness",
        category="Physical",
    )
    return {
        "running": running,
        "cardio": cardio,
        "cardiorespiratory": cardiorespiratory,
    }


# ── Tests: Instant quest creation ─────────────────────────────────────────


class TestInstantQuestCreation:
    """Instant quest is created once per entry with correct fields."""

    def test_instant_quest_created_with_correct_fields(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill_a: Skill
    ) -> None:
        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)
        result = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="test_run",
        )

        assert "error" not in result
        quest = result["instant_quest"]
        assert quest is not None
        assert quest.quest_type == "instant"
        assert quest.completion_type == "one_time"
        assert quest.status == "completed"
        assert quest.base_xp == 480
        assert quest.user_id == test_user.id
        assert quest.entry_id == test_entry.id

    def test_instant_quest_persists_completed_progress_row(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill_a: Skill
    ) -> None:
        structured_data = {
            "extraction_confidence_score": 0.80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [],
        }

        result = QuestMatcherStep(db_session).execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="instant_progress_test",
        )

        quest = result["instant_quest"]
        assert quest is not None
        db_session.refresh(quest)

        progress = (
            db_session.query(QuestProgress)
            .filter(QuestProgress.quest_id == quest.id)
            .one()
        )

        assert quest.status == "completed"
        assert quest.current_progress == 1
        assert quest.required_progress == 1
        assert progress.progress_value == 1
        assert progress.required_progress == 1

    def test_instant_quest_assigns_primary_skill(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
        test_skill_b: Skill,
    ) -> None:
        """Primary skill = lex-min skill_id among those with maximum weight_bp."""
        # skill_a has higher weight (6000 > 4000) → should be primary
        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {
                test_skill_a.id: 6000,
                test_skill_b.id: 4000,
            },
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)
        result = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="test_run",
        )

        assert "error" not in result
        # Quest.skill_id is set to the primary skill (max weight)
        assert result["instant_quest"].skill_id == test_skill_a.id

    def test_low_confidence_skips_instant_quest(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill_a: Skill
    ) -> None:
        """confidence_score below threshold → INSTANT_SKIPPED_CONFIDENCE_BELOW_THRESHOLD_instant."""
        # Default threshold is 0.65; pass 0.0 to guarantee failure.
        structured_data = {
            "extraction_confidence_score": 0.0,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)
        result = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="test_run",
        )

        assert "error" not in result
        assert result["instant_quest"] is None
        assert result["total_xp_awarded"] == 0
        assert any("INSTANT_SKIPPED" in n for n in result["notes"])

    def test_activity_source_skills_create_running_primary_and_award_xp(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
    ) -> None:
        globals_by_name = _seed_running_cardio_globals(db_session)
        structured_data = {
            "extraction_confidence_score": 0.80,
            "source_skills_weights_bp": {
                "skill_physical_running": 7000,
                "skill_physical_cardio_endurance": 1500,
                "skill_physical_cardiorespiratory_fitness": 1500,
            },
            "skills_weights_bp": {},
            "resolved_skill_names": [
                "Running",
                "Cardio Endurance",
                "Cardiorespiratory Fitness",
            ],
            "pattern_hits_json": [
                {"semantic_key": "run", "confidence_score": 0.70},
            ],
            "task_type": "physical",
            "primary_action_type": "run",
        }

        result = QuestMatcherStep(db_session).execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="running_source_skill_test",
        )

        assert "error" not in result
        instant_quest = result["instant_quest"]
        assert instant_quest is not None
        assert len(result["streak_quests"]) == 1

        user_skills = (
            db_session.query(Skill)
            .filter(Skill.user_id == test_user.id)
            .order_by(Skill.global_skill_id.asc())
            .all()
        )
        skills_by_global = {skill.global_skill_id: skill for skill in user_skills}
        running_skill = skills_by_global[globals_by_name["running"].id]
        cardio_skill = skills_by_global[globals_by_name["cardio"].id]
        cardiorespiratory_skill = skills_by_global[globals_by_name["cardiorespiratory"].id]

        assert instant_quest.skill_id == running_skill.id
        assert result["streak_quests"][0].semantic_key == "run"
        assert result["streak_quests"][0].skill_id == running_skill.id

        awards = {award.skill_id: award.amount for award in _skill_awards(result)}
        assert set(awards) == {
            running_skill.id,
            cardio_skill.id,
            cardiorespiratory_skill.id,
        }
        assert awards[running_skill.id] > awards[cardio_skill.id]
        assert awards[running_skill.id] > awards[cardiorespiratory_skill.id]
        assert sum(awards.values()) == result["total_xp_awarded"]

    def test_unresolved_activity_signals_skip_without_arbitrary_fallback(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
    ) -> None:
        structured_data = {
            "extraction_confidence_score": 0.80,
            "source_skills_weights_bp": {"skill_unknown_mystery": 10000},
            "skills_weights_bp": {},
            "pattern_hits_json": [
                {"semantic_key": "mystery_activity", "confidence_score": 0.70},
            ],
            "task_type": "physical",
            "primary_action_type": "mystery_activity",
        }

        result = QuestMatcherStep(db_session).execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="unresolved_activity_test",
        )

        assert "error" not in result
        assert result["instant_quest"] is None
        assert result["streak_quests"] == []
        assert result["total_xp_awarded"] == 0
        assert _skill_awards(result) == []
        user_skills = (
            db_session.query(Skill)
            .filter(Skill.user_id == test_user.id)
            .order_by(Skill.id.asc())
            .all()
        )
        assert [skill.id for skill in user_skills] == [test_skill_a.id]
        assert "SKILL_ROUTING_UNRESOLVED" in result["notes"]
        assert "INSTANT_SKIPPED_NO_SKILL" in result["notes"]
        assert "STREAK_SKIPPED_ENSURE_FAILED_mystery_activity" in result["notes"]

    def test_entry_not_completed_returns_error(
        self, db_session: Session, test_user: User, test_skill_a: Skill
    ) -> None:
        """QuestMatcher requires entry.status == 'completed'."""
        pending_entry = JournalEntry(
            id="00000000-0000-0000-0000-000000000099",
            user_id=test_user.id,
            content="Still in progress.",
            entry_type="text",
            status="pending",   # ← NOT completed
            question_state="none",
        )
        db_session.add(pending_entry)
        db_session.commit()

        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [],
        }
        matcher = QuestMatcherService(db_session)
        result = matcher.match_quests_for_entry(
            user=test_user,
            entry=pending_entry,
            structured_data=structured_data,
        )

        assert "error" in result
        assert result["error"] == "ENTRY_NOT_COMPLETED"


# ── Tests: Multi-skill XP distribution (Huntington-Hill) ──────────────────


class TestMultiSkillXPDistribution:
    """XP is distributed across skills by Huntington-Hill apportionment."""

    def test_two_skills_total_xp_equals_final_xp(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
        test_skill_b: Skill,
    ) -> None:
        """Sum of skill XP awards always equals total_xp_awarded."""
        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {
                test_skill_a.id: 6000,
                test_skill_b.id: 4000,
            },
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)
        result = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="test_run",
        )

        assert "error" not in result
        awards = _skill_awards(result)
        total = result["total_xp_awarded"]

        assert len(awards) == 2
        assert sum(a.amount for a in awards) == total

    def test_primary_skill_label_matches_max_weight(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
        test_skill_b: Skill,
    ) -> None:
        """Award with distribution_type='primary' corresponds to the max-weight skill."""
        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {
                test_skill_a.id: 6000,  # higher weight → primary
                test_skill_b.id: 4000,
            },
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)
        result = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="test_run",
        )

        awards = _skill_awards(result)
        primary_awards = [a for a in awards if a.distribution_type == "primary"]
        secondary_awards = [a for a in awards if a.distribution_type == "secondary"]

        assert len(primary_awards) == 1
        assert len(secondary_awards) == 1
        assert primary_awards[0].skill_id == test_skill_a.id
        assert secondary_awards[0].skill_id == test_skill_b.id

    def test_primary_skill_xp_exceeds_secondary_xp(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
        test_skill_b: Skill,
    ) -> None:
        """Higher-weight skill receives proportionally more XP."""
        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {
                test_skill_a.id: 7000,
                test_skill_b.id: 3000,
            },
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)
        result = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="test_run",
        )

        awards = {a.skill_id: a.amount for a in _skill_awards(result)}
        assert awards[test_skill_a.id] > awards[test_skill_b.id]

    def test_xp_awards_idempotent_via_identity_key(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
    ) -> None:
        """Re-running execute() for the same entry returns the same XP award rows."""
        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)

        result1 = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="run_1",
        )
        result2 = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="run_2",
        )

        # Same award amounts returned (idempotent identity key)
        xp1 = {a.skill_id: a.amount for a in _skill_awards(result1)}
        xp2 = {a.skill_id: a.amount for a in _skill_awards(result2)}
        assert xp1 == xp2

        # Only one quest created for the entry
        db_session.commit()
        quest_count = (
            db_session.query(Quest)
            .filter(
                Quest.user_id == test_user.id,
                Quest.entry_id == test_entry.id,
                Quest.quest_type == "instant",
            )
            .count()
        )
        assert quest_count == 1


# ── Tests: Theme XP derivation ─────────────────────────────────────────────


class TestThemeXPDerivation:
    """Theme awards are derived from skill awards via the JSON mapping artifact."""

    def test_theme_awards_created_for_mapped_skill(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
        test_themes: dict,
    ) -> None:
        """academic_writing resolves to Creative + Intellectual theme awards."""
        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)
        result = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="test_run",
        )

        assert "error" not in result
        t_awards = _theme_awards(result)
        assert len(t_awards) >= 1
        assert all(a.amount >= 1 for a in t_awards)

    def test_theme_awards_have_source_traceability(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
        test_themes: dict,
    ) -> None:
        """Each theme award carries source_skill_id and source_skill_xp (Q22)."""
        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)
        result = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="test_run",
        )

        for t_award in _theme_awards(result):
            assert t_award.source_skill_id == test_skill_a.id
            assert t_award.source_skill_xp is not None
            assert t_award.source_skill_xp > 0
            assert t_award.skill_id is None       # theme awards must have null skill_id
            assert t_award.theme_id is not None   # and a real theme_id

    def test_theme_award_amounts_sum_to_skill_xp(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
        test_themes: dict,
    ) -> None:
        """Theme awards apportion the originating skill XP (HH guarantee)."""
        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)
        result = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="test_run",
        )

        skill_xp = result["total_xp_awarded"]  # 480 for single 1.0× run
        t_awards = _theme_awards(result)

        # Theme amounts derived from this skill's XP must sum exactly to that XP
        theme_sum = sum(a.amount for a in t_awards if a.source_skill_id == test_skill_a.id)
        assert theme_sum == skill_xp

    def test_no_theme_awards_without_matching_themes_in_db(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
        # NOTE: test_themes fixture intentionally NOT requested — no Theme rows
    ) -> None:
        """Derivation skips gracefully when user has no matching Theme rows."""
        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)
        result = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="test_run",
        )

        # Skill XP is still awarded; theme derivation silently skips missing themes
        assert result["total_xp_awarded"] == 480
        assert len(_theme_awards(result)) == 0


class TestQuestMatcherProgression:
    """Quest matcher awards must propagate into visible skill/theme totals exactly once."""

    def test_execute_updates_skill_and_theme_progression_totals(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_themes: dict[str, Theme],
    ) -> None:
        progression_skill = _make_progression_root_skill(db_session, test_user)
        structured_data = {
            "extraction_confidence_score": 0.80,
            "skills_weights_bp": {progression_skill.id: 10000},
            "pattern_hits_json": [],
        }
        before_skill_total = _skill_total_xp(db_session, test_user.id)
        before_theme_total = _theme_total_xp(db_session, test_user.id)

        result = QuestMatcherStep(db_session).execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="progression_run_1",
        )

        after_skill_total = _skill_total_xp(db_session, test_user.id)
        after_theme_total = _theme_total_xp(db_session, test_user.id)

        assert result["progression"]["updated_skills"] >= 1
        assert result["progression"]["updated_themes"] >= 1
        assert after_skill_total > before_skill_total
        assert after_theme_total > before_theme_total
        assert after_skill_total - before_skill_total == result["total_xp_awarded"]

    def test_execute_does_not_double_apply_progression_on_replay(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_themes: dict[str, Theme],
    ) -> None:
        progression_skill = _make_progression_root_skill(db_session, test_user)
        structured_data = {
            "extraction_confidence_score": 0.80,
            "skills_weights_bp": {progression_skill.id: 10000},
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)

        first = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="progression_run_1",
        )
        after_first_skill_total = _skill_total_xp(db_session, test_user.id)
        after_first_theme_total = _theme_total_xp(db_session, test_user.id)

        second = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="progression_run_2",
        )
        after_second_skill_total = _skill_total_xp(db_session, test_user.id)
        after_second_theme_total = _theme_total_xp(db_session, test_user.id)

        assert first["progression"]["updated_skills"] >= 1
        assert second["progression"]["updated_skills"] == 0
        assert second["progression"]["updated_themes"] == 0
        assert after_second_skill_total == after_first_skill_total
        assert after_second_theme_total == after_first_theme_total


# ── Tests: Streak quest contributions ─────────────────────────────────────


class TestStreakQuestContributions:
    """Streak quests are created/updated by pattern hits in structured_data."""

    def test_streak_quest_created_for_pattern_hit(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill_a: Skill
    ) -> None:
        """A pattern hit with sufficient confidence creates a streak quest."""
        # Mark learning phase complete so confidence gate is not applied
        test_user.learning_phase_complete = True
        db_session.commit()

        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [
                {"semantic_key": "daily_coding", "confidence_score": 0.75},
            ],
        }
        matcher = QuestMatcherService(db_session)
        result = matcher.match_quests_for_entry(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
        )

        assert "error" not in result
        assert len(result["streak_quests"]) == 1
        streak = result["streak_quests"][0]
        assert streak.quest_type == "longterm"
        assert streak.completion_type == "streak"
        assert streak.status == "active"
        assert streak.semantic_key == "daily_coding"

    def test_streak_contributions_idempotent(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill_a: Skill
    ) -> None:
        """Re-processing the same entry for the same day is a safe no-op.

        The UNIQUE constraint on (user_id, quest_id, local_date) prevents
        double-counting streak progress (Section 10.5.4).
        """
        test_user.learning_phase_complete = True
        db_session.commit()

        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [
                {"semantic_key": "daily_meditation", "confidence_score": 0.75},
                {"semantic_key": "morning_exercise", "confidence_score": 0.65},
            ],
        }
        matcher = QuestMatcherService(db_session)

        # First pass
        result1 = matcher.match_quests_for_entry(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
        )
        ids1 = [q.id for q in result1["streak_quests"]]

        # Second pass (same entry, same day)
        result2 = matcher.match_quests_for_entry(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
        )
        ids2 = [q.id for q in result2["streak_quests"]]

        # Same quests returned, no duplicates created
        assert len(result1["streak_quests"]) == len(result2["streak_quests"])
        assert set(ids1) == set(ids2)

    def test_streak_quest_normalized_semantic_key(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill_a: Skill
    ) -> None:
        """Semantic key is normalised to snake_case (spaces → underscores, lowercase)."""
        test_user.learning_phase_complete = True
        db_session.commit()

        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [
                {"semantic_key": "Daily Coding", "confidence_score": 0.80},
            ],
        }
        matcher = QuestMatcherService(db_session)
        result = matcher.match_quests_for_entry(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
        )

        assert len(result["streak_quests"]) == 1
        assert result["streak_quests"][0].semantic_key == "daily_coding"

    def test_multiple_pattern_hits_create_multiple_streak_quests(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill_a: Skill
    ) -> None:
        """Each unique semantic key gets its own streak quest."""
        test_user.learning_phase_complete = True
        db_session.commit()

        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [
                {"semantic_key": "yoga_practice", "confidence_score": 0.80},
                {"semantic_key": "book_reading", "confidence_score": 0.70},
                {"semantic_key": "journal_writing", "confidence_score": 0.75},
            ],
        }
        matcher = QuestMatcherService(db_session)
        result = matcher.match_quests_for_entry(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
        )

        assert len(result["streak_quests"]) == 3
        keys = {q.semantic_key for q in result["streak_quests"]}
        assert keys == {"yoga_practice", "book_reading", "journal_writing"}

    def test_streak_confidence_gate_during_learning_phase(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill_a: Skill
    ) -> None:
        """During learning phase, low-confidence pattern hits are skipped."""
        # learning_phase_complete=False by default
        assert not test_user.learning_phase_complete

        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [
                # confidence_score=0.3 < default streak threshold 0.55 → skipped
                {"semantic_key": "low_confidence_habit", "confidence_score": 0.3},
                # confidence_score=0.70 >= 0.55 → allowed
                {"semantic_key": "high_confidence_habit", "confidence_score": 0.70},
            ],
        }
        matcher = QuestMatcherService(db_session)
        result = matcher.match_quests_for_entry(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
        )

        assert len(result["streak_quests"]) == 1
        assert result["streak_quests"][0].semantic_key == "high_confidence_habit"
        assert any("STREAK_SKIPPED_CONFIDENCE" in n for n in result["notes"])


# ── Tests: Learning phase gating ──────────────────────────────────────────


class TestLearningPhaseGating:
    """Learning phase blocks cumulative/recursive but allows instant and streak."""

    def test_instant_quest_allowed_during_learning_phase(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill_a: Skill
    ) -> None:
        """Instant (one_time) quests are always allowed, even during learning."""
        assert not test_user.learning_phase_complete  # sanity check — default False

        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)
        result = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="learning_phase_test",
        )

        assert "error" not in result
        assert result["instant_quest"] is not None
        assert result["instant_quest"].completion_type == "one_time"
        assert result["total_xp_awarded"] == 480

    def test_streak_quest_allowed_during_learning_phase_if_confidence_passes(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill_a: Skill
    ) -> None:
        """Streak quests are allowed during learning phase when confidence ≥ threshold."""
        assert not test_user.learning_phase_complete

        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [
                # 0.70 >= default streak threshold 0.55 → allowed
                {"semantic_key": "daily_journaling", "confidence_score": 0.70},
            ],
        }
        matcher = QuestMatcherService(db_session)
        result = matcher.match_quests_for_entry(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
        )

        assert "error" not in result
        assert result["instant_quest"] is not None  # instant always allowed
        assert len(result["streak_quests"]) == 1    # streak allowed with sufficient confidence

    def test_learning_complete_unlocks_higher_confidence_threshold_quests(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill_a: Skill
    ) -> None:
        """After learning phase is marked complete, confidence gate is not checked."""
        test_user.learning_phase_complete = True
        db_session.commit()

        # confidence_score=0.3 would fail the streak gate during learning phase
        # but passes freely when learning is complete
        structured_data = {
            "extraction_confidence_score": 80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [
                {"semantic_key": "low_confidence_habit", "confidence_score": 0.3},
            ],
        }
        matcher = QuestMatcherService(db_session)
        result = matcher.match_quests_for_entry(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
        )

        # No confidence filtering after learning phase is complete
        assert len(result["streak_quests"]) == 1
        assert result["streak_quests"][0].semantic_key == "low_confidence_habit"


class TestWeek7LongtermBehavior:
    def test_streak_progress_completes_after_new_local_day(
        self,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
    ) -> None:
        test_user.learning_phase_complete = True
        db_session.commit()

        matcher = QuestMatcherService(db_session)
        structured_data = {
            "extraction_confidence_score": 0.80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [
                {"semantic_key": "daily_writing", "confidence_score": 0.80},
            ],
        }

        result1 = matcher.match_quests_for_entry(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
        )
        streak = result1["streak_quests"][0]
        progress = (
            db_session.query(QuestProgress)
            .filter(QuestProgress.quest_id == streak.id)
            .one()
        )
        streak.required_progress = 2
        progress.required_progress = 2
        db_session.commit()

        matcher.match_quests_for_entry(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
        )
        db_session.refresh(streak)
        assert streak.current_progress == 1

        next_entry = _new_entry(
            db_session,
            test_user,
            "00000000-0000-0000-0000-000000000120",
            processed_at=test_entry.processed_at + timedelta(days=1),
        )
        result2 = matcher.match_quests_for_entry(
            user=test_user,
            entry=next_entry,
            structured_data=structured_data,
        )

        db_session.refresh(streak)
        db_session.refresh(progress)
        assert any(quest.id == streak.id for quest in result2["completed_quests"])
        assert streak.status == "completed"
        assert streak.current_progress == 2
        assert progress.progress_value == 2

    def test_cumulative_template_creates_progresses_and_completes(
        self,
        tmp_path: Path,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
    ) -> None:
        test_user.learning_phase_complete = True
        db_session.commit()

        templates_path = _write_templates(
            tmp_path,
            [
                {
                    "template_key": "cumulative_academic_writing",
                    "skill_semantic_key": "skill_creative_academic_writing",
                    "quest_kind": "cumulative",
                    "min_confidence": 65,
                    "max_active": 1,
                    "cooldown_days": 0,
                    "target_range": {"min": 2, "max": 2},
                    "signals_required": ["has_pattern_hit"],
                    "predicate": {"field": "has_pattern_hit", "op": "eq", "value": True},
                    "delta_rule": {"type": "fixed", "delta": 1},
                    "target_select_rule": "min",
                    "score_weights_bp": {
                        "extraction_confidence_score": 6000,
                        "skill_weight_match": 4000,
                    },
                }
            ],
        )
        matcher = QuestMatcherService(db_session, templates_path=str(templates_path))
        structured_data = {
            "extraction_confidence_score": 0.80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [
                {"semantic_key": "writing_session", "confidence_score": 0.80},
            ],
        }

        result1 = matcher.match_quests_for_entry(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
        )
        quest = next(
            quest for quest in result1["created_quests"] if quest.completion_type == "cumulative"
        )
        assert quest.status == "active"
        assert quest.current_progress == 1

        next_entry = _new_entry(
            db_session,
            test_user,
            "00000000-0000-0000-0000-000000000121",
            processed_at=test_entry.processed_at + timedelta(days=1),
        )
        result2 = matcher.match_quests_for_entry(
            user=test_user,
            entry=next_entry,
            structured_data=structured_data,
        )

        db_session.refresh(quest)
        assert any(item.id == quest.id for item in result2["completed_quests"])
        assert quest.status == "completed"
        assert quest.current_progress == 2

    def test_recursive_completion_creates_successor(
        self,
        tmp_path: Path,
        db_session: Session,
        test_user: User,
        test_entry: JournalEntry,
        test_skill_a: Skill,
    ) -> None:
        test_user.learning_phase_complete = True
        db_session.commit()

        templates_path = _write_templates(
            tmp_path,
            [
                {
                    "template_key": "recursive_academic_writing",
                    "skill_semantic_key": "skill_creative_academic_writing",
                    "quest_kind": "recursive",
                    "min_confidence": 65,
                    "max_active": 1,
                    "cooldown_days": 0,
                    "target_range": {"min": 1, "max": 1},
                    "signals_required": ["has_pattern_hit"],
                    "predicate": {"field": "has_pattern_hit", "op": "eq", "value": True},
                    "delta_rule": {"type": "fixed", "delta": 1},
                    "target_select_rule": "min",
                    "score_weights_bp": {
                        "extraction_confidence_score": 6000,
                        "skill_weight_match": 4000,
                    },
                }
            ],
        )
        matcher = QuestMatcherService(db_session, templates_path=str(templates_path))
        structured_data = {
            "extraction_confidence_score": 0.80,
            "skills_weights_bp": {test_skill_a.id: 10000},
            "pattern_hits_json": [
                {"semantic_key": "writing_session", "confidence_score": 0.80},
            ],
        }

        result = matcher.match_quests_for_entry(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
        )

        completed_recursive = next(
            quest for quest in result["completed_quests"] if quest.completion_type == "recursive"
        )
        successor = (
            db_session.query(Quest)
            .filter(
                Quest.user_id == test_user.id,
                Quest.successor_key == f"{completed_recursive.id}:successor",
            )
            .one()
        )

        assert completed_recursive.status == "completed"
        assert successor.status == "active"
        assert successor.template_quest_type == completed_recursive.template_quest_type
