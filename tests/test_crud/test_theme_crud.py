"""
Tests for Theme CRUD operations.

This module tests all CRUD functions in app/crud/theme.py:
- create_theme: Creating themes with parent support
- get_theme: Retrieving by ID
- get_user_themes: Retrieving all user's themes
- get_theme_with_subthemes: Eager loading sub-themes
- add_xp_to_theme: XP addition and level-up handling
- update_theme: Modifying theme fields
- delete_theme: Removing themes and cascade behavior

Uses db_session and sample_user fixtures from conftest.py.
"""
import pytest
from pydantic import ValidationError

from app.crud.theme import (
    add_xp_to_theme,
    create_theme,
    delete_theme,
    get_theme,
    get_theme_with_subthemes,
    get_user_themes,
    update_theme,
)
from app.models.theme import Theme
from app.models.skill import Skill
from app.schemas.theme import ThemeCreate, ThemeUpdate


class TestThemeCRUD:
    """Comprehensive tests for Theme CRUD operations."""

    # =========================================================================
    # CREATE TESTS
    # =========================================================================

    def test_create_theme_success(self, db_session, sample_user):
        """Should create theme with valid data and return Theme instance."""
        # Arrange
        theme_data = ThemeCreate(
            name="Physical Health",
            description="Fitness and wellness goals",
            user_id=sample_user.id,
        )

        # Act
        result = create_theme(db_session, theme_data)

        # Assert
        assert result is not None
        assert result.id is not None
        assert len(result.id) == 36  # UUID format
        assert result.name == "Physical Health"
        assert result.description == "Fitness and wellness goals"
        assert result.user_id == sample_user.id
        assert result.level == 0
        assert result.xp == 0.0
        assert result.xp_to_next_level == 100.0
        assert result.corrosion_level == "Fresh"
        assert result.parent_theme_id is None

    def test_create_theme_with_parent_theme(self, db_session, sample_user):
        """Should create theme with parent theme relationship."""
        # Arrange - Create parent theme
        parent_data = ThemeCreate(
            name="Education",
            user_id=sample_user.id,
        )
        parent = create_theme(db_session, parent_data)

        # Arrange - Create child theme
        child_data = ThemeCreate(
            name="Programming",
            description="Software development skills",
            user_id=sample_user.id,
            parent_theme_id=parent.id,
        )

        # Act
        result = create_theme(db_session, child_data)

        # Assert
        assert result is not None
        assert result.parent_theme_id == parent.id
        assert result.parent_theme.name == "Education"

    def test_create_theme_minimal_data(self, db_session, sample_user):
        """Should create theme with only required fields."""
        # Arrange
        theme_data = ThemeCreate(
            name="Minimal Theme",
            user_id=sample_user.id,
        )

        # Act
        result = create_theme(db_session, theme_data)

        # Assert
        assert result is not None
        assert result.name == "Minimal Theme"
        assert result.description is None
        assert result.parent_theme_id is None

    def test_create_theme_strips_whitespace(self, db_session, sample_user):
        """Should strip whitespace from name and description."""
        # Arrange
        theme_data = ThemeCreate(
            name="  Physical Health  ",
            description="  Fitness goals  ",
            user_id=sample_user.id,
        )

        # Act
        result = create_theme(db_session, theme_data)

        # Assert
        assert result.name == "Physical Health"
        assert result.description == "Fitness goals"

    def test_create_theme_name_max_length(self, db_session, sample_user):
        """Should allow name at max length boundary (100)."""
        # Arrange
        name = "n" * 100
        theme_data = ThemeCreate(name=name, user_id=sample_user.id)

        # Act
        result = create_theme(db_session, theme_data)

        # Assert
        assert result is not None
        assert result.name == name

    def test_create_theme_description_max_length(self, db_session, sample_user):
        """Should allow description at max length boundary (500)."""
        # Arrange
        description = "d" * 500
        theme_data = ThemeCreate(
            name="Max Desc",
            description=description,
            user_id=sample_user.id,
        )

        # Act
        result = create_theme(db_session, theme_data)

        # Assert
        assert result is not None
        assert result.description == description

    def test_create_theme_invalid_name_raises_validation_error(self, sample_user):
        """Should raise ValidationError for empty name."""
        # Act & Assert
        with pytest.raises(ValidationError):
            ThemeCreate(name="", user_id=sample_user.id)

    # =========================================================================
    # READ BY ID TESTS
    # =========================================================================

    def test_get_theme_by_id(self, db_session, sample_user):
        """Should return theme when ID exists."""
        # Arrange
        theme_data = ThemeCreate(
            name="Test Theme",
            user_id=sample_user.id,
        )
        created_theme = create_theme(db_session, theme_data)

        # Act
        result = get_theme(db_session, created_theme.id)

        # Assert
        assert result is not None
        assert result.id == created_theme.id
        assert result.name == "Test Theme"

    def test_get_theme_by_id_not_found(self, db_session):
        """Should return None when ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = get_theme(db_session, non_existent_id)

        # Assert
        assert result is None

    # =========================================================================
    # GET USER THEMES TESTS
    # =========================================================================

    def test_get_user_themes_returns_all_user_themes(self, db_session, sample_user):
        """Should return all themes belonging to the user."""
        # Arrange - Create multiple themes
        themes_data = [
            ThemeCreate(name="Theme 1", user_id=sample_user.id),
            ThemeCreate(name="Theme 2", user_id=sample_user.id),
            ThemeCreate(name="Theme 3", user_id=sample_user.id),
        ]
        for data in themes_data:
            create_theme(db_session, data)

        # Act
        result = get_user_themes(db_session, sample_user.id)

        # Assert
        assert len(result) == 3
        theme_names = {t.name for t in result}
        assert theme_names == {"Theme 1", "Theme 2", "Theme 3"}

    def test_get_user_themes_empty_for_no_themes(self, db_session, sample_user):
        """Should return empty list when user has no themes."""
        # Act
        result = get_user_themes(db_session, sample_user.id)

        # Assert
        assert result == []

    def test_get_user_themes_only_returns_user_themes(self, db_session, sample_user, fake):
        """Should only return themes for the specified user."""
        # Arrange - Create another user with themes
        from app.models.user import User

        other_user = User(username=fake.user_name(), email=fake.email())
        db_session.add(other_user)
        db_session.commit()

        create_theme(db_session, ThemeCreate(name="My Theme", user_id=sample_user.id))
        create_theme(db_session, ThemeCreate(name="Other Theme", user_id=other_user.id))

        # Act
        result = get_user_themes(db_session, sample_user.id)

        # Assert
        assert len(result) == 1
        assert result[0].name == "My Theme"

    # =========================================================================
    # GET THEME WITH SUBTHEMES TESTS
    # =========================================================================

    def test_get_theme_with_subthemes_includes_children(self, db_session, sample_user):
        """Should return theme with sub_themes relationship loaded."""
        # Arrange - Create parent and children
        parent_data = ThemeCreate(name="Parent Theme", user_id=sample_user.id)
        parent = create_theme(db_session, parent_data)

        child1_data = ThemeCreate(
            name="Child 1",
            user_id=sample_user.id,
            parent_theme_id=parent.id,
        )
        child2_data = ThemeCreate(
            name="Child 2",
            user_id=sample_user.id,
            parent_theme_id=parent.id,
        )
        create_theme(db_session, child1_data)
        create_theme(db_session, child2_data)

        # Act
        result = get_theme_with_subthemes(db_session, parent.id)

        # Assert
        assert result is not None
        assert len(result.sub_themes) == 2
        child_names = {c.name for c in result.sub_themes}
        assert child_names == {"Child 1", "Child 2"}

    def test_get_theme_with_subthemes_only_direct_children(self, db_session, sample_user):
        """Should include only direct children, not grandchildren."""
        # Arrange - Create parent -> child -> grandchild
        parent = create_theme(
            db_session,
            ThemeCreate(name="Parent", user_id=sample_user.id),
        )
        child = create_theme(
            db_session,
            ThemeCreate(
                name="Child",
                user_id=sample_user.id,
                parent_theme_id=parent.id,
            ),
        )
        create_theme(
            db_session,
            ThemeCreate(
                name="Grandchild",
                user_id=sample_user.id,
                parent_theme_id=child.id,
            ),
        )

        # Act
        result = get_theme_with_subthemes(db_session, parent.id)

        # Assert
        assert result is not None
        child_names = {c.name for c in result.sub_themes}
        assert child_names == {"Child"}

    def test_get_theme_with_subthemes_no_children(self, db_session, sample_user):
        """Should return theme with empty sub_themes when no children exist."""
        # Arrange
        theme_data = ThemeCreate(name="Lonely Theme", user_id=sample_user.id)
        theme = create_theme(db_session, theme_data)

        # Act
        result = get_theme_with_subthemes(db_session, theme.id)

        # Assert
        assert result is not None
        assert result.sub_themes == []

    def test_get_theme_with_subthemes_not_found(self, db_session):
        """Should return None when theme ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = get_theme_with_subthemes(db_session, non_existent_id)

        # Assert
        assert result is None

    # =========================================================================
    # ADD XP TESTS
    # =========================================================================

    def test_add_xp_to_theme_triggers_level_up(self, db_session, sample_user):
        """Should trigger level-up when XP exceeds threshold."""
        # Arrange
        theme_data = ThemeCreate(name="Leveling Theme", user_id=sample_user.id)
        theme = create_theme(db_session, theme_data)
        assert theme.level == 0
        assert theme.xp_to_next_level == 100.0

        # Act - Add enough XP to level up
        result = add_xp_to_theme(db_session, theme.id, 150.0)

        # Assert
        assert result is not None
        assert result.level == 1
        assert result.xp == pytest.approx(50.0)  # 150 - 100 = 50 overflow
        assert result.xp_to_next_level == pytest.approx(115.0)  # 100 * 1.15^1

    def test_add_xp_to_theme_multiple_level_ups(self, db_session, sample_user):
        """Should handle multiple level-ups from large XP amount."""
        # Arrange
        theme_data = ThemeCreate(name="Power Level Theme", user_id=sample_user.id)
        theme = create_theme(db_session, theme_data)

        # Act - Add enough XP for multiple levels
        # Level 0->1: 100 XP, Level 1->2: 115 XP = 215 total for 2 levels
        result = add_xp_to_theme(db_session, theme.id, 250.0)

        # Assert
        assert result is not None
        assert result.level == 2
        assert result.xp == pytest.approx(35.0)  # 250 - 100 - 115 = 35
        assert result.xp_to_next_level == pytest.approx(132.25)  # 100 * 1.15^2

    def test_add_xp_to_theme_partial_xp(self, db_session, sample_user):
        """Should accumulate XP without level-up when below threshold."""
        # Arrange
        theme_data = ThemeCreate(name="Partial XP Theme", user_id=sample_user.id)
        theme = create_theme(db_session, theme_data)

        # Act
        result = add_xp_to_theme(db_session, theme.id, 50.0)

        # Assert
        assert result is not None
        assert result.level == 0
        assert result.xp == 50.0
        assert result.xp_to_next_level == 100.0

    def test_add_xp_to_theme_exact_threshold(self, db_session, sample_user):
        """Should level up with exact threshold and reset XP to 0."""
        # Arrange
        theme = create_theme(
            db_session,
            ThemeCreate(name="Exact XP", user_id=sample_user.id),
        )

        # Act
        result = add_xp_to_theme(db_session, theme.id, 100.0)

        # Assert
        assert result is not None
        assert result.level == 1
        assert result.xp == pytest.approx(0.0)

    def test_add_xp_to_theme_fractional(self, db_session, sample_user):
        """Should handle fractional XP values correctly."""
        # Arrange
        theme = create_theme(
            db_session,
            ThemeCreate(name="Fractional XP", user_id=sample_user.id),
        )

        # Act
        result = add_xp_to_theme(db_session, theme.id, 12.5)

        # Assert
        assert result is not None
        assert result.xp == pytest.approx(12.5)

    def test_add_xp_to_theme_negative_raises_value_error(self, db_session, sample_user):
        """Should raise ValueError for negative XP."""
        # Arrange
        theme = create_theme(
            db_session,
            ThemeCreate(name="Negative XP", user_id=sample_user.id),
        )

        # Act & Assert
        with pytest.raises(ValueError):
            add_xp_to_theme(db_session, theme.id, -10.0)

    def test_add_xp_to_theme_nonexistent_returns_none(self, db_session):
        """Should return None when theme ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = add_xp_to_theme(db_session, non_existent_id, 100.0)

        # Assert
        assert result is None

    def test_add_xp_to_theme_zero_xp(self, db_session, sample_user):
        """Should handle zero XP addition without error."""
        # Arrange
        theme_data = ThemeCreate(name="Zero XP Theme", user_id=sample_user.id)
        theme = create_theme(db_session, theme_data)

        # Act
        result = add_xp_to_theme(db_session, theme.id, 0.0)

        # Assert
        assert result is not None
        assert result.level == 0
        assert result.xp == 0.0

    # =========================================================================
    # UPDATE TESTS
    # =========================================================================

    def test_update_theme_name(self, db_session, sample_user):
        """Should update theme name."""
        # Arrange
        theme_data = ThemeCreate(name="Original Name", user_id=sample_user.id)
        theme = create_theme(db_session, theme_data)

        # Act
        update = ThemeUpdate(name="Updated Name")
        result = update_theme(db_session, theme.id, update)

        # Assert
        assert result is not None
        assert result.name == "Updated Name"

    def test_update_theme_partial_fields(self, db_session, sample_user):
        """Should update only specified fields, leaving others unchanged."""
        # Arrange
        theme_data = ThemeCreate(
            name="Original",
            description="Original description",
            user_id=sample_user.id,
        )
        theme = create_theme(db_session, theme_data)

        # Act - Update only description
        update = ThemeUpdate(description="New description")
        result = update_theme(db_session, theme.id, update)

        # Assert
        assert result is not None
        assert result.name == "Original"  # Unchanged
        assert result.description == "New description"

    def test_update_theme_all_fields(self, db_session, sample_user):
        """Should update all fields at once."""
        # Arrange
        theme_data = ThemeCreate(
            name="Original",
            description="Original description",
            user_id=sample_user.id,
        )
        theme = create_theme(db_session, theme_data)

        # Act
        update = ThemeUpdate(name="New Name", description="New description")
        result = update_theme(db_session, theme.id, update)

        # Assert
        assert result is not None
        assert result.name == "New Name"
        assert result.description == "New description"

    def test_update_theme_empty_update(self, db_session, sample_user):
        """Should allow empty update with no changes."""
        # Arrange
        theme = create_theme(
            db_session,
            ThemeCreate(
                name="No Change",
                description="Keep me",
                user_id=sample_user.id,
            ),
        )

        # Act
        update = ThemeUpdate()
        result = update_theme(db_session, theme.id, update)

        # Assert
        assert result is not None
        assert result.name == "No Change"
        assert result.description == "Keep me"

    def test_update_theme_same_values(self, db_session, sample_user):
        """Should allow update with same values."""
        # Arrange
        theme = create_theme(
            db_session,
            ThemeCreate(
                name="Same Name",
                description="Same desc",
                user_id=sample_user.id,
            ),
        )

        # Act
        update = ThemeUpdate(name="Same Name", description="Same desc")
        result = update_theme(db_session, theme.id, update)

        # Assert
        assert result is not None
        assert result.name == "Same Name"
        assert result.description == "Same desc"

    def test_update_theme_not_found(self, db_session):
        """Should return None when updating non-existent theme."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        update = ThemeUpdate(name="New Name")
        result = update_theme(db_session, non_existent_id, update)

        # Assert
        assert result is None

    def test_update_theme_clear_description(self, db_session, sample_user):
        """Should allow setting description to None."""
        # Arrange
        theme_data = ThemeCreate(
            name="Theme",
            description="Has description",
            user_id=sample_user.id,
        )
        theme = create_theme(db_session, theme_data)

        # Act
        update = ThemeUpdate(description=None)
        result = update_theme(db_session, theme.id, update)

        # Assert
        assert result is not None
        assert result.description is None

    def test_update_theme_invalid_name_raises_validation_error(self):
        """Should raise ValidationError for invalid name."""
        # Act & Assert
        with pytest.raises(ValidationError):
            ThemeUpdate(name="")

    def test_update_theme_extra_field_raises_validation_error(self):
        """Should raise ValidationError for extra fields."""
        # Act & Assert
        with pytest.raises(ValidationError):
            ThemeUpdate.model_validate({"name": "Valid", "extra": "field"})

    def test_update_theme_description_too_long_raises_validation_error(self):
        """Should raise ValidationError when description exceeds max length."""
        # Act & Assert
        with pytest.raises(ValidationError):
            ThemeUpdate(description="d" * 501)

    # =========================================================================
    # DELETE TESTS
    # =========================================================================

    def test_delete_theme_success(self, db_session, sample_user):
        """Should delete theme and return True."""
        # Arrange
        theme_data = ThemeCreate(name="To Delete", user_id=sample_user.id)
        theme = create_theme(db_session, theme_data)
        theme_id = theme.id

        # Act
        result = delete_theme(db_session, theme_id)

        # Assert
        assert result is True
        assert get_theme(db_session, theme_id) is None

    @pytest.mark.xfail(
        reason="Theme model uses SET NULL, not CASCADE DELETE for sub-themes"
    )
    def test_delete_theme_cascades_to_subthemes(self, db_session, sample_user):
        """Should cascade delete to child themes when parent is deleted.

        EXPECTED BEHAVIOR: When a parent theme is deleted, all child themes
        should also be deleted automatically.

        CURRENT BEHAVIOR: The Theme model's parent_theme relationship uses
        SET NULL, so children become orphans instead of being deleted.

        TODO: Update Theme model to use cascade='all, delete-orphan' on the
        sub_themes backref if cascade delete behavior is desired.
        """
        # Arrange - Create parent with children
        parent_data = ThemeCreate(name="Parent", user_id=sample_user.id)
        parent = create_theme(db_session, parent_data)

        child1 = create_theme(
            db_session,
            ThemeCreate(name="Child 1", user_id=sample_user.id, parent_theme_id=parent.id),
        )
        child2 = create_theme(
            db_session,
            ThemeCreate(name="Child 2", user_id=sample_user.id, parent_theme_id=parent.id),
        )

        parent_id = parent.id
        child1_id = child1.id
        child2_id = child2.id

        # Verify children exist
        assert get_theme(db_session, child1_id) is not None
        assert get_theme(db_session, child2_id) is not None

        # Act - Delete parent
        result = delete_theme(db_session, parent_id)

        # Assert - Parent and children should all be deleted (CASCADE)
        assert result is True
        assert get_theme(db_session, parent_id) is None
        assert get_theme(db_session, child1_id) is None
        assert get_theme(db_session, child2_id) is None

    def test_delete_theme_orphans_subthemes(self, db_session, sample_user):
        """Verifies current SET NULL behavior for sub-themes on parent deletion.

        This test documents the actual behavior: when a parent theme is deleted,
        child themes are NOT deleted but instead have their parent_theme_id
        set to None (orphaned).
        """
        # Arrange - Create parent with children
        parent_data = ThemeCreate(name="Parent", user_id=sample_user.id)
        parent = create_theme(db_session, parent_data)

        child1 = create_theme(
            db_session,
            ThemeCreate(name="Child 1", user_id=sample_user.id, parent_theme_id=parent.id),
        )
        child2 = create_theme(
            db_session,
            ThemeCreate(name="Child 2", user_id=sample_user.id, parent_theme_id=parent.id),
        )

        parent_id = parent.id
        child1_id = child1.id
        child2_id = child2.id

        # Verify children exist
        assert get_theme(db_session, child1_id) is not None
        assert get_theme(db_session, child2_id) is not None

        # Act - Delete parent
        result = delete_theme(db_session, parent_id)

        # Assert - Parent deleted
        assert result is True
        assert get_theme(db_session, parent_id) is None

        # Children still exist but parent_theme_id is set to None
        # (SET NULL behavior from SQLAlchemy's backref)
        child1_after = get_theme(db_session, child1_id)
        child2_after = get_theme(db_session, child2_id)
        assert child1_after is not None
        assert child2_after is not None
        # Children's parent_theme_id is nullified when parent is deleted
        assert child1_after.parent_theme_id is None
        assert child2_after.parent_theme_id is None

    def test_delete_parent_with_grandchildren_orphans_children_only(self, db_session, sample_user):
        """Deleting parent should orphan children while preserving grandchild links."""
        # Arrange
        parent = create_theme(
            db_session,
            ThemeCreate(name="Parent", user_id=sample_user.id),
        )
        child = create_theme(
            db_session,
            ThemeCreate(
                name="Child",
                user_id=sample_user.id,
                parent_theme_id=parent.id,
            ),
        )
        grandchild = create_theme(
            db_session,
            ThemeCreate(
                name="Grandchild",
                user_id=sample_user.id,
                parent_theme_id=child.id,
            ),
        )

        # Act
        result = delete_theme(db_session, parent.id)

        # Assert
        assert result is True
        child_after = get_theme(db_session, child.id)
        grandchild_after = get_theme(db_session, grandchild.id)
        assert child_after is not None
        assert grandchild_after is not None
        assert child_after.parent_theme_id is None
        assert grandchild_after.parent_theme_id == child.id

    def test_delete_theme_nonexistent_returns_false(self, db_session):
        """Should return False when deleting non-existent theme."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = delete_theme(db_session, non_existent_id)

        # Assert
        assert result is False

    def test_delete_theme_already_deleted_returns_false(self, db_session, sample_user):
        """Should return False when deleting theme twice."""
        # Arrange
        theme_data = ThemeCreate(name="Delete Twice", user_id=sample_user.id)
        theme = create_theme(db_session, theme_data)

        # Act
        first_result = delete_theme(db_session, theme.id)
        second_result = delete_theme(db_session, theme.id)

        # Assert
        assert first_result is True
        assert second_result is False

    def test_delete_theme_cascades_to_skills(self, db_session, sample_user):
        """Deleting a theme should delete related skills."""
        # Arrange
        theme = create_theme(
            db_session,
            ThemeCreate(name="Theme With Skills", user_id=sample_user.id),
        )
        skill = Skill(
            user_id=sample_user.id,
            theme_id=theme.id,
            name="Skill 1",
            description="Skill desc",
        )
        db_session.add(skill)
        db_session.commit()
        skill_id = skill.id

        # Act
        result = delete_theme(db_session, theme.id)

        # Assert
        assert result is True
        assert db_session.query(Skill).filter(Skill.id == skill_id).first() is None

    def test_delete_child_theme_keeps_parent(self, db_session, sample_user):
        """Should only delete child theme, keeping parent intact."""
        # Arrange
        parent_data = ThemeCreate(name="Parent", user_id=sample_user.id)
        parent = create_theme(db_session, parent_data)

        child_data = ThemeCreate(
            name="Child",
            user_id=sample_user.id,
            parent_theme_id=parent.id,
        )
        child = create_theme(db_session, child_data)

        parent_id = parent.id
        child_id = child.id

        # Act
        result = delete_theme(db_session, child_id)

        # Assert
        assert result is True
        assert get_theme(db_session, child_id) is None
        assert get_theme(db_session, parent_id) is not None  # Parent still exists
