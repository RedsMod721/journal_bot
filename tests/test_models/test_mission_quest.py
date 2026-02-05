"""
Comprehensive tests for the Mission/Quest models (MissionQuestTemplate and UserMissionQuest).

Tests cover:
- MissionQuestTemplate creation and attributes
- UserMissionQuest creation and relationships
- Status transitions (not_started, in_progress, completed, failed)
- Quest hierarchy (parent-child relationships)
- Completion progress tracking

Follows the AAA pattern: Arrange, Act, Assert
"""
import pytest
from datetime import datetime, timedelta

from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest
from app.models.user import User


class TestMissionQuestTemplateModel:
    """Test suite for MissionQuestTemplate model."""

    # =========================================================================
    # CREATION TESTS
    # =========================================================================

    def test_mq_template_creation(self, db_session):
        """Should create MQ template with all required fields."""
        # Arrange
        name = "Morning Meditation"
        description = "{user_name}, start your day with 10 minutes of mindfulness."
        mq_type = "daily"
        structure = "single_action"
        completion_condition = {"type": "yes_no"}
        reward_xp = 50
        reward_coins = 10
        difficulty = "easy"
        category = "Health"

        # Act
        template = MissionQuestTemplate(
            name=name,
            description_template=description,
            type=mq_type,
            structure=structure,
            completion_condition=completion_condition,
            reward_xp=reward_xp,
            reward_coins=reward_coins,
            difficulty=difficulty,
            category=category,
        )
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert template.id is not None
        assert len(template.id) == 36  # UUID format
        assert template.name == name
        assert template.description_template == description
        assert template.type == mq_type
        assert template.structure == structure
        assert template.completion_condition == completion_condition
        assert template.reward_xp == reward_xp
        assert template.reward_coins == reward_coins
        assert template.difficulty == difficulty
        assert template.category == category

    def test_mq_template_creation_generates_uuid(self, db_session):
        """Should auto-generate a valid UUID string for primary key."""
        # Arrange & Act
        template = MissionQuestTemplate(name="Test Quest")
        db_session.add(template)
        db_session.commit()

        # Assert - UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert template.id is not None
        assert len(template.id) == 36
        assert template.id.count("-") == 4

    # =========================================================================
    # DEFAULT VALUE TESTS
    # =========================================================================

    def test_mq_template_default_difficulty_is_medium(self, db_session):
        """Should default difficulty to 'medium' when not specified."""
        # Arrange & Act
        template = MissionQuestTemplate(name="Default Difficulty Quest")
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert template.difficulty == "medium"

    def test_mq_template_default_reward_xp_is_zero(self, db_session):
        """Should default reward_xp to 0 when not specified."""
        # Arrange & Act
        template = MissionQuestTemplate(name="No XP Quest")
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert template.reward_xp == 0

    def test_mq_template_default_reward_coins_is_zero(self, db_session):
        """Should default reward_coins to 0 when not specified."""
        # Arrange & Act
        template = MissionQuestTemplate(name="No Coins Quest")
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert template.reward_coins == 0

    def test_mq_template_default_completion_condition_is_empty_dict(self, db_session):
        """Should default completion_condition to empty dict when not specified."""
        # Arrange & Act
        template = MissionQuestTemplate(name="No Condition Quest")
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert template.completion_condition == {}

    # =========================================================================
    # JSON STORAGE TESTS
    # =========================================================================

    def test_mq_template_completion_condition_json_storage(self, db_session):
        """Should correctly store and retrieve complex JSON completion condition."""
        # Arrange
        completion_condition = {
            "type": "accumulation",
            "target": 50,
            "unit": "pushups",
            "time_window": {"type": "daily"},
        }

        # Act
        template = MissionQuestTemplate(
            name="50 Pushups Quest",
            completion_condition=completion_condition,
        )
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert template.completion_condition == completion_condition
        assert template.completion_condition["type"] == "accumulation"
        assert template.completion_condition["target"] == 50
        assert template.completion_condition["time_window"]["type"] == "daily"

    # =========================================================================
    # REPR TEST
    # =========================================================================

    def test_mq_template_repr(self, db_session):
        """Should return readable string representation."""
        # Arrange
        template = MissionQuestTemplate(name="Test Quest", type="daily")

        # Act
        repr_string = repr(template)

        # Assert
        assert repr_string == "<MissionQuestTemplate Test Quest (daily)>"

    def test_mq_template_repr_without_type(self, db_session):
        """Should show 'untyped' in repr when type is not set."""
        # Arrange
        template = MissionQuestTemplate(name="Untyped Quest")

        # Act
        repr_string = repr(template)

        # Assert
        assert repr_string == "<MissionQuestTemplate Untyped Quest (untyped)>"


class TestUserMissionQuestModel:
    """Test suite for UserMissionQuest model."""

    # =========================================================================
    # CREATION TESTS
    # =========================================================================

    def test_user_mq_creation(self, db_session, sample_user):
        """Should create user MQ with all required fields."""
        # Arrange
        template = MissionQuestTemplate(
            name="Daily Meditation",
            type="daily",
            reward_xp=50,
        )
        db_session.add(template)
        db_session.commit()

        # Act
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            template_id=template.id,
            name="Daily Meditation",
            personalized_description="Start your day mindfully!",
        )
        db_session.add(user_mq)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.id is not None
        assert len(user_mq.id) == 36
        assert user_mq.user_id == sample_user.id
        assert user_mq.template_id == template.id
        assert user_mq.name == "Daily Meditation"
        assert user_mq.personalized_description == "Start your day mindfully!"
        assert user_mq.status == "not_started"
        assert user_mq.completion_progress == 0
        assert user_mq.completion_target == 100
        assert user_mq.created_at is not None
        assert user_mq.deadline is None
        assert user_mq.completed_at is None

    def test_user_mq_creation_without_template(self, db_session, sample_user):
        """Should create custom user MQ without template reference."""
        # Act
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Custom Personal Quest",
            personalized_description="A quest I created myself",
        )
        db_session.add(user_mq)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.id is not None
        assert user_mq.template_id is None
        assert user_mq.name == "Custom Personal Quest"

    def test_user_mq_creation_with_deadline(self, db_session, sample_user):
        """Should create user MQ with deadline."""
        # Arrange
        deadline = datetime.utcnow() + timedelta(days=7)

        # Act
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Timed Quest",
            deadline=deadline,
        )
        db_session.add(user_mq)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.deadline is not None
        assert user_mq.deadline > datetime.utcnow()

    # =========================================================================
    # DEFAULT VALUE TESTS
    # =========================================================================

    def test_user_mq_default_status_is_not_started(self, db_session, sample_user):
        """Should default status to 'not_started' when not specified."""
        # Act
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="New Quest",
        )
        db_session.add(user_mq)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.status == "not_started"

    def test_user_mq_default_completion_progress_is_zero(self, db_session, sample_user):
        """Should default completion_progress to 0 when not specified."""
        # Act
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Progress Quest",
        )
        db_session.add(user_mq)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.completion_progress == 0

    def test_user_mq_default_completion_target_is_100(self, db_session, sample_user):
        """Should default completion_target to 100 when not specified."""
        # Act
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Target Quest",
        )
        db_session.add(user_mq)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.completion_target == 100

    # =========================================================================
    # STATUS TRANSITION TESTS
    # =========================================================================

    def test_user_mq_status_transitions(self, db_session, sample_user):
        """Should properly transition between all valid statuses."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Status Test Quest",
        )
        db_session.add(user_mq)
        db_session.commit()

        # Assert initial status
        assert user_mq.status == "not_started"

        # Act - start the quest
        user_mq.start()
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert - should be in_progress
        assert user_mq.status == "in_progress"

        # Act - complete the quest
        user_mq.complete()
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert - should be completed
        assert user_mq.status == "completed"
        assert user_mq.completed_at is not None

    def test_user_mq_status_transition_to_failed(self, db_session, sample_user):
        """Should transition to failed status."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Fail Test Quest",
        )
        db_session.add(user_mq)
        db_session.commit()

        user_mq.start()
        db_session.commit()

        # Act
        user_mq.fail()
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.status == "failed"
        assert user_mq.completed_at is None

    def test_user_mq_start_after_failed_does_not_change(self, db_session, sample_user):
        """start() should not change status if already failed."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Failed Quest",
            status="failed",
        )
        db_session.add(user_mq)
        db_session.commit()

        # Act
        user_mq.start()
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.status == "failed"

    def test_user_mq_complete_after_failed_sets_completed(self, db_session, sample_user):
        """complete() should set completed status even if previously failed."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Failed Then Completed Quest",
            status="failed",
            completion_target=10,
            completion_progress=3,
        )
        db_session.add(user_mq)
        db_session.commit()

        # Act
        user_mq.complete()
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.status == "completed"
        assert user_mq.completed_at is not None
        assert user_mq.completion_progress == 10

    def test_user_mq_start_idempotent(self, db_session, sample_user):
        """start() should be idempotent when already in_progress."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Idempotent Start Quest",
        )
        db_session.add(user_mq)
        db_session.commit()

        # Act
        user_mq.start()
        user_mq.start()
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.status == "in_progress"

    def test_user_mq_start_only_changes_not_started(self, db_session, sample_user):
        """Should only change status if currently not_started."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Already Started Quest",
            status="in_progress",
        )
        db_session.add(user_mq)
        db_session.commit()

        # Act
        user_mq.start()  # Should not change anything
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert - status unchanged
        assert user_mq.status == "in_progress"

    # =========================================================================
    # HIERARCHY TESTS (PARENT-CHILD)
    # =========================================================================

    def test_user_mq_hierarchy_parent_child(self, db_session, sample_user):
        """Should support parent-child quest hierarchy."""
        # Arrange - Create parent quest (Story Arc)
        parent_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Become Healthier",
            personalized_description="A journey to better health",
        )
        db_session.add(parent_mq)
        db_session.commit()
        db_session.refresh(parent_mq)

        # Act - Create child quests
        child_mq1 = UserMissionQuest(
            user_id=sample_user.id,
            name="Go to Gym 3x",
            parent_mq_id=parent_mq.id,
        )
        child_mq2 = UserMissionQuest(
            user_id=sample_user.id,
            name="Eat 5 Vegetables Daily",
            parent_mq_id=parent_mq.id,
        )
        db_session.add_all([child_mq1, child_mq2])
        db_session.commit()
        db_session.refresh(parent_mq)
        db_session.refresh(child_mq1)
        db_session.refresh(child_mq2)

        # Assert - parent-child relationships
        assert child_mq1.parent_mq_id == parent_mq.id
        assert child_mq2.parent_mq_id == parent_mq.id
        assert child_mq1.parent_mq.id == parent_mq.id
        assert child_mq2.parent_mq.id == parent_mq.id

        # Assert - child_mq backref
        assert len(parent_mq.child_mq) == 2
        child_names = {c.name for c in parent_mq.child_mq}
        assert child_names == {"Go to Gym 3x", "Eat 5 Vegetables Daily"}

    def test_user_mq_multi_level_hierarchy(self, db_session, sample_user):
        """Should support multi-level quest hierarchy (grandparent-parent-child)."""
        # Arrange - Create story arc
        story_arc = UserMissionQuest(
            user_id=sample_user.id,
            name="Health Journey Story Arc",
        )
        db_session.add(story_arc)
        db_session.commit()

        # Create mission under story arc
        mission = UserMissionQuest(
            user_id=sample_user.id,
            name="Exercise Routine Mission",
            parent_mq_id=story_arc.id,
        )
        db_session.add(mission)
        db_session.commit()

        # Create sub-quest under mission
        sub_quest = UserMissionQuest(
            user_id=sample_user.id,
            name="Do 20 Pushups",
            parent_mq_id=mission.id,
        )
        db_session.add(sub_quest)
        db_session.commit()

        db_session.refresh(story_arc)
        db_session.refresh(mission)
        db_session.refresh(sub_quest)

        # Assert - full hierarchy
        assert sub_quest.parent_mq.id == mission.id
        assert mission.parent_mq.id == story_arc.id
        assert story_arc.parent_mq is None

        # Assert - child_mq at each level
        assert len(story_arc.child_mq) == 1
        assert story_arc.child_mq[0].name == "Exercise Routine Mission"
        assert len(mission.child_mq) == 1
        assert mission.child_mq[0].name == "Do 20 Pushups"

    # =========================================================================
    # COMPLETION PROGRESS TRACKING TESTS
    # =========================================================================

    def test_user_mq_completion_progress_tracking(self, db_session, sample_user):
        """Should track completion progress for accumulation quests."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="50 Pushups Quest",
            completion_target=50,
        )
        db_session.add(user_mq)
        db_session.commit()

        # Act - Update progress incrementally
        completed = user_mq.update_progress(20)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert - partial progress
        assert user_mq.completion_progress == 20
        assert user_mq.status == "in_progress"
        assert completed is False
        assert user_mq.completion_percentage == 40.0

        # Act - More progress
        completed = user_mq.update_progress(15)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert - still in progress
        assert user_mq.completion_progress == 35
        assert user_mq.status == "in_progress"
        assert completed is False
        assert user_mq.completion_percentage == 70.0

        # Act - Complete the quest
        completed = user_mq.update_progress(20)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert - completed
        assert user_mq.completion_progress == 55  # Can exceed target
        assert user_mq.status == "completed"
        assert completed is True
        assert user_mq.completed_at is not None
        assert user_mq.completion_percentage == pytest.approx(110.0)

    def test_user_mq_update_progress_auto_starts(self, db_session, sample_user):
        """Should auto-start quest when progress is added."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Auto Start Quest",
            completion_target=100,
        )
        db_session.add(user_mq)
        db_session.commit()
        assert user_mq.status == "not_started"

        # Act
        user_mq.update_progress(10)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.status == "in_progress"

    def test_user_mq_update_progress_negative(self, db_session, sample_user):
        """Negative progress should reduce completion_progress (no validation enforced)."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Negative Progress Quest",
            completion_target=10,
        )
        db_session.add(user_mq)
        db_session.commit()

        # Act
        completed = user_mq.update_progress(-5)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.completion_progress == -5
        assert user_mq.status == "in_progress"
        assert completed is False
        assert user_mq.completed_at is None

    def test_user_mq_update_progress_zero(self, db_session, sample_user):
        """Zero progress should still auto-start when not started."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Zero Progress Quest",
            completion_target=10,
        )
        db_session.add(user_mq)
        db_session.commit()

        # Act
        completed = user_mq.update_progress(0)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.completion_progress == 0
        assert user_mq.status == "in_progress"
        assert completed is False
        assert user_mq.completed_at is None

    def test_user_mq_deadline_in_past_allowed(self, db_session, sample_user):
        """Past deadlines should be stored (no validation enforced)."""
        # Arrange
        past_deadline = datetime.utcnow() - timedelta(days=1)

        # Act
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Past Deadline Quest",
            deadline=past_deadline,
        )
        db_session.add(user_mq)
        db_session.commit()
        db_session.refresh(user_mq)

        # Assert
        assert user_mq.deadline == past_deadline

    def test_user_mq_completion_percentage_calculation(self, db_session, sample_user):
        """Should correctly calculate completion percentage."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Percentage Test Quest",
            completion_progress=25,
            completion_target=50,
        )
        db_session.add(user_mq)
        db_session.commit()

        # Assert
        assert user_mq.completion_percentage == 50.0

    def test_user_mq_completion_percentage_fractional(self, db_session, sample_user):
        """Should handle fractional completion percentages."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Fractional Percentage Quest",
            completion_progress=1,
            completion_target=3,
        )
        db_session.add(user_mq)
        db_session.commit()

        # Assert
        assert user_mq.completion_percentage == pytest.approx(33.333333, rel=1e-6)

    def test_user_mq_completion_percentage_zero_target(self, db_session, sample_user):
        """Should handle zero target gracefully in percentage calculation."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Zero Target Quest",
            completion_progress=0,
            completion_target=0,
        )
        db_session.add(user_mq)
        db_session.commit()

        # Assert - zero progress, zero target
        assert user_mq.completion_percentage == 0.0

        # Act - add progress
        user_mq.completion_progress = 1

        # Assert - any progress with zero target = 100%
        assert user_mq.completion_percentage == 100.0

    # =========================================================================
    # RELATIONSHIP TESTS
    # =========================================================================

    def test_user_mq_relationship_to_template(self, db_session, sample_user):
        """Should have bidirectional relationship with MissionQuestTemplate."""
        # Arrange
        template = MissionQuestTemplate(
            name="Template Quest",
            type="daily",
            reward_xp=100,
        )
        db_session.add(template)
        db_session.commit()

        # Act
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            template_id=template.id,
            name="Template Quest",
        )
        db_session.add(user_mq)
        db_session.commit()
        db_session.refresh(user_mq)
        db_session.refresh(template)

        # Assert - bidirectional access
        assert user_mq.template.id == template.id
        assert user_mq.template.name == "Template Quest"
        assert len(template.user_mq) == 1
        assert template.user_mq[0].id == user_mq.id

    def test_user_mq_relationship_to_user(self, db_session, sample_user):
        """Should have bidirectional relationship with User."""
        # Act
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="User Related Quest",
        )
        db_session.add(user_mq)
        db_session.commit()
        db_session.refresh(user_mq)
        db_session.refresh(sample_user)

        # Assert - bidirectional access
        assert user_mq.user.id == sample_user.id
        assert len(sample_user.user_mq) == 1
        assert sample_user.user_mq[0].id == user_mq.id

    def test_user_can_have_multiple_quests(self, db_session, sample_user):
        """User should be able to have multiple quests."""
        # Act
        mq1 = UserMissionQuest(user_id=sample_user.id, name="Quest 1")
        mq2 = UserMissionQuest(user_id=sample_user.id, name="Quest 2")
        mq3 = UserMissionQuest(user_id=sample_user.id, name="Quest 3")
        db_session.add_all([mq1, mq2, mq3])
        db_session.commit()
        db_session.refresh(sample_user)

        # Assert
        assert len(sample_user.user_mq) == 3
        quest_names = {mq.name for mq in sample_user.user_mq}
        assert quest_names == {"Quest 1", "Quest 2", "Quest 3"}

    def test_multiple_users_can_have_same_template(self, db_session, fake):
        """Multiple users should be able to use the same template."""
        # Arrange
        template = MissionQuestTemplate(name="Shared Template")
        db_session.add(template)
        db_session.commit()

        user1 = User(username=fake.user_name(), email=fake.email())
        user2 = User(username=fake.user_name(), email=fake.email())
        db_session.add_all([user1, user2])
        db_session.commit()

        # Act
        mq1 = UserMissionQuest(
            user_id=user1.id,
            template_id=template.id,
            name="Shared Template",
        )
        mq2 = UserMissionQuest(
            user_id=user2.id,
            template_id=template.id,
            name="Shared Template",
        )
        db_session.add_all([mq1, mq2])
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert len(template.user_mq) == 2
        user_ids = {mq.user_id for mq in template.user_mq}
        assert user_ids == {user1.id, user2.id}

    # =========================================================================
    # CASCADE DELETE TESTS
    # =========================================================================

    def test_user_deletion_cascades_to_user_mq(self, db_session, sample_user):
        """Deleting user should cascade delete all their quests."""
        # Arrange
        mq1 = UserMissionQuest(user_id=sample_user.id, name="Delete Quest 1")
        mq2 = UserMissionQuest(user_id=sample_user.id, name="Delete Quest 2")
        db_session.add_all([mq1, mq2])
        db_session.commit()
        user_id = sample_user.id

        # Act
        db_session.delete(sample_user)
        db_session.commit()

        # Assert
        remaining_quests = db_session.query(UserMissionQuest).filter(
            UserMissionQuest.user_id == user_id
        ).all()
        assert len(remaining_quests) == 0

    def test_template_deletion_cascades_to_user_mq(self, db_session, sample_user):
        """Deleting template should cascade delete all user quests referencing it."""
        # Arrange
        template = MissionQuestTemplate(name="Delete Me Template")
        db_session.add(template)
        db_session.commit()

        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            template_id=template.id,
            name="Delete Me Template",
        )
        db_session.add(user_mq)
        db_session.commit()
        template_id = template.id

        # Act
        db_session.delete(template)
        db_session.commit()

        # Assert
        remaining_quests = db_session.query(UserMissionQuest).filter(
            UserMissionQuest.template_id == template_id
        ).all()
        assert len(remaining_quests) == 0

    # =========================================================================
    # REPR TEST
    # =========================================================================

    def test_user_mq_repr(self, db_session, sample_user):
        """Should return readable string representation."""
        # Arrange
        user_mq = UserMissionQuest(
            user_id=sample_user.id,
            name="Repr Test Quest",
            status="in_progress",
        )

        # Act
        repr_string = repr(user_mq)

        # Assert
        assert repr_string == "<UserMissionQuest Repr Test Quest (in_progress)>"


class TestMissionQuestCategory:
    """Test suite for M/Q categories."""

    def test_mq_templates_can_be_queried_by_category(self, db_session):
        """Should be able to filter templates by category."""
        # Arrange
        templates = [
            MissionQuestTemplate(name="Health Quest", category="Health"),
            MissionQuestTemplate(name="Productivity Quest", category="Productivity"),
            MissionQuestTemplate(name="Social Quest", category="Social"),
            MissionQuestTemplate(name="Another Health", category="Health"),
        ]
        db_session.add_all(templates)
        db_session.commit()

        # Act
        health_quests = db_session.query(MissionQuestTemplate).filter(
            MissionQuestTemplate.category == "Health"
        ).all()

        # Assert
        assert len(health_quests) == 2
        quest_names = {t.name for t in health_quests}
        assert quest_names == {"Health Quest", "Another Health"}


class TestMissionQuestType:
    """Test suite for M/Q types."""

    def test_mq_templates_can_be_queried_by_type(self, db_session):
        """Should be able to filter templates by type."""
        # Arrange
        templates = [
            MissionQuestTemplate(name="Daily 1", type="daily"),
            MissionQuestTemplate(name="Daily 2", type="daily"),
            MissionQuestTemplate(name="Weekly", type="periodic"),
            MissionQuestTemplate(name="Repeatable", type="repeatable"),
        ]
        db_session.add_all(templates)
        db_session.commit()

        # Act
        daily_quests = db_session.query(MissionQuestTemplate).filter(
            MissionQuestTemplate.type == "daily"
        ).all()

        # Assert
        assert len(daily_quests) == 2
        quest_names = {t.name for t in daily_quests}
        assert quest_names == {"Daily 1", "Daily 2"}
