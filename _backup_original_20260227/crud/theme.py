"""
CRUD operations for Theme model.

This module provides database operations for Theme management:
- Create: Create new themes with parent theme support
- Read: Get themes by ID, user, or with subthemes
- Update: Modify theme attributes and add XP
- Delete: Remove themes (cascades to sub-themes)

All functions take a SQLAlchemy Session as the first argument
and return Theme model instances or None for not-found cases.
"""
from sqlalchemy.orm import Session, joinedload

from app.models.theme import Theme
from app.schemas.theme import ThemeCreate, ThemeUpdate


def create_theme(db: Session, theme: ThemeCreate) -> Theme:
    """
    Create a new theme in the database.

    Args:
        db: Database session
        theme: ThemeCreate schema with name, description, user_id, and optional parent_theme_id

    Returns:
        Theme: The created theme instance

    Example:
        theme_data = ThemeCreate(
            name="Physical Health",
            user_id="123e4567-...",
            description="Fitness goals"
        )
        theme = create_theme(db, theme_data)
    """
    db_theme = Theme(
        user_id=theme.user_id,
        name=theme.name,
        description=theme.description,
        parent_theme_id=theme.parent_theme_id,
    )
    db.add(db_theme)
    db.commit()
    db.refresh(db_theme)
    return db_theme


def get_theme(db: Session, theme_id: str) -> Theme | None:
    """
    Retrieve a theme by its ID.

    Args:
        db: Database session
        theme_id: The UUID string of the theme

    Returns:
        Theme: The theme instance if found
        None: If no theme exists with that ID
    """
    return db.query(Theme).filter(Theme.id == theme_id).first()


def get_user_themes(db: Session, user_id: str) -> list[Theme]:
    """
    Retrieve all themes belonging to a user.

    Args:
        db: Database session
        user_id: The UUID string of the user

    Returns:
        list[Theme]: List of theme instances owned by the user
    """
    return db.query(Theme).filter(Theme.user_id == user_id).all()


def get_theme_with_subthemes(db: Session, theme_id: str) -> Theme | None:
    """
    Retrieve a theme with its sub-themes eagerly loaded.

    Uses joinedload to fetch sub_themes relationship in a single query,
    avoiding N+1 query issues when accessing child themes.

    Args:
        db: Database session
        theme_id: The UUID string of the theme

    Returns:
        Theme: The theme instance with sub_themes loaded if found
        None: If no theme exists with that ID
    """
    return (
        db.query(Theme)
        .options(joinedload(Theme.sub_themes))
        .filter(Theme.id == theme_id)
        .first()
    )


def add_xp_to_theme(db: Session, theme_id: str, xp_amount: float) -> Theme | None:
    """
    Add XP to a theme and handle level-ups.

    Calls the theme's add_xp() method which handles:
    - XP accumulation
    - Automatic level-up when threshold is reached
    - Exponential scaling of next level requirements

    Args:
        db: Database session
        theme_id: The UUID string of the theme
        xp_amount: Amount of XP to add (must be non-negative)

    Returns:
        Theme: The updated theme instance
        None: If no theme exists with that ID

    Example:
        theme = add_xp_to_theme(db, theme_id, 50.0)
        # theme.level may have increased if XP threshold was crossed
    """
    theme = db.query(Theme).filter(Theme.id == theme_id).first()
    if theme is None:
        return None

    theme.add_xp(xp_amount)
    db.commit()
    db.refresh(theme)
    return theme


def update_theme(db: Session, theme_id: str, theme_update: ThemeUpdate) -> Theme | None:
    """
    Update a theme's attributes.

    Only updates fields that are explicitly set in the update schema.
    Uses exclude_unset=True to allow partial updates.

    Args:
        db: Database session
        theme_id: The UUID string of the theme to update
        theme_update: ThemeUpdate schema with fields to update

    Returns:
        Theme: The updated theme instance
        None: If no theme exists with that ID

    Example:
        update = ThemeUpdate(name="New Name")
        theme = update_theme(db, theme_id, update)
    """
    db_theme = db.query(Theme).filter(Theme.id == theme_id).first()
    if db_theme is None:
        return None

    update_data = theme_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_theme, field, value)

    db.commit()
    db.refresh(db_theme)
    return db_theme


def delete_theme(db: Session, theme_id: str) -> bool:
    """
    Delete a theme and its sub-themes.

    Due to the self-referential relationship with cascade delete,
    deleting a parent theme will also delete all child themes.

    Args:
        db: Database session
        theme_id: The UUID string of the theme to delete

    Returns:
        True: If the theme was successfully deleted
        False: If no theme exists with that ID
    """
    db_theme = db.query(Theme).filter(Theme.id == theme_id).first()
    if db_theme is None:
        return False

    db.delete(db_theme)
    db.commit()
    return True
