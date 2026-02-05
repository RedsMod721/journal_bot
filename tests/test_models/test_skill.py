"""
Comprehensive tests for the Skill model.

Tests cover:
- Rank progression (Beginner -> Amateur -> Intermediate -> Advanced -> Expert -> Master)
- Practice time tracking and XP awards
- XP multipliers
- Skill tree hierarchy (parent-child relationships)
- Level-up mechanics

Follows the AAA pattern: Arrange, Act, Assert
"""
import pytest  # type: ignore

from app.models.skill import Skill


class TestSkillModel:
    """Test suite for Skill model."""

    # =========================================================================
    # RANK PROGRESSION TESTS
    # =========================================================================

    def test_skill_rank_progression_beginner_to_amateur(self, db_session, sample_user):
        """Should progress from Beginner to Amateur at level 5."""
        # Arrange
        skill = Skill(
            user_id=sample_user.id,
            name="Test Skill",
            level=0,
            rank="Beginner"
        )
        db_session.add(skill)
        db_session.commit()

        # Act
        skill.level = 5
        skill.update_rank()

        # Assert
        assert skill.rank == "Amateur"

    def test_skill_rank_all_transitions(self, db_session, sample_user):
        """Should correctly transition through all 6 ranks at correct thresholds."""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill")
        db_session.add(skill)
        db_session.commit()

        # Test Beginner (0-4)
        skill.level = 0
        skill.update_rank()
        assert skill.rank == "Beginner"

        skill.level = 4
        skill.update_rank()
        assert skill.rank == "Beginner"

        # Test Amateur (5-14)
        skill.level = 5
        skill.update_rank()
        assert skill.rank == "Amateur"

        skill.level = 14
        skill.update_rank()
        assert skill.rank == "Amateur"

        # Test Intermediate (15-29)
        skill.level = 15
        skill.update_rank()
        assert skill.rank == "Intermediate"

        skill.level = 29
        skill.update_rank()
        assert skill.rank == "Intermediate"

        # Test Advanced (30-49)
        skill.level = 30
        skill.update_rank()
        assert skill.rank == "Advanced"

        skill.level = 49
        skill.update_rank()
        assert skill.rank == "Advanced"

        # Test Expert (50-79)
        skill.level = 50
        skill.update_rank()
        assert skill.rank == "Expert"

        skill.level = 79
        skill.update_rank()
        assert skill.rank == "Expert"

        # Test Master (80+)
        skill.level = 80
        skill.update_rank()
        assert skill.rank == "Master"

        skill.level = 100
        skill.update_rank()
        assert skill.rank == "Master"

    # =========================================================================
    # PRACTICE TIME TESTS
    # =========================================================================

    def test_skill_add_practice_time_increments_total(self, db_session, sample_user):
        """Adding practice time should increment total practice_time_minutes."""
        # Arrange
        skill = Skill(
            user_id=sample_user.id,
            name="Test Skill",
            practice_time_minutes=0
        )
        db_session.add(skill)
        db_session.commit()

        # Act
        skill.add_practice_time(30)
        db_session.commit()

        # Assert
        assert skill.practice_time_minutes == 30

    def test_skill_add_practice_time_awards_xp(self, db_session, sample_user):
        """Adding practice time should award XP (0.5 XP per minute)."""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill", xp=0)
        db_session.add(skill)
        db_session.commit()

        # Act - 30 minutes * 0.5 XP/min = 15 XP
        skill.add_practice_time(30, xp_multiplier=1.0)
        db_session.commit()

        # Assert
        assert skill.xp == 15.0

    def test_skill_add_practice_time_with_multiplier(self, db_session, sample_user):
        """XP multiplier should affect XP gained from practice."""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill", xp=0)
        db_session.add(skill)
        db_session.commit()

        # Act - 30 minutes * 0.5 XP/min * 2.0 multiplier = 30 XP
        skill.add_practice_time(30, xp_multiplier=2.0)
        db_session.commit()

        # Assert
        assert skill.xp == 30.0

    # =========================================================================
    # SKILL TREE TESTS
    # =========================================================================

    def test_skill_tree_parent_child_relationship(self, db_session, sample_user):
        """Should support parent-child skill tree relationships."""
        # Arrange
        parent_skill = Skill(user_id=sample_user.id, name="Programming")
        db_session.add(parent_skill)
        db_session.commit()

        # Act
        child_skill = Skill(
            user_id=sample_user.id,
            name="Python",
            parent_skill_id=parent_skill.id
        )
        db_session.add(child_skill)
        db_session.commit()
        db_session.refresh(parent_skill)

        # Assert
        assert child_skill.parent_skill.name == "Programming"
        assert len(parent_skill.child_skills) == 1
        assert parent_skill.child_skills[0].name == "Python"

    def test_skill_tree_multiple_children(self, db_session, sample_user):
        """Should support multiple child skills (parallel branches)."""
        # Arrange
        parent = Skill(user_id=sample_user.id, name="Programming")
        db_session.add(parent)
        db_session.commit()

        # Act
        child1 = Skill(
            user_id=sample_user.id,
            name="Python",
            parent_skill_id=parent.id
        )
        child2 = Skill(
            user_id=sample_user.id,
            name="JavaScript",
            parent_skill_id=parent.id
        )
        db_session.add_all([child1, child2])
        db_session.commit()
        db_session.refresh(parent)

        # Assert
        assert len(parent.child_skills) == 2
        child_names = {s.name for s in parent.child_skills}
        assert "Python" in child_names
        assert "JavaScript" in child_names

    # =========================================================================
    # CREATION TESTS
    # =========================================================================

    def test_skill_creation_with_valid_data(self, db_session, sample_user, sample_theme):
        """Should create skill with all required fields populated correctly."""
        # Arrange
        name = "Python Programming"
        description = "Learn Python programming"

        # Act
        skill = Skill(
            user_id=sample_user.id,
            theme_id=sample_theme.id,
            name=name,
            description=description
        )
        db_session.add(skill)
        db_session.commit()
        db_session.refresh(skill)

        # Assert
        assert skill.id is not None
        assert skill.user_id == sample_user.id
        assert skill.theme_id == sample_theme.id
        assert skill.name == name
        assert skill.description == description

    def test_skill_creation_generates_uuid(self, db_session, sample_user):
        """Should auto-generate a valid UUID string for primary key."""
        # Arrange & Act
        skill = Skill(user_id=sample_user.id, name="Test Skill")
        db_session.add(skill)
        db_session.commit()

        # Assert - UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert skill.id is not None
        assert len(skill.id) == 36
        assert skill.id.count("-") == 4

    # =========================================================================
    # DEFAULT VALUE TESTS
    # =========================================================================

    def test_skill_default_values(self, db_session, sample_user):
        """Should have correct default values for all fields."""
        # Arrange & Act
        skill = Skill(user_id=sample_user.id, name="Test Skill")
        db_session.add(skill)
        db_session.commit()
        db_session.refresh(skill)

        # Assert
        assert skill.level == 0
        assert skill.xp == 0.0
        assert skill.xp_to_next_level == 50.0
        assert skill.rank == "Beginner"
        assert skill.practice_time_minutes == 0
        assert skill.difficulty == "Medium"
        assert skill.skill_metadata == {}

    # =========================================================================
    # XP AND LEVELING TESTS
    # =========================================================================

    def test_skill_add_xp_below_threshold_no_level_up(self, db_session, sample_user):
        """Adding XP below threshold should not trigger level-up."""
        # Arrange
        skill = Skill(
            user_id=sample_user.id,
            name="Test Skill",
            xp=0,
            level=0,
            xp_to_next_level=50
        )
        db_session.add(skill)
        db_session.commit()

        # Act
        skill.add_xp(25)
        db_session.commit()

        # Assert
        assert skill.xp == 25
        assert skill.level == 0

    def test_skill_add_xp_at_threshold_triggers_level_up(self, db_session, sample_user):
        """Adding XP to reach threshold should trigger level-up."""
        # Arrange
        skill = Skill(
            user_id=sample_user.id,
            name="Test Skill",
            xp=0,
            level=0,
            xp_to_next_level=50
        )
        db_session.add(skill)
        db_session.commit()

        # Act
        skill.add_xp(50)
        db_session.commit()

        # Assert
        assert skill.level == 1
        assert skill.xp == 0  # Overflow should reset
        assert skill.xp_to_next_level > 50  # Next level requires more XP

    def test_skill_add_xp_carries_overflow(self, db_session, sample_user):
        """Adding XP above threshold should carry overflow to next level."""
        # Arrange
        skill = Skill(
            user_id=sample_user.id,
            name="Test Skill",
            xp=0,
            level=0,
            xp_to_next_level=50
        )
        db_session.add(skill)
        db_session.commit()

        # Act
        skill.add_xp(75)  # 50 to level up, 25 overflow
        db_session.commit()

        # Assert
        assert skill.level == 1
        assert skill.xp == 25  # 75 - 50 = 25 overflow

    def test_skill_xp_calculation_exponential_scaling(self, db_session, sample_user):
        """XP requirements should scale exponentially (50 * 1.2^level)."""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill", level=0)
        db_session.add(skill)
        db_session.commit()

        # Act
        xp_level_0 = skill.calculate_next_level_xp()
        skill.level = 5
        xp_level_5 = skill.calculate_next_level_xp()
        skill.level = 10
        xp_level_10 = skill.calculate_next_level_xp()

        # Assert
        assert xp_level_0 == 50.0  # 50 * 1.2^0 = 50
        assert abs(xp_level_5 - 50 * (1.2 ** 5)) < 0.01  # ~124.4
        assert abs(xp_level_10 - 50 * (1.2 ** 10)) < 0.01  # ~309.6
        assert xp_level_10 > xp_level_5 > xp_level_0

    # =========================================================================
    # LEVEL UP UPDATES RANK TEST
    # =========================================================================

    def test_skill_level_up_updates_rank(self, db_session, sample_user):
        """Level-up should automatically update rank when threshold is crossed."""
        # Arrange
        skill = Skill(
            user_id=sample_user.id,
            name="Test Skill",
            level=4,
            xp=0,
            xp_to_next_level=50,
            rank="Beginner"
        )
        db_session.add(skill)
        db_session.commit()

        # Act - add enough XP to trigger level up to level 5
        skill.add_xp(50)
        db_session.commit()

        # Assert
        assert skill.level == 5
        assert skill.rank == "Amateur"

    # =========================================================================
    # RELATIONSHIP TESTS
    # =========================================================================

    def test_skill_user_relationship(self, db_session, sample_user):
        """Skill should have bidirectional relationship with user."""
        # Arrange & Act
        skill = Skill(user_id=sample_user.id, name="Test Skill")
        db_session.add(skill)
        db_session.commit()
        db_session.refresh(sample_user)

        # Assert
        assert skill.user.id == sample_user.id
        assert len(sample_user.skills) == 1
        assert sample_user.skills[0].name == "Test Skill"

    def test_skill_theme_relationship(self, db_session, sample_user, sample_theme):
        """Skill should have bidirectional relationship with theme."""
        # Arrange & Act
        skill = Skill(
            user_id=sample_user.id,
            theme_id=sample_theme.id,
            name="Test Skill"
        )
        db_session.add(skill)
        db_session.commit()
        db_session.refresh(sample_theme)

        # Assert
        assert skill.theme.id == sample_theme.id
        assert len(sample_theme.skills) == 1
        assert sample_theme.skills[0].name == "Test Skill"

    def test_skill_without_theme(self, db_session, sample_user):
        """Skill should work without theme (theme_id is nullable)."""
        # Arrange & Act
        skill = Skill(user_id=sample_user.id, name="Standalone Skill")
        db_session.add(skill)
        db_session.commit()
        db_session.refresh(skill)

        # Assert
        assert skill.theme_id is None
        assert skill.theme is None

    # =========================================================================
    # EDGE CASES
    # =========================================================================

    def test_skill_add_xp_negative_raises_error(self, db_session, sample_user):
        """Adding negative XP should raise ValueError."""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill", xp=50)
        db_session.add(skill)
        db_session.commit()

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            skill.add_xp(-100)

        assert "cannot be negative" in str(exc_info.value)

    def test_skill_add_practice_time_negative_raises_error(self, db_session, sample_user):
        """Adding negative practice time should raise ValueError."""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill")
        db_session.add(skill)
        db_session.commit()

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            skill.add_practice_time(-30)

        assert "cannot be negative" in str(exc_info.value)

    def test_skill_accumulative_practice_time(self, db_session, sample_user):
        """Multiple practice sessions should accumulate time and XP."""
        # Arrange
        skill = Skill(
            user_id=sample_user.id,
            name="Test Skill",
            practice_time_minutes=0,
            xp=0
        )
        db_session.add(skill)
        db_session.commit()

        # Act
        skill.add_practice_time(30)  # 30 min, 15 XP
        skill.add_practice_time(20)  # 20 min, 10 XP
        skill.add_practice_time(10)  # 10 min, 5 XP
        db_session.commit()

        # Assert
        assert skill.practice_time_minutes == 60  # Total 60 minutes
        assert skill.xp == 30.0  # Total 30 XP

    def test_skill_add_practice_time_with_zero_multiplier(self, db_session, sample_user):
        """Zero multiplier should add time but not XP."""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill", xp=10)
        db_session.add(skill)
        db_session.commit()

        # Act
        skill.add_practice_time(20, xp_multiplier=0.0)
        db_session.commit()

        # Assert
        assert skill.practice_time_minutes == 20
        assert skill.xp == 10

    def test_skill_add_practice_time_negative_multiplier(self, db_session, sample_user):
        """Negative multiplier should raise ValueError via add_xp validation."""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill", xp=10)
        db_session.add(skill)
        db_session.commit()

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            skill.add_practice_time(10, xp_multiplier=-1.0)

        assert "cannot be negative" in str(exc_info.value)

    def test_skill_add_xp_fractional_amount(self, db_session, sample_user):
        """Fractional XP should be supported."""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill", xp=0)
        db_session.add(skill)
        db_session.commit()

        # Act
        skill.add_xp(12.75)
        db_session.commit()

        # Assert
        assert skill.xp == 12.75

    def test_skill_level_up_manual_overflow(self, db_session, sample_user):
        """Manual level_up should keep XP overflow."""
        # Arrange
        skill = Skill(
            user_id=sample_user.id,
            name="Test Skill",
            xp=60,
            level=0,
            xp_to_next_level=50,
        )
        db_session.add(skill)
        db_session.commit()

        # Act
        skill.level_up()
        db_session.commit()

        # Assert
        assert skill.level == 1
        assert skill.xp == 10
        assert skill.xp_to_next_level > 50

    def test_skill_calculate_next_level_xp_negative_level(self, db_session, sample_user):
        """Negative level should still calculate XP (no validation enforced)."""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill", level=-1)
        db_session.add(skill)
        db_session.commit()

        # Act
        xp_required = skill.calculate_next_level_xp()

        # Assert
        assert xp_required == 50.0 * (1.2 ** -1)

    def test_skill_update_rank_with_manual_level(self, db_session, sample_user):
        """update_rank should map ranks correctly for manual level changes."""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill", level=30)
        db_session.add(skill)
        db_session.commit()

        # Act
        skill.update_rank()

        # Assert
        assert skill.rank == "Advanced"

    # =========================================================================
    # REPR TEST
    # =========================================================================

    def test_skill_repr(self, db_session, sample_user):
        """Should return readable string representation."""
        # Arrange
        skill = Skill(
            user_id=sample_user.id,
            name="Python",
            level=5,
            rank="Amateur"
        )

        # Act
        repr_string = repr(skill)

        # Assert
        assert repr_string == "<Skill Python (Lv 5, Amateur)>"

    # =========================================================================
    # MULTI-LEVEL SKILL TREE TEST
    # =========================================================================

    def test_skill_tree_multi_level_hierarchy(self, db_session, sample_user):
        """Should support multi-level skill tree hierarchy."""
        # Arrange
        level1 = Skill(user_id=sample_user.id, name="Programming")
        db_session.add(level1)
        db_session.commit()

        level2 = Skill(
            user_id=sample_user.id,
            name="Python",
            parent_skill_id=level1.id
        )
        db_session.add(level2)
        db_session.commit()

        # Act
        level3 = Skill(
            user_id=sample_user.id,
            name="Data Analysis",
            parent_skill_id=level2.id
        )
        db_session.add(level3)
        db_session.commit()

        # Assert
        assert level3.parent_skill.name == "Python"
        assert level3.parent_skill.parent_skill.name == "Programming"
