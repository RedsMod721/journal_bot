"""
Tests for UserStats model.

Tests cover:
- UserStats creation
- Default values for status bars
- One-to-one relationship with User
- UUID generation
- Stat modification
- Boundary validation
- Cascade deletion
- Repr formatting

Following AAA pattern (Arrange, Act, Assert) as per TESTING_GUIDE.md
"""
import pytest  # type: ignore
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError  # type: ignore

from app.models.user_stats import UserStats


class TestUserStatsModel:
    """Tests for UserStats model"""

    # =========================================================================
    # CREATION TESTS
    # =========================================================================

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

    def test_user_stats_creation_generates_uuid(self, db_session, sample_user):
        """Should auto-generate a valid UUID string for primary key"""
        # Arrange & Act
        stats = UserStats(user_id=sample_user.id)
        db_session.add(stats)
        db_session.commit()

        # Assert - UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert stats.id is not None
        assert len(stats.id) == 36
        assert stats.id.count("-") == 4

        # Verify it's a valid UUID by checking each segment
        parts = stats.id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    # =========================================================================
    # DEFAULT VALUE TESTS
    # =========================================================================

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

    def test_user_stats_updated_at_set_automatically(self, db_session, sample_user):
        """Should auto-set updated_at timestamp on creation"""
        # Arrange & Act
        stats = UserStats(user_id=sample_user.id)
        db_session.add(stats)
        db_session.commit()

        # Assert
        assert stats.updated_at is not None
        # Verify it's a recent timestamp (within last minute)
        assert stats.updated_at > datetime.utcnow() - timedelta(minutes=1)

    # =========================================================================
    # RELATIONSHIP TESTS
    # =========================================================================

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

    def test_user_deletion_cascades_to_user_stats(self, db_session, sample_user):
        """Deleting user should cascade delete UserStats"""
        # Arrange
        stats = UserStats(user_id=sample_user.id)
        db_session.add(stats)
        db_session.commit()
        user_id = sample_user.id

        # Act
        db_session.delete(sample_user)
        db_session.commit()

        # Assert
        remaining_stats = db_session.query(UserStats).filter(
            UserStats.user_id == user_id
        ).all()
        assert len(remaining_stats) == 0

    def test_user_can_only_have_one_stats(self, db_session, sample_user):
        """User should only be able to have one UserStats (unique constraint)"""
        # Arrange
        stats1 = UserStats(user_id=sample_user.id, hp=100)
        db_session.add(stats1)
        db_session.commit()

        # Act & Assert - Attempting to create second stats should fail
        stats2 = UserStats(user_id=sample_user.id, hp=80)
        db_session.add(stats2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    # =========================================================================
    # STAT MODIFICATION TESTS
    # =========================================================================

    def test_user_stats_hp_can_be_modified(self, db_session, sample_user):
        """HP should be modifiable"""
        # Arrange
        stats = UserStats(user_id=sample_user.id, hp=100)
        db_session.add(stats)
        db_session.commit()

        # Act
        stats.hp = 75
        db_session.commit()
        db_session.refresh(stats)

        # Assert
        assert stats.hp == 75

    def test_user_stats_mp_can_be_modified(self, db_session, sample_user):
        """MP should be modifiable"""
        # Arrange
        stats = UserStats(user_id=sample_user.id, mp=100)
        db_session.add(stats)
        db_session.commit()

        # Act
        stats.mp = 60
        db_session.commit()
        db_session.refresh(stats)

        # Assert
        assert stats.mp == 60

    def test_user_stats_all_bars_modifiable(self, db_session, sample_user):
        """All status bars should be independently modifiable"""
        # Arrange
        stats = UserStats(user_id=sample_user.id)
        db_session.add(stats)
        db_session.commit()

        # Act
        stats.hp = 85
        stats.mp = 75
        stats.mental_health = 60
        stats.physical_health = 80
        stats.relationship_quality = 45
        stats.socialization_level = 55
        db_session.commit()
        db_session.refresh(stats)

        # Assert
        assert stats.hp == 85
        assert stats.mp == 75
        assert stats.mental_health == 60
        assert stats.physical_health == 80
        assert stats.relationship_quality == 45
        assert stats.socialization_level == 55

    def test_user_stats_updated_at_not_auto_updated(self, db_session, sample_user):
        """updated_at should not change automatically on updates (no onupdate)."""
        # Arrange
        stats = UserStats(user_id=sample_user.id, hp=100)
        db_session.add(stats)
        db_session.commit()
        db_session.refresh(stats)
        initial_updated_at = stats.updated_at

        # Act
        stats.hp = 90
        db_session.commit()
        db_session.refresh(stats)

        # Assert
        assert stats.updated_at == initial_updated_at

    def test_user_stats_allows_out_of_range_values(self, db_session, sample_user):
        """Stats should allow out-of-range values (no validation enforced)."""
        # Arrange & Act
        stats = UserStats(
            user_id=sample_user.id,
            hp=-5,
            mp=200,
            mental_health=-1,
            physical_health=101,
            relationship_quality=-10,
            socialization_level=999,
        )
        db_session.add(stats)
        db_session.commit()
        db_session.refresh(stats)

        # Assert
        assert stats.hp == -5
        assert stats.mp == 200
        assert stats.mental_health == -1
        assert stats.physical_health == 101
        assert stats.relationship_quality == -10
        assert stats.socialization_level == 999

    # =========================================================================
    # BOUNDARY VALUE TESTS
    # =========================================================================

    def test_user_stats_can_be_set_to_zero(self, db_session, sample_user):
        """Stats should be able to reach 0"""
        # Arrange
        stats = UserStats(
            user_id=sample_user.id,
            hp=0,
            mp=0,
            mental_health=0,
            physical_health=0,
            relationship_quality=0,
            socialization_level=0,
        )
        db_session.add(stats)
        db_session.commit()

        # Assert
        assert stats.hp == 0
        assert stats.mp == 0
        assert stats.mental_health == 0
        assert stats.physical_health == 0
        assert stats.relationship_quality == 0
        assert stats.socialization_level == 0

    def test_user_stats_can_be_set_to_max(self, db_session, sample_user):
        """Stats should be able to reach 100"""
        # Arrange
        stats = UserStats(
            user_id=sample_user.id,
            hp=100,
            mp=100,
            mental_health=100,
            physical_health=100,
            relationship_quality=100,
            socialization_level=100,
        )
        db_session.add(stats)
        db_session.commit()

        # Assert
        assert stats.hp == 100
        assert stats.mp == 100
        assert stats.mental_health == 100
        assert stats.physical_health == 100
        assert stats.relationship_quality == 100
        assert stats.socialization_level == 100

    # =========================================================================
    # REPR TEST
    # =========================================================================

    def test_user_stats_repr(self, db_session, sample_user):
        """Should return readable string representation with HP and MP"""
        # Arrange
        stats = UserStats(user_id=sample_user.id, hp=85, mp=70)
        db_session.add(stats)
        db_session.commit()

        # Act
        repr_string = repr(stats)

        # Assert
        assert repr_string == "<UserStats HP:85 MP:70>"

    # =========================================================================
    # UUID UNIQUENESS TEST
    # =========================================================================

    def test_multiple_users_have_unique_stats_ids(self, db_session, fake):
        """Each UserStats should get a unique UUID"""
        # Arrange
        from app.models.user import User

        user1 = User(username=fake.user_name(), email=fake.email())
        user2 = User(username=fake.user_name(), email=fake.email())
        db_session.add_all([user1, user2])
        db_session.commit()

        # Act
        stats1 = UserStats(user_id=user1.id)
        stats2 = UserStats(user_id=user2.id)
        db_session.add_all([stats1, stats2])
        db_session.commit()

        # Assert
        assert stats1.id != stats2.id
        assert len(stats1.id) == 36
        assert len(stats2.id) == 36
