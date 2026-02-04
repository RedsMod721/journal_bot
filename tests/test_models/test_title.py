"""
Comprehensive tests for the Title models (TitleTemplate and UserTitle).

Tests cover:
- TitleTemplate creation and attributes
- UserTitle creation and relationships
- User-title relationships (one-to-many)
- JSON storage for effects and unlock conditions
- Default values and constraints

Follows the AAA pattern: Arrange, Act, Assert
"""
import pytest
from datetime import datetime, timedelta

from app.models.title import TitleTemplate, UserTitle
from app.models.user import User


class TestTitleTemplateModel:
    """Test suite for TitleTemplate model."""

    # =========================================================================
    # CREATION TESTS
    # =========================================================================

    def test_title_template_creation(self, db_session):
        """Should create title template with all required fields."""
        # Arrange
        name = "Consistent Chronicler"
        description = "{user_name} has shown dedication to daily journaling."
        effect = {"type": "xp_multiplier", "scope": "theme", "target": "Education", "value": 1.10}
        rank = "C"
        unlock_condition = {"type": "journal_streak", "value": 7}
        category = "Productivity"

        # Act
        template = TitleTemplate(
            name=name,
            description_template=description,
            effect=effect,
            rank=rank,
            unlock_condition=unlock_condition,
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
        assert template.effect == effect
        assert template.rank == rank
        assert template.unlock_condition == unlock_condition
        assert template.category == category
        assert template.is_hidden is False

    def test_title_template_creation_generates_uuid(self, db_session):
        """Should auto-generate a valid UUID string for primary key."""
        # Arrange & Act
        template = TitleTemplate(name="Test Title")
        db_session.add(template)
        db_session.commit()

        # Assert - UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert template.id is not None
        assert len(template.id) == 36
        assert template.id.count("-") == 4

    # =========================================================================
    # DEFAULT VALUE TESTS
    # =========================================================================

    def test_title_template_default_rank_is_d(self, db_session):
        """Should default rank to 'D' when not specified."""
        # Arrange & Act
        template = TitleTemplate(name="Default Rank Title")
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert template.rank == "D"

    def test_title_template_default_is_hidden_is_false(self, db_session):
        """Should default is_hidden to False when not specified."""
        # Arrange & Act
        template = TitleTemplate(name="Visible Title")
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert template.is_hidden is False

    def test_title_template_default_effect_is_empty_dict(self, db_session):
        """Should default effect to empty dict when not specified."""
        # Arrange & Act
        template = TitleTemplate(name="No Effect Title")
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert template.effect == {}

    def test_title_template_default_unlock_condition_is_empty_dict(self, db_session):
        """Should default unlock_condition to empty dict when not specified."""
        # Arrange & Act
        template = TitleTemplate(name="No Condition Title")
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert template.unlock_condition == {}

    # =========================================================================
    # CONSTRAINT TESTS
    # =========================================================================

    def test_title_template_unique_name_constraint(self, db_session):
        """Should raise error for duplicate title names."""
        # Arrange
        template1 = TitleTemplate(name="Unique Title")
        db_session.add(template1)
        db_session.commit()

        # Act & Assert
        from sqlalchemy.exc import IntegrityError

        template2 = TitleTemplate(name="Unique Title")
        db_session.add(template2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    # =========================================================================
    # JSON STORAGE TESTS
    # =========================================================================

    def test_title_template_effect_json_storage(self, db_session):
        """Should correctly store and retrieve complex JSON effect data."""
        # Arrange
        effect = {
            "type": "xp_multiplier",
            "scope": "theme",
            "target": "Education",
            "value": 1.10,
            "conditions": {"time_of_day": "morning", "min_level": 5},
        }

        # Act
        template = TitleTemplate(name="Complex Effect Title", effect=effect)
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert template.effect == effect
        assert template.effect["type"] == "xp_multiplier"
        assert template.effect["value"] == 1.10
        assert template.effect["conditions"]["time_of_day"] == "morning"

    def test_title_template_unlock_condition_json_storage(self, db_session):
        """Should correctly store and retrieve complex JSON unlock condition data."""
        # Arrange
        unlock_condition = {
            "type": "compound",
            "operator": "AND",
            "conditions": [
                {"type": "journal_streak", "value": 7},
                {"type": "theme_level", "theme": "Education", "value": 10},
            ],
        }

        # Act
        template = TitleTemplate(
            name="Complex Unlock Title",
            unlock_condition=unlock_condition,
        )
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert template.unlock_condition == unlock_condition
        assert template.unlock_condition["type"] == "compound"
        assert len(template.unlock_condition["conditions"]) == 2

    # =========================================================================
    # REPR TEST
    # =========================================================================

    def test_title_template_repr(self, db_session):
        """Should return readable string representation."""
        # Arrange
        template = TitleTemplate(name="Test Title", rank="A")

        # Act
        repr_string = repr(template)

        # Assert
        assert repr_string == "<TitleTemplate Test Title (Rank A)>"


class TestUserTitleModel:
    """Test suite for UserTitle model."""

    # =========================================================================
    # CREATION TESTS
    # =========================================================================

    def test_user_title_creation(self, db_session, sample_user):
        """Should create user title with all required fields."""
        # Arrange
        template = TitleTemplate(
            name="Test Title",
            effect={"type": "xp_multiplier", "value": 1.05},
        )
        db_session.add(template)
        db_session.commit()

        # Act
        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
        )
        db_session.add(user_title)
        db_session.commit()
        db_session.refresh(user_title)

        # Assert
        assert user_title.id is not None
        assert len(user_title.id) == 36
        assert user_title.user_id == sample_user.id
        assert user_title.title_template_id == template.id
        assert user_title.acquired_at is not None
        assert user_title.is_equipped is True
        assert user_title.personalized_description is None
        assert user_title.expires_at is None

    def test_user_title_creation_with_personalized_description(self, db_session, sample_user):
        """Should create user title with personalized description."""
        # Arrange
        template = TitleTemplate(name="Personal Title")
        db_session.add(template)
        db_session.commit()

        personalized = "Congratulations, testuser! You've earned this title!"

        # Act
        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            personalized_description=personalized,
        )
        db_session.add(user_title)
        db_session.commit()
        db_session.refresh(user_title)

        # Assert
        assert user_title.personalized_description == personalized

    def test_user_title_creation_with_expiration(self, db_session, sample_user):
        """Should create temporary user title with expiration date."""
        # Arrange
        template = TitleTemplate(name="Temporary Title")
        db_session.add(template)
        db_session.commit()

        expires = datetime.utcnow() + timedelta(days=7)

        # Act
        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            expires_at=expires,
        )
        db_session.add(user_title)
        db_session.commit()
        db_session.refresh(user_title)

        # Assert
        assert user_title.expires_at is not None
        assert user_title.expires_at > datetime.utcnow()

    # =========================================================================
    # DEFAULT VALUE TESTS
    # =========================================================================

    def test_user_title_default_is_equipped_is_true(self, db_session, sample_user):
        """Should default is_equipped to True when not specified."""
        # Arrange
        template = TitleTemplate(name="Equipped Title")
        db_session.add(template)
        db_session.commit()

        # Act
        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
        )
        db_session.add(user_title)
        db_session.commit()
        db_session.refresh(user_title)

        # Assert
        assert user_title.is_equipped is True

    def test_user_title_acquired_at_set_automatically(self, db_session, sample_user):
        """Should auto-set acquired_at timestamp on creation."""
        # Arrange
        template = TitleTemplate(name="Timed Title")
        db_session.add(template)
        db_session.commit()

        # Act
        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
        )
        db_session.add(user_title)
        db_session.commit()
        db_session.refresh(user_title)

        # Assert
        assert user_title.acquired_at is not None
        assert user_title.acquired_at > datetime.utcnow() - timedelta(minutes=1)

    # =========================================================================
    # RELATIONSHIP TESTS
    # =========================================================================

    def test_user_title_relationship_to_template(self, db_session, sample_user):
        """Should have bidirectional relationship with TitleTemplate."""
        # Arrange
        template = TitleTemplate(
            name="Related Title",
            effect={"type": "xp_multiplier", "value": 1.15},
        )
        db_session.add(template)
        db_session.commit()

        # Act
        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
        )
        db_session.add(user_title)
        db_session.commit()
        db_session.refresh(user_title)
        db_session.refresh(template)

        # Assert - bidirectional access
        assert user_title.title_template.id == template.id
        assert user_title.title_template.name == "Related Title"
        assert len(template.user_titles) == 1
        assert template.user_titles[0].id == user_title.id

    def test_user_title_relationship_to_user(self, db_session, sample_user):
        """Should have bidirectional relationship with User."""
        # Arrange
        template = TitleTemplate(name="User Related Title")
        db_session.add(template)
        db_session.commit()

        # Act
        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
        )
        db_session.add(user_title)
        db_session.commit()
        db_session.refresh(user_title)
        db_session.refresh(sample_user)

        # Assert - bidirectional access
        assert user_title.user.id == sample_user.id
        assert len(sample_user.user_titles) == 1
        assert sample_user.user_titles[0].id == user_title.id

    def test_user_can_have_multiple_titles(self, db_session, sample_user):
        """User should be able to have multiple titles."""
        # Arrange
        template1 = TitleTemplate(name="Title 1", rank="D")
        template2 = TitleTemplate(name="Title 2", rank="C")
        template3 = TitleTemplate(name="Title 3", rank="B")
        db_session.add_all([template1, template2, template3])
        db_session.commit()

        # Act
        user_title1 = UserTitle(user_id=sample_user.id, title_template_id=template1.id)
        user_title2 = UserTitle(user_id=sample_user.id, title_template_id=template2.id)
        user_title3 = UserTitle(user_id=sample_user.id, title_template_id=template3.id)
        db_session.add_all([user_title1, user_title2, user_title3])
        db_session.commit()
        db_session.refresh(sample_user)

        # Assert
        assert len(sample_user.user_titles) == 3
        title_names = {ut.title_template.name for ut in sample_user.user_titles}
        assert title_names == {"Title 1", "Title 2", "Title 3"}

    def test_multiple_users_can_have_same_title_template(self, db_session, fake):
        """Multiple users should be able to earn the same title."""
        # Arrange
        template = TitleTemplate(name="Shared Title")
        db_session.add(template)
        db_session.commit()

        user1 = User(username=fake.user_name(), email=fake.email())
        user2 = User(username=fake.user_name(), email=fake.email())
        db_session.add_all([user1, user2])
        db_session.commit()

        # Act
        user_title1 = UserTitle(user_id=user1.id, title_template_id=template.id)
        user_title2 = UserTitle(user_id=user2.id, title_template_id=template.id)
        db_session.add_all([user_title1, user_title2])
        db_session.commit()
        db_session.refresh(template)

        # Assert
        assert len(template.user_titles) == 2
        user_ids = {ut.user_id for ut in template.user_titles}
        assert user_ids == {user1.id, user2.id}

    # =========================================================================
    # CASCADE DELETE TESTS
    # =========================================================================

    def test_user_deletion_cascades_to_user_titles(self, db_session, sample_user):
        """Deleting user should cascade delete all their user titles."""
        # Arrange
        template1 = TitleTemplate(name="Cascade Title 1")
        template2 = TitleTemplate(name="Cascade Title 2")
        db_session.add_all([template1, template2])
        db_session.commit()

        user_title1 = UserTitle(user_id=sample_user.id, title_template_id=template1.id)
        user_title2 = UserTitle(user_id=sample_user.id, title_template_id=template2.id)
        db_session.add_all([user_title1, user_title2])
        db_session.commit()
        user_id = sample_user.id

        # Act
        db_session.delete(sample_user)
        db_session.commit()

        # Assert
        remaining_titles = db_session.query(UserTitle).filter(
            UserTitle.user_id == user_id
        ).all()
        assert len(remaining_titles) == 0

    def test_title_template_deletion_cascades_to_user_titles(self, db_session, sample_user):
        """Deleting title template should cascade delete all user titles referencing it."""
        # Arrange
        template = TitleTemplate(name="Delete Me Title")
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(user_id=sample_user.id, title_template_id=template.id)
        db_session.add(user_title)
        db_session.commit()
        template_id = template.id

        # Act
        db_session.delete(template)
        db_session.commit()

        # Assert
        remaining_titles = db_session.query(UserTitle).filter(
            UserTitle.title_template_id == template_id
        ).all()
        assert len(remaining_titles) == 0

    # =========================================================================
    # EQUIP/UNEQUIP TESTS
    # =========================================================================

    def test_user_title_can_be_unequipped(self, db_session, sample_user):
        """Should be able to unequip a title."""
        # Arrange
        template = TitleTemplate(name="Unequip Test Title")
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            is_equipped=True,
        )
        db_session.add(user_title)
        db_session.commit()

        # Act
        user_title.is_equipped = False
        db_session.commit()
        db_session.refresh(user_title)

        # Assert
        assert user_title.is_equipped is False

    def test_user_title_can_be_reequipped(self, db_session, sample_user):
        """Should be able to re-equip an unequipped title."""
        # Arrange
        template = TitleTemplate(name="Reequip Test Title")
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            is_equipped=False,
        )
        db_session.add(user_title)
        db_session.commit()

        # Act
        user_title.is_equipped = True
        db_session.commit()
        db_session.refresh(user_title)

        # Assert
        assert user_title.is_equipped is True

    # =========================================================================
    # REPR TEST
    # =========================================================================

    def test_user_title_repr_equipped(self, db_session, sample_user):
        """Should return readable string representation for equipped title."""
        # Arrange
        template = TitleTemplate(name="Repr Test Title")
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            is_equipped=True,
        )
        db_session.add(user_title)
        db_session.commit()

        # Act
        repr_string = repr(user_title)

        # Assert
        assert repr_string == "<UserTitle Repr Test Title (Equipped)>"

    def test_user_title_repr_unequipped(self, db_session, sample_user):
        """Should return readable string representation for unequipped title."""
        # Arrange
        template = TitleTemplate(name="Unequipped Repr Title")
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            is_equipped=False,
        )
        db_session.add(user_title)
        db_session.commit()

        # Act
        repr_string = repr(user_title)

        # Assert
        assert repr_string == "<UserTitle Unequipped Repr Title (Unequipped)>"


class TestTitleRankSystem:
    """Test suite for title rank system."""

    def test_all_valid_ranks(self, db_session):
        """Should accept all valid rank values (F, E, D, C, B, A, S)."""
        # Arrange
        valid_ranks = ["F", "E", "D", "C", "B", "A", "S"]

        # Act & Assert
        for rank in valid_ranks:
            template = TitleTemplate(name=f"Rank {rank} Title", rank=rank)
            db_session.add(template)
            db_session.commit()
            db_session.refresh(template)
            assert template.rank == rank

    def test_title_templates_can_be_queried_by_rank(self, db_session):
        """Should be able to filter title templates by rank."""
        # Arrange
        templates = [
            TitleTemplate(name="F Rank", rank="F"),
            TitleTemplate(name="D Rank", rank="D"),
            TitleTemplate(name="S Rank", rank="S"),
        ]
        db_session.add_all(templates)
        db_session.commit()

        # Act
        s_rank_titles = db_session.query(TitleTemplate).filter(
            TitleTemplate.rank == "S"
        ).all()

        # Assert
        assert len(s_rank_titles) == 1
        assert s_rank_titles[0].name == "S Rank"


class TestTitleCategory:
    """Test suite for title categories."""

    def test_title_templates_can_be_queried_by_category(self, db_session):
        """Should be able to filter title templates by category."""
        # Arrange
        templates = [
            TitleTemplate(name="Health Title", category="Health"),
            TitleTemplate(name="Productivity Title", category="Productivity"),
            TitleTemplate(name="Social Title", category="Social"),
            TitleTemplate(name="Another Health", category="Health"),
        ]
        db_session.add_all(templates)
        db_session.commit()

        # Act
        health_titles = db_session.query(TitleTemplate).filter(
            TitleTemplate.category == "Health"
        ).all()

        # Assert
        assert len(health_titles) == 2
        title_names = {t.name for t in health_titles}
        assert title_names == {"Health Title", "Another Health"}
