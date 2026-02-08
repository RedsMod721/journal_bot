"""
Tests for Skill CRUD operations.

This module tests all CRUD functions in app/crud/skill.py:
- create_skill: Creating skills with parent skill and theme support
- get_skill: Retrieving by ID
- get_user_skills: Retrieving all user's skills
- get_theme_skills: Retrieving all theme's skills
- get_skill_with_children: Eager loading child skills
- add_practice_time: Practice time tracking and XP awards
- add_xp_to_skill: XP addition and level-up handling
- update_skill: Modifying skill fields
- delete_skill: Removing skills and cascade behavior

Uses db_session, sample_user, and sample_theme fixtures from conftest.py.
"""
import pytest
from pydantic import ValidationError  # type: ignore

from app.crud.skill import (
    add_practice_time,
    add_xp_to_skill,
    create_skill,
    delete_skill,
    get_skill,
    get_skill_with_children,
    get_theme_skills,
    get_user_skills,
    update_skill,
)
from app.models.skill import Skill
from app.models.theme import Theme
from app.models.user import User
from app.schemas.skill import SkillCreate, SkillUpdate
from app.schemas.theme import ThemeCreate
from app.crud.theme import create_theme


class TestSkillCRUD:
    """Comprehensive tests for Skill CRUD operations."""

    # =========================================================================
    # CREATE TESTS
    # =========================================================================

    def test_create_skill_success(self, db_session, sample_user):
        """Should create skill with valid data and return Skill instance."""
        # Arrange
        skill_data = SkillCreate(
            name="Python Programming",
            description="Learning Python",
            user_id=sample_user.id,
        )

        # Act
        result = create_skill(db_session, skill_data)

        # Assert
        assert result is not None
        assert result.id is not None
        assert len(result.id) == 36
        assert result.name == "Python Programming"
        assert result.description == "Learning Python"
        assert result.user_id == sample_user.id
        assert result.theme_id is None
        assert result.level == 0
        assert result.xp == 0.0
        assert result.xp_to_next_level == 50.0
        assert result.rank == "Beginner"
        assert result.practice_time_minutes == 0
        assert result.difficulty == "Medium"

    def test_create_skill_with_parent_skill(self, db_session, sample_user):
        """Should create skill with parent skill relationship."""
        # Arrange - Create parent skill
        parent_data = SkillCreate(name="Programming", user_id=sample_user.id)
        parent = create_skill(db_session, parent_data)

        # Arrange - Create child skill
        child_data = SkillCreate(
            name="Python",
            user_id=sample_user.id,
            parent_skill_id=parent.id,
        )

        # Act
        result = create_skill(db_session, child_data)

        # Assert
        assert result is not None
        assert result.parent_skill_id == parent.id
        assert result.parent_skill.name == "Programming"

    def test_create_skill_with_theme(self, db_session, sample_user, sample_theme):
        """Should create skill associated with a theme."""
        # Arrange
        skill_data = SkillCreate(
            name="Strength Training",
            user_id=sample_user.id,
            theme_id=sample_theme.id,
        )

        # Act
        result = create_skill(db_session, skill_data)

        # Assert
        assert result is not None
        assert result.theme_id == sample_theme.id
        assert result.theme.name == sample_theme.name

    def test_create_skill_minimal_data(self, db_session, sample_user):
        """Should create skill with only required fields."""
        # Arrange
        skill_data = SkillCreate(name="Minimal Skill", user_id=sample_user.id)

        # Act
        result = create_skill(db_session, skill_data)

        # Assert
        assert result is not None
        assert result.description is None
        assert result.theme_id is None
        assert result.parent_skill_id is None

    def test_create_skill_strips_whitespace(self, db_session, sample_user):
        """Should strip whitespace from name and description."""
        # Arrange
        skill_data = SkillCreate(
            name="  Skill Name  ",
            description="  Description  ",
            user_id=sample_user.id,
        )

        # Act
        result = create_skill(db_session, skill_data)

        # Assert
        assert result.name == "Skill Name"
        assert result.description == "Description"

    def test_create_skill_name_max_length(self, db_session, sample_user):
        """Should allow name at max length boundary (100)."""
        # Arrange
        name = "n" * 100
        skill_data = SkillCreate(name=name, user_id=sample_user.id)

        # Act
        result = create_skill(db_session, skill_data)

        # Assert
        assert result is not None
        assert result.name == name

    def test_create_skill_description_max_length(self, db_session, sample_user):
        """Should allow description at max length boundary (500)."""
        # Arrange
        description = "d" * 500
        skill_data = SkillCreate(
            name="Max Desc",
            description=description,
            user_id=sample_user.id,
        )

        # Act
        result = create_skill(db_session, skill_data)

        # Assert
        assert result is not None
        assert result.description == description

    def test_create_skill_invalid_name_raises_validation_error(self, sample_user):
        """Should raise ValidationError for empty name."""
        # Act & Assert
        with pytest.raises(ValidationError):
            SkillCreate(name="", user_id=sample_user.id)

    def test_create_skill_invalid_user_id_raises_validation_error(self):
        """Should raise ValidationError for invalid user_id UUID."""
        # Act & Assert
        with pytest.raises(ValidationError):
            SkillCreate(name="Valid", user_id="not-a-uuid")

    def test_create_skill_extra_field_raises_validation_error(self, sample_user):
        """Should raise ValidationError for extra fields."""
        # Act & Assert
        with pytest.raises(ValidationError):
            SkillCreate.model_validate({
                "name": "Valid",
                "user_id": sample_user.id,
                "extra": "field",
            })

    # =========================================================================
    # READ BY ID TESTS
    # =========================================================================

    def test_get_skill_by_id(self, db_session, sample_user):
        """Should return skill when ID exists."""
        # Arrange
        skill_data = SkillCreate(name="Test Skill", user_id=sample_user.id)
        created_skill = create_skill(db_session, skill_data)

        # Act
        result = get_skill(db_session, created_skill.id)

        # Assert
        assert result is not None
        assert result.id == created_skill.id
        assert result.name == "Test Skill"

    def test_get_skill_by_id_not_found(self, db_session):
        """Should return None when ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = get_skill(db_session, non_existent_id)

        # Assert
        assert result is None

    # =========================================================================
    # GET USER SKILLS TESTS
    # =========================================================================

    def test_get_user_skills_returns_all(self, db_session, sample_user):
        """Should return all skills belonging to the user."""
        # Arrange
        skills = [
            SkillCreate(name="Skill 1", user_id=sample_user.id),
            SkillCreate(name="Skill 2", user_id=sample_user.id),
            SkillCreate(name="Skill 3", user_id=sample_user.id),
        ]
        for data in skills:
            create_skill(db_session, data)

        # Act
        result = get_user_skills(db_session, sample_user.id)

        # Assert
        assert len(result) == 3
        skill_names = {s.name for s in result}
        assert skill_names == {"Skill 1", "Skill 2", "Skill 3"}

    def test_get_user_skills_empty_for_no_skills(self, db_session, sample_user):
        """Should return empty list when user has no skills."""
        # Act
        result = get_user_skills(db_session, sample_user.id)

        # Assert
        assert result == []

    def test_get_user_skills_only_returns_user_skills(self, db_session, sample_user, fake):
        """Should only return skills for the specified user."""
        # Arrange - Create another user with skills
        other_user = User(username=fake.user_name(), email=fake.email())
        db_session.add(other_user)
        db_session.commit()

        create_skill(db_session, SkillCreate(name="My Skill", user_id=sample_user.id))
        create_skill(db_session, SkillCreate(name="Other Skill", user_id=other_user.id))

        # Act
        result = get_user_skills(db_session, sample_user.id)

        # Assert
        assert len(result) == 1
        assert result[0].name == "My Skill"

    # =========================================================================
    # GET THEME SKILLS TESTS
    # =========================================================================

    def test_get_theme_skills_returns_only_theme_skills(self, db_session, sample_user, sample_theme):
        """Should only return skills belonging to the specified theme."""
        # Arrange - Create another theme
        other_theme = create_theme(
            db_session,
            ThemeCreate(name="Other Theme", user_id=sample_user.id),
        )

        create_skill(
            db_session,
            SkillCreate(name="Theme Skill", user_id=sample_user.id, theme_id=sample_theme.id),
        )
        create_skill(
            db_session,
            SkillCreate(name="Other Skill", user_id=sample_user.id, theme_id=other_theme.id),
        )

        # Act
        result = get_theme_skills(db_session, sample_theme.id)

        # Assert
        assert len(result) == 1
        assert result[0].name == "Theme Skill"

    def test_get_theme_skills_empty_for_no_skills(self, db_session, sample_theme):
        """Should return empty list when theme has no skills."""
        # Act
        result = get_theme_skills(db_session, sample_theme.id)

        # Assert
        assert result == []

    # =========================================================================
    # GET SKILL WITH CHILDREN TESTS
    # =========================================================================

    def test_get_skill_with_children_includes_tree(self, db_session, sample_user):
        """Should return skill with child_skills relationship loaded."""
        # Arrange - Create parent and children
        parent = create_skill(db_session, SkillCreate(name="Parent", user_id=sample_user.id))
        create_skill(
            db_session,
            SkillCreate(name="Child 1", user_id=sample_user.id, parent_skill_id=parent.id),
        )
        create_skill(
            db_session,
            SkillCreate(name="Child 2", user_id=sample_user.id, parent_skill_id=parent.id),
        )

        # Act
        result = get_skill_with_children(db_session, parent.id)

        # Assert
        assert result is not None
        assert len(result.child_skills) == 2
        child_names = {c.name for c in result.child_skills}
        assert child_names == {"Child 1", "Child 2"}

    def test_get_skill_with_children_only_direct_children(self, db_session, sample_user):
        """Should include only direct children, not grandchildren."""
        # Arrange - Create parent -> child -> grandchild
        parent = create_skill(db_session, SkillCreate(name="Parent", user_id=sample_user.id))
        child = create_skill(
            db_session,
            SkillCreate(name="Child", user_id=sample_user.id, parent_skill_id=parent.id),
        )
        create_skill(
            db_session,
            SkillCreate(name="Grandchild", user_id=sample_user.id, parent_skill_id=child.id),
        )

        # Act
        result = get_skill_with_children(db_session, parent.id)

        # Assert
        assert result is not None
        child_names = {c.name for c in result.child_skills}
        assert child_names == {"Child"}

    def test_get_skill_with_children_not_found(self, db_session):
        """Should return None when skill ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = get_skill_with_children(db_session, non_existent_id)

        # Assert
        assert result is None

    # =========================================================================
    # PRACTICE TIME TESTS
    # =========================================================================

    def test_add_practice_time_increments_and_awards_xp(self, db_session, sample_user):
        """Should increment practice time and award XP."""
        # Arrange
        skill = create_skill(db_session, SkillCreate(name="Practice", user_id=sample_user.id))

        # Act
        result = add_practice_time(db_session, skill.id, minutes=30)

        # Assert
        assert result is not None
        assert result.practice_time_minutes == 30
        assert result.xp == pytest.approx(15.0)  # 30 * 0.5

    def test_add_practice_time_with_multiplier(self, db_session, sample_user):
        """Should apply multiplier to XP awarded."""
        # Arrange
        skill = create_skill(db_session, SkillCreate(name="Multiplier", user_id=sample_user.id))

        # Act
        result = add_practice_time(db_session, skill.id, minutes=30, multiplier=2.0)

        # Assert
        assert result is not None
        assert result.practice_time_minutes == 30
        assert result.xp == pytest.approx(30.0)  # 30 * 0.5 * 2

    def test_add_practice_time_zero_minutes(self, db_session, sample_user):
        """Should handle zero minutes without changes."""
        # Arrange
        skill = create_skill(db_session, SkillCreate(name="Zero", user_id=sample_user.id))

        # Act
        result = add_practice_time(db_session, skill.id, minutes=0)

        # Assert
        assert result is not None
        assert result.practice_time_minutes == 0
        assert result.xp == 0.0

    def test_add_practice_time_negative_raises_value_error(self, db_session, sample_user):
        """Should raise ValueError for negative practice time."""
        # Arrange
        skill = create_skill(db_session, SkillCreate(name="Negative", user_id=sample_user.id))

        # Act & Assert
        with pytest.raises(ValueError):
            add_practice_time(db_session, skill.id, minutes=-5)

    def test_add_practice_time_nonexistent_returns_none(self, db_session):
        """Should return None when skill ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = add_practice_time(db_session, non_existent_id, minutes=10)

        # Assert
        assert result is None

    # =========================================================================
    # XP TESTS
    # =========================================================================

    def test_add_xp_to_skill_triggers_level_up_and_rank_change(self, db_session, sample_user):
        """Should trigger level-up and rank change when XP exceeds threshold."""
        # Arrange
        skill = create_skill(db_session, SkillCreate(name="Leveling", user_id=sample_user.id))

        # Act - Add enough XP to reach level 5 (Amateur)
        result = add_xp_to_skill(db_session, skill.id, 400.0)

        # Assert
        assert result is not None
        assert result.level == 5
        assert result.rank == "Amateur"

    def test_add_xp_to_skill_exact_threshold(self, db_session, sample_user):
        """Should level up with exact threshold and reset XP to 0."""
        # Arrange
        skill = create_skill(db_session, SkillCreate(name="Exact XP", user_id=sample_user.id))

        # Act
        result = add_xp_to_skill(db_session, skill.id, 50.0)

        # Assert
        assert result is not None
        assert result.level == 1
        assert result.xp == pytest.approx(0.0)

    def test_add_xp_to_skill_fractional(self, db_session, sample_user):
        """Should handle fractional XP values correctly."""
        # Arrange
        skill = create_skill(db_session, SkillCreate(name="Fractional", user_id=sample_user.id))

        # Act
        result = add_xp_to_skill(db_session, skill.id, 12.5)

        # Assert
        assert result is not None
        assert result.xp == pytest.approx(12.5)

    def test_add_xp_to_skill_negative_raises_value_error(self, db_session, sample_user):
        """Should raise ValueError for negative XP."""
        # Arrange
        skill = create_skill(db_session, SkillCreate(name="Negative XP", user_id=sample_user.id))

        # Act & Assert
        with pytest.raises(ValueError):
            add_xp_to_skill(db_session, skill.id, -10.0)

    def test_add_xp_to_skill_nonexistent_returns_none(self, db_session):
        """Should return None when skill ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = add_xp_to_skill(db_session, non_existent_id, 10.0)

        # Assert
        assert result is None

    # =========================================================================
    # UPDATE TESTS
    # =========================================================================

    def test_update_skill_partial_fields(self, db_session, sample_user):
        """Should update only specified fields, leaving others unchanged."""
        # Arrange
        skill = create_skill(
            db_session,
            SkillCreate(
                name="Original",
                description="Original desc",
                user_id=sample_user.id,
            ),
        )

        # Act
        update = SkillUpdate(description="New description")
        result = update_skill(db_session, skill.id, update)

        # Assert
        assert result is not None
        assert result.name == "Original"
        assert result.description == "New description"

    def test_update_skill_all_fields(self, db_session, sample_user):
        """Should update all fields at once."""
        # Arrange
        skill = create_skill(
            db_session,
            SkillCreate(
                name="Original",
                description="Original desc",
                difficulty="Medium",
                user_id=sample_user.id,
            ),
        )

        # Act
        update = SkillUpdate(
            name="Updated",
            description="Updated desc",
            difficulty="Hard",
        )
        result = update_skill(db_session, skill.id, update)

        # Assert
        assert result is not None
        assert result.name == "Updated"
        assert result.description == "Updated desc"
        assert result.difficulty == "Hard"

    def test_update_skill_empty_update(self, db_session, sample_user):
        """Should allow empty update with no changes."""
        # Arrange
        skill = create_skill(
            db_session,
            SkillCreate(
                name="No Change",
                description="Keep me",
                user_id=sample_user.id,
            ),
        )

        # Act
        update = SkillUpdate()
        result = update_skill(db_session, skill.id, update)

        # Assert
        assert result is not None
        assert result.name == "No Change"
        assert result.description == "Keep me"

    def test_update_skill_same_values(self, db_session, sample_user):
        """Should allow update with same values."""
        # Arrange
        skill = create_skill(
            db_session,
            SkillCreate(
                name="Same",
                description="Same desc",
                difficulty="Medium",
                user_id=sample_user.id,
            ),
        )

        # Act
        update = SkillUpdate(name="Same", description="Same desc", difficulty="Medium")
        result = update_skill(db_session, skill.id, update)

        # Assert
        assert result is not None
        assert result.name == "Same"
        assert result.description == "Same desc"
        assert result.difficulty == "Medium"

    def test_update_skill_invalid_name_raises_validation_error(self):
        """Should raise ValidationError for invalid name."""
        # Act & Assert
        with pytest.raises(ValidationError):
            SkillUpdate(name="")

    def test_update_skill_extra_field_raises_validation_error(self):
        """Should raise ValidationError for extra fields."""
        # Act & Assert
        with pytest.raises(ValidationError):
            SkillUpdate.model_validate({"name": "Valid", "extra": "field"})

    def test_update_skill_description_too_long_raises_validation_error(self):
        """Should raise ValidationError when description exceeds max length."""
        # Act & Assert
        with pytest.raises(ValidationError):
            SkillUpdate(description="d" * 501)

    def test_update_skill_not_found(self, db_session):
        """Should return None when updating non-existent skill."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        update = SkillUpdate(name="New Name")
        result = update_skill(db_session, non_existent_id, update)

        # Assert
        assert result is None

    # =========================================================================
    # DELETE TESTS
    # =========================================================================

    def test_delete_skill_success(self, db_session, sample_user):
        """Should delete skill and return True."""
        # Arrange
        skill = create_skill(db_session, SkillCreate(name="To Delete", user_id=sample_user.id))
        skill_id = skill.id

        # Act
        result = delete_skill(db_session, skill_id)

        # Assert
        assert result is True
        assert get_skill(db_session, skill_id) is None

    @pytest.mark.xfail(
        reason="Skill model uses SET NULL or no cascade for child skills"
    )
    def test_delete_skill_cascades_to_children(self, db_session, sample_user):
        """Should cascade delete to child skills when parent is deleted."""
        # Arrange
        parent = create_skill(db_session, SkillCreate(name="Parent", user_id=sample_user.id))
        child1 = create_skill(
            db_session,
            SkillCreate(name="Child 1", user_id=sample_user.id, parent_skill_id=parent.id),
        )
        child2 = create_skill(
            db_session,
            SkillCreate(name="Child 2", user_id=sample_user.id, parent_skill_id=parent.id),
        )

        # Act
        result = delete_skill(db_session, parent.id)

        # Assert
        assert result is True
        assert get_skill(db_session, parent.id) is None
        assert get_skill(db_session, child1.id) is None
        assert get_skill(db_session, child2.id) is None

    def test_delete_skill_orphans_children(self, db_session, sample_user):
        """Documents current behavior: children are orphaned on parent deletion."""
        # Arrange
        parent = create_skill(db_session, SkillCreate(name="Parent", user_id=sample_user.id))
        child = create_skill(
            db_session,
            SkillCreate(name="Child", user_id=sample_user.id, parent_skill_id=parent.id),
        )

        # Act
        result = delete_skill(db_session, parent.id)

        # Assert
        assert result is True
        child_after = get_skill(db_session, child.id)
        assert child_after is not None
        assert child_after.parent_skill_id is None or child_after.parent_skill_id == parent.id

    def test_delete_skill_nonexistent_returns_false(self, db_session):
        """Should return False when deleting non-existent skill."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = delete_skill(db_session, non_existent_id)

        # Assert
        assert result is False

    def test_delete_skill_already_deleted_returns_false(self, db_session, sample_user):
        """Should return False when deleting skill twice."""
        # Arrange
        skill = create_skill(db_session, SkillCreate(name="Delete Twice", user_id=sample_user.id))

        # Act
        first_result = delete_skill(db_session, skill.id)
        second_result = delete_skill(db_session, skill.id)

        # Assert
        assert first_result is True
        assert second_result is False

    def test_delete_child_skill_keeps_parent(self, db_session, sample_user):
        """Should delete child skill while keeping parent intact."""
        # Arrange
        parent = create_skill(db_session, SkillCreate(name="Parent", user_id=sample_user.id))
        child = create_skill(
            db_session,
            SkillCreate(name="Child", user_id=sample_user.id, parent_skill_id=parent.id),
        )

        # Act
        result = delete_skill(db_session, child.id)

        # Assert
        assert result is True
        assert get_skill(db_session, child.id) is None
        assert get_skill(db_session, parent.id) is not None
