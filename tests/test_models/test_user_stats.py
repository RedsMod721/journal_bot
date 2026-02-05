"""
Tests for UserStats model.

Tests cover:
- UserStats creation
- Default values for status bars
- One-to-one relationship with User

Following AAA pattern (Arrange, Act, Assert) as per TESTING_GUIDE.md
"""
import pytest  # type: ignore

from app.models.user_stats import UserStats


class TestUserStatsModel:
    """Tests for UserStats model"""

    def test_user_stats_creation(self, db_session, sample_user):
        """UserStats should be created with required fields"""
        # Arrange & Act
        stats = UserStats(
            user_id=sample_user.id,
            hp=80,
            mp=90,
            mental_health=65,
            physical_health=75,
            relationship_quality=60,
            socialization_level=55,
        )
        db_session.add(stats)
        db_session.commit()

        # Assert
        assert stats.id is not None
        assert len(stats.id) == 36  # UUID format
        assert stats.user_id == sample_user.id
        assert stats.hp == 80
        assert stats.mp == 90
        assert stats.mental_health == 65
        assert stats.physical_health == 75
        assert stats.relationship_quality == 60
        assert stats.socialization_level == 55
        assert stats.updated_at is not None

    def test_user_stats_default_values(self, db_session, sample_user):
        """UserStats should have correct default values"""
        # Arrange & Act
        stats = UserStats(user_id=sample_user.id)
        db_session.add(stats)
        db_session.commit()

        # Assert
        assert stats.hp == 100
        assert stats.mp == 100
        assert stats.mental_health == 70
        assert stats.physical_health == 70
        assert stats.relationship_quality == 50
        assert stats.socialization_level == 50

    def test_user_stats_one_to_one_relationship_with_user(self, db_session, sample_user):
        """UserStats should have bidirectional one-to-one relationship with User"""
        # Arrange & Act
        stats = UserStats(user_id=sample_user.id)
        db_session.add(stats)
        db_session.commit()
        db_session.refresh(sample_user)

        # Assert - Forward relationship (stats -> user)
        assert stats.user is not None
        assert stats.user.id == sample_user.id

        # Assert - Reverse relationship (user -> stats)
        assert sample_user.stats is not None
        assert sample_user.stats.id == stats.id

        # Assert - One-to-one (not a list)
        assert not isinstance(sample_user.stats, list)
