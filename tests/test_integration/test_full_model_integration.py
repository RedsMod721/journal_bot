"""
Comprehensive integration tests for all models working together.

This module tests the complete "character sheet" creation flow, verifying:
- All models can be created and linked correctly
- Bidirectional relationships work as expected
- Cascade delete properly removes all related records
- The full user ecosystem functions as a cohesive unit
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.models.theme import Theme
from app.models.skill import Skill
from app.models.title import TitleTemplate, UserTitle
from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest
from app.models.journal_entry import JournalEntry
from app.models.user_stats import UserStats


class TestFullModelIntegration:
    """Test all models working together as a complete system."""

    def test_create_user_with_full_character_sheet(self, db_session, fake):
        """
        Test creating a complete user with all related entities.

        This test creates a full "character sheet" for a user:
        1. User (the central entity)
        2. Theme (life category)
        3. Skill (under the theme)
        4. TitleTemplate + UserTitle (achievements)
        5. MissionQuestTemplate + UserMissionQuest (quests)
        6. JournalEntry (diary entry)
        7. UserStats (status bars)

        Then verifies all bidirectional relationships and cascade delete.
        """
        # =================================================================
        # STEP 1: Create User
        # =================================================================
        user = User(
            username=fake.user_name(),
            email=fake.email()
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id is not None
        assert len(user.id) == 36  # UUID format
        assert user.is_active is True
        assert user.created_at is not None

        # =================================================================
        # STEP 2: Create Theme for the user
        # =================================================================
        theme = Theme(
            user_id=user.id,
            name="Career Development",
            description="Professional growth and work skills",
            level=5,
            xp=250.0,
            corrosion_level="Fresh"
        )
        db_session.add(theme)
        db_session.commit()
        db_session.refresh(theme)
        db_session.refresh(user)

        assert theme.id is not None
        assert theme.user_id == user.id
        assert theme.level == 5

        # Verify bidirectional relationship: User -> Themes
        assert theme in user.themes
        assert theme.user == user

        # =================================================================
        # STEP 3: Create Skill under the Theme
        # =================================================================
        skill = Skill(
            user_id=user.id,
            theme_id=theme.id,
            name="Python Programming",
            description="Backend development with Python",
            level=15,
            xp=500.0,
            rank="Intermediate",
            practice_time_minutes=1200,
            difficulty="Medium"
        )
        db_session.add(skill)
        db_session.commit()
        db_session.refresh(skill)
        db_session.refresh(theme)
        db_session.refresh(user)

        assert skill.id is not None
        assert skill.user_id == user.id
        assert skill.theme_id == theme.id
        assert skill.rank == "Intermediate"

        # Verify bidirectional relationships
        assert skill in user.skills
        assert skill in theme.skills
        assert skill.user == user
        assert skill.theme == theme

        # =================================================================
        # STEP 4: Create TitleTemplate and award UserTitle
        # =================================================================
        title_template = TitleTemplate(
            name="Code Warrior",
            description_template="Awarded to {user_name} for programming excellence",
            effect={"type": "xp_multiplier", "scope": "skill", "target": "Programming", "value": 1.15},
            rank="B",
            unlock_condition={"type": "skill_level", "skill": "Python Programming", "value": 15},
            category="Skills",
            is_hidden=False
        )
        db_session.add(title_template)
        db_session.commit()
        db_session.refresh(title_template)

        assert title_template.id is not None
        assert title_template.rank == "B"

        # Award the title to the user
        user_title = UserTitle(
            user_id=user.id,
            title_template_id=title_template.id,
            is_equipped=True,
            personalized_description=f"Awarded to {user.username} for reaching Intermediate rank in Python"
        )
        db_session.add(user_title)
        db_session.commit()
        db_session.refresh(user_title)
        db_session.refresh(title_template)
        db_session.refresh(user)

        assert user_title.id is not None
        assert user_title.is_equipped is True
        assert user_title.acquired_at is not None

        # Verify bidirectional relationships
        assert user_title in user.user_titles
        assert user_title in title_template.user_titles
        assert user_title.user == user
        assert user_title.title_template == title_template

        # =================================================================
        # STEP 5: Create MissionQuestTemplate and assign UserMissionQuest
        # =================================================================
        mq_template = MissionQuestTemplate(
            name="Learn a New Framework",
            description_template="{user_name} must master a new Python framework",
            type="story_arc",
            structure="multi_part",
            completion_condition={"type": "accumulation", "target": 100},
            reward_xp=500,
            reward_coins=50,
            difficulty="hard",
            category="Learning"
        )
        db_session.add(mq_template)
        db_session.commit()
        db_session.refresh(mq_template)

        assert mq_template.id is not None
        assert mq_template.reward_xp == 500

        # Assign the quest to the user
        user_mq = UserMissionQuest(
            user_id=user.id,
            template_id=mq_template.id,
            name="Learn FastAPI Framework",
            personalized_description=f"{user.username} will master the FastAPI framework",
            status="in_progress",
            completion_progress=45,
            completion_target=100,
            deadline=datetime.utcnow() + timedelta(days=30)
        )
        db_session.add(user_mq)
        db_session.commit()
        db_session.refresh(user_mq)
        db_session.refresh(mq_template)
        db_session.refresh(user)

        assert user_mq.id is not None
        assert user_mq.status == "in_progress"
        assert user_mq.completion_progress == 45
        assert user_mq.completion_percentage == 45.0

        # Verify bidirectional relationships
        assert user_mq in user.user_mq
        assert user_mq in mq_template.user_mq
        assert user_mq.user == user
        assert user_mq.template == mq_template

        # =================================================================
        # STEP 6: Create JournalEntry
        # =================================================================
        journal_entry = JournalEntry(
            user_id=user.id,
            content="Today I made great progress learning FastAPI. "
                    "I completed the routing chapter and built my first endpoint. "
                    "Feeling accomplished and motivated to continue tomorrow.",
            entry_type="text",
            ai_categories={
                "themes": ["Career Development"],
                "skills": ["Python Programming"],
                "sentiment": "positive",
                "energy_level": "high"
            },
            ai_suggested_quests=[
                {"name": "Complete API documentation", "priority": "medium"},
                {"name": "Build a CRUD endpoint", "priority": "high"}
            ],
            ai_processed=True,
            manual_theme_ids=[theme.id],
            manual_skill_ids=[skill.id]
        )
        db_session.add(journal_entry)
        db_session.commit()
        db_session.refresh(journal_entry)
        db_session.refresh(user)

        assert journal_entry.id is not None
        assert journal_entry.ai_processed is True
        assert journal_entry.created_at is not None
        assert len(journal_entry.ai_suggested_quests) == 2

        # Verify bidirectional relationship
        assert journal_entry in user.journal_entries
        assert journal_entry.user == user

        # =================================================================
        # STEP 7: Create UserStats
        # =================================================================
        user_stats = UserStats(
            user_id=user.id,
            hp=95,
            mp=80,
            mental_health=85,
            physical_health=70,
            relationship_quality=65,
            socialization_level=55
        )
        db_session.add(user_stats)
        db_session.commit()
        db_session.refresh(user_stats)
        db_session.refresh(user)

        assert user_stats.id is not None
        assert user_stats.hp == 95
        assert user_stats.updated_at is not None

        # Verify one-to-one relationship
        assert user.stats == user_stats
        assert user_stats.user == user

        # =================================================================
        # STEP 8: Verify all relationships work bidirectionally
        # =================================================================

        # Count all related entities
        assert len(user.themes) == 1
        assert len(user.skills) == 1
        assert len(user.user_titles) == 1
        assert len(user.user_mq) == 1
        assert len(user.journal_entries) == 1
        assert user.stats is not None

        # Verify theme -> skill relationship
        assert len(theme.skills) == 1
        assert skill in theme.skills

        # Verify template -> user instance relationships
        assert len(title_template.user_titles) == 1
        assert len(mq_template.user_mq) == 1

        # =================================================================
        # STEP 9: Verify cascade delete
        # =================================================================

        # Store IDs for verification after deletion
        user_id = user.id
        theme_id = theme.id
        skill_id = skill.id
        user_title_id = user_title.id
        user_mq_id = user_mq.id
        journal_entry_id = journal_entry.id
        user_stats_id = user_stats.id

        # Templates should NOT be deleted (they are global)
        title_template_id = title_template.id
        mq_template_id = mq_template.id

        # Delete the user
        db_session.delete(user)
        db_session.commit()

        # Verify user is deleted
        deleted_user = db_session.query(User).filter(User.id == user_id).first()
        assert deleted_user is None

        # Verify all user-owned entities are cascade deleted
        deleted_theme = db_session.query(Theme).filter(Theme.id == theme_id).first()
        assert deleted_theme is None

        deleted_skill = db_session.query(Skill).filter(Skill.id == skill_id).first()
        assert deleted_skill is None

        deleted_user_title = db_session.query(UserTitle).filter(UserTitle.id == user_title_id).first()
        assert deleted_user_title is None

        deleted_user_mq = db_session.query(UserMissionQuest).filter(UserMissionQuest.id == user_mq_id).first()
        assert deleted_user_mq is None

        deleted_journal = db_session.query(JournalEntry).filter(JournalEntry.id == journal_entry_id).first()
        assert deleted_journal is None

        deleted_stats = db_session.query(UserStats).filter(UserStats.id == user_stats_id).first()
        assert deleted_stats is None

        # Verify templates are NOT deleted (global resources)
        remaining_title_template = db_session.query(TitleTemplate).filter(
            TitleTemplate.id == title_template_id
        ).first()
        assert remaining_title_template is not None
        assert remaining_title_template.name == "Code Warrior"

        remaining_mq_template = db_session.query(MissionQuestTemplate).filter(
            MissionQuestTemplate.id == mq_template_id
        ).first()
        assert remaining_mq_template is not None
        assert remaining_mq_template.name == "Learn a New Framework"

        # Verify template relationships are cleared
        db_session.refresh(remaining_title_template)
        db_session.refresh(remaining_mq_template)
        assert len(remaining_title_template.user_titles) == 0
        assert len(remaining_mq_template.user_mq) == 0

    def test_skill_without_theme(self, db_session, fake):
        """Test that skills can exist without a theme (independent skills)."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create skill without theme
        skill = Skill(
            user_id=user.id,
            theme_id=None,  # No theme
            name="General Communication",
            description="Speaking and writing skills"
        )
        db_session.add(skill)
        db_session.commit()
        db_session.refresh(skill)
        db_session.refresh(user)

        assert skill.theme_id is None
        assert skill.theme is None
        assert skill in user.skills

    def test_quest_hierarchy(self, db_session, fake):
        """Test quest parent-child relationships (Story Arc -> Mission -> Sub-quest)."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create parent quest (Story Arc)
        story_arc = UserMissionQuest(
            user_id=user.id,
            name="Master Python Development",
            status="in_progress"
        )
        db_session.add(story_arc)
        db_session.commit()

        # Create child mission
        mission = UserMissionQuest(
            user_id=user.id,
            parent_mq_id=story_arc.id,
            name="Learn Web Frameworks",
            status="in_progress"
        )
        db_session.add(mission)
        db_session.commit()

        # Create sub-quest
        sub_quest = UserMissionQuest(
            user_id=user.id,
            parent_mq_id=mission.id,
            name="Complete FastAPI Tutorial",
            status="not_started"
        )
        db_session.add(sub_quest)
        db_session.commit()

        db_session.refresh(story_arc)
        db_session.refresh(mission)
        db_session.refresh(sub_quest)

        # Verify hierarchy
        assert sub_quest.parent_mq == mission
        assert mission.parent_mq == story_arc
        assert story_arc.parent_mq is None

        # Verify children
        assert mission in story_arc.child_mq
        assert sub_quest in mission.child_mq

    def test_theme_hierarchy(self, db_session, fake):
        """Test theme parent-child relationships (sub-themes)."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create parent theme
        parent_theme = Theme(
            user_id=user.id,
            name="Health & Wellness"
        )
        db_session.add(parent_theme)
        db_session.commit()

        # Create sub-themes
        sub_theme1 = Theme(
            user_id=user.id,
            parent_theme_id=parent_theme.id,
            name="Physical Fitness"
        )
        sub_theme2 = Theme(
            user_id=user.id,
            parent_theme_id=parent_theme.id,
            name="Mental Health"
        )
        db_session.add_all([sub_theme1, sub_theme2])
        db_session.commit()

        db_session.refresh(parent_theme)
        db_session.refresh(sub_theme1)
        db_session.refresh(sub_theme2)

        # Verify hierarchy
        assert sub_theme1.parent_theme == parent_theme
        assert sub_theme2.parent_theme == parent_theme
        assert sub_theme1 in parent_theme.sub_themes
        assert sub_theme2 in parent_theme.sub_themes
        assert len(parent_theme.sub_themes) == 2

    def test_skill_tree_hierarchy(self, db_session, fake):
        """Test skill parent-child relationships (skill trees)."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create parent skill
        parent_skill = Skill(
            user_id=user.id,
            name="Programming"
        )
        db_session.add(parent_skill)
        db_session.commit()

        # Create child skills
        child_skill1 = Skill(
            user_id=user.id,
            parent_skill_id=parent_skill.id,
            name="Backend Development"
        )
        child_skill2 = Skill(
            user_id=user.id,
            parent_skill_id=parent_skill.id,
            name="Frontend Development"
        )
        db_session.add_all([child_skill1, child_skill2])
        db_session.commit()

        db_session.refresh(parent_skill)

        # Verify hierarchy
        assert child_skill1.parent_skill == parent_skill
        assert child_skill2.parent_skill == parent_skill
        assert child_skill1 in parent_skill.child_skills
        assert child_skill2 in parent_skill.child_skills
        assert len(parent_skill.child_skills) == 2

    def test_multiple_users_isolated(self, db_session, fake):
        """Test that multiple users have isolated data."""
        # Create two users
        user1 = User(username=fake.user_name() + "_1", email=fake.email())
        user2 = User(username=fake.user_name() + "_2", email=fake.email())
        db_session.add_all([user1, user2])
        db_session.commit()

        # Create themes for each user
        theme1 = Theme(user_id=user1.id, name="User1 Theme")
        theme2 = Theme(user_id=user2.id, name="User2 Theme")
        db_session.add_all([theme1, theme2])
        db_session.commit()

        # Create stats for each user
        stats1 = UserStats(user_id=user1.id, hp=100)
        stats2 = UserStats(user_id=user2.id, hp=50)
        db_session.add_all([stats1, stats2])
        db_session.commit()

        db_session.refresh(user1)
        db_session.refresh(user2)

        # Verify isolation
        assert len(user1.themes) == 1
        assert len(user2.themes) == 1
        assert user1.themes[0].name == "User1 Theme"
        assert user2.themes[0].name == "User2 Theme"
        assert user1.stats.hp == 100
        assert user2.stats.hp == 50

        # Delete user1, verify user2 is unaffected
        db_session.delete(user1)
        db_session.commit()

        remaining_user = db_session.query(User).filter(User.id == user2.id).first()
        assert remaining_user is not None
        db_session.refresh(remaining_user)
        assert len(remaining_user.themes) == 1
        assert remaining_user.stats.hp == 50

    def test_title_template_shared_across_users(self, db_session, fake):
        """Test that one TitleTemplate can be awarded to multiple users."""
        # Create template
        template = TitleTemplate(
            name="Early Adopter",
            description_template="Awarded to {user_name} for joining early",
            rank="C"
        )
        db_session.add(template)
        db_session.commit()

        # Create multiple users and award the same title
        users = []
        for i in range(3):
            user = User(username=f"user_{fake.user_name()}_{i}", email=fake.email())
            db_session.add(user)
            db_session.commit()
            users.append(user)

            user_title = UserTitle(
                user_id=user.id,
                title_template_id=template.id
            )
            db_session.add(user_title)

        db_session.commit()
        db_session.refresh(template)

        # Verify template has 3 user titles
        assert len(template.user_titles) == 3

        # Delete one user
        db_session.delete(users[0])
        db_session.commit()
        db_session.refresh(template)

        # Template still exists with 2 user titles
        assert len(template.user_titles) == 2

    def test_quest_progression_integration(self, db_session, fake):
        """Test quest progression methods work correctly in integration."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        quest = UserMissionQuest(
            user_id=user.id,
            name="Complete 10 journal entries",
            status="not_started",
            completion_progress=0,
            completion_target=10
        )
        db_session.add(quest)
        db_session.commit()

        # Start the quest
        quest.start()
        db_session.commit()
        assert quest.status == "in_progress"

        # Update progress
        quest.update_progress(5)
        db_session.commit()
        assert quest.completion_progress == 5
        assert quest.completion_percentage == 50.0

        # Complete the quest
        quest.update_progress(5)  # Reaches 10/10
        db_session.commit()
        assert quest.status == "completed"
        assert quest.completed_at is not None

    def test_xp_and_leveling_integration(self, db_session, fake):
        """Test XP and leveling systems work correctly together."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education")
        db_session.add(theme)
        db_session.commit()

        skill = Skill(user_id=user.id, theme_id=theme.id, name="Python")
        db_session.add(skill)
        db_session.commit()

        # Add XP to skill
        initial_level = skill.level
        skill.add_xp(150)  # Should trigger level up (default xp_to_next_level is 50)
        db_session.commit()

        assert skill.level > initial_level
        assert skill.xp >= 0

        # Add practice time (which adds XP)
        skill.add_practice_time(60)  # 60 minutes * 0.5 = 30 XP
        db_session.commit()

        assert skill.practice_time_minutes == 60

    def test_journal_entry_with_ai_categorization(self, db_session, fake):
        """Test journal entries with complex AI categorization data."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Work")
        skill = Skill(user_id=user.id, name="Project Management")
        db_session.add_all([theme, skill])
        db_session.commit()

        entry = JournalEntry(
            user_id=user.id,
            content="Had a productive meeting today. Discussed project milestones.",
            ai_categories={
                "themes": ["Work"],
                "skills": ["Project Management", "Communication"],
                "sentiment": "positive",
                "keywords": ["meeting", "project", "milestones"]
            },
            ai_suggested_quests=[
                {"name": "Follow up on action items", "priority": "high"},
                {"name": "Update project timeline", "priority": "medium"}
            ],
            ai_processed=True,
            manual_theme_ids=[theme.id],
            manual_skill_ids=[skill.id]
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Verify JSON fields are stored and retrieved correctly
        assert entry.ai_categories["sentiment"] == "positive"
        assert len(entry.ai_suggested_quests) == 2
        assert theme.id in entry.manual_theme_ids
        assert skill.id in entry.manual_skill_ids

    def test_template_reuse_with_user_lifecycle(self, db_session, fake):
        """Templates should persist while user instances are deleted."""
        title_template = TitleTemplate(name="Pioneer", rank="C")
        mq_template = MissionQuestTemplate(name="Shared Quest", type="daily")
        db_session.add_all([title_template, mq_template])
        db_session.commit()

        users = []
        for i in range(3):
            user = User(username=f"user_{fake.user_name()}_{i}", email=fake.email())
            db_session.add(user)
            db_session.commit()
            users.append(user)

            db_session.add(UserTitle(user_id=user.id, title_template_id=title_template.id))
            db_session.add(UserMissionQuest(user_id=user.id, template_id=mq_template.id, name="Shared Quest"))

        db_session.commit()
        db_session.refresh(title_template)
        db_session.refresh(mq_template)

        assert len(title_template.user_titles) == 3
        assert len(mq_template.user_mq) == 3

        db_session.delete(users[0])
        db_session.commit()
        db_session.refresh(title_template)
        db_session.refresh(mq_template)

        assert len(title_template.user_titles) == 2
        assert len(mq_template.user_mq) == 2

    def test_skill_theme_unlinking(self, db_session, fake):
        """Skills should remain after unlinking from a theme."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Work")
        db_session.add(theme)
        db_session.commit()

        skill = Skill(user_id=user.id, theme_id=theme.id, name="Writing")
        db_session.add(skill)
        db_session.commit()

        skill.theme_id = None
        db_session.commit()
        db_session.refresh(skill)
        db_session.refresh(theme)

        assert skill.theme is None
        assert len(theme.skills) == 0

    def test_quest_completion_idempotent(self, db_session, fake):
        """Completing a quest twice should keep it completed."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        quest = UserMissionQuest(user_id=user.id, name="Repeat Complete Quest", completion_target=5)
        db_session.add(quest)
        db_session.commit()

        quest.complete()
        db_session.commit()
        first_completed_at = quest.completed_at

        quest.complete()
        db_session.commit()
        db_session.refresh(quest)

        assert quest.status == "completed"
        assert quest.completed_at is not None
        assert quest.completed_at >= first_completed_at
        assert quest.completion_progress == quest.completion_target

    def test_quest_progress_after_completion(self, db_session, fake):
        """Progress updates after completion should keep status completed."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        quest = UserMissionQuest(user_id=user.id, name="Post Completion Quest", completion_target=5)
        db_session.add(quest)
        db_session.commit()

        quest.update_progress(5)
        db_session.commit()
        completed_at = quest.completed_at

        quest.update_progress(2)
        db_session.commit()
        db_session.refresh(quest)

        assert quest.status == "completed"
        assert quest.completed_at >= completed_at
        assert quest.completion_progress == 7

    def test_quest_progress_zero_and_negative(self, db_session, fake):
        """Zero and negative progress should be stored as-is."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        quest = UserMissionQuest(user_id=user.id, name="Zero Negative Quest", completion_target=10)
        db_session.add(quest)
        db_session.commit()

        quest.update_progress(0)
        quest.update_progress(-3)
        db_session.commit()
        db_session.refresh(quest)

        assert quest.completion_progress == -3
        assert quest.status == "in_progress"

    def test_quest_hierarchy_delete_parent(self, db_session, fake):
        """Deleting a parent quest should leave child quests intact."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        parent = UserMissionQuest(user_id=user.id, name="Parent Quest")
        db_session.add(parent)
        db_session.commit()

        child = UserMissionQuest(user_id=user.id, name="Child Quest", parent_mq_id=parent.id)
        db_session.add(child)
        db_session.commit()

        db_session.delete(parent)
        db_session.commit()

        remaining_child = db_session.query(UserMissionQuest).filter(UserMissionQuest.id == child.id).first()
        assert remaining_child is not None
        assert remaining_child.parent_mq is None
        assert remaining_child.parent_mq_id is None

    def test_journal_entry_cross_user_manual_ids(self, db_session, fake):
        """Manual IDs should persist even if they reference another user's entities."""
        user_a = User(username=fake.user_name(), email=fake.email())
        user_b = User(username=fake.user_name(), email=fake.email())
        db_session.add_all([user_a, user_b])
        db_session.commit()

        theme_b = Theme(user_id=user_b.id, name="User B Theme")
        skill_b = Skill(user_id=user_b.id, name="User B Skill")
        db_session.add_all([theme_b, skill_b])
        db_session.commit()

        entry = JournalEntry(
            user_id=user_a.id,
            content="Cross user manual IDs",
            manual_theme_ids=[theme_b.id],
            manual_skill_ids=[skill_b.id],
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        assert theme_b.id in entry.manual_theme_ids
        assert skill_b.id in entry.manual_skill_ids

    def test_user_stats_unique_integration(self, db_session, fake):
        """UserStats should remain unique per user in integration flow."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        stats1 = UserStats(user_id=user.id, hp=90)
        db_session.add(stats1)
        db_session.commit()

        stats2 = UserStats(user_id=user.id, hp=80)
        db_session.add(stats2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_bulk_create_and_refresh_integrity(self, db_session, fake):
        """Bulk insert should preserve relationships after refresh."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        themes = [Theme(user_id=user.id, name=f"Theme {i}") for i in range(3)]
        skills = [Skill(user_id=user.id, name=f"Skill {i}") for i in range(4)]
        quests = [UserMissionQuest(user_id=user.id, name=f"Quest {i}") for i in range(2)]

        db_session.add_all(themes + skills + quests)
        db_session.commit()
        db_session.refresh(user)

        assert len(user.themes) == 3
        assert len(user.skills) == 4
        assert len(user.user_mq) == 2

    def test_session_expunge_and_reload(self, db_session, fake):
        """Expunged objects should reload relationships correctly."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        user_id = user.id

        theme = Theme(user_id=user.id, name="Reload Theme")
        db_session.add(theme)
        db_session.commit()

        db_session.expunge_all()

        reloaded_user = db_session.query(User).filter(User.id == user_id).first()
        assert reloaded_user is not None
        assert len(reloaded_user.themes) == 1

    def test_template_deletion_cascades_user_instances(self, db_session, fake):
        """Deleting templates should cascade delete user instances."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        title_template = TitleTemplate(name="Temp Title")
        mq_template = MissionQuestTemplate(name="Temp Quest")
        db_session.add_all([title_template, mq_template])
        db_session.commit()

        user_title = UserTitle(user_id=user.id, title_template_id=title_template.id)
        user_mq = UserMissionQuest(user_id=user.id, template_id=mq_template.id, name="Temp Quest")
        db_session.add_all([user_title, user_mq])
        db_session.commit()

        title_id = title_template.id
        mq_id = mq_template.id

        db_session.delete(title_template)
        db_session.delete(mq_template)
        db_session.commit()

        remaining_titles = db_session.query(UserTitle).filter(UserTitle.title_template_id == title_id).all()
        remaining_mq = db_session.query(UserMissionQuest).filter(UserMissionQuest.template_id == mq_id).all()

        assert len(remaining_titles) == 0
        assert len(remaining_mq) == 0

    def test_timestamp_ordering_integration(self, db_session, fake):
        """Timestamps should be ordered logically across entities."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        quest = UserMissionQuest(user_id=user.id, name="Timed Quest", completion_target=1)
        db_session.add(quest)
        db_session.commit()

        quest.start()
        quest.complete()
        db_session.commit()

        title_template = TitleTemplate(name="Timed Title")
        db_session.add(title_template)
        db_session.commit()

        user_title = UserTitle(user_id=user.id, title_template_id=title_template.id)
        db_session.add(user_title)
        db_session.commit()

        entry = JournalEntry(user_id=user.id, content="Timed entry")
        db_session.add(entry)
        db_session.commit()

        assert user.created_at <= quest.created_at
        assert quest.created_at <= quest.completed_at
        assert user.created_at <= user_title.acquired_at
        assert user.created_at <= entry.created_at
