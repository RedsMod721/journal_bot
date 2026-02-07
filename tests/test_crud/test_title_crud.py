"""
Tests for Title CRUD operations.

This module tests all CRUD functions in app/crud/title.py:
- TitleTemplate: create/get/list/query by name/category
- UserTitle: award, get, list, equip/unequip, remove

Uses db_session and sample_user fixtures from conftest.py.
"""
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.crud.title import (
    award_title_to_user,
    create_title_template,
    equip_title,
    get_all_title_templates,
    get_title_template,
    get_title_template_by_name,
    get_title_templates_by_category,
    get_user_title,
    get_user_titles,
    remove_user_title,
    unequip_title,
)
from app.models.title import TitleTemplate, UserTitle
from app.models.user import User
from app.schemas.title import TitleTemplateCreate, UserTitleCreate


class TestTitleTemplateCRUD:
    """Comprehensive tests for TitleTemplate CRUD operations."""

    # =========================================================================
    # CREATE TESTS
    # =========================================================================

    def test_create_title_template(self, db_session):
        """Should create title template with valid data."""
        # Arrange
        template_data = TitleTemplateCreate(
            name="Early Riser",
            description_template="{user_name} wakes before the sun",
            effect={"type": "xp_multiplier", "value": 1.05},
            rank="C",
            unlock_condition={"type": "morning_entries", "count": 10},
            category="Productivity",
            is_hidden=False,
        )

        # Act
        result = create_title_template(db_session, template_data)

        # Assert
        assert result is not None
        assert result.id is not None
        assert len(result.id) == 36
        assert result.name == "Early Riser"
        assert result.description_template == "{user_name} wakes before the sun"
        assert result.effect["type"] == "xp_multiplier"
        assert result.rank == "C"
        assert result.unlock_condition["type"] == "morning_entries"
        assert result.category == "Productivity"
        assert result.is_hidden is False

    def test_create_title_template_defaults(self, db_session):
        """Should apply defaults for optional fields."""
        # Arrange
        template_data = TitleTemplateCreate(
            name="Default Title",
            description_template="Default desc",
            effect={},
            unlock_condition={},
        )

        # Act
        result = create_title_template(db_session, template_data)

        # Assert
        assert result.rank == "D"
        assert result.category is None
        assert result.is_hidden is False

    def test_create_title_template_name_max_length(self, db_session):
        """Should allow name at max length boundary (100)."""
        # Arrange
        name = "n" * 100
        template_data = TitleTemplateCreate(
            name=name,
            description_template="desc",
            effect={},
            unlock_condition={},
        )

        # Act
        result = create_title_template(db_session, template_data)

        # Assert
        assert result.name == name

    def test_create_title_template_invalid_name_raises_validation_error(self):
        """Should raise ValidationError for empty name."""
        # Act & Assert
        with pytest.raises(ValidationError):
            TitleTemplateCreate(
                name="",
                description_template="desc",
                effect={},
                unlock_condition={},
            )

    def test_create_title_template_extra_field_raises_validation_error(self):
        """Should raise ValidationError for extra fields."""
        # Act & Assert
        with pytest.raises(ValidationError):
            TitleTemplateCreate.model_validate({
                "name": "Valid",
                "description_template": "desc",
                "effect": {},
                "unlock_condition": {},
                "extra": "field",
            })

    # =========================================================================
    # READ TESTS
    # =========================================================================

    def test_get_title_template(self, db_session):
        """Should return title template when ID exists."""
        # Arrange
        template = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Reader",
                description_template="Reads daily",
                effect={},
                unlock_condition={},
            ),
        )

        # Act
        result = get_title_template(db_session, template.id)

        # Assert
        assert result is not None
        assert result.id == template.id

    def test_get_title_template_by_name(self, db_session):
        """Should return title template when name exists."""
        # Arrange
        create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Night Owl",
                description_template="Stays up late",
                effect={},
                unlock_condition={},
            ),
        )

        # Act
        result = get_title_template_by_name(db_session, "Night Owl")

        # Assert
        assert result is not None
        assert result.name == "Night Owl"

    def test_get_title_template_by_name_not_found(self, db_session):
        """Should return None when name does not exist."""
        # Act
        result = get_title_template_by_name(db_session, "Missing")

        # Assert
        assert result is None

    def test_get_all_title_templates(self, db_session):
        """Should return all title templates."""
        # Arrange
        for name in ["A", "B", "C"]:
            create_title_template(
                db_session,
                TitleTemplateCreate(
                    name=name,
                    description_template="desc",
                    effect={},
                    unlock_condition={},
                ),
            )

        # Act
        result = get_all_title_templates(db_session)

        # Assert
        assert len(result) == 3
        names = {t.name for t in result}
        assert names == {"A", "B", "C"}

    def test_get_all_title_templates_empty(self, db_session):
        """Should return empty list when no templates exist."""
        # Act
        result = get_all_title_templates(db_session)

        # Assert
        assert result == []

    def test_get_title_templates_by_category(self, db_session):
        """Should return templates filtered by category."""
        # Arrange
        create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Cat1",
                description_template="desc",
                effect={},
                unlock_condition={},
                category="Productivity",
            ),
        )
        create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Cat2",
                description_template="desc",
                effect={},
                unlock_condition={},
                category="Lifestyle",
            ),
        )

        # Act
        result = get_title_templates_by_category(db_session, "Productivity")

        # Assert
        assert len(result) == 1
        assert result[0].name == "Cat1"

    def test_get_title_templates_by_category_empty(self, db_session):
        """Should return empty list when category has no templates."""
        # Act
        result = get_title_templates_by_category(db_session, "Missing")

        # Assert
        assert result == []


class TestUserTitleCRUD:
    """Comprehensive tests for UserTitle CRUD operations."""

    # =========================================================================
    # AWARD TESTS
    # =========================================================================

    def test_award_title_to_user(self, db_session, sample_user):
        """Should award a title to a user and return UserTitle instance."""
        # Arrange
        template = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Consistent",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )
        award_data = UserTitleCreate(
            user_id=sample_user.id,
            title_template_id=template.id,
            personalized_description="Great work!",
        )

        # Act
        result = award_title_to_user(db_session, award_data)

        # Assert
        assert result is not None
        assert result.id is not None
        assert len(result.id) == 36
        assert result.user_id == sample_user.id
        assert result.title_template_id == template.id
        assert result.is_equipped is True
        assert result.personalized_description == "Great work!"
        assert result.acquired_at is not None

    def test_award_title_with_expiration(self, db_session, sample_user):
        """Should store expiration datetime when provided."""
        # Arrange
        template = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Temp",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )
        expires_at = datetime.utcnow() + timedelta(days=7)
        award_data = UserTitleCreate(
            user_id=sample_user.id,
            title_template_id=template.id,
            expires_at=expires_at,
        )

        # Act
        result = award_title_to_user(db_session, award_data)

        # Assert
        assert result.expires_at is not None
        assert result.expires_at.date() == expires_at.date()

    def test_award_title_invalid_user_id_raises_validation_error(self, db_session):
        """Should raise ValidationError for invalid user_id UUID."""
        # Arrange
        template = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="BadUser",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )

        # Act & Assert
        with pytest.raises(ValidationError):
            UserTitleCreate(user_id="not-a-uuid", title_template_id=template.id)

    def test_award_title_invalid_template_id_raises_validation_error(self, db_session, sample_user):
        """Should raise ValidationError for invalid title_template_id UUID."""
        # Act & Assert
        with pytest.raises(ValidationError):
            UserTitleCreate(user_id=sample_user.id, title_template_id="not-a-uuid")

    # =========================================================================
    # READ TESTS
    # =========================================================================

    def test_get_user_title(self, db_session, sample_user):
        """Should return user title when ID exists."""
        # Arrange
        template = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Reader",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )
        user_title = award_title_to_user(
            db_session,
            UserTitleCreate(user_id=sample_user.id, title_template_id=template.id),
        )

        # Act
        result = get_user_title(db_session, user_title.id)

        # Assert
        assert result is not None
        assert result.id == user_title.id

    def test_get_user_title_not_found(self, db_session):
        """Should return None when user title ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = get_user_title(db_session, non_existent_id)

        # Assert
        assert result is None

    def test_get_user_titles_all(self, db_session, sample_user):
        """Should return all titles for a user."""
        # Arrange
        templates = []
        for name in ["T1", "T2", "T3"]:
            templates.append(
                create_title_template(
                    db_session,
                    TitleTemplateCreate(
                        name=name,
                        description_template="desc",
                        effect={},
                        unlock_condition={},
                    ),
                )
            )
        for template in templates:
            award_title_to_user(
                db_session,
                UserTitleCreate(user_id=sample_user.id, title_template_id=template.id),
            )

        # Act
        result = get_user_titles(db_session, sample_user.id)

        # Assert
        assert len(result) == 3
        template_ids = {t.title_template_id for t in result}
        assert template_ids == {t.id for t in templates}

    def test_get_user_titles_equipped_only(self, db_session, sample_user):
        """Should return only equipped titles when equipped_only=True."""
        # Arrange
        template1 = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Equipped",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )
        template2 = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Unequipped",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )
        t1 = award_title_to_user(
            db_session,
            UserTitleCreate(user_id=sample_user.id, title_template_id=template1.id),
        )
        t2 = award_title_to_user(
            db_session,
            UserTitleCreate(
                user_id=sample_user.id,
                title_template_id=template2.id,
                is_equipped=False,
            ),
        )

        # Act
        result = get_user_titles(db_session, sample_user.id, equipped_only=True)

        # Assert
        assert len(result) == 1
        assert result[0].id == t1.id
        assert result[0].is_equipped is True

    def test_get_user_titles_only_returns_user_titles(self, db_session, sample_user, fake):
        """Should only return titles for the specified user."""
        # Arrange - Create another user
        other_user = User(username=fake.user_name(), email=fake.email())
        db_session.add(other_user)
        db_session.commit()

        template = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Shared",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )
        award_title_to_user(
            db_session,
            UserTitleCreate(user_id=sample_user.id, title_template_id=template.id),
        )
        award_title_to_user(
            db_session,
            UserTitleCreate(user_id=other_user.id, title_template_id=template.id),
        )

        # Act
        result = get_user_titles(db_session, sample_user.id)

        # Assert
        assert len(result) == 1
        assert result[0].user_id == sample_user.id

    # =========================================================================
    # EQUIP/UNEQUIP TESTS
    # =========================================================================

    def test_equip_title_sets_flag(self, db_session, sample_user):
        """Should set is_equipped to True."""
        # Arrange
        template = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Equip",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )
        user_title = award_title_to_user(
            db_session,
            UserTitleCreate(
                user_id=sample_user.id,
                title_template_id=template.id,
                is_equipped=False,
            ),
        )

        # Act
        result = equip_title(db_session, user_title.id)

        # Assert
        assert result is not None
        assert result.is_equipped is True

    def test_equip_title_not_found(self, db_session):
        """Should return None when user title does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = equip_title(db_session, non_existent_id)

        # Assert
        assert result is None

    def test_unequip_title_sets_flag(self, db_session, sample_user):
        """Should set is_equipped to False."""
        # Arrange
        template = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Unequip",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )
        user_title = award_title_to_user(
            db_session,
            UserTitleCreate(user_id=sample_user.id, title_template_id=template.id),
        )

        # Act
        result = unequip_title(db_session, user_title.id)

        # Assert
        assert result is not None
        assert result.is_equipped is False

    def test_unequip_title_not_found(self, db_session):
        """Should return None when user title does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = unequip_title(db_session, non_existent_id)

        # Assert
        assert result is None

    # =========================================================================
    # REMOVE TESTS
    # =========================================================================

    def test_user_can_have_multiple_titles(self, db_session, sample_user):
        """User should be able to have multiple titles."""
        # Arrange
        template1 = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Multi 1",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )
        template2 = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Multi 2",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )
        award_title_to_user(
            db_session,
            UserTitleCreate(user_id=sample_user.id, title_template_id=template1.id),
        )
        award_title_to_user(
            db_session,
            UserTitleCreate(user_id=sample_user.id, title_template_id=template2.id),
        )

        # Act
        result = get_user_titles(db_session, sample_user.id)

        # Assert
        assert len(result) == 2

    def test_remove_user_title_success(self, db_session, sample_user):
        """Should remove user title and return True."""
        # Arrange
        template = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Remove",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )
        user_title = award_title_to_user(
            db_session,
            UserTitleCreate(user_id=sample_user.id, title_template_id=template.id),
        )

        # Act
        result = remove_user_title(db_session, user_title.id)

        # Assert
        assert result is True
        assert get_user_title(db_session, user_title.id) is None

    def test_remove_user_title_not_found(self, db_session):
        """Should return False when user title does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = remove_user_title(db_session, non_existent_id)

        # Assert
        assert result is False

    def test_remove_user_title_already_removed_returns_false(self, db_session, sample_user):
        """Should return False when removing title twice."""
        # Arrange
        template = create_title_template(
            db_session,
            TitleTemplateCreate(
                name="Remove Twice",
                description_template="desc",
                effect={},
                unlock_condition={},
            ),
        )
        user_title = award_title_to_user(
            db_session,
            UserTitleCreate(user_id=sample_user.id, title_template_id=template.id),
        )

        # Act
        first_result = remove_user_title(db_session, user_title.id)
        second_result = remove_user_title(db_session, user_title.id)

        # Assert
        assert first_result is True
        assert second_result is False
