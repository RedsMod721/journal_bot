"""
CRUD operations for User model.

This module provides database operations for User management:
- Create: Create new users with duplicate checking
- Read: Get users by ID, username, email, or in bulk
- Update: Modify user attributes
- Delete: Remove users (cascades to related records)

All functions take a SQLAlchemy Session as the first argument
and return User model instances or None for not-found cases.
"""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate


def create_user(db: Session, user: UserCreate) -> User | None:
    """
    Create a new user in the database.

    Args:
        db: Database session
        user: UserCreate schema with username and email

    Returns:
        User: The created user instance
        None: If username or email already exists (IntegrityError)

    Example:
        user_data = UserCreate(username="john", email="john@example.com")
        user = create_user(db, user_data)
    """
    db_user = User(
        username=user.username,
        email=user.email,
    )
    db.add(db_user)
    try:
        db.commit()
        db.refresh(db_user)
        return db_user
    except IntegrityError:
        db.rollback()
        return None


def get_user(db: Session, user_id: str) -> User | None:
    """
    Retrieve a user by their ID.

    Args:
        db: Database session
        user_id: The UUID string of the user

    Returns:
        User: The user instance if found
        None: If no user exists with that ID
    """
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> User | None:
    """
    Retrieve a user by their username.

    Args:
        db: Database session
        username: The unique username

    Returns:
        User: The user instance if found
        None: If no user exists with that username
    """
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    """
    Retrieve a user by their email address.

    Args:
        db: Database session
        email: The unique email address

    Returns:
        User: The user instance if found
        None: If no user exists with that email
    """
    return db.query(User).filter(User.email == email).first()


def get_users(db: Session, skip: int = 0, limit: int = 100) -> list[User]:
    """
    Retrieve multiple users with pagination.

    Args:
        db: Database session
        skip: Number of records to skip (offset)
        limit: Maximum number of records to return

    Returns:
        list[User]: List of user instances
    """
    return db.query(User).offset(skip).limit(limit).all()


def update_user(db: Session, user_id: str, user_update: dict) -> User | None:
    """
    Update a user's attributes.

    Args:
        db: Database session
        user_id: The UUID string of the user to update
        user_update: Dictionary of fields to update

    Returns:
        User: The updated user instance
        None: If no user exists with that ID

    Example:
        updated = update_user(db, user_id, {"email": "new@example.com"})
    """
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user is None:
        return None

    for field, value in user_update.items():
        if hasattr(db_user, field):
            setattr(db_user, field, value)

    db.commit()
    db.refresh(db_user)
    return db_user


def delete_user(db: Session, user_id: str) -> bool:
    """
    Delete a user and all related records.

    Due to cascade delete configuration, this will also delete:
    - Themes
    - Skills
    - Journal entries
    - User titles
    - Missions/quests
    - User stats

    Args:
        db: Database session
        user_id: The UUID string of the user to delete

    Returns:
        True: If the user was successfully deleted
        False: If no user exists with that ID
    """
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user is None:
        return False

    db.delete(db_user)
    db.commit()
    return True
