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
import pytest
from sqlalchemy.exc import IntegrityError

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
