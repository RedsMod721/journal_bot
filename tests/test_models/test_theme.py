"""
Comprehensive tests for Theme model.

Tests cover:
- XP and leveling system (add_xp, level_up, exponential scaling)
- Self-referential hierarchy (parent/child themes)
- Default values and corrosion system
- Edge cases

Following AAA pattern (Arrange, Act, Assert) as per TESTING_GUIDE.md
"""
import pytest  # type: ignore

from app.models.theme import Theme


class TestThemeModel:
    """Comprehensive tests for Theme model"""

    # =========================================================================
    # XP & LEVELING TESTS
    # =========================================================================

    def test_theme_add_xp_below_threshold_no_level_up(self, db_session, sample_user):
        """Adding XP below threshold should not trigger level-up"""
        # Arrange
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme",
            xp=0,
            level=0,
            xp_to_next_level=100
        )
        db_session.add(theme)
        db_session.commit()

        # Act
        theme.add_xp(50)
        db_session.commit()

        # Assert
        assert theme.xp == 50
        assert theme.level == 0
        assert theme.xp_to_next_level == 100

    def test_theme_add_xp_at_threshold_triggers_level_up(self, db_session, sample_user):
        """Adding XP to reach threshold should trigger level-up"""
        # Arrange
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme",
            xp=0,
            level=0,
            xp_to_next_level=100
        )
        db_session.add(theme)
        db_session.commit()

        # Act
        theme.add_xp(100)
        db_session.commit()

        # Assert
        assert theme.level == 1
        assert theme.xp == 0  # XP resets after exact threshold
        assert theme.xp_to_next_level > 100  # Next level requires more XP

    def test_theme_add_xp_above_threshold_carries_overflow(self, db_session, sample_user):
        """Adding XP above threshold should carry overflow to next level"""
        # Arrange
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme",
            xp=0,
            level=0,
            xp_to_next_level=100
        )
        db_session.add(theme)
        db_session.commit()

        # Act
        theme.add_xp(150)
        db_session.commit()

        # Assert
        assert theme.level == 1
        assert theme.xp == 50  # 150 - 100 = 50 overflow

    def test_theme_add_xp_multiple_level_ups(self, db_session, sample_user):
        """Adding large XP should trigger multiple level-ups"""
        # Arrange
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme",
            xp=0,
            level=0,
            xp_to_next_level=100
        )
        db_session.add(theme)
        db_session.commit()

        # Act - Add enough XP for multiple levels
        # Level 0->1: 100 XP, Level 1->2: 115 XP, total = 215 for 2 levels
        theme.add_xp(500)
        db_session.commit()

        # Assert
        assert theme.level >= 3  # Should be at least level 3 with 500 XP

    def test_theme_xp_calculation_exponential_scaling(self, db_session, sample_user):
        """XP requirements should scale exponentially with level"""
        # Arrange
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme",
            level=0
        )
        db_session.add(theme)
        db_session.commit()

        # Act
        xp_level_0 = theme.calculate_next_level_xp()
        theme.level = 5
        xp_level_5 = theme.calculate_next_level_xp()
        theme.level = 10
        xp_level_10 = theme.calculate_next_level_xp()

        # Assert
        assert xp_level_0 == 100.0  # Base XP at level 0
        assert xp_level_5 > xp_level_0  # Higher level = more XP needed
        assert xp_level_10 > xp_level_5  # Even higher level = even more XP
        # Verify exponential formula: 100 * 1.15^level
        assert abs(xp_level_5 - 100 * (1.15 ** 5)) < 0.01
        assert abs(xp_level_10 - 100 * (1.15 ** 10)) < 0.01

    # =========================================================================
    # HIERARCHY TESTS (Self-Referential)
    # =========================================================================

    def test_theme_parent_child_relationship(self, db_session, sample_user):
        """Should support parent-child theme hierarchy"""
        # Arrange
        parent_theme = Theme(
            user_id=sample_user.id,
            name="Education"
        )
        db_session.add(parent_theme)
        db_session.commit()

        # Act
        child_theme = Theme(
            user_id=sample_user.id,
            name="Programming",
            parent_theme_id=parent_theme.id
        )
        db_session.add(child_theme)
        db_session.commit()
        db_session.refresh(parent_theme)

        # Assert
        assert child_theme.parent_theme is not None
        assert child_theme.parent_theme.name == "Education"
        assert len(parent_theme.sub_themes) == 1
        assert parent_theme.sub_themes[0].name == "Programming"

    def test_theme_multi_level_hierarchy(self, db_session, sample_user):
        """Should support multi-level theme hierarchy (grandparent-parent-child)"""
        # Arrange
        level1 = Theme(user_id=sample_user.id, name="Education")
        db_session.add(level1)
        db_session.commit()

        level2 = Theme(
            user_id=sample_user.id,
            name="Programming",
            parent_theme_id=level1.id
        )
        db_session.add(level2)
        db_session.commit()

        # Act
        level3 = Theme(
            user_id=sample_user.id,
            name="Python",
            parent_theme_id=level2.id
        )
        db_session.add(level3)
        db_session.commit()

        # Assert
        assert level3.parent_theme.name == "Programming"
        assert level3.parent_theme.parent_theme.name == "Education"

    def test_theme_multiple_sub_themes(self, db_session, sample_user):
        """Should support multiple sub-themes under one parent"""
        # Arrange
        parent = Theme(user_id=sample_user.id, name="Education")
        db_session.add(parent)
        db_session.commit()

        # Act
        child1 = Theme(
            user_id=sample_user.id,
            name="Programming",
            parent_theme_id=parent.id
        )
        child2 = Theme(
            user_id=sample_user.id,
            name="Languages",
            parent_theme_id=parent.id
        )
        db_session.add_all([child1, child2])
        db_session.commit()
        db_session.refresh(parent)

        # Assert
        assert len(parent.sub_themes) == 2
        sub_theme_names = [t.name for t in parent.sub_themes]
        assert "Programming" in sub_theme_names
        assert "Languages" in sub_theme_names

    # =========================================================================
    # CORROSION & DEFAULT VALUES TESTS
    # =========================================================================

    def test_theme_default_corrosion_level_is_fresh(self, db_session, sample_user):
        """New themes should have 'Fresh' corrosion level by default"""
        # Arrange & Act
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme"
        )
        db_session.add(theme)
        db_session.commit()

        # Assert
        assert theme.corrosion_level == "Fresh"

    def test_theme_default_values(self, db_session, sample_user):
        """Theme should have correct default values"""
        # Arrange & Act
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme"
        )
        db_session.add(theme)
        db_session.commit()

        # Assert
        assert theme.level == 0
        assert theme.xp == 0.0
        assert theme.xp_to_next_level == 100.0
        assert theme.corrosion_level == "Fresh"
        assert theme.description is None
        assert theme.parent_theme_id is None
        assert theme.theme_metadata == {}

    # =========================================================================
    # EDGE CASES
    # =========================================================================

    def test_theme_add_xp_negative_raises_value_error(self, db_session, sample_user):
        """Adding negative XP should raise ValueError"""
        # Arrange
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme",
            xp=50
        )
        db_session.add(theme)
        db_session.commit()

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            theme.add_xp(-100)
        assert "negative" in str(exc_info.value).lower()

    def test_theme_add_xp_zero_no_change(self, db_session, sample_user):
        """Adding zero XP should not change anything"""
        # Arrange
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme",
            xp=25,
            level=0
        )
        db_session.add(theme)
        db_session.commit()

        # Act
        theme.add_xp(0)
        db_session.commit()

        # Assert
        assert theme.xp == 25
        assert theme.level == 0

    def test_theme_add_xp_fractional(self, db_session, sample_user):
        """Should handle fractional XP values correctly"""
        # Arrange
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme",
            xp=0,
            level=0
        )
        db_session.add(theme)
        db_session.commit()

        # Act
        theme.add_xp(10.5)
        theme.add_xp(20.3)
        db_session.commit()

        # Assert
        assert abs(theme.xp - 30.8) < 0.001

    def test_theme_level_up_manual_overflow(self, db_session, sample_user):
        """Manual level_up should keep XP overflow."""
        # Arrange
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme",
            xp=120,
            level=0,
            xp_to_next_level=100,
        )
        db_session.add(theme)
        db_session.commit()

        # Act
        theme.level_up()
        db_session.commit()

        # Assert
        assert theme.level == 1
        assert theme.xp == 20
        assert theme.xp_to_next_level > 100

    def test_theme_calculate_next_level_xp_specific_level(self, db_session, sample_user):
        """calculate_next_level_xp should follow expected formula."""
        # Arrange
        theme = Theme(user_id=sample_user.id, name="Test Theme", level=5)
        db_session.add(theme)
        db_session.commit()

        # Act
        xp_required = theme.calculate_next_level_xp()

        # Assert
        assert abs(xp_required - 100 * (1.15 ** 5)) < 0.01

    def test_theme_corrosion_level_allows_custom_value(self, db_session, sample_user):
        """corrosion_level should accept custom values (no validation enforced)."""
        # Arrange & Act
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme",
            corrosion_level="Experimental",
        )
        db_session.add(theme)
        db_session.commit()
        db_session.refresh(theme)

        # Assert
        assert theme.corrosion_level == "Experimental"

    def test_theme_metadata_persists(self, db_session, sample_user):
        """theme_metadata should store JSON values correctly."""
        # Arrange
        metadata = {"tags": ["focus", "health"], "priority": 2}

        # Act
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme",
            theme_metadata=metadata,
        )
        db_session.add(theme)
        db_session.commit()
        db_session.refresh(theme)

        # Assert
        assert theme.theme_metadata == metadata

    def test_theme_uuid_generation(self, db_session, sample_user):
        """Theme should auto-generate UUID for primary key"""
        # Arrange & Act
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme"
        )
        db_session.add(theme)
        db_session.commit()

        # Assert
        assert theme.id is not None
        assert len(theme.id) == 36  # UUID format
        assert theme.id.count('-') == 4

    def test_theme_repr(self, db_session, sample_user):
        """Theme __repr__ should show name and level"""
        # Arrange
        theme = Theme(
            user_id=sample_user.id,
            name="Physical Health",
            level=5
        )
        db_session.add(theme)
        db_session.commit()

        # Act
        repr_str = repr(theme)

        # Assert
        assert "Physical Health" in repr_str
        assert "5" in repr_str

    # =========================================================================
    # USER RELATIONSHIP TESTS
    # =========================================================================

    def test_theme_user_relationship_bidirectional(self, db_session, sample_user):
        """Theme should have bidirectional relationship with user"""
        # Arrange & Act
        theme = Theme(
            user_id=sample_user.id,
            name="Test Theme"
        )
        db_session.add(theme)
        db_session.commit()
        db_session.refresh(sample_user)

        # Assert
        assert theme.user is not None
        assert theme.user.id == sample_user.id
        assert theme in sample_user.themes

    def test_user_deletion_cascades_to_themes(self, db_session, sample_user):
        """Deleting user should cascade delete all themes"""
        # Arrange
        theme1 = Theme(user_id=sample_user.id, name="Theme 1")
        theme2 = Theme(user_id=sample_user.id, name="Theme 2")
        db_session.add_all([theme1, theme2])
        db_session.commit()
        user_id = sample_user.id

        # Act
        db_session.delete(sample_user)
        db_session.commit()

        # Assert
        remaining_themes = db_session.query(Theme).filter(
            Theme.user_id == user_id
        ).all()
        assert len(remaining_themes) == 0
