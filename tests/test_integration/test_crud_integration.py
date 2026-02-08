"""
Comprehensive integration tests for all CRUD operations working together.

This module tests the complete CRUD layer end-to-end, verifying:
- All CRUD functions work correctly in a realistic user journey
- Data flows correctly between CRUD modules
- Schema validation works as expected
- Cascade delete properly removes all related records via CRUD layer
"""
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError  # type: ignore[import-not-found]
from sqlalchemy.exc import IntegrityError

# Import all CRUD modules
from app.crud import user as user_crud
from app.crud import theme as theme_crud
from app.crud import skill as skill_crud
from app.crud import title as title_crud
from app.crud import mission_quest as mq_crud
from app.crud import journal as journal_crud
from app.crud import user_stats as stats_crud

# Import all schema modules
from app.schemas.user import UserCreate
from app.schemas.theme import ThemeCreate
from app.schemas.skill import SkillCreate
from app.schemas.title import TitleTemplateCreate, UserTitleCreate
from app.schemas.mission_quest import MQTemplateCreate, UserMQCreate, UserMQUpdate
from app.schemas.journal import JournalEntryCreate
from app.schemas.user_stats import UserStatsCreate

# Import models for verification queries
from app.models.user import User
from app.models.theme import Theme
from app.models.skill import Skill
from app.models.title import TitleTemplate, UserTitle
from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest
from app.models.journal_entry import JournalEntry
from app.models.user_stats import UserStats


class TestFullCRUDIntegration:
    """Test all CRUD operations working together as a complete system."""

    def test_full_crud_flow_create_character_and_journal(self, db_session, fake):
        """
        Test a complete user journey using only CRUD functions.

        This test creates a full "character sheet" and exercises all CRUD layers:
        1. Create user (user CRUD)
        2. Create user stats for user (stats CRUD)
        3. Create 2 themes for user (theme CRUD)
        4. Create 3 skills (2 under theme 1, 1 standalone) (skill CRUD)
        5. Create title template (title CRUD)
        6. Award title to user (title CRUD)
        7. Equip the title (title CRUD)
        8. Create MQ template (mq CRUD)
        9. Create user MQ from template (mq CRUD)
        10. Create journal entry (journal CRUD)
        11. Add practice time to skill 1 via CRUD
        12. Add XP to theme 1 via CRUD
        13. Update MQ progress to 50
        14. Mark journal entry as AI processed
        15. Get user with all relationships and verify counts
        16. Delete user and verify cascade
        """
        # =================================================================
        # STEP 1: Create User via CRUD
        # =================================================================
        user_data = UserCreate(
            username=fake.user_name(),
            email=fake.email()
        )
        user = user_crud.create_user(db_session, user_data)

        assert user is not None
        assert user.id is not None
        assert len(user.id) == 36  # UUID format
        assert user.username == user_data.username
        assert user.email == user_data.email
        assert user.is_active is True

        # Verify we can retrieve the user
        retrieved_user = user_crud.get_user(db_session, user.id)
        assert retrieved_user is not None
        assert retrieved_user.id == user.id

        # =================================================================
        # STEP 2: Create UserStats for user via CRUD
        # =================================================================
        stats_data = UserStatsCreate(
            user_id=user.id,
            hp=95,
            mp=85,
            mental_health=75,
            physical_health=80,
            relationship_quality=60,
            socialization_level=55
        )
        user_stats = stats_crud.create_user_stats(db_session, stats_data)

        assert user_stats is not None
        assert user_stats.user_id == user.id
        assert user_stats.hp == 95
        assert user_stats.mp == 85

        # Verify we can retrieve stats
        retrieved_stats = stats_crud.get_user_stats(db_session, user.id)
        assert retrieved_stats is not None
        assert retrieved_stats.hp == 95

        # =================================================================
        # STEP 3: Create 2 Themes for user via CRUD
        # =================================================================
        theme1_data = ThemeCreate(
            user_id=user.id,
            name="Career Development",
            description="Professional growth and work skills"
        )
        theme1 = theme_crud.create_theme(db_session, theme1_data)

        theme2_data = ThemeCreate(
            user_id=user.id,
            name="Health & Wellness",
            description="Physical and mental health"
        )
        theme2 = theme_crud.create_theme(db_session, theme2_data)

        assert theme1 is not None
        assert theme2 is not None
        assert theme1.user_id == user.id
        assert theme2.user_id == user.id

        # Verify we can retrieve themes
        user_themes = theme_crud.get_user_themes(db_session, user.id)
        assert len(user_themes) == 2

        # =================================================================
        # STEP 4: Create 3 Skills (2 under theme1, 1 standalone)
        # =================================================================
        skill1_data = SkillCreate(
            user_id=user.id,
            theme_id=theme1.id,
            name="Python Programming",
            description="Backend development with Python",
            difficulty="Hard"
        )
        skill1 = skill_crud.create_skill(db_session, skill1_data)

        skill2_data = SkillCreate(
            user_id=user.id,
            theme_id=theme1.id,
            name="Project Management",
            description="Managing projects and teams",
            difficulty="Medium"
        )
        skill2 = skill_crud.create_skill(db_session, skill2_data)

        skill3_data = SkillCreate(
            user_id=user.id,
            theme_id=None,  # Standalone skill
            name="Communication",
            description="Verbal and written communication",
            difficulty="Medium"
        )
        skill3 = skill_crud.create_skill(db_session, skill3_data)

        assert skill1.theme_id == theme1.id
        assert skill2.theme_id == theme1.id
        assert skill3.theme_id is None

        # Verify theme skills
        theme1_skills = skill_crud.get_theme_skills(db_session, theme1.id)
        assert len(theme1_skills) == 2

        # Verify user skills
        user_skills = skill_crud.get_user_skills(db_session, user.id)
        assert len(user_skills) == 3

        # =================================================================
        # STEP 5: Create Title Template via CRUD
        # =================================================================
        title_template_data = TitleTemplateCreate(
            name="Code Warrior",
            description_template="{user_name} is a master of code",
            effect={"type": "xp_multiplier", "scope": "skill", "value": 1.15},
            rank="B",
            unlock_condition={"type": "skill_level", "skill": "Python", "value": 10},
            category="Skills",
            is_hidden=False
        )
        title_template = title_crud.create_title_template(db_session, title_template_data)

        assert title_template is not None
        assert title_template.name == "Code Warrior"
        assert title_template.rank == "B"

        # Verify we can retrieve the template
        retrieved_template = title_crud.get_title_template(db_session, title_template.id)
        assert retrieved_template is not None

        # =================================================================
        # STEP 6: Award Title to User via CRUD
        # =================================================================
        user_title_data = UserTitleCreate(
            user_id=user.id,
            title_template_id=title_template.id,
            is_equipped=False,
            personalized_description=f"{user.username} is a master of code"
        )
        user_title = title_crud.award_title_to_user(db_session, user_title_data)

        assert user_title is not None
        assert user_title.user_id == user.id
        assert user_title.title_template_id == title_template.id
        assert user_title.is_equipped is False
        assert user_title.acquired_at is not None

        # =================================================================
        # STEP 7: Equip the Title via CRUD
        # =================================================================
        equipped_title = title_crud.equip_title(db_session, user_title.id)

        assert equipped_title is not None
        assert equipped_title.is_equipped is True

        # Verify equipped titles query
        equipped_titles = title_crud.get_user_titles(db_session, user.id, equipped_only=True)
        assert len(equipped_titles) == 1

        # =================================================================
        # STEP 8: Create MQ Template via CRUD
        # =================================================================
        mq_template_data = MQTemplateCreate(
            name="Learn a Framework",
            description_template="{user_name} must master a new framework",
            type="story_arc",
            structure="multi_part",
            completion_condition={"type": "accumulation", "target": 100},
            reward_xp=500,
            reward_coins=50,
            difficulty="hard",
            category="Learning"
        )
        mq_template = mq_crud.create_mq_template(db_session, mq_template_data)

        assert mq_template is not None
        assert mq_template.name == "Learn a Framework"
        assert mq_template.reward_xp == 500

        # Verify we can retrieve by type
        story_arc_templates = mq_crud.get_mq_templates_by_type(db_session, "story_arc")
        assert len(story_arc_templates) >= 1

        # =================================================================
        # STEP 9: Create User MQ from Template via CRUD
        # =================================================================
        user_mq_data = UserMQCreate(
            user_id=user.id,
            template_id=mq_template.id,
            name="Learn FastAPI",
            personalized_description=f"{user.username} will master FastAPI",
            status="in_progress",
            completion_target=100
        )
        user_mq = mq_crud.create_user_mq(db_session, user_mq_data)

        assert user_mq is not None
        assert user_mq.user_id == user.id
        assert user_mq.template_id == mq_template.id
        assert user_mq.status == "in_progress"
        assert user_mq.completion_progress == 0

        # =================================================================
        # STEP 10: Create Journal Entry via CRUD
        # =================================================================
        journal_data = JournalEntryCreate(
            user_id=user.id,
            content="Today I made great progress learning FastAPI. "
                    "I completed the routing chapter and built my first endpoint. "
                    "Feeling accomplished and motivated!",
            entry_type="text"
        )
        journal_entry = journal_crud.create_journal_entry(db_session, journal_data)

        assert journal_entry is not None
        assert journal_entry.user_id == user.id
        assert journal_entry.ai_processed is False
        assert journal_entry.created_at is not None

        # Verify we can retrieve entries
        user_entries = journal_crud.get_user_journal_entries(db_session, user.id)
        assert len(user_entries) == 1

        # =================================================================
        # STEP 11: Add Practice Time to Skill 1 via CRUD
        # =================================================================
        initial_practice_time = skill1.practice_time_minutes
        initial_xp = skill1.xp

        updated_skill1 = skill_crud.add_practice_time(db_session, skill1.id, 60)

        assert updated_skill1 is not None
        assert updated_skill1.practice_time_minutes == initial_practice_time + 60
        # Practice time adds XP: 60 * 0.5 = 30 XP
        assert updated_skill1.xp > initial_xp

        # =================================================================
        # STEP 12: Add XP to Theme 1 via CRUD
        # =================================================================
        initial_theme_xp = theme1.xp
        initial_theme_level = theme1.level

        updated_theme1 = theme_crud.add_xp_to_theme(db_session, theme1.id, 100.0)

        assert updated_theme1 is not None
        assert updated_theme1.xp >= 0  # XP may have reset if level up occurred
        # Either XP increased or level increased (due to level-up)
        assert updated_theme1.xp > initial_theme_xp or updated_theme1.level > initial_theme_level

        # =================================================================
        # STEP 13: Update MQ Progress to 50 via CRUD
        # =================================================================
        mq_update = UserMQUpdate(completion_progress=50)
        updated_mq = mq_crud.update_user_mq(db_session, user_mq.id, mq_update)

        assert updated_mq is not None
        assert updated_mq.completion_progress == 50

        # Also test update_mq_progress function
        updated_mq2 = mq_crud.update_mq_progress(db_session, user_mq.id, 75)
        assert updated_mq2 is not None
        assert updated_mq2.completion_progress == 75

        # =================================================================
        # STEP 14: Mark Journal Entry as AI Processed via CRUD
        # =================================================================
        ai_categories = {
            "themes": ["Career Development"],
            "skills": ["Python Programming"],
            "sentiment": "positive",
            "energy_level": "high"
        }
        processed_entry = journal_crud.mark_as_ai_processed(
            db_session, journal_entry.id, ai_categories
        )

        assert processed_entry is not None
        assert processed_entry.ai_processed is True
        assert processed_entry.ai_categories["sentiment"] == "positive"
        assert "Career Development" in processed_entry.ai_categories["themes"]

        # =================================================================
        # STEP 15: Verify All Relationships via Query
        # =================================================================
        db_session.refresh(user)

        # Verify counts via relationships
        assert len(user.themes) == 2
        assert len(user.skills) == 3
        assert len(user.user_titles) == 1
        assert len(user.user_mq) == 1
        assert len(user.journal_entries) == 1
        assert user.stats is not None

        # Verify theme -> skills relationship
        db_session.refresh(theme1)
        assert len(theme1.skills) == 2

        # Verify title template -> user titles relationship
        db_session.refresh(title_template)
        assert len(title_template.user_titles) == 1

        # Verify MQ template -> user MQ relationship
        db_session.refresh(mq_template)
        assert len(mq_template.user_mq) == 1

        # =================================================================
        # STEP 16: Delete User and Verify Cascade
        # =================================================================
        # Store IDs for verification after deletion
        user_id = user.id
        theme1_id = theme1.id
        theme2_id = theme2.id
        skill1_id = skill1.id
        skill2_id = skill2.id
        skill3_id = skill3.id
        user_title_id = user_title.id
        user_mq_id = user_mq.id
        journal_entry_id = journal_entry.id
        user_stats_id = user_stats.id

        # Templates should NOT be deleted (global resources)
        title_template_id = title_template.id
        mq_template_id = mq_template.id

        # Delete user via CRUD
        delete_result = user_crud.delete_user(db_session, user.id)
        assert delete_result is True

        # Verify user is deleted
        deleted_user = user_crud.get_user(db_session, user_id)
        assert deleted_user is None

        # Verify all user-owned entities are cascade deleted
        assert db_session.query(Theme).filter(Theme.id == theme1_id).first() is None
        assert db_session.query(Theme).filter(Theme.id == theme2_id).first() is None
        assert db_session.query(Skill).filter(Skill.id == skill1_id).first() is None
        assert db_session.query(Skill).filter(Skill.id == skill2_id).first() is None
        assert db_session.query(Skill).filter(Skill.id == skill3_id).first() is None
        assert db_session.query(UserTitle).filter(UserTitle.id == user_title_id).first() is None
        assert db_session.query(UserMissionQuest).filter(UserMissionQuest.id == user_mq_id).first() is None
        assert db_session.query(JournalEntry).filter(JournalEntry.id == journal_entry_id).first() is None
        assert db_session.query(UserStats).filter(UserStats.id == user_stats_id).first() is None

        # Verify templates are NOT deleted (global resources)
        remaining_title_template = title_crud.get_title_template(db_session, title_template_id)
        assert remaining_title_template is not None
        assert remaining_title_template.name == "Code Warrior"

        remaining_mq_template = mq_crud.get_mq_template(db_session, mq_template_id)
        assert remaining_mq_template is not None
        assert remaining_mq_template.name == "Learn a Framework"

        # Verify template relationships are cleared
        db_session.refresh(remaining_title_template)
        db_session.refresh(remaining_mq_template)
        assert len(remaining_title_template.user_titles) == 0
        assert len(remaining_mq_template.user_mq) == 0

    def test_multi_user_isolation_across_crud(self, db_session, fake):
        user1 = user_crud.create_user(
            db_session,
            UserCreate(username=fake.user_name(), email=fake.email()),
        )
        user2 = user_crud.create_user(
            db_session,
            UserCreate(username=fake.user_name(), email=fake.email()),
        )
        assert user1 is not None
        assert user2 is not None

        stats_crud.create_user_stats(db_session, UserStatsCreate(user_id=user1.id))
        stats_crud.create_user_stats(db_session, UserStatsCreate(user_id=user2.id))

        theme1 = theme_crud.create_theme(
            db_session,
            ThemeCreate(user_id=user1.id, name="Focus", description="User1"),
        )
        theme2 = theme_crud.create_theme(
            db_session,
            ThemeCreate(user_id=user2.id, name="Focus", description="User2"),
        )

        skill1 = skill_crud.create_skill(
            db_session,
            SkillCreate(user_id=user1.id, theme_id=theme1.id, name="Python"),
        )
        skill2 = skill_crud.create_skill(
            db_session,
            SkillCreate(user_id=user2.id, theme_id=theme2.id, name="Python"),
        )

        journal_crud.create_journal_entry(
            db_session,
            JournalEntryCreate(user_id=user1.id, content="User1 entry"),
        )
        journal_crud.create_journal_entry(
            db_session,
            JournalEntryCreate(user_id=user2.id, content="User2 entry"),
        )

        assert len(theme_crud.get_user_themes(db_session, user1.id)) == 1
        assert len(theme_crud.get_user_themes(db_session, user2.id)) == 1
        assert theme_crud.get_user_themes(db_session, user1.id)[0].id == theme1.id
        assert theme_crud.get_user_themes(db_session, user2.id)[0].id == theme2.id

        assert len(skill_crud.get_user_skills(db_session, user1.id)) == 1
        assert len(skill_crud.get_user_skills(db_session, user2.id)) == 1
        assert skill_crud.get_user_skills(db_session, user1.id)[0].id == skill1.id
        assert skill_crud.get_user_skills(db_session, user2.id)[0].id == skill2.id

        assert len(journal_crud.get_user_journal_entries(db_session, user1.id)) == 1
        assert len(journal_crud.get_user_journal_entries(db_session, user2.id)) == 1

    def test_theme_and_skill_hierarchy_fetch(self, db_session, fake):
        user = user_crud.create_user(
            db_session,
            UserCreate(username=fake.user_name(), email=fake.email()),
        )
        assert user is not None

        parent_theme = theme_crud.create_theme(
            db_session,
            ThemeCreate(user_id=user.id, name="Parent", description=""),
        )
        child_theme = theme_crud.create_theme(
            db_session,
            ThemeCreate(
                user_id=user.id,
                name="Child",
                description="",
                parent_theme_id=parent_theme.id,
            ),
        )

        parent_skill = skill_crud.create_skill(
            db_session,
            SkillCreate(user_id=user.id, theme_id=parent_theme.id, name="Parent Skill"),
        )
        child_skill = skill_crud.create_skill(
            db_session,
            SkillCreate(
                user_id=user.id,
                theme_id=parent_theme.id,
                name="Child Skill",
                parent_skill_id=parent_skill.id,
            ),
        )

        fetched_theme = theme_crud.get_theme_with_subthemes(db_session, parent_theme.id)
        assert fetched_theme is not None
        assert len(fetched_theme.sub_themes) == 1
        assert fetched_theme.sub_themes[0].id == child_theme.id

        fetched_skill = skill_crud.get_skill_with_children(db_session, parent_skill.id)
        assert fetched_skill is not None
        assert len(fetched_skill.child_skills) == 1
        assert fetched_skill.child_skills[0].id == child_skill.id

    def test_journal_pagination_and_ordering(self, db_session, fake):
        user = user_crud.create_user(
            db_session,
            UserCreate(username=fake.user_name(), email=fake.email()),
        )
        assert user is not None

        entry_old = journal_crud.create_journal_entry(
            db_session,
            JournalEntryCreate(user_id=user.id, content="Old"),
        )
        entry_mid = journal_crud.create_journal_entry(
            db_session,
            JournalEntryCreate(user_id=user.id, content="Mid"),
        )
        entry_new = journal_crud.create_journal_entry(
            db_session,
            JournalEntryCreate(user_id=user.id, content="New"),
        )

        entry_old.created_at = datetime.utcnow() - timedelta(days=3)
        entry_mid.created_at = datetime.utcnow() - timedelta(days=2)
        entry_new.created_at = datetime.utcnow() - timedelta(days=1)
        db_session.commit()

        all_entries = journal_crud.get_user_journal_entries(db_session, user.id)
        assert [e.id for e in all_entries[:3]] == [entry_new.id, entry_mid.id, entry_old.id]

        page1 = journal_crud.get_user_journal_entries(db_session, user.id, limit=2)
        page2 = journal_crud.get_user_journal_entries(db_session, user.id, skip=2, limit=2)
        assert [e.id for e in page1] == [entry_new.id, entry_mid.id]
        assert [e.id for e in page2] == [entry_old.id]

    def test_recent_entries_filter(self, db_session, fake):
        user = user_crud.create_user(
            db_session,
            UserCreate(username=fake.user_name(), email=fake.email()),
        )
        assert user is not None
        recent_entry = journal_crud.create_journal_entry(
            db_session,
            JournalEntryCreate(user_id=user.id, content="Recent"),
        )
        old_entry = journal_crud.create_journal_entry(
            db_session,
            JournalEntryCreate(user_id=user.id, content="Old"),
        )

        recent_entry.created_at = datetime.utcnow() - timedelta(days=1)
        old_entry.created_at = datetime.utcnow() - timedelta(days=10)
        db_session.commit()

        recent = journal_crud.get_recent_entries(db_session, user.id, days=7)
        assert [e.id for e in recent] == [recent_entry.id]

    def test_mq_update_progress_and_complete(self, db_session, fake):
        user = user_crud.create_user(
            db_session,
            UserCreate(username=fake.user_name(), email=fake.email()),
        )
        assert user is not None
        template = mq_crud.create_mq_template(
            db_session,
            MQTemplateCreate(
                name="Daily Task",
                description_template="Task",
                type="daily",
                structure="single_action",
                completion_condition={"type": "yes_no"},
            ),
        )
        quest = mq_crud.create_user_mq(
            db_session,
            UserMQCreate(
                user_id=user.id,
                template_id=template.id,
                name="Daily Task",
                status="in_progress",
                completion_target=100,
            ),
        )

        updated = mq_crud.update_mq_progress(db_session, quest.id, 120)
        assert updated is not None
        assert updated.completion_progress == 120

        completed = mq_crud.complete_user_mq(db_session, quest.id)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.completed_at is not None

    def test_user_title_equip_unequip_and_remove(self, db_session, fake):
        user = user_crud.create_user(
            db_session,
            UserCreate(username=fake.user_name(), email=fake.email()),
        )
        assert user is not None
        template = title_crud.create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Consistency",
                description_template="Desc",
                effect={"type": "xp_multiplier", "value": 1.1},
                rank="C",
                unlock_condition={"type": "journal_streak", "value": 3},
                category="Habits",
            ),
        )
        awarded = title_crud.award_title_to_user(
            db_session,
            UserTitleCreate(user_id=user.id, title_template_id=template.id),
        )

        unequipped = title_crud.unequip_title(db_session, awarded.id)
        assert unequipped is not None
        assert unequipped.is_equipped is False

        equipped = title_crud.equip_title(db_session, awarded.id)
        assert equipped is not None
        assert equipped.is_equipped is True

        assert len(title_crud.get_user_titles(db_session, user.id, equipped_only=True)) == 1
        assert title_crud.remove_user_title(db_session, awarded.id) is True
        assert title_crud.get_user_title(db_session, awarded.id) is None

    def test_schema_validation_rejects_extra_fields(self):
        schemas = [
            (UserCreate, {"username": "user1", "email": "user1@example.com", "extra": 1}),
            (
                ThemeCreate,
                {
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "name": "Theme",
                    "extra": 1,
                },
            ),
            (
                SkillCreate,
                {
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "name": "Skill",
                    "extra": 1,
                },
            ),
            (
                TitleTemplateCreate,
                {
                    "name": "Title",
                    "description_template": "Desc",
                    "extra": 1,
                },
            ),
            (
                MQTemplateCreate,
                {
                    "name": "Quest",
                    "description_template": "Desc",
                    "type": "daily",
                    "structure": "single_action",
                    "extra": 1,
                },
            ),
            (
                JournalEntryCreate,
                {
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "content": "Entry",
                    "extra": 1,
                },
            ),
            (
                UserStatsCreate,
                {
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "extra": 1,
                },
            ),
        ]

        for schema_class, payload in schemas:
            with pytest.raises(ValidationError):
                schema_class(**payload)

    def test_schema_validation_rejects_invalid_uuids(self):
        invalid_payloads = [
            (ThemeCreate, {"user_id": "bad", "name": "Theme"}),
            (SkillCreate, {"user_id": "bad", "name": "Skill"}),
            (UserTitleCreate, {"user_id": "bad", "title_template_id": "bad"}),
            (UserMQCreate, {"user_id": "bad", "name": "Quest"}),
            (JournalEntryCreate, {"user_id": "bad", "content": "Entry"}),
        ]

        for schema_class, payload in invalid_payloads:
            with pytest.raises(ValidationError):
                schema_class(**payload)

    def test_schema_validation_allows_non_uuid_user_stats_user_id(self):
        stats = UserStatsCreate(user_id="not-a-uuid")

        assert stats.user_id == "not-a-uuid"

    def test_duplicate_title_template_name_raises_integrity_error(
        self, db_session
    ):
        template = TitleTemplateCreate(
            name="Unique Title",
            description_template="Desc",
        )
        title_crud.create_title_template(db_session, template)

        with pytest.raises(IntegrityError):
            title_crud.create_title_template(db_session, template)
        db_session.rollback()

    def test_duplicate_user_stats_raises_integrity_error(self, db_session, fake):
        user = user_crud.create_user(
            db_session,
            UserCreate(username=fake.user_name(), email=fake.email()),
        )
        assert user is not None
        stats_crud.create_user_stats(db_session, UserStatsCreate(user_id=user.id))

        with pytest.raises(IntegrityError):
            stats_crud.create_user_stats(db_session, UserStatsCreate(user_id=user.id))
        db_session.rollback()

    def test_crud_returns_none_or_false_for_missing_ids(self, db_session):
        assert user_crud.get_user(db_session, "missing") is None
        assert theme_crud.get_theme(db_session, "missing") is None
        assert skill_crud.get_skill(db_session, "missing") is None
        assert title_crud.get_title_template(db_session, "missing") is None
        assert mq_crud.get_mq_template(db_session, "missing") is None
        assert journal_crud.get_journal_entry(db_session, "missing") is None
        assert stats_crud.get_user_stats(db_session, "missing") is None

        assert user_crud.delete_user(db_session, "missing") is False
        assert theme_crud.delete_theme(db_session, "missing") is False
        assert skill_crud.delete_skill(db_session, "missing") is False
        assert mq_crud.delete_user_mq(db_session, "missing") is False
        assert journal_crud.delete_journal_entry(db_session, "missing") is False
