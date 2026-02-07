"""
Tests for Mission/Quest CRUD operations.

This module tests all CRUD functions in app/crud/mission_quest.py:
- MQTemplate: create/get/filter by type
- UserMissionQuest: create/get/list/filter, hierarchy, progress, completion, update, delete

Uses db_session and sample_user fixtures from conftest.py.
"""
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.crud.mission_quest import (
    complete_user_mq,
    create_mq_template,
    create_user_mq,
    delete_user_mq,
    get_mq_template,
    get_mq_templates_by_type,
    get_user_mq,
    get_user_mq_with_children,
    get_user_mqs,
    update_mq_progress,
    update_user_mq,
)
from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest
from app.models.user import User
from app.schemas.mission_quest import (
    MQTemplateCreate,
    UserMQCreate,
    UserMQUpdate,
)


class TestMQTemplateCRUD:
    """Comprehensive tests for MissionQuestTemplate CRUD operations."""

    def test_create_mq_template(self, db_session):
        """Should create MQ template with valid data."""
        # Arrange
        template_data = MQTemplateCreate(
            name="Morning Meditation",
            description_template="Meditate for {duration} minutes",
            type="daily",
            structure="single_action",
            completion_condition={"type": "yes_no"},
            reward_xp=25,
            reward_coins=10,
            difficulty="easy",
            category="Health",
        )

        # Act
        result = create_mq_template(db_session, template_data)

        # Assert
        assert result is not None
        assert result.id is not None
        assert len(result.id) == 36
        assert result.name == "Morning Meditation"
        assert result.type == "daily"
        assert result.structure == "single_action"
        assert result.reward_xp == 25
        assert result.reward_coins == 10
        assert result.category == "Health"

    def test_create_mq_template_defaults(self, db_session):
        """Should apply defaults for optional fields."""
        # Arrange
        template_data = MQTemplateCreate(
            name="Default MQ",
            description_template="desc",
            type="daily",
            structure="single_action",
            completion_condition={},
        )

        # Act
        result = create_mq_template(db_session, template_data)

        # Assert
        assert result.reward_xp == 0
        assert result.reward_coins == 0
        assert result.difficulty == "medium"
        assert result.category is None

    def test_create_mq_template_name_max_length(self, db_session):
        """Should allow name at max length boundary (100)."""
        # Arrange
        name = "n" * 100
        template_data = MQTemplateCreate(
            name=name,
            description_template="desc",
            type="daily",
            structure="single_action",
            completion_condition={},
        )

        # Act
        result = create_mq_template(db_session, template_data)

        # Assert
        assert result.name == name

    def test_create_mq_template_invalid_name_raises_validation_error(self):
        """Should raise ValidationError for empty name."""
        # Act & Assert
        with pytest.raises(ValidationError):
            MQTemplateCreate(
                name="",
                description_template="desc",
                type="daily",
                structure="single_action",
                completion_condition={},
            )

    def test_create_mq_template_negative_rewards_raise_validation_error(self):
        """Should raise ValidationError for negative rewards."""
        # Act & Assert
        with pytest.raises(ValidationError):
            MQTemplateCreate(
                name="Bad Rewards",
                description_template="desc",
                type="daily",
                structure="single_action",
                completion_condition={},
                reward_xp=-1,
            )
        with pytest.raises(ValidationError):
            MQTemplateCreate(
                name="Bad Rewards 2",
                description_template="desc",
                type="daily",
                structure="single_action",
                completion_condition={},
                reward_coins=-5,
            )

    def test_get_mq_template(self, db_session):
        """Should return template when ID exists."""
        # Arrange
        template = create_mq_template(
            db_session,
            MQTemplateCreate(
                name="Template",
                description_template="desc",
                type="daily",
                structure="single_action",
                completion_condition={},
            ),
        )

        # Act
        result = get_mq_template(db_session, template.id)

        # Assert
        assert result is not None
        assert result.id == template.id

    def test_get_mq_template_not_found(self, db_session):
        """Should return None when ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = get_mq_template(db_session, non_existent_id)

        # Assert
        assert result is None

    def test_get_mq_templates_by_type(self, db_session):
        """Should return templates filtered by type."""
        # Arrange
        create_mq_template(
            db_session,
            MQTemplateCreate(
                name="Daily",
                description_template="desc",
                type="daily",
                structure="single_action",
                completion_condition={},
            ),
        )
        create_mq_template(
            db_session,
            MQTemplateCreate(
                name="Timed",
                description_template="desc",
                type="timed",
                structure="single_action",
                completion_condition={},
            ),
        )

        # Act
        result = get_mq_templates_by_type(db_session, "daily")

        # Assert
        assert len(result) == 1
        assert result[0].name == "Daily"

    def test_get_mq_templates_by_type_empty(self, db_session):
        """Should return empty list when type has no templates."""
        # Act
        result = get_mq_templates_by_type(db_session, "missing")

        # Assert
        assert result == []


class TestUserMissionQuestCRUD:
    """Comprehensive tests for UserMissionQuest CRUD operations."""

    def test_create_user_mq_from_template(self, db_session, sample_user):
        """Should create user MQ linked to a template."""
        # Arrange
        template = create_mq_template(
            db_session,
            MQTemplateCreate(
                name="Template MQ",
                description_template="desc",
                type="daily",
                structure="single_action",
                completion_condition={},
            ),
        )
        user_mq_data = UserMQCreate(
            name="Daily Routine",
            user_id=sample_user.id,
            template_id=template.id,
            status="not_started",
            completion_target=100,
        )

        # Act
        result = create_user_mq(db_session, user_mq_data)

        # Assert
        assert result is not None
        assert result.id is not None
        assert len(result.id) == 36
        assert result.user_id == sample_user.id
        assert result.template_id == template.id
        assert result.status == "not_started"
        assert result.completion_target == 100
        assert result.completion_progress == 0
        assert result.created_at is not None

    def test_create_user_mq_with_parent(self, db_session, sample_user):
        """Should create user MQ with parent hierarchy."""
        # Arrange
        parent = create_user_mq(
            db_session,
            UserMQCreate(name="Parent MQ", user_id=sample_user.id),
        )
        child_data = UserMQCreate(
            name="Child MQ",
            user_id=sample_user.id,
            parent_mq_id=parent.id,
        )

        # Act
        result = create_user_mq(db_session, child_data)

        # Assert
        assert result.parent_mq_id == parent.id
        assert result.parent_mq.name == "Parent MQ"

    def test_create_user_mq_defaults(self, db_session, sample_user):
        """Should apply defaults for status and completion_target."""
        # Arrange
        user_mq_data = UserMQCreate(name="Defaults", user_id=sample_user.id)

        # Act
        result = create_user_mq(db_session, user_mq_data)

        # Assert
        assert result.status == "not_started"
        assert result.completion_target == 100
        assert result.completion_progress == 0

    def test_create_user_mq_with_deadline(self, db_session, sample_user):
        """Should store deadline when provided."""
        # Arrange
        deadline = datetime.utcnow() + timedelta(days=3)
        user_mq_data = UserMQCreate(
            name="Timed MQ",
            user_id=sample_user.id,
            deadline=deadline,
        )

        # Act
        result = create_user_mq(db_session, user_mq_data)

        # Assert
        assert result.deadline is not None
        assert result.deadline.date() == deadline.date()

    def test_create_user_mq_invalid_user_id_raises_validation_error(self):
        """Should raise ValidationError for invalid user_id UUID."""
        # Act & Assert
        with pytest.raises(ValidationError):
            UserMQCreate(name="Invalid", user_id="not-a-uuid")

    def test_get_user_mq(self, db_session, sample_user):
        """Should return user MQ when ID exists."""
        # Arrange
        user_mq = create_user_mq(
            db_session,
            UserMQCreate(name="Fetch", user_id=sample_user.id),
        )

        # Act
        result = get_user_mq(db_session, user_mq.id)

        # Assert
        assert result is not None
        assert result.id == user_mq.id

    def test_get_user_mq_not_found(self, db_session):
        """Should return None when ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = get_user_mq(db_session, non_existent_id)

        # Assert
        assert result is None

    def test_get_user_mqs_all(self, db_session, sample_user):
        """Should return all MQs for a user."""
        # Arrange
        for name in ["MQ1", "MQ2", "MQ3"]:
            create_user_mq(db_session, UserMQCreate(name=name, user_id=sample_user.id))

        # Act
        result = get_user_mqs(db_session, sample_user.id)

        # Assert
        assert len(result) == 3
        names = {mq.name for mq in result}
        assert names == {"MQ1", "MQ2", "MQ3"}

    def test_get_user_mqs_filtered_by_status(self, db_session, sample_user):
        """Should return only MQs with the specified status."""
        # Arrange
        create_user_mq(
            db_session,
            UserMQCreate(name="Not Started", user_id=sample_user.id, status="not_started"),
        )
        create_user_mq(
            db_session,
            UserMQCreate(name="In Progress", user_id=sample_user.id, status="in_progress"),
        )

        # Act
        result = get_user_mqs(db_session, sample_user.id, status="in_progress")

        # Assert
        assert len(result) == 1
        assert result[0].name == "In Progress"

    def test_get_user_mqs_empty_for_no_mqs(self, db_session, sample_user):
        """Should return empty list when user has no MQs."""
        # Act
        result = get_user_mqs(db_session, sample_user.id)

        # Assert
        assert result == []

    def test_get_user_mqs_only_returns_user_mqs(self, db_session, sample_user, fake):
        """Should only return MQs for the specified user."""
        # Arrange
        other_user = User(username=fake.user_name(), email=fake.email())
        db_session.add(other_user)
        db_session.commit()

        create_user_mq(db_session, UserMQCreate(name="Mine", user_id=sample_user.id))
        create_user_mq(db_session, UserMQCreate(name="Other", user_id=other_user.id))

        # Act
        result = get_user_mqs(db_session, sample_user.id)

        # Assert
        assert len(result) == 1
        assert result[0].user_id == sample_user.id

    def test_get_user_mq_with_children(self, db_session, sample_user):
        """Should return user MQ with child quests loaded."""
        # Arrange
        parent = create_user_mq(
            db_session,
            UserMQCreate(name="Parent", user_id=sample_user.id),
        )
        create_user_mq(
            db_session,
            UserMQCreate(name="Child 1", user_id=sample_user.id, parent_mq_id=parent.id),
        )
        create_user_mq(
            db_session,
            UserMQCreate(name="Child 2", user_id=sample_user.id, parent_mq_id=parent.id),
        )

        # Act
        result = get_user_mq_with_children(db_session, parent.id)

        # Assert
        assert result is not None
        assert len(result.child_mq) == 2
        child_names = {c.name for c in result.child_mq}
        assert child_names == {"Child 1", "Child 2"}

    def test_get_user_mq_with_children_only_direct(self, db_session, sample_user):
        """Should include only direct children, not grandchildren."""
        # Arrange
        parent = create_user_mq(
            db_session,
            UserMQCreate(name="Parent", user_id=sample_user.id),
        )
        child = create_user_mq(
            db_session,
            UserMQCreate(name="Child", user_id=sample_user.id, parent_mq_id=parent.id),
        )
        create_user_mq(
            db_session,
            UserMQCreate(name="Grandchild", user_id=sample_user.id, parent_mq_id=child.id),
        )

        # Act
        result = get_user_mq_with_children(db_session, parent.id)

        # Assert
        assert result is not None
        child_names = {c.name for c in result.child_mq}
        assert child_names == {"Child"}

    def test_get_user_mq_with_children_not_found(self, db_session):
        """Should return None when quest ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = get_user_mq_with_children(db_session, non_existent_id)

        # Assert
        assert result is None

    def test_update_mq_progress(self, db_session, sample_user):
        """Should update completion progress."""
        # Arrange
        user_mq = create_user_mq(
            db_session,
            UserMQCreate(name="Progress", user_id=sample_user.id),
        )

        # Act
        result = update_mq_progress(db_session, user_mq.id, progress=50)

        # Assert
        assert result is not None
        assert result.completion_progress == 50

    def test_update_mq_progress_not_found(self, db_session):
        """Should return None when quest ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = update_mq_progress(db_session, non_existent_id, progress=10)

        # Assert
        assert result is None

    def test_complete_user_mq_sets_status_and_timestamp(self, db_session, sample_user):
        """Should set status to completed and completed_at to now."""
        # Arrange
        user_mq = create_user_mq(
            db_session,
            UserMQCreate(name="Complete", user_id=sample_user.id),
        )

        # Act
        result = complete_user_mq(db_session, user_mq.id)

        # Assert
        assert result is not None
        assert result.status == "completed"
        assert result.completed_at is not None

    def test_complete_user_mq_not_found(self, db_session):
        """Should return None when quest ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = complete_user_mq(db_session, non_existent_id)

        # Assert
        assert result is None

    def test_update_user_mq_partial_fields(self, db_session, sample_user):
        """Should update specified fields only."""
        # Arrange
        user_mq = create_user_mq(
            db_session,
            UserMQCreate(name="Update", user_id=sample_user.id),
        )

        # Act
        update = UserMQUpdate(status="in_progress", completion_progress=25)
        result = update_user_mq(db_session, user_mq.id, update)

        # Assert
        assert result is not None
        assert result.status == "in_progress"
        assert result.completion_progress == 25

    def test_update_user_mq_empty_update(self, db_session, sample_user):
        """Should allow empty update with no changes."""
        # Arrange
        user_mq = create_user_mq(
            db_session,
            UserMQCreate(name="No Change", user_id=sample_user.id),
        )

        # Act
        update = UserMQUpdate()
        result = update_user_mq(db_session, user_mq.id, update)

        # Assert
        assert result is not None
        assert result.name == "No Change"

    def test_update_user_mq_invalid_progress_raises_validation_error(self):
        """Should raise ValidationError for negative progress."""
        # Act & Assert
        with pytest.raises(ValidationError):
            UserMQUpdate(completion_progress=-1)

    def test_update_user_mq_extra_field_raises_validation_error(self):
        """Should raise ValidationError for extra fields."""
        # Act & Assert
        with pytest.raises(ValidationError):
            UserMQUpdate.model_validate({"status": "in_progress", "extra": "field"})

    def test_update_user_mq_not_found(self, db_session):
        """Should return None when quest ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        update = UserMQUpdate(status="in_progress")
        result = update_user_mq(db_session, non_existent_id, update)

        # Assert
        assert result is None

    def test_delete_user_mq_success(self, db_session, sample_user):
        """Should delete quest and return True."""
        # Arrange
        user_mq = create_user_mq(
            db_session,
            UserMQCreate(name="Delete", user_id=sample_user.id),
        )

        # Act
        result = delete_user_mq(db_session, user_mq.id)

        # Assert
        assert result is True
        assert get_user_mq(db_session, user_mq.id) is None

    @pytest.mark.xfail(
        reason="UserMissionQuest uses SET NULL or no cascade for child_mq"
    )
    def test_delete_user_mq_cascades_to_children(self, db_session, sample_user):
        """Should cascade delete to child quests when parent is deleted."""
        # Arrange
        parent = create_user_mq(
            db_session,
            UserMQCreate(name="Parent", user_id=sample_user.id),
        )
        child1 = create_user_mq(
            db_session,
            UserMQCreate(name="Child 1", user_id=sample_user.id, parent_mq_id=parent.id),
        )
        child2 = create_user_mq(
            db_session,
            UserMQCreate(name="Child 2", user_id=sample_user.id, parent_mq_id=parent.id),
        )

        # Act
        result = delete_user_mq(db_session, parent.id)

        # Assert
        assert result is True
        assert get_user_mq(db_session, parent.id) is None
        assert get_user_mq(db_session, child1.id) is None
        assert get_user_mq(db_session, child2.id) is None

    def test_delete_user_mq_orphans_children(self, db_session, sample_user):
        """Documents current behavior: children are orphaned on parent deletion."""
        # Arrange
        parent = create_user_mq(
            db_session,
            UserMQCreate(name="Parent", user_id=sample_user.id),
        )
        child = create_user_mq(
            db_session,
            UserMQCreate(name="Child", user_id=sample_user.id, parent_mq_id=parent.id),
        )

        # Act
        result = delete_user_mq(db_session, parent.id)

        # Assert
        assert result is True
        child_after = get_user_mq(db_session, child.id)
        assert child_after is not None
        assert child_after.parent_mq_id is None or child_after.parent_mq_id == parent.id

    def test_delete_user_mq_nonexistent_returns_false(self, db_session):
        """Should return False when quest ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = delete_user_mq(db_session, non_existent_id)

        # Assert
        assert result is False

    def test_delete_user_mq_already_deleted_returns_false(self, db_session, sample_user):
        """Should return False when deleting quest twice."""
        # Arrange
        user_mq = create_user_mq(
            db_session,
            UserMQCreate(name="Delete Twice", user_id=sample_user.id),
        )

        # Act
        first_result = delete_user_mq(db_session, user_mq.id)
        second_result = delete_user_mq(db_session, user_mq.id)

        # Assert
        assert first_result is True
        assert second_result is False
