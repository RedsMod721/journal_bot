"""
Comprehensive tests for the User model.

Tests cover:
- User creation with valid data
- UUID auto-generation
- Unique constraint enforcement (username, email)
- Default values
- Edge cases

Follows the AAA pattern: Arrange, Act, Assert
"""
import pytest  # type: ignore
from sqlalchemy.exc import IntegrityError  # type: ignore

from app.models.user import User


class TestUserModel:
    """Test suite for User model."""

    # =========================================================================
    # CREATION TESTS
    # =========================================================================

    def test_user_creation_with_valid_data(self, db_session, fake):
        """Should create user with all required fields populated correctly."""
        # Arrange
        username = fake.user_name()
        email = fake.email()

        # Act
        user = User(username=username, email=email)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Assert
        assert user.id is not None
        assert user.username == username
        assert user.email == email
        assert user.created_at is not None
        assert user.is_active is True

    def test_user_creation_generates_uuid(self, db_session, fake):
        """Should auto-generate a valid UUID string for primary key."""
        # Arrange & Act
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Assert - UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert user.id is not None
        assert len(user.id) == 36
        assert user.id.count("-") == 4

        # Verify it's a valid UUID by checking each segment
        parts = user.id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    # =========================================================================
    # CONSTRAINT TESTS
    # =========================================================================

    def test_user_creation_duplicate_username_raises_error(self, db_session, fake):
        """Should raise IntegrityError when creating user with duplicate username."""
        # Arrange
        username = fake.user_name()
        user1 = User(username=username, email=fake.email())
        db_session.add(user1)
        db_session.commit()

        # Act & Assert
        user2 = User(username=username, email=fake.email())
        db_session.add(user2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_user_creation_duplicate_email_raises_error(self, db_session, fake):
        """Should raise IntegrityError when creating user with duplicate email."""
        # Arrange
        email = fake.email()
        user1 = User(username=fake.user_name(), email=email)
        db_session.add(user1)
        db_session.commit()

        # Act & Assert
        user2 = User(username=fake.user_name(), email=email)
        db_session.add(user2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    # =========================================================================
    # DEFAULT VALUE TESTS
    # =========================================================================

    def test_user_default_is_active_is_true(self, db_session, fake):
        """Should default is_active to True when not specified."""
        # Arrange & Act
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Assert
        assert user.is_active is True

    def test_user_created_at_is_set_automatically(self, db_session, fake):
        """Should auto-set created_at timestamp on creation."""
        # Arrange & Act
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Assert
        assert user.created_at is not None
        # Verify it's a recent timestamp (within last minute)
        from datetime import datetime, timedelta

        assert user.created_at > datetime.utcnow() - timedelta(minutes=1)

    # =========================================================================
    # REPR TEST
    # =========================================================================

    def test_user_repr_returns_username(self, db_session, fake):
        """Should return readable string representation with username."""
        # Arrange
        username = fake.user_name()
        user = User(username=username, email=fake.email())

        # Act
        repr_string = repr(user)

        # Assert
        assert repr_string == f"<User {username}>"

    # =========================================================================
    # MULTIPLE USERS TEST
    # =========================================================================

    def test_multiple_users_have_unique_ids(self, db_session, fake):
        """Should generate unique UUIDs for each user."""
        # Arrange & Act
        user1 = User(username=fake.user_name(), email=fake.email())
        user2 = User(username=fake.user_name(), email=fake.email())
        user3 = User(username=fake.user_name(), email=fake.email())

        db_session.add_all([user1, user2, user3])
        db_session.commit()

        # Assert
        ids = {user1.id, user2.id, user3.id}
        assert len(ids) == 3  # All unique

    # =========================================================================
    # DEFAULT VALUES COMPREHENSIVE TEST
    # =========================================================================

    def test_user_all_default_values(self, db_session, fake):
        """Should have correct default values for all fields."""
        # Arrange & Act
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Assert
        assert user.is_active is True
        assert user.created_at is not None
        assert user.id is not None

    # =========================================================================
    # EDGE CASES & VALIDATION
    # =========================================================================

    def test_user_username_whitespace_allowed(self, db_session, fake):
        """Username with spaces should be allowed."""
        # Arrange & Act
        username = "test user"
        user = User(username=username, email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Assert
        assert user.username == username

    def test_user_email_formats_accepted(self, db_session, fake):
        """Should accept various valid email formats."""
        # Arrange
        emails = [
            "user@example.com",
            "user.name@example.co.uk",
            "user+tag@example.com",
            "user_123@sub.example.com",
        ]

        # Act & Assert
        for email in emails:
            user = User(username=fake.user_name(), email=email)
            db_session.add(user)
            db_session.commit()
            assert user.email == email

    # =========================================================================
    # RELATIONSHIP TESTS
    # =========================================================================

    def test_user_theme_relationship_bidirectional(self, db_session, sample_user):
        """User should have bidirectional relationship with themes."""
        # Arrange
        from app.models.theme import Theme

        theme = Theme(user_id=sample_user.id, name="Test Theme")
        db_session.add(theme)
        db_session.commit()
        db_session.refresh(sample_user)

        # Act & Assert - bidirectional access
        assert len(sample_user.themes) == 1
        assert sample_user.themes[0].id == theme.id
        assert theme.user.id == sample_user.id

    def test_user_multiple_themes(self, db_session, sample_user):
        """User should be able to have multiple themes."""
        # Arrange
        from app.models.theme import Theme

        themes = [
            Theme(user_id=sample_user.id, name="Health"),
            Theme(user_id=sample_user.id, name="Work"),
            Theme(user_id=sample_user.id, name="Learning"),
        ]

        # Act
        db_session.add_all(themes)
        db_session.commit()
        db_session.refresh(sample_user)

        # Assert
        assert len(sample_user.themes) == 3
        theme_names = {t.name for t in sample_user.themes}
        assert theme_names == {"Health", "Work", "Learning"}

    def test_user_deletion_cascades_to_themes(self, db_session, sample_user):
        """Deleting user should cascade delete all related themes."""
        # Arrange
        from app.models.theme import Theme

        theme1 = Theme(user_id=sample_user.id, name="Theme 1")
        theme2 = Theme(user_id=sample_user.id, name="Theme 2")
        db_session.add_all([theme1, theme2])
        db_session.commit()
        user_id = sample_user.id

        # Act
        db_session.delete(sample_user)
        db_session.commit()

        # Assert
        from app.models.theme import Theme

        remaining_themes = db_session.query(Theme).filter(
            Theme.user_id == user_id
        ).all()
        assert len(remaining_themes) == 0

    # =========================================================================
    # UUID EDGE CASES
    # =========================================================================

    def test_user_uuid_is_different_each_time(self, db_session, fake):
        """Each user should get a different UUID on creation."""
        # Arrange & Act
        user1 = User(username=fake.user_name(), email=fake.email())
        user2 = User(username=fake.user_name(), email=fake.email())

        db_session.add_all([user1, user2])
        db_session.commit()

        # Assert
        assert user1.id != user2.id
        assert len(user1.id) == 36
        assert len(user2.id) == 36

    # =========================================================================
    # IMMUTABILITY TESTS
    # =========================================================================

    def test_user_is_active_can_be_set_to_false(self, db_session, sample_user):
        """is_active should be modifiable."""
        # Arrange
        sample_user.is_active = False

        # Act
        db_session.commit()
        db_session.refresh(sample_user)

        # Assert
        assert sample_user.is_active is False

    def test_user_can_be_reactivated(self, db_session, sample_user):
        """User can be deactivated and reactivated."""
        # Arrange
        sample_user.is_active = False
        db_session.commit()

        # Act
        sample_user.is_active = True
        db_session.commit()
        db_session.refresh(sample_user)

        # Assert
        assert sample_user.is_active is True
