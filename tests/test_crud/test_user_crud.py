"""
Tests for User CRUD operations.

This module tests all CRUD functions in app/crud/user.py:
- create_user: Creating users, handling duplicates
- get_user: Retrieving by ID
- get_user_by_username: Retrieving by username
- get_user_by_email: Retrieving by email
- get_users: Pagination
- update_user: Modifying user fields
- delete_user: Removing users and cascade behavior

Uses db_session fixture from conftest.py for database access.
"""
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.crud.user import (
    create_user,
    delete_user,
    get_user,
    get_user_by_email,
    get_user_by_username,
    get_users,
    update_user,
)
from app.models.theme import Theme
from app.models.user import User
from app.schemas.user import UserCreate


class TestUserCRUD:
    """Comprehensive tests for User CRUD operations."""

    # =========================================================================
    # CREATE TESTS
    # =========================================================================

    def test_create_user_success(self, db_session, fake):
        """Should create user with valid data and return User instance."""
        # Arrange
        user_data = UserCreate(
            username=fake.user_name()[:50],
            email=fake.email(),
        )

        # Act
        result = create_user(db_session, user_data)

        # Assert
        assert result is not None
        assert result.id is not None
        assert len(result.id) == 36  # UUID format
        assert result.username == user_data.username
        assert result.email == user_data.email
        assert result.is_active is True
        assert result.created_at is not None

    def test_create_user_duplicate_username_returns_none(self, db_session, fake):
        """Should return None when creating user with duplicate username."""
        # Arrange
        username = fake.user_name()[:50]
        user1_data = UserCreate(username=username, email=fake.email())
        user2_data = UserCreate(username=username, email=fake.email())

        # Act
        result1 = create_user(db_session, user1_data)
        result2 = create_user(db_session, user2_data)

        # Assert
        assert result1 is not None
        assert result2 is None

    def test_create_user_duplicate_email_returns_none(self, db_session, fake):
        """Should return None when creating user with duplicate email."""
        # Arrange
        email = fake.email()
        user1_data = UserCreate(username=fake.user_name()[:50], email=email)
        user2_data = UserCreate(username=fake.user_name()[:50], email=email)

        # Act
        result1 = create_user(db_session, user1_data)
        result2 = create_user(db_session, user2_data)

        # Assert
        assert result1 is not None
        assert result2 is None

    def test_create_user_strips_whitespace(self, db_session):
        """Should strip whitespace from username and email in schema."""
        # Arrange
        user_data = UserCreate(username="  test_user  ", email="  test@example.com  ")

        # Act
        result = create_user(db_session, user_data)

        # Assert
        assert result is not None
        assert result.username == "test_user"
        assert result.email == "test@example.com"

    def test_create_user_username_max_length(self, db_session, fake):
        """Should allow username at max length boundary (50)."""
        # Arrange
        username = "u" * 50
        user_data = UserCreate(username=username, email=fake.email())

        # Act
        result = create_user(db_session, user_data)

        # Assert
        assert result is not None
        assert result.username == username

    def test_create_user_email_max_length(self, db_session):
        """Should allow email at max length boundary (255)."""
        # Arrange
        local_part = "a" * 64
        domain = "b" * 186
        email = f"{local_part}@{domain}.com"
        assert len(email) == 255
        user_data = UserCreate(username="maxlen_user", email=email)

        # Act
        result = create_user(db_session, user_data)

        # Assert
        assert result is not None
        assert result.email == email

    def test_create_user_invalid_email_raises_validation_error(self):
        """Should raise ValidationError for invalid email format."""
        # Act & Assert
        with pytest.raises(ValidationError):
            UserCreate(username="valid_user", email="not-an-email")

    def test_create_user_invalid_username_raises_validation_error(self):
        """Should raise ValidationError for invalid username format."""
        # Act & Assert
        with pytest.raises(ValidationError):
            UserCreate(username="bad user", email="valid@example.com")

    def test_create_user_username_too_short_raises_validation_error(self):
        """Should raise ValidationError when username is too short."""
        # Act & Assert
        with pytest.raises(ValidationError):
            UserCreate(username="ab", email="valid@example.com")

    def test_create_user_empty_username_raises_validation_error(self):
        """Should raise ValidationError when username is empty."""
        # Act & Assert
        with pytest.raises(ValidationError):
            UserCreate(username="", email="valid@example.com")

    # =========================================================================
    # READ BY ID TESTS
    # =========================================================================

    def test_get_user_by_id_found(self, db_session, fake):
        """Should return user when ID exists."""
        # Arrange
        user_data = UserCreate(username=fake.user_name()[:50], email=fake.email())
        created_user = create_user(db_session, user_data)

        # Act
        result = get_user(db_session, created_user.id)

        # Assert
        assert result is not None
        assert result.id == created_user.id
        assert result.username == created_user.username

    def test_get_user_by_id_not_found(self, db_session):
        """Should return None when ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = get_user(db_session, non_existent_id)

        # Assert
        assert result is None

    # =========================================================================
    # READ BY USERNAME TESTS
    # =========================================================================

    def test_get_user_by_username_found(self, db_session, fake):
        """Should return user when username exists."""
        # Arrange
        username = fake.user_name()[:50]
        user_data = UserCreate(username=username, email=fake.email())
        create_user(db_session, user_data)

        # Act
        result = get_user_by_username(db_session, username)

        # Assert
        assert result is not None
        assert result.username == username

    def test_get_user_by_username_not_found(self, db_session):
        """Should return None when username does not exist."""
        # Act
        result = get_user_by_username(db_session, "nonexistent_user_12345")

        # Assert
        assert result is None

    # =========================================================================
    # READ BY EMAIL TESTS
    # =========================================================================

    def test_get_user_by_email_found(self, db_session, fake):
        """Should return user when email exists."""
        # Arrange
        email = fake.email()
        user_data = UserCreate(username=fake.user_name()[:50], email=email)
        create_user(db_session, user_data)

        # Act
        result = get_user_by_email(db_session, email)

        # Assert
        assert result is not None
        assert result.email == email

    def test_get_user_by_email_not_found(self, db_session):
        """Should return None when email does not exist."""
        # Act
        result = get_user_by_email(db_session, "missing@example.com")

        # Assert
        assert result is None

    # =========================================================================
    # PAGINATION TESTS
    # =========================================================================

    def test_get_users_pagination(self, db_session, fake):
        """Should return paginated list of users."""
        # Arrange - Create 5 users
        for i in range(5):
            user_data = UserCreate(
                username=f"testuser{i}_{fake.user_name()[:30]}",
                email=f"test{i}_{fake.email()}",
            )
            create_user(db_session, user_data)

        # Act - Get first 3 users
        result_page1 = get_users(db_session, skip=0, limit=3)
        result_page2 = get_users(db_session, skip=3, limit=3)

        # Assert
        assert len(result_page1) == 3
        assert len(result_page2) == 2  # Only 2 remaining

    def test_get_users_empty_database(self, db_session):
        """Should return empty list when no users exist."""
        # Act
        result = get_users(db_session)

        # Assert
        assert result == []

    def test_get_users_limit_only(self, db_session, fake):
        """Should respect limit parameter when skip is default."""
        # Arrange
        for i in range(4):
            user_data = UserCreate(
                username=f"limituser{i}_{fake.user_name()[:30]}",
                email=f"limit{i}_{fake.email()}",
            )
            create_user(db_session, user_data)

        # Act
        result = get_users(db_session, limit=2)

        # Assert
        assert len(result) == 2

    def test_get_users_skip_only(self, db_session, fake):
        """Should respect skip parameter when limit is default."""
        # Arrange
        for i in range(4):
            user_data = UserCreate(
                username=f"skipuser{i}_{fake.user_name()[:30]}",
                email=f"skip{i}_{fake.email()}",
            )
            create_user(db_session, user_data)

        # Act
        result = get_users(db_session, skip=2)

        # Assert
        assert len(result) == 2

    def test_get_users_skip_beyond_range(self, db_session, fake):
        """Should return empty list when skip exceeds total users."""
        # Arrange
        for i in range(2):
            user_data = UserCreate(
                username=f"beyond{i}_{fake.user_name()[:30]}",
                email=f"beyond{i}_{fake.email()}",
            )
            create_user(db_session, user_data)

        # Act
        result = get_users(db_session, skip=5, limit=2)

        # Assert
        assert result == []

    # =========================================================================
    # UPDATE TESTS
    # =========================================================================

    def test_update_user_success(self, db_session, fake):
        """Should update user fields and return updated user."""
        # Arrange
        user_data = UserCreate(username=fake.user_name()[:50], email=fake.email())
        created_user = create_user(db_session, user_data)
        new_email = "updated_" + fake.email()

        # Act
        result = update_user(db_session, created_user.id, {"email": new_email})

        # Assert
        assert result is not None
        assert result.email == new_email
        assert result.username == created_user.username  # Unchanged

    def test_update_user_multiple_fields(self, db_session, fake):
        """Should update multiple fields at once."""
        # Arrange
        user_data = UserCreate(username=fake.user_name()[:50], email=fake.email())
        created_user = create_user(db_session, user_data)
        new_username = f"updated_{fake.user_name()[:40]}"
        new_email = f"updated_{fake.email()}"

        # Act
        result = update_user(
            db_session,
            created_user.id,
            {"username": new_username, "email": new_email},
        )

        # Assert
        assert result is not None
        assert result.username == new_username
        assert result.email == new_email

    def test_update_user_same_values(self, db_session, fake):
        """Should allow update with same values and return user."""
        # Arrange
        user_data = UserCreate(username=fake.user_name()[:50], email=fake.email())
        created_user = create_user(db_session, user_data)

        # Act
        result = update_user(
            db_session,
            created_user.id,
            {"username": created_user.username, "email": created_user.email},
        )

        # Assert
        assert result is not None
        assert result.username == created_user.username
        assert result.email == created_user.email

    def test_update_user_is_active_toggle(self, db_session, fake):
        """Should toggle is_active field."""
        # Arrange
        user_data = UserCreate(username=fake.user_name()[:50], email=fake.email())
        created_user = create_user(db_session, user_data)

        # Act
        result = update_user(db_session, created_user.id, {"is_active": False})

        # Assert
        assert result is not None
        assert result.is_active is False

    def test_update_user_invalid_field_ignored(self, db_session, fake):
        """Should ignore invalid fields without raising errors."""
        # Arrange
        user_data = UserCreate(username=fake.user_name()[:50], email=fake.email())
        created_user = create_user(db_session, user_data)

        # Act
        result = update_user(db_session, created_user.id, {"not_a_field": "value"})

        # Assert
        assert result is not None
        assert not hasattr(result, "not_a_field")

    def test_update_user_duplicate_username_raises_integrity_error(self, db_session, fake):
        """Should raise IntegrityError when updating to duplicate username."""
        # Arrange
        user1 = create_user(
            db_session,
            UserCreate(username=fake.user_name()[:50], email=fake.email()),
        )
        user2 = create_user(
            db_session,
            UserCreate(username=fake.user_name()[:50], email=fake.email()),
        )

        # Act & Assert
        with pytest.raises(IntegrityError):
            update_user(db_session, user2.id, {"username": user1.username})
        db_session.rollback()

    def test_update_user_duplicate_email_raises_integrity_error(self, db_session, fake):
        """Should raise IntegrityError when updating to duplicate email."""
        # Arrange
        user1 = create_user(
            db_session,
            UserCreate(username=fake.user_name()[:50], email=fake.email()),
        )
        user2 = create_user(
            db_session,
            UserCreate(username=fake.user_name()[:50], email=fake.email()),
        )

        # Act & Assert
        with pytest.raises(IntegrityError):
            update_user(db_session, user2.id, {"email": user1.email})
        db_session.rollback()

    def test_update_user_not_found(self, db_session):
        """Should return None when updating non-existent user."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = update_user(db_session, non_existent_id, {"email": "new@example.com"})

        # Assert
        assert result is None

    # =========================================================================
    # DELETE TESTS
    # =========================================================================

    def test_delete_user_success(self, db_session, fake):
        """Should delete user and return True."""
        # Arrange
        user_data = UserCreate(username=fake.user_name()[:50], email=fake.email())
        created_user = create_user(db_session, user_data)
        user_id = created_user.id

        # Act
        result = delete_user(db_session, user_id)

        # Assert
        assert result is True
        assert get_user(db_session, user_id) is None

    def test_delete_user_with_no_relations(self, db_session, fake):
        """Should delete user with no related records."""
        # Arrange
        user_data = UserCreate(username=fake.user_name()[:50], email=fake.email())
        created_user = create_user(db_session, user_data)

        # Act
        result = delete_user(db_session, created_user.id)

        # Assert
        assert result is True
        assert get_user(db_session, created_user.id) is None

    def test_delete_user_not_found(self, db_session):
        """Should return False when deleting non-existent user."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = delete_user(db_session, non_existent_id)

        # Assert
        assert result is False

    def test_delete_user_already_deleted_returns_false(self, db_session, fake):
        """Should return False when deleting user twice."""
        # Arrange
        user_data = UserCreate(username=fake.user_name()[:50], email=fake.email())
        created_user = create_user(db_session, user_data)

        # Act
        first_result = delete_user(db_session, created_user.id)
        second_result = delete_user(db_session, created_user.id)

        # Assert
        assert first_result is True
        assert second_result is False

    def test_delete_user_cascades_to_related_records(self, db_session, fake):
        """Should cascade delete to related themes."""
        # Arrange - Create user with themes
        user_data = UserCreate(username=fake.user_name()[:50], email=fake.email())
        created_user = create_user(db_session, user_data)

        theme1 = Theme(user_id=created_user.id, name="Theme 1")
        theme2 = Theme(user_id=created_user.id, name="Theme 2")
        db_session.add_all([theme1, theme2])
        db_session.commit()

        user_id = created_user.id

        # Verify themes exist
        themes_before = db_session.query(Theme).filter(Theme.user_id == user_id).all()
        assert len(themes_before) == 2

        # Act
        delete_user(db_session, user_id)

        # Assert - Themes should be deleted
        themes_after = db_session.query(Theme).filter(Theme.user_id == user_id).all()
        assert len(themes_after) == 0
